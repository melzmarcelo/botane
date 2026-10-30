"""Catálogo simples com abertura e cartões no site, destaque/esgotado, e a pré-visualização.

🔑 **Pedido do dono (30/10/2026)**, estudo em `docs/catalogo-simples-estudo.md`: o catálogo que
não é Cardápio Vivo ganha abertura e cartões no site (sem vídeo); destaque e esgotado valem no
site; e a aba Pré-visualização mostra o que vai ao ar — em qualquer situação — com um pedido de
TESTE que o servidor confere e não grava.

    python tests/smoke_catalogo_previa.py        (API de pé na 9200)
"""

import atexit
import json
import random
import sys
import time
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import garantir_cozinha, preservar_reserva  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
MARCA = str(time.time_ns() // 100)[-6:]
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
        b = e.read()
        try:
            return e.code, json.loads(b or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": b.decode(errors="replace")}


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
cozinha = garantir_cozinha(chamar, token)
init_pool()
_st, eu = chamar("GET", "/auth/me", token=token)
U = (eu.get("unidades") or [{}])[0].get("id") or 1
preservar_reserva(U)


def _devolver():
    with get_cursor() as cur:
        cur.execute("DELETE FROM catalogos WHERE nome LIKE %s", (f"%{MARCA}%",))
        cur.execute("DELETE FROM reserva_clientes WHERE nome LIKE %s", (f"%{MARCA}%",))


atexit.register(_devolver)
_st, par = chamar("GET", f"/unidades/{U}/parametros", token=token)
chamar("PUT", f"/unidades/{U}/parametros", {**par, "reservas_ligado": True}, token)
with get_cursor() as cur:
    cur.execute("DELETE FROM reserva_bloqueios WHERE id_unidade = %s", (U,))
    cur.execute("DELETE FROM reserva_dias_especiais WHERE id_unidade = %s", (U,))
    for d in range(1, 8):
        cur.execute(
            """INSERT INTO reserva_horarios (id_unidade, dia_semana, aberto, abre, fecha, ultima_reserva)
               VALUES (%s, %s, true, '00:00', '23:59', '23:00')
               ON CONFLICT (id_unidade, dia_semana) DO UPDATE
                  SET aberto = true, abre = '00:00', fecha = '23:59', ultima_reserva = '23:00'""",
            (U, d))


def produto(nome, preco):
    _st, p = chamar("POST", "/produtos", {"nome": f"{nome} {MARCA}", "tipo": "INSUMO",
                                          "um_estoque": "UN", "controla_estoque": False}, token)
    _st, atual = chamar("GET", f"/produtos/{p['id']}", token=token)
    chamar("PUT", f"/produtos/{p['id']}", {**atual, "integrado_pdv": True, "preco_venda": preco}, token)
    return p["id"]


print("0. cenário: um catálogo simples em RASCUNHO, com abertura e um cartão")
_st, cat = chamar("POST", "/catalogos", {"nome": f"Simples {MARCA}", "origem": "PRODUTOS"}, token)
ID = cat["id"]
_st, g = chamar("POST", f"/catalogos/{ID}/categorias", {"nome": "Doces"}, token)
_st, ia = chamar("POST", f"/catalogos/categorias/{g['id']}/itens", {"id_produto": produto("PREV BOLO", 10)}, token)
_st, ib = chamar("POST", f"/catalogos/categorias/{g['id']}/itens", {"id_produto": produto("PREV TORTA", 20)}, token)
st, ab = chamar("POST", f"/catalogos/{ID}/cartoes", {"titulo": "Bem-vindo", "texto": "Feito em casa."}, token)
checar("a abertura (cartão sem seção) se cria no catálogo simples", st == 201, (st, ab))
st, ct = chamar("POST", f"/catalogos/{ID}/cartoes", {"id_categoria": g["id"], "antes_do_item": ib["id"],
                                                      "titulo": "Da semana"}, token)
_st, vazio = chamar("POST", f"/catalogos/{ID}/cartoes", {"id_categoria": g["id"]}, token)
chamar("PUT", f"/catalogos/itens/{ia['id']}/marcas", {"destaque": True}, token)
chamar("PUT", f"/catalogos/itens/{ib['id']}/marcas", {"esgotado": True}, token)

print("\n1. a pré-visualização, em rascunho")
st, r = chamar("GET", f"/publico/{U}/catalogos/{ID}")
checar("o público não vê o rascunho (404)", st == 404, st)
st, pv = chamar("GET", f"/catalogos/{ID}/previa-site", token=token)
checar("a prévia abre o rascunho, com a montagem do site", st == 200 and pv.get("previa") is True
       and pv["categorias"][0]["nome"] == "Doces", (st, pv))
checar("e a seção leva o id (é por ele que o cartão se encaixa)", pv["categorias"][0].get("id") == g["id"])
itens = {i["id"]: i for i in pv["categorias"][0]["itens"]}
checar("destaque e esgotado chegam ao site",
       itens[ia["id"]]["destaque"] is True and itens[ib["id"]]["esgotado"] is True, itens)
cartoes = {c["id"]: c for c in pv.get("cartoes") or []}
checar("a abertura vem sem seção, com título e texto",
       ab["id"] in cartoes and cartoes[ab["id"]]["id_categoria"] is None
       and cartoes[ab["id"]]["texto"] == "Feito em casa.", pv.get("cartoes"))
checar("o cartão da seção vem antes do prato dele", cartoes.get(ct["id"], {}).get("antes_do_item") == ib["id"])
checar("cartão vazio não vai ao site", vazio["id"] not in cartoes)
checar("e nada de vídeo no cartão do site", all("video" not in c and "midia" not in c for c in cartoes.values()))
checar("nem id de produto em lugar nenhum", "id_produto" not in json.dumps(pv))
st, r = chamar("GET", f"/catalogos/{ID}/previa-site", token=cozinha)
checar("sem permissão de catálogos, a prévia é recusada (403)", st == 403, st)

print("\n2. o pedido de TESTE: confere e não grava")
st, r = chamar("POST", f"/catalogos/{ID}/pedido-teste",
               {"itens": [{"id_item": ia["id"], "quantidade": 3}]}, token)
with get_cursor() as cur:
    cur.execute("SELECT count(*) AS n FROM pedidos WHERE id_catalogo = %s", (ID,))
    n = cur.fetchone()["n"]
checar("responde o total que daria (3 × 10 = 30), dizendo que é teste",
       st == 200 and r.get("teste") is True and r.get("total") == 30.0, (st, r))
checar("e nenhum pedido foi gravado", n == 0, n)
st, r = chamar("POST", f"/catalogos/{ID}/pedido-teste", {"itens": [{"id_item": ib["id"], "quantidade": 1}]}, token)
checar("o esgotado é recusado no teste (409), como no envio", st == 409 and "esgotou" in r["detail"], (st, r))

print("\n3. no ar: o site mostra o mesmo, e o envio recusa o esgotado")
chamar("PUT", f"/catalogos/{ID}", {"situacao": "ATIVO"}, token)
chamar("PUT", f"/pedidos/config/{ID}", {
    "aceita": True, "retirada": True, "entrega": False, "taxa_entrega": 0, "pedido_minimo": 0,
    "antecedencia_min": 0, "antecedencia_max_dias": 7, "pagamentos": ["RETIRADA"], "texto_pagamento": None}, token)
st, pub = chamar("GET", f"/publico/{U}/catalogos/{ID}")
checar("o cardápio público traz a abertura e os cartões",
       st == 200 and {c["id"] for c in pub.get("cartoes") or []} == {ab["id"], ct["id"]}, (st, pub.get("cartoes")))
FONE = f"4799{random.randint(1000000, 9999999)}"
chamar("POST", f"/publico/{U}/cliente", {"telefone": FONE, "nome": f"Previa {MARCA}", "genero": "FEMININO",
                                         "cidade": "Blumenau", "nascimento": "1990-05-10", "aceite_termo": True})
st, r = chamar("POST", f"/publico/{U}/catalogos/{ID}/pedido", {
    "telefone": FONE, "chave": uuid.uuid4().hex, "modo": "RETIRADA", "forma_pagamento": "RETIRADA",
    "itens": [{"id_item": ib["id"], "quantidade": 1}]})
checar("o pedido do site recusa o prato esgotado (409)", st == 409 and "esgotou" in r["detail"], (st, r))

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
