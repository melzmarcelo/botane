"""O custo que alguém DIGITA, e o produzido que ainda não foi produzido.

Dois pedidos do dono, de 08/10/2026, que fecham o mesmo buraco — receita sem
custo por um ingrediente que o sistema não sabia custear:

1. *"Temos o produto Água, que é água encanada, não tem estoque, mas precisa ter
   custo, e não conseguimos informar este custo em local nenhum."*
   `PUT /produtos/{id}/custo-informado` grava o custo de referência com a origem
   `MANUAL` — o último degrau da cascata.

2. *"Tenho uma ficha que não foi produzida ainda … caso utilize ela em outra
   ficha, o custo desta nova ficha não consegue demonstrar."*
   Dentro de uma receita, o produzido sem custo apurado vale o que a ficha DELE
   prevê, marcado `ficha_provisoria` — até a primeira produção.

    python tests/smoke_custo_informado.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, "tests")
sys.path.insert(0, ".")
from comum import garantir_cozinha, garantir_locais  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

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
        with urllib.request.urlopen(req, dados, timeout=90) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")[:300]}


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


def perto(a, b, folga=0.0001):
    return a is not None and abs(float(a) - float(b)) < folga


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
assert st == 200, r
token = r["access_token"]

marca = str(time.time_ns() // 100)[-6:]
hoje = date.today().isoformat()
locais = garantir_locais(chamar, token)
principal = next((x for x in locais if x.get("principal")), locais[0])
criados: list[int] = []

print("1. a água: tem custo, não tem estoque")
# ⚠️ `controla_estoque` DESLIGADO de propósito: é o caso pedido. A água não entra
# por nota, não tem fornecedor e nunca vai ter custo médio.
st, r = chamar("POST", "/produtos", {
    "codigo": f"AGUA-{marca}", "nome": f"Agua encanada {marca}", "tipo": "INSUMO",
    "um_estoque": "L", "controla_estoque": False, "status": "ATIVO",
}, token=token)
agua = r.get("id")
criados.append(agua)
checar("a água é cadastrada sem controlar estoque", st == 201, (st, r))

st, c = chamar("GET", f"/produtos/{agua}/custo", token=token)
checar("antes, ninguém sabe quanto ela custa", c.get("atual") is None, c.get("atual"))

st, r = chamar("PUT", f"/produtos/{agua}/custo-informado", {"custo": 0.02}, token=token)
checar("o custo é informado", st == 200, (st, r))
checar("e a resposta diz que é ele quem responde", r.get("responde") is True, r)

st, c = chamar("GET", f"/produtos/{agua}/custo", token=token)
checar("a água passa a custar 0,02 o litro", perto(c.get("atual"), 0.02), c.get("atual"))
checar("pelo degrau da referência", c.get("origem") == "referencia", c.get("origem"))
checar("e a tela sabe que foi digitado, e não trazido de fora",
       c.get("informado_a_mao") is True and "à mão" in (c.get("origem_texto") or ""), c)
checar("o histórico diz de onde veio",
       any("à mão" in (l.get("detalhe") or "") for l in c.get("linhas") or []),
       c.get("linhas"))

# ⚠️ Zero não é um custo: é "ninguém sabe". Gravá-lo faria a ficha calcular com
# um número inventado e o aviso de "sem custo" sumir.
st, r = chamar("PUT", f"/produtos/{agua}/custo-informado", {"custo": 0}, token=token)
checar("custo zero é recusado", st == 422, st)
st, r = chamar("PUT", "/produtos/99999999/custo-informado", {"custo": 1}, token=token)
checar("produto inexistente é 404", st == 404, st)

tk_coz = garantir_cozinha(chamar, token)
st, r = chamar("PUT", f"/produtos/{agua}/custo-informado", {"custo": 9}, token=tk_coz)
checar("quem não ajusta custo não informa custo", st == 403, st)
st, c = chamar("GET", f"/produtos/{agua}/custo", token=token)
checar("e o número não mudou", perto(c.get("atual"), 0.02), c.get("atual"))

print("\n2. o número digitado é o ÚLTIMO degrau")
# Um insumo com estoque: o médio do razão responde, e o digitado fica guardado.
st, r = chamar("POST", "/produtos", {
    "codigo": f"ACU-{marca}", "nome": f"Acucar informado {marca}", "tipo": "INSUMO",
    "um_estoque": "KG", "controla_estoque": True, "status": "ATIVO",
}, token=token)
acucar = r.get("id")
criados.append(acucar)
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": acucar, "quantidade": 10, "custo_unitario": 5,
    "id_local": principal["id"], "documento": f"CI-{marca}",
}, token=token)
checar("o açúcar entra a 5,00 o quilo", st == 201, (st, r))
st, r = chamar("PUT", f"/produtos/{acucar}/custo-informado", {"custo": 99}, token=token)
checar("informar custo em quem tem médio é aceito", st == 200, (st, r))
checar("mas a resposta avisa que não é ele quem responde", r.get("responde") is False, r)
st, c = chamar("GET", f"/produtos/{acucar}/custo", token=token)
checar("o custo continua sendo o médio do razão", perto(c.get("atual"), 5), c.get("atual"))
checar("e o digitado fica guardado, à vista", perto(c.get("custo_informado"), 99), c)

print("\n3. a receita de baixo, que ainda não foi produzida")
st, r = chamar("POST", "/produtos", {
    "codigo": f"CALDA-{marca}", "nome": f"Calda informada {marca}", "tipo": "PRODUZIDO",
    "um_estoque": "KG", "producao_propria": True, "controla_estoque": True,
    "modo_producao": "PARA_ESTOQUE", "status": "ATIVO",
}, token=token)
calda = r.get("id")
criados.append(calda)
checar("a calda é cadastrada", st == 201, (st, r))
# 1 kg de açúcar (5,00) + 1 L de água (0,02) = 5,02 para 2 KG: 2,51 o quilo.
st, r = chamar("POST", "/fichas", {
    "id_produto": calda, "rendimento_qtd": 2, "rendimento_um": "KG", "porcoes": 1,
    "itens": [{"id_insumo": acucar, "qtd_bruta": 1, "um": "KG"},
              {"id_insumo": agua, "qtd_bruta": 1, "um": "L"}],
}, token=token)
ficha_calda = r.get("id")
checar("a ficha da calda é criada", st == 201, (st, r))
st, f = chamar("GET", f"/fichas/{ficha_calda}", token=token)
checar("a água custeia a receita: 5,02 no total", perto(f.get("custo_total"), 5.02),
       f.get("custo_total"))
checar("e a receita sai completa", f.get("custo_completo") is True, f.get("itens_sem_custo"))

print("\n4. a receita de cima usa a de baixo como ingrediente")
# ⚠️ Sem controlar estoque: a venda lá embaixo só precisa CONGELAR o custo, e
# produzir o bolo na hora deixaria a calda negativa nesta base.
st, r = chamar("POST", "/produtos", {
    "codigo": f"BOLOCI-{marca}", "nome": f"Bolo informado {marca}", "tipo": "PRODUZIDO",
    "um_estoque": "UN", "producao_propria": True, "controla_estoque": False,
    "status": "ATIVO",
}, token=token)
bolo = r.get("id")
criados.append(bolo)
st, r = chamar("POST", "/fichas", {
    "id_produto": bolo, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": calda, "qtd_bruta": 0.5, "um": "KG"}],
}, token=token)
ficha_bolo = r.get("id")
checar("a ficha do bolo é criada", st == 201, (st, r))

st, f = chamar("GET", f"/fichas/{ficha_bolo}", token=token)
linha = (f.get("itens") or [{}])[0]
# 0,5 kg × 2,51 = 1,255.
checar("a calda vale o que a ficha DELA prevê", perto(linha.get("custo_total"), 1.255),
       linha.get("custo_total"))
checar("e a linha diz que é provisório", linha.get("origem_custo") == "ficha_provisoria",
       linha.get("origem_custo"))
checar("a receita de cima deixa de sair parcial", f.get("custo_completo") is True,
       (f.get("custo_completo"), f.get("itens_sem_custo")))
checar("e conta o item provisório", f.get("itens_provisorios") == 1, f.get("itens_provisorios"))

# A prévia ao vivo é a MESMA conta — o que a tela mostra enquanto se digita.
st, pv = chamar("POST", "/fichas/previa-de-custo", {
    "itens": [{"id_insumo": calda, "qtd_bruta": 1, "um": "KG"}],
    "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
}, token=token)
checar("a prévia ao vivo usa o mesmo provisório",
       st == 200 and perto(pv.get("custo_total"), 2.51) and pv.get("itens_provisorios") == 1,
       (st, pv.get("custo_total"), pv.get("itens_provisorios")))

print("\n5. a venda congela o custo, e a origem diz que ele é previsto")
chamar("POST", f"/fichas/{ficha_bolo}/homologar", token=token)
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": hoje, "documento": f"CI-{marca}", "origem": "MANUAL", "canal": "BALCAO",
    "itens": [{"id_produto": bolo, "quantidade": 1, "valor_unitario": 10}],
}]}, token=token)
checar("a venda do bolo entra", st == 201, (st, r))
st, lista = chamar("GET", f"/vendas?busca=CI-{marca}", token=token)
id_venda = next((v["id"] for v in (lista or []) if v.get("documento") == f"CI-{marca}"), None)
st, d = chamar("GET", f"/vendas/{id_venda}", token=token)
item = next((i for i in (d.get("itens") or []) if i.get("id_produto") == bolo), {})
checar("com o custo de 1,255 congelado", perto(item.get("custo_ficha_unitario"), 1.255),
       item.get("custo_ficha_unitario"))
checar("e a origem avisando do ingrediente provisório",
       item.get("origem_custo") == "ficha_provisoria", item.get("origem_custo"))
chamar("DELETE", f"/vendas/{id_venda}", token=token)

print("\n6. produziu: o custo de verdade volta a responder")
chamar("POST", f"/fichas/{ficha_calda}/homologar", token=token)
st, r = chamar("POST", "/estoque/producoes", {
    "id_produto": calda, "quantidade": 2, "id_local": principal["id"]}, token=token)
checar("a calda é produzida, mesmo levando água", st == 201, (st, r))
# 🔑 **O que não controla estoque entra no CUSTO e não sai de lugar nenhum.** A
# produção era recusada inteira ("não controla estoque") por causa da água.
checar("o lote custa o açúcar MAIS a água: 5,02", perto(r.get("custo_total"), 5.02),
       r.get("custo_total"))
linha_agua = next((x for x in r.get("consumos") or [] if x.get("id_produto") == agua), {})
checar("a água aparece no consumo, marcada como sem estoque",
       linha_agua.get("sem_estoque") is True and perto(linha_agua.get("quantidade"), 1),
       linha_agua)
st, movs = chamar("GET", f"/estoque/movimentos?id_produto={agua}", token=token)
checar("e nenhum movimento nasce para ela", not movs, movs)
st, prev = chamar(
    "GET", f"/producao-agenda/necessario?id_produto={calda}&quantidade=2"
           f"&id_local={principal['id']}", token=token)
linha_prev = next((x for x in (prev or {}).get("itens") or []
                   if x.get("id_produto") == agua), {})
checar("a folha de produção não diz que falta água",
       st == 200 and linha_prev.get("sem_estoque") is True and linha_prev.get("falta") == 0,
       (st, linha_prev))
st, f = chamar("GET", f"/fichas/{ficha_bolo}", token=token)
linha = (f.get("itens") or [{}])[0]
checar("a linha passa a valer pelo custo médio", linha.get("origem_custo") == "custo_medio",
       linha.get("origem_custo"))
checar("e não há mais nada provisório na receita", f.get("itens_provisorios") == 0,
       f.get("itens_provisorios"))

# Desativa o que a rodada criou: produto de teste não fica na lista da casa.
for id_produto in reversed(criados):
    chamar("DELETE", f"/produtos/{id_produto}", token=token)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print(f"  - {x}")
sys.exit(1 if falhas else 0)
