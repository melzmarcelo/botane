"""Teste de fumaça: a evolução de preço × custo de um produto (tela de Preços).

O cenário, num produto novo de revenda:

    há 60 dias   preço R$ 16,00              (vigência antiga, fechada ontem)
    hoje         preço R$ 20,00, e uma entrada a R$ 8,00

    -> dois degraus de preço (16 e 20) e UMA mudança;
    -> o custo só existe a partir de hoje: antes dele a margem é nula, nunca 100%;
    -> hoje: (20 − 8) ÷ 20 = 60% de margem.

Prova também que produto sem preço e sem custo responde sem erro e sem inventar
número, que a janela começa onde há dado, e que a rota pede a permissão do CMV.

⚠️ **A vigência antiga entra por SQL.** A tela de produto só grava preço com a
data de hoje; para medir um DEGRAU no tempo o cenário precisa de um preço com
data de trás. É fixture de `produto_precos` — não é o razão —, e a suíte apaga o
que criou.

    python tests/smoke_preco_custo.py      (da pasta `api`, com a API de pé na 9200)
"""

import datetime
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
sys.path.insert(0, ".")
from comum import garantir_cozinha, garantir_local  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []
marca = str(int(time.time()))[-6:]
HOJE = datetime.date.today()
ANTES = HOJE - datetime.timedelta(days=60)


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
    return a is not None and b is not None and abs(float(a) - float(b)) < tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
local = garantir_local(chamar, token)
init_pool()

print("1. produto sem preço e sem custo: responde, e não inventa nada")
st, p = chamar("POST", "/produtos", {
    "codigo": f"PXC-{marca}", "nome": f"PRECO X CUSTO {marca}", "tipo": "REVENDA",
    "um_estoque": "UN", "controla_estoque": True, "status": "ATIVO"}, token=token)
produto = (p or {}).get("id")
checar("o produto de teste nasce", bool(produto), (st, p))
st, e = chamar("GET", f"/cmv/preco-custo/{produto}", token=token)
checar("a rota responde", st == 200, (st, e))
checar("sem custo, a fonte é nula", e.get("fonte_custo") is None, e.get("fonte_custo"))
checar("e nenhum ponto traz número", all(x["preco"] is None and x["custo"] is None
                                         and x["margem_pct"] is None for x in e["pontos"]),
       e["pontos"])
checar("nem mudança de preço", e.get("mudancas_de_preco") == [], e.get("mudancas_de_preco"))

print("\n2. o cenário: um preço de 60 dias atrás, o de hoje e uma compra hoje")
st, r = chamar("PUT", f"/produtos/{produto}", {"preco_venda": 20}, token=token)
checar("o preço de hoje é gravado pela tela", st == 200, (st, r))
with get_cursor() as cur:
    cur.execute(
        """INSERT INTO produto_precos (id_produto, id_unidade, preco_venda, vigente_de, vigente_ate)
           VALUES (%s, NULL, 16, %s, %s)""",
        (produto, ANTES, HOJE - datetime.timedelta(days=1)))
    cur.execute("UPDATE produto_precos SET vigente_de = %s WHERE id_produto = %s AND vigente_ate IS NULL",
                (HOJE, produto))
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": produto, "quantidade": 10, "custo_unitario": 8, "id_local": local["id"]},
    token=token)
checar("a compra de hoje entra a R$ 8,00", st == 201, (st, r))

st, e = chamar("GET", f"/cmv/preco-custo/{produto}?meses=12", token=token)
pontos = e.get("pontos", [])
por_data = {x["data"]: x for x in pontos}
checar("a janela começa onde há dado: no primeiro preço, não um ano atrás",
       e.get("inicio") == str(ANTES) and pontos[0]["data"] == str(ANTES), (e.get("inicio"), pontos[:1]))
checar("o degrau antigo é R$ 16,00", perto(por_data.get(str(ANTES), {}).get("preco"), 16), pontos)
checar("o de hoje é R$ 20,00", perto(por_data.get(str(HOJE), {}).get("preco"), 20), pontos)
checar("UMA mudança de preço, na data de hoje", e.get("mudancas_de_preco") == [str(HOJE)],
       e.get("mudancas_de_preco"))
checar("o custo vem do razão", e.get("fonte_custo") == "razao", e.get("fonte_custo"))
checar("e é R$ 8,00 hoje", perto(por_data.get(str(HOJE), {}).get("custo"), 8), pontos)
# 🔑 Sem custo é NULO, nunca zero: zero faria a margem do degrau antigo sair em 100%.
checar("antes da compra não há custo — e a margem é nula, não 100%",
       por_data[str(ANTES)]["custo"] is None and por_data[str(ANTES)]["margem_pct"] is None,
       por_data[str(ANTES)])
checar("hoje a margem é (20 − 8) ÷ 20 = 60%", perto(por_data[str(HOJE)]["margem_pct"], 60),
       por_data[str(HOJE)])
checar("as datas vêm em ordem", [x["data"] for x in pontos] == sorted(x["data"] for x in pontos))

print("\n3. a janela corta o que é mais antigo que ela")
st, curto = chamar("GET", f"/cmv/preco-custo/{produto}?meses=1", token=token)
checar("em 1 mês, o início já mostra o preço que valia ali (16), sem o ponto de 60 dias",
       str(ANTES) not in [x["data"] for x in curto["pontos"]]
       and perto(curto["pontos"][0]["preco"], 16), curto["pontos"][:2])
checar("e a mudança de hoje continua lá", curto.get("mudancas_de_preco") == [str(HOJE)],
       curto.get("mudancas_de_preco"))

print("\n4. o preço médio cobrado sai das vendas")
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": str(HOJE), "documento": f"PXC-{marca}", "origem": "MANUAL",
    "itens": [{"id_produto": produto, "quantidade": 2, "valor_unitario": 18}]}]}, token=token)
checar("uma venda com desconto entra (2 × 18,00)", st in (200, 201), (st, r))
st, e = chamar("GET", f"/cmv/preco-custo/{produto}", token=token)
checar("o praticado é R$ 18,00, não o de cadastro",
       perto(e["praticado"]["preco_medio"], 18) and perto(e["praticado"]["quantidade"], 2),
       e["praticado"])
checar("e o preço de cadastro continua R$ 20,00", perto(e["pontos"][-1]["preco"], 20),
       e["pontos"][-1])

print("\n5. o que não existe, o que não cabe e quem não pode")
st, r = chamar("GET", "/cmv/preco-custo/99999999", token=token)
checar("produto inexistente é 404", st == 404, (st, r))
st, r = chamar("GET", f"/cmv/preco-custo/{produto}?meses=0", token=token)
checar("janela de zero meses é 422", st == 422, st)
cozinha = garantir_cozinha(chamar, token)
st, r = chamar("GET", f"/cmv/preco-custo/{produto}", token=cozinha)
checar("a cozinha não vê preço e margem", st == 403, st)

print("\n6. limpeza")
st, vendas = chamar("GET", f"/vendas?busca=PXC-{marca}", token=token)
for v in (vendas or []):
    if not v.get("cancelada"):
        chamar("DELETE", f"/vendas/{v['id']}", token=token)
st, movs = chamar("GET", f"/estoque/movimentos?id_produto={produto}&limite=50", token=token)
entrada = next((m for m in (movs or []) if m.get("tipo") == "ENTRADA_MANUAL"), None)
if entrada:
    chamar("POST", f"/estoque/movimentos/{entrada['id']}/estornar", {"motivo": "limpeza da suíte"},
           token=token)
with get_cursor() as cur:
    cur.execute("DELETE FROM produto_precos WHERE id_produto = %s", (produto,))
chamar("DELETE", f"/produtos/{produto}", token=token)
st, saldos = chamar("GET", f"/estoque/saldos?id_produto={produto}&incluir_inativos=true", token=token)
checar("o saldo do produto de teste volta a zero",
       all(float(s.get("quantidade") or 0) == 0 for s in (saldos or [])), saldos)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
