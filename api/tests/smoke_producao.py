"""Agenda de produção e os dois modos de produzir.

Duas coisas que o sistema tratava igual e não são:

* **Massa de pizza** (PARA_ESTOQUE): produz, guarda, sai depois. Tem estoque,
  tem mínimo, e alguém precisa decidir produzir antes que falte — é o que a
  agenda serve. A agenda é PLANO: não mexe no estoque até ser cumprida.

* **Café passado** (NA_HORA): não fica em estoque. A venda e a produção são o
  mesmo instante — a venda produz e baixa junto, e o saldo volta a zero. Sem
  isso, a casa venderia mil cafés e o pó continuaria inteiro no razão.

    python tests/smoke_producao.py            (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date, timedelta

sys.path.insert(0, "tests")
from comum import garantir_local  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []
SUF = uuid.uuid4().hex[:5]


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
        print(f"  FALHA {nome} -> {extra}")


def perto(a, b, tol=0.001):
    return a is not None and abs(float(a) - float(b)) < tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = r["access_token"]
local = garantir_local(chamar, token)
amanha = date.today() + timedelta(days=1)
ontem = date.today() - timedelta(days=1)


def novo_produto(nome, um, **extra):
    st, r = chamar("POST", "/produtos", {"nome": nome, "um_estoque": um, **extra}, token=token)
    return r.get("id")


print("1. o cenário: farinha, massa (para estoque) e café (na hora)")
farinha = novo_produto(f"Prod farinha {SUF}", "KG", tipo="INSUMO")
po = novo_produto(f"Prod pó de café {SUF}", "KG", tipo="INSUMO")
massa = novo_produto(f"Prod massa {SUF}", "UN", tipo="PRODUZIDO", producao_propria=True,
                     estoque_minimo=10, estoque_maximo=30)
cafe = novo_produto(f"Prod café passado {SUF}", "UN", tipo="PRODUZIDO",
                    producao_propria=True, modo_producao="NA_HORA")
st, p = chamar("GET", f"/produtos/{cafe}", token=token)
checar("o café é NA_HORA", p.get("modo_producao") == "NA_HORA", p.get("modo_producao"))
st, p = chamar("GET", f"/produtos/{massa}", token=token)
checar("a massa é PARA_ESTOQUE (o padrão)", p.get("modo_producao") == "PARA_ESTOQUE",
       p.get("modo_producao"))
st, r = chamar("PUT", f"/produtos/{cafe}", {"modo_producao": "INVENTADO"}, token=token)
checar("modo inventado é recusado", st == 400, (st, r))

for insumo, custo in ((farinha, 5.00), (po, 40.00)):
    chamar("POST", "/estoque/entradas",
           {"id_produto": insumo, "quantidade": 100, "custo_unitario": custo,
            "id_local": local["id"]}, token=token)

# 1 massa = 0,2 KG de farinha = 1,00 | 1 café = 0,01 KG de pó = 0,40
st, r = chamar("POST", "/fichas", {
    "id_produto": massa, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": farinha, "qtd_bruta": 0.2, "um": "KG"}]}, token=token)
ficha_massa = r.get("id")
chamar("POST", f"/fichas/{ficha_massa}/homologar", {}, token=token)
st, r = chamar("POST", "/fichas", {
    "id_produto": cafe, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": po, "qtd_bruta": 0.01, "um": "KG"}]}, token=token)
ficha_cafe = r.get("id")
chamar("POST", f"/fichas/{ficha_cafe}/homologar", {}, token=token)

print("\n2. a agenda é plano: não mexe no estoque")
st, r = chamar("POST", "/producao-agenda",
               {"id_produto": massa, "data_prevista": str(amanha), "quantidade": 20},
               token=token)
checar("agenda 20 massas para amanhã", st == 201, r)
id_linha = r.get("id")
st, saldos = chamar("GET", "/estoque/saldos", token=token)
checar("o estoque NÃO se mexeu ao agendar",
       not any(s["id_produto"] == massa for s in saldos), saldos[:2])
st, saldo_farinha = chamar("GET", f"/estoque/saldos?id_produto={farinha}", token=token)
checar("nem o da farinha", perto(saldo_farinha[0]["quantidade"], 100),
       saldo_farinha[0]["quantidade"])

st, r = chamar("POST", "/producao-agenda",
               {"id_produto": massa, "data_prevista": str(amanha), "quantidade": 5},
               token=token)
checar("agendar de novo no mesmo dia SOMA, não duplica", perto(r.get("quantidade"), 25), r)

st, r = chamar("POST", "/producao-agenda",
               {"id_produto": cafe, "data_prevista": str(amanha), "quantidade": 10},
               token=token)
checar("o que é feito na hora não se agenda", st == 400, (st, r))
checar("e a recusa explica por quê", "na hora" in str(r.get("detail", "")).lower(), r)

print("\n3. cumprir a linha é que mexe no estoque")
st, r = chamar("POST", f"/producao-agenda/{id_linha}/produzir", {"quantidade": 22},
               token=token)
checar("produz 22 (a cozinha rendeu diferente do plano)", st == 200, r)
checar("guarda o planejado e o produzido",
       perto(r.get("planejado"), 25) and perto(r.get("produzido"), 22), r)
checar("consumindo 4,4 KG de farinha",
       perto((r.get("consumos") or [{}])[0].get("quantidade"), 4.4), r.get("consumos"))
checar("a 22,00 (4,4 × 5,00)", perto(r.get("custo_total"), 22.00, 0.01), r.get("custo_total"))
st, saldos = chamar("GET", f"/estoque/saldos?id_produto={massa}", token=token)
checar("22 massas em estoque", perto(saldos[0]["quantidade"], 22), saldos)
checar("a 1,00 cada", perto(saldos[0]["custo_medio"], 1.00), saldos)

st, r = chamar("POST", f"/producao-agenda/{id_linha}/produzir", {}, token=token)
checar("não produz a mesma linha duas vezes", st == 400, (st, r))

# Agenda é lista de TAREFA: cumprida, sai dela. O que já foi produzido tem
# lugar próprio ("Produções recentes"); misturar faria a agenda crescer para
# sempre e esconder o que falta fazer no meio do que já foi feito.
st, agenda = chamar("GET", "/producao-agenda", token=token)
checar("a linha produzida sai da agenda",
       not any(l["id"] == id_linha for l in agenda["linhas"]),
       [(l["id"], l["status"]) for l in agenda["linhas"]])
st, historico = chamar("GET", "/producao-agenda?status=PRODUZIDA", token=token)
checar("mas continua no histórico, para conferir plano contra realizado",
       any(l["id"] == id_linha for l in historico["linhas"]),
       [(l["id"], l["status"]) for l in historico["linhas"]])

print("\n4. o café passado: a venda produz e baixa")
st, antes = chamar("GET", f"/estoque/saldos?id_produto={po}", token=token)
po_antes = float(antes[0]["quantidade"])
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": str(date.today()), "documento": f"CUPOM-{SUF}",
    "itens": [{"id_produto": cafe, "quantidade": 30, "valor_unitario": 6.00}]}]},
    token=token)
checar("importa a venda de 30 cafés", st == 201, r)
checar("e diz que produziu na hora", r.get("produzidos_na_hora") == 1, r)

st, depois = chamar("GET", f"/estoque/saldos?id_produto={po}", token=token)
checar("o pó baixou 0,3 KG (30 × 0,01)", perto(float(depois[0]["quantidade"]), po_antes - 0.3),
       (po_antes, depois[0]["quantidade"]))
st, saldos = chamar("GET", f"/estoque/saldos?id_produto={cafe}", token=token)
checar("e o café passado NÃO fica em estoque",
       not saldos or perto(saldos[0]["quantidade"], 0), saldos)

st, mov = chamar("GET", f"/estoque/movimentos?id_produto={cafe}", token=token)
tipos = {m["tipo"] for m in mov}
checar("o razão mostra os dois lados: produção e venda",
       {"ENTRADA_PRODUCAO", "SAIDA_VENDA"} <= tipos, tipos)

# A massa é do outro tipo: vender não produz nada sozinho.
st, antes = chamar("GET", f"/estoque/saldos?id_produto={massa}", token=token)
chamar("POST", "/vendas/importar", {"vendas": [{
    "data": str(date.today()), "documento": f"CUPOM-M-{SUF}",
    "itens": [{"id_produto": massa, "quantidade": 2, "valor_unitario": 12.00}]}]},
    token=token)
st, depois = chamar("GET", f"/estoque/saldos?id_produto={massa}", token=token)
checar("vender massa NÃO dispara produção (ela sai do que já existe)",
       perto(depois[0]["quantidade"], antes[0]["quantidade"]), (antes, depois))

print("\n5. o mínimo vira agenda")
st, r = chamar("POST", "/estoque/saidas",
               {"id_produto": massa, "quantidade": 15, "id_local": local["id"],
                "tipo": "SAIDA_CONSUMO_INTERNO"}, token=token)
checar("consome 15 massas, ficando abaixo do mínimo", st == 201, r)
st, agenda = chamar("GET", "/producao-agenda", token=token)
sugerida = next((s for s in agenda["sugestoes"] if s["id_produto"] == massa), None)
checar("a massa aparece como sugestão", sugerida is not None,
       [s["produto"] for s in agenda["sugestoes"]])
if sugerida:
    checar("sugerindo repor até o MÁXIMO (30 − 7 = 23)", perto(sugerida["sugerido"], 23),
           sugerida)

st, alertas = chamar("GET", "/alertas", token=token)
chaves = {a["chave"] for a in alertas}
checar("o alerta separa 'produzir' de 'comprar'", "producao.agendar" in chaves, chaves)

st, r = chamar("POST", "/producao-agenda/das-sugestoes", token=token)
checar("um botão põe todas na agenda", st == 201 and r.get("criadas", 0) >= 1, r)
st, agenda = chamar("GET", "/producao-agenda", token=token)
checar("e a sugestão some depois de agendada",
       not any(s["id_produto"] == massa for s in agenda["sugestoes"]),
       [s["produto"] for s in agenda["sugestoes"]])

print("\n6. o que ficou para trás")
st, r = chamar("POST", "/producao-agenda",
               {"id_produto": massa, "data_prevista": str(ontem), "quantidade": 3},
               token=token)
atrasada = r.get("id")
st, agenda = chamar("GET", "/producao-agenda", token=token)
linha = next((l for l in agenda["linhas"] if l["id"] == atrasada), None)
checar("a linha de ontem aparece como atrasada", linha and linha["atrasada"] is True, linha)
checar("e o resumo conta as atrasadas", agenda["resumo"]["atrasadas"] >= 1, agenda["resumo"])

st, r = chamar("DELETE", f"/producao-agenda/{atrasada}", token=token)
checar("dá para cancelar o que não vai ser feito", st == 200, r)
st, r = chamar("DELETE", f"/producao-agenda/{id_linha}", token=token)
checar("mas não se cancela o que já virou produção", st == 400, (st, r))

print("\n7. limpeza")
st, agenda = chamar("GET", "/producao-agenda", token=token)
for l in agenda["linhas"]:
    if l["status"] == "PLANEJADA":
        chamar("DELETE", f"/producao-agenda/{l['id']}", token=token)
for pid in (farinha, po, massa, cafe):
    chamar("DELETE", f"/produtos/{pid}", token=token)
checar("limpeza concluída", True)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
