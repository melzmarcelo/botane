"""Incluir numa contagem aberta um produto achado na prateleira que não estava na lista.

🔑 **Pedido do dono (26/09/2026):** *"ao realizar um inventário de um setor, e for
encontrado um produto que não estava no inventário ou não estava naquele setor, como
proceder? … pode incluir."* (migração 096).

    python tests/smoke_inventario_incluir.py        (API de pé na 9200)
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import garantir_locais  # noqa: E402
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


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()
marca = str(time.time_ns() // 100)[-6:]
abertas: list[int] = []
atexit.register(lambda: [chamar("DELETE", f"/inventarios/{i}", token=token) for i in abertas])


def novo(nome, **extra):
    st, r = chamar("POST", "/produtos", {"nome": nome, "tipo": "INSUMO", "um_estoque": "UN",
                                         **extra}, token=token)
    return (r or {}).get("id")


print("0. cenário: um produto na prateleira 1, outro só na prateleira 2")
l1, l2 = garantir_locais(chamar, token, 2)[:2]
na_lista = novo(f"Inclui na lista {marca}")
achado = novo(f"Inclui achado {marca}")
sem_estoque = novo(f"Inclui sem estoque {marca}", controla_estoque=False)
chamar("POST", "/estoque/entradas", {"id_produto": na_lista, "quantidade": 5,
                                     "custo_unitario": 2, "id_local": l1["id"]}, token=token)
# O achado mora (no sistema) só na prateleira 2, a R$ 5,00 — é esse o custo médio dele.
chamar("POST", "/estoque/entradas", {"id_produto": achado, "quantidade": 4,
                                     "custo_unitario": 5, "id_local": l2["id"]}, token=token)
st, inv = chamar("POST", "/inventarios", {"locais": [l1["id"]]}, token=token)
checar("abre a contagem da prateleira 1", st == 201, (st, inv))
id_inv = (inv or {}).get("id")
if id_inv:
    abertas.append(id_inv)
st, inv = chamar("GET", f"/inventarios/{id_inv}", token=token)
checar("o produto da prateleira 2 NÃO está na lista",
       not any(i["id_produto"] == achado for i in inv.get("itens", [])), len(inv.get("itens", [])))
checar("a contagem diz em que prateleiras se pode incluir",
       [l["id"] for l in inv.get("locais_da_contagem", [])] == [l1["id"]],
       inv.get("locais_da_contagem"))

print("\n1. incluir o produto achado")
st, inv = chamar("POST", f"/inventarios/{id_inv}/incluir", {"id_produto": achado}, token=token)
item = next((i for i in (inv or {}).get("itens", []) if i["id_produto"] == achado), {})
checar("com uma prateleira só, nem precisa dizer qual", st == 200 and item, (st, inv))
checar("entra marcado como incluído, com o saldo do sistema ALI (zero)",
       item.get("incluido") is True and float(item.get("qtd_sistema") or 0) == 0
       and item.get("id_local") == l1["id"], item)
st, r = chamar("POST", f"/inventarios/{id_inv}/incluir", {"id_produto": achado}, token=token)
checar("incluir de novo é recusado (409), dizendo onde já está",
       st == 409 and l1["nome"] in str(r.get("detail", "")), (st, r))
st, r = chamar("POST", f"/inventarios/{id_inv}/incluir",
               {"id_produto": na_lista, "id_local": l2["id"]}, token=token)
checar("prateleira que não é da contagem é recusada", st == 400, (st, r))
st, r = chamar("POST", f"/inventarios/{id_inv}/incluir", {"id_produto": sem_estoque}, token=token)
checar("produto que não controla estoque é recusado", st == 400, (st, r))

print("\n2. contar e fechar: a sobra entra pelo custo MÉDIO, nunca zero")
st, inv = chamar("PUT", f"/inventarios/{id_inv}/contagem",
                 {"itens": [{"id_produto": achado, "qtd_contada": 3}]}, token=token)
checar("conta 3 do achado, como qualquer item", st == 200, (st, inv))
st, r = chamar("POST", f"/inventarios/{id_inv}/fechar", token=token)
checar("a contagem fecha", st == 200, (st, r))
if st == 200:
    abertas.remove(id_inv)
with get_cursor() as cur:
    cur.execute("""SELECT tipo, quantidade, custo_unitario FROM estoque_movimentos
                    WHERE origem_tipo = 'INVENTARIO' AND origem_id = %s AND id_produto = %s""",
                (id_inv, achado))
    mov = dict(cur.fetchone() or {})
    cur.execute("SELECT quantidade FROM estoque_saldos WHERE id_produto = %s AND id_local = %s",
                (achado, l1["id"]))
    saldo = (cur.fetchone() or {}).get("quantidade")
checar("vira sobra na prateleira 1 (ajuste de inventário)",
       mov.get("tipo") == "AJUSTE_INVENTARIO_ENTRADA" and float(mov.get("quantidade") or 0) == 3,
       mov)
checar("valendo o custo médio do produto (5,00), não zero",
       abs(float(mov.get("custo_unitario") or 0) - 5) < 0.01, mov)
checar("e o produto passa a morar na prateleira 1, com 3",
       saldo is not None and float(saldo) == 3, saldo)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
