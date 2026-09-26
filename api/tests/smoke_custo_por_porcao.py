"""O custo unitário de uma ficha é o da PORÇÃO vendida — na venda, na tela e na produção.

🔑 **Pedido do dono (26/09/2026):** *"na venda o custo da ficha técnica está indo por KG,
não por unidade/porção, que é a correta. No produto mostra a por porção, mas na venda
considera o custo por KG. Organizar o sistema para sempre considerar a porção no custo
unitário de uma ficha técnica."*

O cenário é o do cookie: o produto é contado em UN, e a ficha rende em KG, dividida em
porções. Antes, a venda congelava `custo ÷ rendimento` — o custo de 1 KG de massa por
cookie vendido.

    python tests/smoke_custo_por_porcao.py        (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from decimal import Decimal

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import garantir_local  # noqa: E402
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

# ⚠️ Marca com nanossegundos e o pid: as suítes que usam só os últimos dígitos da hora
# colidem com o rastro de rodadas anteriores.
import os  # noqa: E402

marca = f"{time.time_ns() % 10**9}{os.getpid() % 1000}"
hoje = date.today()
local = garantir_local(chamar, token)
criados: list[int] = []


def novo_produto(nome, tipo="INSUMO", um="KG"):
    st, r = chamar("POST", "/produtos", {"nome": nome, "tipo": tipo, "um_estoque": um},
                   token=token)
    if st == 201:
        criados.append(r["id"])
        return r["id"]
    return None


print("0. o cenário do cookie: produto em UN, ficha que rende 2 KG em 10 porções")
massa = novo_produto(f"Porcao insumo {marca}")
cookie = novo_produto(f"Porcao cookie {marca}", tipo="PRODUZIDO", um="UN")
checar("produtos criados", bool(massa and cookie))
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": massa, "quantidade": 30, "custo_unitario": 10, "id_local": local["id"],
    "documento": f"NF-PORCAO-{marca}"}, token=token)
checar("insumo a R$ 10,00 o KG", st == 201, r)
# 2 KG de insumo (R$ 20,00) rendem 2 KG de massa em 10 cookies → R$ 2,00 o cookie.
st, r = chamar("POST", "/fichas", {
    "id_produto": cookie, "rendimento_qtd": 2, "rendimento_um": "KG", "porcoes": 10,
    "itens": [{"id_insumo": massa, "qtd_bruta": 2, "um": "KG"}]}, token=token)
ficha = r.get("id")
chamar("POST", f"/fichas/{ficha}/homologar", token=token)
st, f = chamar("GET", f"/fichas/{ficha}", token=token)
checar("a ficha custa 20,00; 2,00 a porção; 10,00 o KG",
       perto(f.get("custo_total"), 20) and perto(f.get("custo_por_porcao"), 2)
       and perto(f.get("custo_por_unidade_rendimento"), 10), f)

print("\n1. a regra única")
from services import cmv, custos  # noqa: E402

with get_cursor() as cur:
    ums = custos._carregar_ums(cur)
    checar("a ponte: ficha em KG de produto em UN rende as PORÇÕES",
           custos.unidades_por_receita(2, 10, "KG", "UN", ums) == Decimal(10))
    checar("a ponte: ficha na unidade do produto rende o próprio rendimento",
           custos.unidades_por_receita(10, 8, "KG", "KG", ums) == Decimal(10))
    checar("a ponte: sem porções, a grandeza (2 KG = 2.000 G)",
           custos.unidades_por_receita(2, None, "KG", "G", ums) == Decimal(2000))
    checar("a ponte: sem nada que ligue, None",
           custos.unidades_por_receita(2, None, "KG", "UN", ums) is None)
    valor, origem = cmv.custo_teorico_do_produto(cur, cookie)
    checar("o custo da VENDA é o da porção (2,00), não o do KG (10,00)",
           perto(valor, 2) and origem == "ficha", (valor, origem))
    prov = custos.custo_provisorio_da_ficha(cur, cookie)
    checar("a tela do produto mostra o MESMO número que a venda congela",
           prov and perto(prov["custo"], valor), prov)

# 🔑 **"Sempre a porção"** (13/09 e 26/09/2026): também no produto estocado em KG. A
# ficha de 10 KG em 8 porções custa 24,00 → 3,00 a porção (e não 2,40 o KG).
massa_kg = novo_produto(f"Porcao massa kg {marca}", tipo="PRODUZIDO", um="KG")
chamar("POST", "/fichas", {
    "id_produto": massa_kg, "rendimento_qtd": 10, "rendimento_um": "KG", "porcoes": 8,
    "itens": [{"id_insumo": massa, "qtd_bruta": 2.4, "um": "KG"}]}, token=token)
with get_cursor() as cur:
    valor_kg, _o = cmv.custo_teorico_do_produto(cur, massa_kg)
    prov_kg = custos.custo_provisorio_da_ficha(cur, massa_kg)
checar("produto em KG com porções: a venda também usa a PORÇÃO (3,00)",
       perto(valor_kg, 3), valor_kg)
checar("e a tela concorda", prov_kg and perto(prov_kg["custo"], 3), prov_kg)
# Sem porções (a receita inteira é uma), a porção seria o lote: vale o KG.
massa_lote = novo_produto(f"Porcao lote kg {marca}", tipo="PRODUZIDO", um="KG")
chamar("POST", "/fichas", {
    "id_produto": massa_lote, "rendimento_qtd": 10, "rendimento_um": "KG", "porcoes": 1,
    "itens": [{"id_insumo": massa, "qtd_bruta": 2.4, "um": "KG"}]}, token=token)
with get_cursor() as cur:
    valor_lote, _o = cmv.custo_teorico_do_produto(cur, massa_lote)
checar("sem porções, o custo é o da unidade do produto (2,40 o KG), não o do lote",
       perto(valor_lote, 2.4), valor_lote)

print("\n2. a venda congela o custo da porção")
doc = f"CUPOM-PORCAO-{marca}"
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": str(hoje), "documento": doc, "canal": "SALAO", "origem": "PLANILHA",
    "itens": [{"id_produto": cookie, "quantidade": 3, "valor_unitario": 9}]}]}, token=token)
checar("a venda de 3 cookies entra", st == 201 and r.get("importadas") == 1, r)
with get_cursor() as cur:
    cur.execute("""SELECT vi.id, vi.custo_ficha_unitario, vi.custo_revisto
                     FROM venda_itens vi JOIN vendas v ON v.id = vi.id_venda
                    WHERE v.documento = %s""", (doc,))
    item = dict(cur.fetchone() or {})
checar("custo congelado: 2,00 por cookie", perto(item.get("custo_ficha_unitario"), 2), item)
checar("e a venda nova já nasce marcada como revista", item.get("custo_revisto") is True, item)

print("\n3. a correção das vendas antigas (migração 094)")
# Uma venda "de antes": o custo do KG (10,00) congelado, sem a marca.
with get_cursor() as cur:
    cur.execute("UPDATE venda_itens SET custo_ficha_unitario = 10, custo_revisto = NULL "
                "WHERE id = %s", (item["id"],))
sql = open("db_scripts/094_custo_da_venda_por_porcao.sql", encoding="utf-8").read()
with get_cursor() as cur:
    cur.execute(sql)
    cur.execute("SELECT custo_ficha_unitario, custo_revisto FROM venda_itens WHERE id = %s",
                (item["id"],))
    corrigido = dict(cur.fetchone())
checar("a migração corrige 10,00 → 2,00 (× rendimento ÷ porções)",
       perto(corrigido["custo_ficha_unitario"], 2) and corrigido["custo_revisto"], corrigido)
with get_cursor() as cur:
    cur.execute(sql)
    cur.execute("SELECT custo_ficha_unitario FROM venda_itens WHERE id = %s", (item["id"],))
    de_novo = cur.fetchone()["custo_ficha_unitario"]
checar("rodar de novo NÃO divide de novo (idempotente)", perto(de_novo, 2), de_novo)

# ⚠️ Período fechado não se toca.
with get_cursor() as cur:
    cur.execute("UPDATE venda_itens SET custo_ficha_unitario = 10, custo_revisto = NULL "
                "WHERE id = %s", (item["id"],))
    cur.execute("SELECT id_unidade FROM vendas v JOIN venda_itens vi ON vi.id_venda = v.id "
                "WHERE vi.id = %s", (item["id"],))
    id_unidade = cur.fetchone()["id_unidade"]
    cur.execute(
        """INSERT INTO cmv_fechamentos (id_unidade, competencia, inicio, fim, status)
           VALUES (%s, %s, %s, %s, 'FECHADO') RETURNING id""",
        (id_unidade, date(1999, 1, 1), hoje, hoje))
    id_fech = cur.fetchone()["id"]
    cur.execute(sql)
    cur.execute("SELECT custo_ficha_unitario FROM venda_itens WHERE id = %s", (item["id"],))
    fechado = cur.fetchone()["custo_ficha_unitario"]
    cur.execute("DELETE FROM cmv_fechamentos WHERE id = %s", (id_fech,))
checar("venda de período FECHADO fica como estava", perto(fechado, 10), fechado)

print("\n4. limpeza")
with get_cursor() as cur:
    cur.execute("""DELETE FROM venda_itens WHERE id_venda IN
                     (SELECT id FROM vendas WHERE documento = %s)""", (doc,))
    # ⚠️ Os movimentos de estoque FICAM: o razão é append-only (regra 1), e a baixa
    # desta venda é tão fato quanto qualquer outra. Só a venda de teste sai.
    cur.execute("DELETE FROM vendas WHERE documento = %s", (doc,))
for i in criados:
    chamar("DELETE", f"/produtos/{i}", token=token)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
