"""A venda para uma pessoa marcada como CONSUMO INTERNO.

🔑 **Pedido do dono (26/09/2026):** *"quando lanço uma venda para uma pessoa, habilitar um
novo campo, Considerar consumo interno. Quando marcada, este documento entra como consumo
interno e não é considerado no CMV, somente o custo … deve manter a mesma regra do
consumo interno."*

Mede pelo DELTA da apuração do dia (a base tem dado de outras suítes): o documento não
mexe na receita nem no CMV teórico, e o custo dele entra na linha de consumo interno.

    python tests/smoke_venda_consumo_interno.py        (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import garantir_ciclo_de_consumo, garantir_local  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


def perto(a, b, tol=0.005):
    return a is not None and abs(float(a) - float(b)) <= tol


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()
marca = str(time.time_ns() // 100)[-6:]
hoje = date.today()
local = garantir_local(chamar, token)
ciclo_da_suite = garantir_ciclo_de_consumo(chamar, token)


def apuracao():
    _st, a = chamar("GET", f"/cmv/apuracao?inicio={hoje}&fim={hoje}", token=token)
    return a or {}


print("0. o cenário: um produto a R$ 4,00 de custo e R$ 10,00 de venda, e uma pessoa")
st, prod = chamar("POST", "/produtos", {
    "nome": f"CONSUMO INTERNO {marca}", "tipo": "REVENDA", "um_estoque": "UN",
    "preco_venda": 10, "status": "ATIVO"}, token=token)
produto = (prod or {}).get("id")
chamar("PUT", f"/produtos/{produto}", {"id_local_padrao": local["id"]}, token=token)
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": produto, "quantidade": 10, "custo_unitario": 4, "id_local": local["id"],
    "documento": f"NF-CI-{marca}"}, token=token)
checar("10 unidades a R$ 4,00 em estoque", st == 201, r)
st, pes = chamar("POST", "/fornecedores", {"nome": f"EQUIPE {marca}", "fornecedor": False},
                 token=token)
pessoa = (pes or {}).get("id")
checar("a pessoa existe", bool(pessoa), pes)
antes = apuracao()

print("\n1. o consumo interno é de alguém")
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": str(hoje), "documento": f"SEMPESSOA-{marca}", "origem": "MANUAL",
    "consumo_interno": True,
    "itens": [{"id_produto": produto, "quantidade": 1, "valor_unitario": 10}]}]}, token=token)
checar("sem pessoa é recusado (422), dizendo o que falta",
       st == 422 and "pessoa" in str(r.get("detail", "")), (st, r))

print("\n2. o documento de consumo interno")
doc = f"CI-{marca}"
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": str(hoje), "documento": doc, "origem": "MANUAL", "id_pessoa": pessoa,
    "consumo_interno": True,
    "itens": [{"id_produto": produto, "quantidade": 2, "valor_unitario": 10}]}]}, token=token)
checar("entra", st == 201 and r.get("importadas") == 1, (st, r))
with get_cursor() as cur:
    cur.execute("SELECT id, consumo_interno FROM vendas WHERE documento = %s", (doc,))
    venda = dict(cur.fetchone() or {})
    cur.execute("""SELECT tipo, quantidade, custo_total, origem_tipo FROM estoque_movimentos
                    WHERE origem_tipo = 'VENDA' AND origem_id = %s""", (venda.get("id"),))
    movs = [dict(x) for x in cur.fetchall()]
checar("gravado como consumo interno", venda.get("consumo_interno") is True, venda)
checar("o estoque sai como CONSUMO INTERNO, não como venda",
       len(movs) == 1 and movs[0]["tipo"] == "SAIDA_CONSUMO_INTERNO"
       and perto(abs(movs[0]["quantidade"]), 2), movs)

depois = apuracao()
d = {k: float(depois.get(k) or 0) - float(antes.get(k) or 0)
     for k in ("receita", "cmv_teorico", "consumo_interno", "cmv_real")}
checar("a RECEITA não muda (ninguém vendeu)", perto(d["receita"], 0), d)
checar("o CMV TEÓRICO não muda", perto(d["cmv_teorico"], 0), d)
checar("o custo (2 × 4,00) entra na linha de consumo interno", perto(d["consumo_interno"], 8), d)
checar("e no CMV real, que é o que saiu do estoque", perto(d["cmv_real"], 8), d)

st, lista = chamar("GET", f"/vendas?busca={doc}", token=token)
checar("a lista de vendas mostra a marca",
       st == 200 and lista and lista[0].get("consumo_interno") is True, lista)
st, det = chamar("GET", f"/vendas/{venda.get('id')}", token=token)
checar("e o detalhe também", det.get("consumo_interno") is True, det.get("consumo_interno"))
st, mg = chamar("GET", f"/cmv/margem?inicio={hoje}&fim={hoje}&limite=200", token=token)
checar("não aparece na margem por prato (não é venda)",
       st == 200 and not any(x.get("id_produto") == produto for x in (mg or [])),
       [x for x in (mg or []) if x.get("id_produto") == produto])
st, pp = chamar("GET", f"/vendas/por-pessoa?id_pessoa={pessoa}&detalhe=documento", token=token)
checar("continua no consumo da PESSOA",
       st == 200 and any(x.get("documento") == doc for x in pp.get("linhas") or []), pp)
st, sb = chamar("GET", "/vendas/sem-baixa/previa", token=token)
pendente = [x for x in (sb or {}).get("itens", []) if x.get("id_produto") == produto]
checar("e não aparece como 'vendido e não baixado' (a baixa foi o consumo interno)",
       st == 200 and not pendente, pendente)

print("\n3. cancelar devolve ao estoque e tira da linha")
st, r = chamar("DELETE", f"/vendas/{venda.get('id')}", token=token)
checar("o cancelamento estorna o consumo interno", st == 200 and r.get("estornados") == 1,
       (st, r))
fim = apuracao()
checar("e a linha de consumo interno volta ao que era",
       perto(float(fim.get("consumo_interno") or 0), float(antes.get("consumo_interno") or 0)),
       (fim.get("consumo_interno"), antes.get("consumo_interno")))

print("\n4. limpeza")
with get_cursor() as cur:
    cur.execute("DELETE FROM venda_itens WHERE id_venda IN "
                "(SELECT id FROM vendas WHERE documento = ANY(%s))", ([doc, f"SEMPESSOA-{marca}"],))
    cur.execute("DELETE FROM vendas WHERE documento = ANY(%s)", ([doc, f"SEMPESSOA-{marca}"],))
chamar("DELETE", f"/produtos/{produto}", token=token)
if pessoa:
    chamar("DELETE", f"/fornecedores/{pessoa}", token=token)
if ciclo_da_suite:
    chamar("DELETE", f"/consumo/periodos/{ciclo_da_suite}", token=token)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
