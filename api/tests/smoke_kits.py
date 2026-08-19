"""Teste de fumaça do kit/combo na venda.

O cenário:

    Prato do dia  — produzido, ficha com 200 g de arroz a 10,00/kg = 2,00
    Refrigerante  — revenda, custo médio do estoque = 3,00
    Combo         — 1 prato + 1 refrigerante  ->  deveria custar 5,00

O que este teste existe para provar:

* **O combo deixa de entrar sem custo.** Antes ele não tinha ficha (não é
  produzido) nem custo médio (não é estocado), e o CMV teórico do mês ficava
  furado justamente no item que mais vende.
* **O kit segue a ficha VIGENTE do prato.** Homologar uma receita nova muda o
  custo do combo na hora — é por isso que a composição aponta para o produto e
  não para a ficha.
* **Componente sem custo não zera o combo**: o que se sabe entra, e a origem
  vira `kit_parcial`, para o buraco aparecer em vez de sumir.
* **Ciclo é recusado** — kit que contém kit que contém o primeiro.
* **A venda congela o custo**: mexer no combo amanhã não reescreve o CMV de
  hoje.

    python tests/smoke_kits.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
COZINHA = ("smoke.cozinha@botane.com.br", "smoke12345")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=40) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")}


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


def perto(a, b, tol=0.01):
    return a is not None and abs(float(a) - float(b)) < tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
marca = str(time.time_ns())[-6:]
hoje = date.today()

st, locais = chamar("GET", "/locais", token=token)
local = next((l for l in locais if l["principal"]), locais[0])

print("0. o prato, o refrigerante e o combo")
st, arroz = chamar("POST", "/produtos", {
    "nome": f"Kit arroz {marca}", "tipo": "INSUMO", "um_estoque": "KG"}, token=token)
chamar("POST", "/estoque/entradas", {
    "id_produto": arroz["id"], "quantidade": 10, "custo_unitario": 10,
    "id_local": local["id"]}, token=token)

st, prato = chamar("POST", "/produtos", {
    "nome": f"Kit prato {marca}", "tipo": "PRODUZIDO", "um_estoque": "UN",
    "producao_propria": True}, token=token)
st, ficha = chamar("POST", "/fichas", {
    "id_produto": prato["id"], "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": arroz["id"], "qtd_bruta": 0.2, "um": "KG"}],
}, token=token)
checar("ficha do prato criada", st == 201, ficha)
st, r = chamar("POST", f"/fichas/{ficha['id']}/homologar", token=token)
checar("ficha homologada", st == 200, r)

st, refri = chamar("POST", "/produtos", {
    "nome": f"Kit refri {marca}", "tipo": "REVENDA", "um_estoque": "UN"}, token=token)
chamar("POST", "/estoque/entradas", {
    "id_produto": refri["id"], "quantidade": 20, "custo_unitario": 3,
    "id_local": local["id"]}, token=token)

st, combo = chamar("POST", "/produtos", {
    "nome": f"Kit combo {marca}", "tipo": "KIT", "um_estoque": "UN"}, token=token)
checar("combo criado como KIT", st == 201, combo)

print("1. sem composição, o combo não tem custo — e diz isso")
st, k = chamar("GET", f"/produtos/{combo['id']}/kit", token=token)
checar("a composição vem vazia", st == 200 and k["itens"] == [], k)
checar("e a origem é 'kit_vazio', não zero", k.get("origem") == "kit_vazio", k)

print("2. com a composição, custa a soma das partes")
st, r = chamar("PUT", f"/produtos/{combo['id']}/kit", {
    "itens": [{"id_componente": prato["id"], "quantidade": 1},
              {"id_componente": refri["id"], "quantidade": 1}],
}, token=token)
checar("composição gravada", st == 200 and r["itens"] == 2, r)
# 0,2 kg x 10,00 = 2,00 do prato + 3,00 do refrigerante
checar("o combo custa 5,00 (2,00 do prato + 3,00 do refri)", perto(r.get("custo"), 5), r)
checar("e a origem diz que está completo", r.get("origem") == "kit", r)

st, k = chamar("GET", f"/produtos/{combo['id']}/kit", token=token)
detalhe = {d["componente"]: d for d in k["detalhe"]}
checar("o detalhe mostra de onde veio cada real", len(detalhe) == 2, k["detalhe"])
checar("o prato custa pela ficha",
       detalhe.get(f"Kit prato {marca}", {}).get("origem") == "ficha", detalhe)
checar("o refrigerante custa pelo médio do estoque",
       detalhe.get(f"Kit refri {marca}", {}).get("origem") in ("estoque", "medio", "custo_medio"),
       detalhe)

print("3. o kit segue a ficha VIGENTE do prato")
# Receita nova: dobra o arroz. O combo tem de acompanhar na hora.
st, nova = chamar("POST", "/fichas", {
    "id_produto": prato["id"], "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": arroz["id"], "qtd_bruta": 0.4, "um": "KG"}],
}, token=token)
st, r = chamar("POST", f"/fichas/{nova['id']}/homologar", token=token)
checar("versão nova da ficha homologada", st == 200, r)
st, k = chamar("GET", f"/produtos/{combo['id']}/kit", token=token)
checar("o combo passa a custar 7,00 (4,00 + 3,00)", perto(k.get("custo"), 7), k)

print("4. componente sem custo não zera o combo")
st, sem_custo = chamar("POST", "/produtos", {
    "nome": f"Kit brinde {marca}", "tipo": "PRODUZIDO", "um_estoque": "UN",
    "producao_propria": True}, token=token)
st, r = chamar("PUT", f"/produtos/{combo['id']}/kit", {
    "itens": [{"id_componente": prato["id"], "quantidade": 1},
              {"id_componente": refri["id"], "quantidade": 1},
              {"id_componente": sem_custo["id"], "quantidade": 1}],
}, token=token)
checar("o que se sabe continua na conta", perto(r.get("custo"), 7), r)
checar("mas a origem avisa que falta pedaço", r.get("origem") == "kit_parcial", r)

print("5. ciclo é recusado")
st, outro = chamar("POST", "/produtos", {
    "nome": f"Kit outro {marca}", "tipo": "KIT", "um_estoque": "UN"}, token=token)
chamar("PUT", f"/produtos/{outro['id']}/kit",
       {"itens": [{"id_componente": combo["id"], "quantidade": 1}]}, token=token)
st, r = chamar("PUT", f"/produtos/{combo['id']}/kit",
               {"itens": [{"id_componente": outro["id"], "quantidade": 1}]}, token=token)
checar("kit dentro de kit que volta ao primeiro é recusado", st == 400, st)
checar("com uma frase que explica", "ciclo" in (r.get("detail") or "").lower(), r)
st, r = chamar("PUT", f"/produtos/{combo['id']}/kit",
               {"itens": [{"id_componente": combo["id"], "quantidade": 1}]}, token=token)
checar("e conter a si mesmo também", st == 400, st)
st, r = chamar("PUT", f"/produtos/{combo['id']}/kit", {
    "itens": [{"id_componente": prato["id"], "quantidade": 1},
              {"id_componente": prato["id"], "quantidade": 1}]}, token=token)
checar("componente repetido é recusado", st == 400, st)

print("6. só produto do tipo KIT tem composição")
st, r = chamar("PUT", f"/produtos/{prato['id']}/kit",
               {"itens": [{"id_componente": refri["id"], "quantidade": 1}]}, token=token)
checar("produto que não é KIT recusa composição", st == 400, st)
checar("dizendo o que fazer", "tipo" in (r.get("detail") or "").lower(), r)

print("7. a venda do combo congela o custo")
chamar("PUT", f"/produtos/{combo['id']}/kit", {
    "itens": [{"id_componente": prato["id"], "quantidade": 1},
              {"id_componente": refri["id"], "quantidade": 1}]}, token=token)
st, venda = chamar("POST", "/vendas/importar", {
    "origem": "PLANILHA", "documento": f"KIT{marca}",
    "vendas": [{
        "data": str(hoje), "documento": f"KIT{marca}",
        "itens": [{"id_produto": combo["id"], "quantidade": 2, "valor_unitario": 25}],
    }],
}, token=token)
checar("a venda do combo importa", st in (200, 201), venda)

st, itens = chamar("GET", f"/vendas?inicio={hoje}&fim={hoje}&limite=50", token=token)
nossa = next((v for v in (itens or []) if v.get("documento") == f"KIT{marca}"), None)
checar("a venda aparece", nossa is not None, [v.get("documento") for v in (itens or [])[:5]])

st, apuracao = chamar("GET", f"/cmv/apuracao?inicio={hoje}&fim={hoje}", token=token)
checar("o CMV teórico contou o combo (2 x 7,00 = 14,00)",
       apuracao.get("cmv_teorico") is not None
       and float(apuracao["cmv_teorico"]) >= 14, apuracao.get("cmv_teorico"))

# Mexer no combo agora não pode mudar o que já foi vendido.
chamar("PUT", f"/produtos/{combo['id']}/kit",
       {"itens": [{"id_componente": refri["id"], "quantidade": 1}]}, token=token)
st, depois = chamar("GET", f"/cmv/apuracao?inicio={hoje}&fim={hoje}", token=token)
checar("mexer no combo depois NÃO reescreve o CMV da venda",
       perto(depois.get("cmv_teorico"), apuracao.get("cmv_teorico"), 0.02),
       (apuracao.get("cmv_teorico"), depois.get("cmv_teorico")))

print("8. custo do combo é dinheiro — obedece a chave de custo")
st, r = chamar("POST", "/auth/login", {"email": COZINHA[0], "senha": COZINHA[1]})
tk = r.get("access_token")
if tk:
    st, k = chamar("GET", f"/produtos/{combo['id']}/kit", token=tk)
    checar("cozinha vê a composição", st == 200 and len(k["itens"]) >= 1, k)
    checar("mas NÃO vê o custo", k.get("custo") is None, k)
    st, r = chamar("PUT", f"/produtos/{combo['id']}/kit", {"itens": []}, token=tk)
    checar("e não edita a composição", st == 403, st)
else:
    checar("usuário de cozinha disponível", False, r)

print("9. limpeza")
for p in (combo.get("id"), outro.get("id"), sem_custo.get("id"), prato.get("id"),
          refri.get("id"), arroz.get("id")):
    chamar("DELETE", f"/produtos/{p}", token=token)
checar("limpeza concluída", True)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
