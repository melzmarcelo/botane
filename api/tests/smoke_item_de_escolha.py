"""Item de escolha no catálogo e adicionais que repetem (migração 142).

🔑 **Pedido do dono (29/10/2026)**, estudo em `docs/item-de-escolha-estudo.md`:
"Chocolate Quente → Preto ou Branco" e "Monte sua cesta → Pequena/Média/Grande, de um mínimo
a um máximo de itens, somando o valor". Decisões: item repete, embalagem + soma (com
"incluso" a R$ 0), no site e na mesa.

    python tests/smoke_item_de_escolha.py        (API de pé na 9200)
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

from comum import gravar_cardapio, preservar_cardapio_vivo, preservar_reserva  # noqa: E402
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
init_pool()
_st, eu = chamar("GET", "/auth/me", token=token)
U = (eu.get("unidades") or [{}])[0].get("id") or 1

# 🔑 Suíte devolve o que encontrou: reserva, pedidos e o Cardápio Vivo da loja.
preservar_reserva(U)
preservar_cardapio_vivo(U)


def _devolver():
    with get_cursor() as cur:
        cur.execute("DELETE FROM catalogos WHERE nome LIKE %s", (f"%{MARCA}%",))
        cur.execute("DELETE FROM reserva_clientes WHERE nome LIKE %s", (f"%{MARCA}%",))


atexit.register(_devolver)
_st, par = chamar("GET", f"/unidades/{U}/parametros", token=token)
chamar("PUT", f"/unidades/{U}/parametros", {**par, "reservas_ligado": True}, token)
with get_cursor() as cur:
    # A casa aberta o dia todo: o que se testa é o pedido, não o relógio.
    cur.execute("DELETE FROM reserva_bloqueios WHERE id_unidade = %s", (U,))
    cur.execute("DELETE FROM reserva_dias_especiais WHERE id_unidade = %s", (U,))
    for d in range(1, 8):
        cur.execute(
            """INSERT INTO reserva_horarios (id_unidade, dia_semana, aberto, abre, fecha, ultima_reserva)
               VALUES (%s, %s, true, '00:00', '23:59', '23:00')
               ON CONFLICT (id_unidade, dia_semana) DO UPDATE
                  SET aberto = true, abre = '00:00', fecha = '23:59', ultima_reserva = '23:00'""",
            (U, d))


def produto(nome, preco=None, pdv=True):
    _st, p = chamar("POST", "/produtos", {"nome": f"{nome} {MARCA}", "tipo": "INSUMO",
                                          "um_estoque": "UN", "controla_estoque": False}, token)
    _st, atual = chamar("GET", f"/produtos/{p['id']}", token=token)
    chamar("PUT", f"/produtos/{p['id']}", {**atual, "integrado_pdv": pdv,
                                            **({"preco_venda": preco} if preco is not None else {})},
           token)
    return p["id"]


print("0. cenário: chocolates, cestas e os itens da cesta")
PRETO, BRANCO = produto("CHOC QUENTE PRETO", 14), produto("CHOC QUENTE BRANCO", 16)
FORA_PDV = produto("CHOC FORA DO PDV", 9, pdv=False)
CP, CM = produto("CESTA PEQUENA", 20), produto("CESTA MEDIA", 30)
GELEIA, PAO, LACO = produto("CESTA GELEIA", 12), produto("CESTA PAO", 8), produto("CESTA LACO", 5)
_st, cat = chamar("POST", "/catalogos", {"nome": f"Escolha {MARCA}", "origem": "PRODUTOS",
                                         "situacao": "ATIVO"}, token)
ID_CAT = cat["id"]
_st, g = chamar("POST", f"/catalogos/{ID_CAT}/categorias", {"nome": "Bebidas"}, token)
_st, g2 = chamar("POST", f"/catalogos/{ID_CAT}/categorias", {"nome": "Presentes"}, token)

print("\n1. o cadastro do item de escolha")
st, r = chamar("POST", f"/catalogos/categorias/{g['id']}/escolhas",
               {"nome": "Chocolate Quente", "opcoes": [{"id_produto": PRETO}]}, token)
checar("com uma opção só é recusado (422)", st == 422, (st, r))
st, r = chamar("POST", f"/catalogos/categorias/{g['id']}/escolhas",
               {"nome": "Chocolate Quente", "opcoes": [{"id_produto": PRETO}, {"id_produto": FORA_PDV}]},
               token)
checar("opção que não vai ao PDV é recusada, dizendo qual", st == 409 and "PDV" in r["detail"], (st, r))
st, r = chamar("POST", f"/catalogos/categorias/{g['id']}/escolhas",
               {"nome": "Chocolate Quente", "opcoes": [{"id_produto": PRETO}, {"id_produto": PRETO}]},
               token)
checar("o mesmo produto duas vezes é recusado", st == 409, (st, r))
st, choc = chamar("POST", f"/catalogos/categorias/{g['id']}/escolhas",
                  {"nome": "Chocolate Quente", "descricao": "Cremoso, feito na hora",
                   "opcoes": [{"id_produto": PRETO, "rotulo": "Preto"},
                              {"id_produto": BRANCO, "rotulo": "Branco"}]}, token)
checar("o item de escolha nasce (201)", st == 201 and choc.get("id"), (st, choc))
st, cesta = chamar("POST", f"/catalogos/categorias/{g2['id']}/escolhas",
                   {"nome": "Monte sua cesta", "opcoes": [{"id_produto": CP, "rotulo": "Pequena"},
                                                          {"id_produto": CM, "rotulo": "Média"}]}, token)
checar("a cesta também", st == 201, (st, cesta))
_st, comum = chamar("POST", f"/catalogos/categorias/{g['id']}/itens", {"id_produto": GELEIA}, token)

_st, ct = chamar("GET", f"/catalogos/{ID_CAT}/conteudo", token=token)
it = next(i for c in ct["categorias"] for i in c["itens"] if i["id"] == choc["id"])
checar("o cadastro mostra o tipo, o nome e as opções na ordem",
       it["tipo"] == "ESCOLHA" and it["produto"] == "Chocolate Quente"
       and [o["nome"] for o in it["escolhas"]] == ["Preto", "Branco"], it)
checar("o preço da linha é o menor das opções (a partir de 14)", float(it["preco"]) == 14, it["preco"])
checar("e o prato comum continua tipo PRODUTO, sem 'escolhas'",
       any(i["id"] == comum["id"] and i["tipo"] == "PRODUTO" and "escolhas" not in i
           for c in ct["categorias"] for i in c["itens"]))

st, r = chamar("PUT", f"/catalogos/itens/{choc['id']}/escolha",
               {"nome": "Chocolate Quente", "descricao": "Cremoso",
                "opcoes": [{"id_produto": BRANCO, "rotulo": "Branco"},
                           {"id_produto": PRETO, "rotulo": "Preto"}]}, token)
_st, ct = chamar("GET", f"/catalogos/{ID_CAT}/conteudo", token=token)
it = next(i for c in ct["categorias"] for i in c["itens"] if i["id"] == choc["id"])
checar("editar regrava a lista inteira, na ordem nova",
       st == 200 and [o["nome"] for o in it["escolhas"]] == ["Branco", "Preto"], (st, it))
st, r = chamar("PUT", f"/catalogos/itens/{comum['id']}/escolha",
               {"nome": "x", "opcoes": [{"id_produto": PRETO}, {"id_produto": BRANCO}]}, token)
checar("o prato comum não vira item de escolha pela rota (409)", st == 409, (st, r))
st, r = chamar("PUT", f"/catalogos/itens/{choc['id']}/marcas", {"destaque": True}, token)
checar("destaque vale também no item de escolha", st == 200 and r.get("destaque") is True, (st, r))
st, r = chamar("PUT", f"/catalogos/itens/{choc['id']}/marcas", {"destaque": False}, token)
with get_cursor() as cur:
    cur.execute("SAVEPOINT s")
    try:
        cur.execute("""INSERT INTO catalogo_itens (id_categoria, tipo, nome, id_produto)
                       VALUES (%s, 'ESCOLHA', 'x', %s)""", (g["id"], PRETO))
        checar("o banco recusa item de escolha com produto", False)
    except Exception:
        cur.execute("ROLLBACK TO SAVEPOINT s")
        checar("o banco recusa item de escolha com produto", True)

print("\n2. os adicionais da cesta: repetir e incluso")
st, r = chamar("PUT", f"/produtos/{CM}/adicionais", [
    {"nome": "Itens da cesta", "minimo": 3, "maximo": 4, "permite_repetir": True,
     "opcoes": [{"nome": "Geleia", "id_produto_ref": GELEIA}, {"nome": "Pão", "id_produto_ref": PAO}]},
    {"nome": "Laço", "minimo": 0, "maximo": 1,
     "opcoes": [{"nome": "Laço", "id_produto_ref": LACO, "incluso": True}]}], token)
checar("grava o grupo que repete e a opção inclusa", st == 200, (st, r))
gr = (r or {}).get("adicionais") or []
checar("e devolve as duas marcas",
       gr and gr[0]["permite_repetir"] is True and gr[1]["opcoes"][0]["incluso"] is True, gr)
st, r = chamar("PUT", f"/produtos/{CP}/adicionais", [
    {"nome": "Itens", "minimo": 3, "maximo": 3,
     "opcoes": [{"nome": "Geleia", "id_produto_ref": GELEIA}, {"nome": "Pão", "id_produto_ref": PAO}]}],
    token)
checar("sem repetir, mínimo maior que as opções continua recusado", st == 422, (st, r))
chamar("PUT", f"/produtos/{CP}/adicionais", [
    {"nome": "Itens", "minimo": 2, "maximo": 3, "permite_repetir": True,
     "opcoes": [{"nome": "Geleia", "id_produto_ref": GELEIA}, {"nome": "Pão", "id_produto_ref": PAO}]}],
    token)
_st, ad = chamar("GET", f"/produtos/{CM}/cardapio", token=token)
OP = {o["nome"]: o["id"] for gg in ad["adicionais"] for o in gg["opcoes"]}

print("\n3. o cardápio do site")
st, r = chamar("PUT", f"/pedidos/config/{ID_CAT}", {
    "aceita": True, "retirada": True, "entrega": False, "taxa_entrega": 0, "pedido_minimo": 0,
    "antecedencia_min": 0, "antecedencia_max_dias": 7, "pagamentos": ["RETIRADA"],
    "texto_pagamento": "Na retirada."}, token)
st, site = chamar("GET", f"/publico/{U}/catalogos/{ID_CAT}")
todos = {i["id"]: i for c in site.get("categorias", []) for i in c["itens"]}
sc = todos.get(choc["id"]) or {}
checar("o item de escolha aparece com nome, descrição e as opções",
       sc.get("nome") == "Chocolate Quente" and sc.get("descricao") == "Cremoso"
       and [o["nome"] for o in sc.get("escolhas") or []] == ["Branco", "Preto"], sc)
checar("com o preço de cada opção e 'a partir de' no item",
       [o["preco"] for o in sc["escolhas"]] == [16.0, 14.0] and sc["preco"] == 14.0, sc)
checar("a opção sai com o id DELA, nunca o do produto",
       all("id_produto" not in o and o["id"] not in (PRETO, BRANCO) for o in sc["escolhas"]), sc["escolhas"])
scesta = todos.get(cesta["id"]) or {}
media = next((o for o in scesta.get("escolhas") or [] if o["nome"] == "Média"), {})
# 🔑 O pedido manda o id da OPÇÃO; o servidor acha o produto.
OPC = {o["nome"]: o["id"] for i in (sc, scesta) for o in i.get("escolhas") or []}
checar("a opção da cesta traz os adicionais dela, com 'repete' e o incluso a R$ 0",
       media.get("adicionais") and media["adicionais"][0]["permite_repetir"] is True
       and media["adicionais"][1]["opcoes"][0]["preco"] == 0, media)
checar("o prato comum vem com escolhas nulo", todos.get(comum["id"], {}).get("escolhas", "x") is None)

print("\n4. o pedido pelo site")
FONE = f"4799{random.randint(1000000, 9999999)}"
chamar("POST", f"/publico/{U}/cliente", {"telefone": FONE, "nome": f"Cesta {MARCA}",
                                         "genero": "FEMININO", "cidade": "Blumenau",
                                         "nascimento": "1990-05-10", "aceite_termo": True})


def pedir_site(itens_):
    return chamar("POST", f"/publico/{U}/catalogos/{ID_CAT}/pedido", {
        "telefone": FONE, "chave": uuid.uuid4().hex, "modo": "RETIRADA",
        "forma_pagamento": "RETIRADA", "itens": itens_})


st, r = pedir_site([{"id_item": choc["id"], "quantidade": 1}])
checar("item de escolha sem escolha é recusado (422)", st == 422 and "escolha" in r["detail"], (st, r))
st, r = pedir_site([{"id_item": choc["id"], "quantidade": 1, "escolha": OPC["Média"]}])
checar("escolha que não é opção do item é recusada (409)", st == 409, (st, r))
st, r = pedir_site([{"id_item": comum["id"], "quantidade": 1, "escolha": OPC["Preto"]}])
checar("prato comum com escolha é recusado", st == 409, (st, r))
st, r = pedir_site([{"id_item": cesta["id"], "quantidade": 1, "escolha": OPC["Média"],
                     "adicionais": [OP["Geleia"], OP["Pão"]]}])
checar("cesta abaixo do mínimo (2 de 3) é recusada, dizendo o grupo",
       st == 422 and "Itens da cesta" in r["detail"], (st, r))
st, r = pedir_site([{"id_item": cesta["id"], "quantidade": 1, "escolha": OPC["Média"],
                     "adicionais": [OP["Geleia"]] * 3 + [OP["Pão"]] * 2}])
checar("acima do máximo (5 de 4) também", st == 422, (st, r))
st, r = pedir_site([{"id_item": choc["id"], "quantidade": 1, "escolha": BRANCO}])
checar("mandar o id do PRODUTO no lugar do da opção é recusado", st == 409, (st, r))
st, p = pedir_site([{"id_item": choc["id"], "quantidade": 2, "escolha": OPC["Branco"]},
                    {"id_item": cesta["id"], "quantidade": 1, "escolha": OPC["Média"],
                     "adicionais": [OP["Geleia"], OP["Pão"], OP["Geleia"], OP["Laço"]]}])
checar("o pedido nasce (201)", st == 201, (st, p))
itens_p = (p or {}).get("itens") or []
checar("a linha leva o PRODUTO escolhido, com o nome do item e da opção",
       itens_p and itens_p[0]["nome"] == "Chocolate Quente · Branco", itens_p[:1])
checar("cesta = 30 + 2 geleias (24) + pão (8) + laço incluso (0) = 62; total 2×16 + 62 = 94",
       p.get("total") == 94.0, p.get("total"))
ad_cesta = itens_p[1].get("adicionais") if len(itens_p) > 1 else None
checar("os adicionais ficam congelados com a quantidade, na ordem do cardápio",
       [(a["nome"], a["quantidade"]) for a in ad_cesta or []] == [("Geleia", 2), ("Pão", 1), ("Laço", 1)],
       ad_cesta)
with get_cursor() as cur:
    cur.execute("""SELECT pi.id_produto FROM pedido_itens pi JOIN pedidos pe ON pe.id = pi.id_pedido
                    WHERE pe.chave IS NOT NULL AND pe.numero = %s AND pe.id_unidade = %s
                    ORDER BY pi.ordem""", (p.get("numero"), U))
    gravados = [r["id_produto"] for r in cur.fetchall()]
checar("no banco, a linha aponta para o produto escolhido (é ele que vai ao PDV)",
       gravados == [BRANCO, CM], gravados)

print("\n5. opção que sai de linha some do cardápio, e o item sem opção some junto")
_st, atual = chamar("GET", f"/produtos/{PRETO}", token=token)
chamar("PUT", f"/produtos/{PRETO}", {**atual, "ativo": False}, token)
_st, site = chamar("GET", f"/publico/{U}/catalogos/{ID_CAT}")
sc = next((i for c in site["categorias"] for i in c["itens"] if i["id"] == choc["id"]), {})
checar("a opção inativa não é oferecida", [o["nome"] for o in sc.get("escolhas") or []] == ["Branco"], sc)
st, r = pedir_site([{"id_item": choc["id"], "quantidade": 1, "escolha": OPC["Preto"]}])
checar("e não pode ser pedida", st == 409, (st, r))
_st, ct = chamar("GET", f"/catalogos/{ID_CAT}/conteudo", token=token)
it = next(i for c in ct["categorias"] for i in c["itens"] if i["id"] == choc["id"])
checar("o cadastro ainda a mostra, marcada inativa",
       any(o["id_produto"] == PRETO and o["ativo"] is False for o in it["escolhas"]), it["escolhas"])
st, r = chamar("PUT", f"/catalogos/itens/{choc['id']}/escolha",
               {"nome": "Chocolate Quente", "opcoes": [{"id_produto": BRANCO, "rotulo": "Branco"},
                                                       {"id_produto": PRETO, "rotulo": "Preto"}]}, token)
checar("e a edição do resto não trava por causa dela", st == 200, (st, r))
_st, atual = chamar("GET", f"/produtos/{BRANCO}", token=token)
chamar("PUT", f"/produtos/{BRANCO}", {**atual, "ativo": False}, token)
_st, site = chamar("GET", f"/publico/{U}/catalogos/{ID_CAT}")
checar("sem nenhuma opção ativa, o item some do site",
       choc["id"] not in [i["id"] for c in site["categorias"] for i in c["itens"]])
for pid in (PRETO, BRANCO):
    _st, atual = chamar("GET", f"/produtos/{pid}", token=token)
    chamar("PUT", f"/produtos/{pid}", {**atual, "ativo": True}, token)

print("\n6. a mesa (Cardápio Vivo)")
_st, salao = chamar("POST", "/reservas/saloes", {"nome": f"Escolha {MARCA}"}, token)
_st, m1 = chamar("POST", "/reservas/mesas", {"id_salao": salao["id"], "nome": "E1", "lugares": 4}, token)
_st, ac = chamar("GET", "/cardapio-vivo/mesas", token=token)
T1 = next(m["link"].rsplit("/", 1)[1] for m in ac["mesas"] if m["id"] == m1["id"])
gravar_cardapio(chamar, token, {"id_catalogo": ID_CAT, "modo": "PEDIDO", "exige_confirmacao": True,
                                "chamar_garcom": False, "fonte": "NEWSREADER", "retencao_meses": 13})
_st, f = chamar("GET", f"/publico/cardapio/mesa/{T1}")
fi = next((i for i in f.get("itens", []) if i["id"] == choc["id"]), {})
fcesta = next((i for i in f.get("itens", []) if i["id"] == cesta["id"]), {})
OPF = {o["nome"]: o["id"] for i in (fi, fcesta) for o in i.get("escolhas") or []}
checar("o feed traz o item de escolha com as opções", [o["nome"] for o in fi.get("escolhas") or []]
       == ["Branco", "Preto"] and fi.get("preco") == 14.0, fi)
fc = next((i for i in f.get("itens", []) if i["id"] == comum["id"]), {})
checar("e o prato comum com escolhas nulo", fc.get("escolhas", "x") is None, fc)
S = str(uuid.uuid4())
st, r = chamar("POST", f"/publico/cardapio/mesa/{T1}/pedido", {
    "sessao": S, "chave": uuid.uuid4().hex,
    "itens": [{"item": cesta["id"], "quantidade": 1, "escolha": OPF["Pequena"], "adicionais": []}]})
checar("na mesa, a cesta pequena sem itens é recusada", st == 422, (st, r))
_st, adp = chamar("GET", f"/produtos/{CP}/cardapio", token=token)
OPP = {o["nome"]: o["id"] for gg in adp["adicionais"] for o in gg["opcoes"]}
st, pm = chamar("POST", f"/publico/cardapio/mesa/{T1}/pedido", {
    "sessao": S, "chave": uuid.uuid4().hex,
    "itens": [{"item": cesta["id"], "quantidade": 1, "escolha": OPF["Pequena"],
               "adicionais": [OPP["Pão"], OPP["Pão"], OPP["Pão"]]},
              {"item": choc["id"], "quantidade": 1, "escolha": OPF["Preto"]}]})
checar("na mesa, 3 pães na pequena: 20 + 24 = 44; + Preto 14 = 58",
       st == 201 and pm.get("total") == 58.0, (st, pm))
chamar("DELETE", f"/reservas/mesas/{m1['id']}", token=token)
with get_cursor() as cur:
    cur.execute("DELETE FROM mesas WHERE id = %s", (m1["id"],))
chamar("DELETE", f"/reservas/saloes/{salao['id']}", token=token)

print("\n7. tirar o item de escolha do cardápio leva as opções junto")
st, r = chamar("DELETE", f"/catalogos/itens/{choc['id']}", token=token)
with get_cursor() as cur:
    cur.execute("SELECT count(*) AS n FROM catalogo_item_escolhas WHERE id_item = %s", (choc["id"],))
    n = cur.fetchone()["n"]
checar("sai, e as opções somem com ele", st == 200 and n == 0, (st, r, n))

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
