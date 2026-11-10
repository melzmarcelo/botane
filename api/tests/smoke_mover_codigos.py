"""Teste de fumaça de "mover códigos para outro produto".

🔑 O caso que motivou (pedido do dono, 10/11/2026): CATCHUP e KETCHUP eram o
mesmo produto, a fusão recusou porque os DOIS tinham movimento no razão, e os
códigos do CATCHUP ficaram presos nele. Aqui se cobra:

1. a fusão continua recusando (dois com história) — e mover é o caminho
2. a prévia lista TODOS os códigos: principais (coluna), vinculados e o código no
   fornecedor; sugere a conversão pela última nota só com a mesma unidade
3. sem conversão, o código que decide quantidade NÃO se move
4. movido: a cascata da nota acha o destino por cada código, com o fator dito
   (o caso do bag de 2 kg contra o galão de 3,8 kg do destino)
5. a coluna da origem é zerada; o principal do destino não muda
6. item de nota ainda não lançada muda de dono e a nota é recalculada
7. destino inativo e "para si mesmo" são recusados

    python tests/smoke_mover_codigos.py      (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
sys.path.insert(0, ".")
from comum import garantir_locais  # noqa: E402
from database import get_cursor  # noqa: E402
from services.omie.importador import _fator_do_item, conciliar_item  # noqa: E402

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
        with urllib.request.urlopen(req, dados, timeout=120) as r:
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


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
assert st == 200, r
token = r["access_token"]
marca = str(time.time_ns() // 100)[-7:]
locais = garantir_locais(chamar, token, 1)
id_local = locais[0]["id"]

print("1. dois cadastros do mesmo produto, os dois com história")
st, r = chamar("POST", "/fornecedores", {"nome": f"SDB Teste {marca}"}, token=token)
checar("fornecedor criado", st in (200, 201), (st, r))
id_forn = r.get("id")

st, r = chamar("POST", "/produtos", {
    "codigo": f"CAT-{marca}", "nome": f"CATCHUP {marca}", "tipo": "INSUMO",
    "um_estoque": "KG", "um_compra": "UN", "fator_compra": 1, "controla_estoque": True,
    "status": "ATIVO", "codigo_omie": f"61{marca}", "codigo_barras": f"789{marca}1",
}, token=token)
checar("a origem (CATCHUP)", st == 201, (st, r))
origem = r.get("id")
st, r = chamar("POST", "/produtos", {
    "codigo": f"KET-{marca}", "nome": f"KETCHUP {marca}", "tipo": "INSUMO",
    "um_estoque": "KG", "um_compra": "CX", "fator_compra": 3.8, "controla_estoque": True,
    "status": "ATIVO", "codigo_omie": f"62{marca}", "codigo_barras": f"789{marca}2",
}, token=token)
checar("o destino (KETCHUP, galão de 3,8 kg)", st == 201, (st, r))
destino = r.get("id")

for pid in (origem, destino):
    st, r = chamar("POST", "/estoque/entradas", {
        "id_produto": pid, "quantidade": 1, "custo_unitario": 10, "id_local": id_local,
        "observacao": "smoke mover códigos"}, token=token)
    checar(f"movimento no razão do {pid}", st == 201, (st, r))

st, r = chamar("GET", f"/produtos/{destino}/vincular/previa?id_sai={origem}", token=token)
checar("a fusão recusa: os dois têm história", r.get("pode") is False, r.get("impedimentos"))

# Um apelido (o bag de 2 kg, fator 2 confirmado), o código no fornecedor e duas
# notas: uma LANÇADA (de onde vem a sugestão) e uma ABERTA (que deve mudar de dono).
with get_cursor() as cur:
    cur.execute(
        """INSERT INTO codigos_externos (sistema, codigo, id_produto, descricao_externa,
                                         origem_vinculo, fator, fator_confirmado)
           VALUES ('OMIE_PRODUTO', %s, %s, 'CATCHUP BAG 2KG', 'FUSAO', 2, true)""",
        (f"63{marca}", origem))
    cur.execute(
        """INSERT INTO produto_fornecedor (id_produto, id_fornecedor, codigo_no_fornecedor)
           VALUES (%s, %s, %s)""", (origem, id_forn, f"F{marca}"))
    cur.execute("SELECT id FROM unidades WHERE ativo ORDER BY matriz DESC, id LIMIT 1")
    id_unidade = cur.fetchone()["id"]
    cur.execute(
        """INSERT INTO notas_entrada (id_unidade, numero, status, origem, id_fornecedor,
                                      data_emissao)
           VALUES (%s, %s, 'LANCADA', 'OMIE', %s, current_date - 5) RETURNING id""",
        (id_unidade, f"MV1{marca}", id_forn))
    nota_lancada = cur.fetchone()["id"]
    # 1 UN entrou como 1,5 KG: é isso que a sugestão tem de repetir.
    cur.execute(
        """INSERT INTO nota_itens (id_nota, seq, descricao_fornecedor, quantidade, um_nota,
                                   codigo_omie, codigo_fornecedor, id_produto,
                                   quantidade_convertida)
           VALUES (%s, 1, 'CATCHUP', 4, 'UN', %s, %s, %s, 6)""",
        (nota_lancada, f"61{marca}", f"F{marca}", origem))
    cur.execute(
        """INSERT INTO notas_entrada (id_unidade, numero, status, origem, id_fornecedor)
           VALUES (%s, %s, 'CONCILIADA', 'OMIE', %s) RETURNING id""",
        (id_unidade, f"MV2{marca}", id_forn))
    nota_aberta = cur.fetchone()["id"]
    cur.execute(
        """INSERT INTO nota_itens (id_nota, seq, descricao_fornecedor, quantidade, um_nota,
                                   valor_unitario, valor_total, codigo_omie, id_produto)
           VALUES (%s, 1, 'CATCHUP BAG', 3, 'UN', 20, 60, %s, %s) RETURNING id""",
        (nota_aberta, f"63{marca}", origem))
    item_aberto = cur.fetchone()["id"]

print("\n2. a prévia")
st, pv = chamar("GET", f"/produtos/{origem}/codigos/mudanca/previa?id_destino={destino}",
                token=token)
checar("responde e pode", st == 200 and pv.get("pode") is True, (st, pv))
por = {(c["sistema"], c["codigo"]): c for c in pv.get("codigos", [])}
checar("lista o código do Omie da COLUNA", por.get(("OMIE_PRODUTO", f"61{marca}"), {})
       .get("onde") == "principal", list(por))
checar("lista o EAN da coluna", ("EAN", f"789{marca}1") in por, list(por))
checar("lista o apelido (bag 2 kg)", por.get(("OMIE_PRODUTO", f"63{marca}"), {})
       .get("onde") == "vinculado", list(por))
checar("lista o código no fornecedor", por.get(("OMIE", f"F{marca}"), {})
       .get("onde") == "fornecedor", list(por))
checar("o código do Omie pede conversão; o EAN não",
       por[("OMIE_PRODUTO", f"61{marca}")]["pede_fator"]
       and not por[("EAN", f"789{marca}1")]["pede_fator"])
checar("a sugestão do principal é a da última nota (6/4 = 1,5)",
       por[("OMIE_PRODUTO", f"61{marca}")]["fator_sugerido"] == 1.5,
       por[("OMIE_PRODUTO", f"61{marca}")])
checar("a do apelido é a conversão já confirmada (2)",
       por[("OMIE_PRODUTO", f"63{marca}")]["fator_sugerido"] == 2,
       por[("OMIE_PRODUTO", f"63{marca}")])
checar("conta o item de nota aberta", pv.get("itens_de_nota_abertos") == 1, pv)

print("\n3. recusas")
st, r = chamar("POST", f"/produtos/{origem}/codigos/mover", {
    "id_destino": destino,
    "codigos": [{"sistema": "OMIE_PRODUTO", "codigo": f"61{marca}"}]}, token=token)
checar("sem conversão, o código do Omie não se move (400)", st == 400, (st, r))
st, r = chamar("POST", f"/produtos/{origem}/codigos/mover", {
    "id_destino": origem,
    "codigos": [{"sistema": "EAN", "codigo": f"789{marca}1"}]}, token=token)
checar("para si mesmo, não (400)", st == 400, (st, r))
st, r = chamar("POST", f"/produtos/{destino}/codigos/mover", {
    "id_destino": origem,
    "codigos": [{"sistema": "EAN", "codigo": f"789{marca}1"}]}, token=token)
checar("código que não é da origem (404)", st == 404, (st, r))

print("\n4. mover tudo")
st, r = chamar("POST", f"/produtos/{origem}/codigos/mover", {
    "id_destino": destino,
    "codigos": [
        {"sistema": "OMIE_PRODUTO", "codigo": f"61{marca}", "fator": 1.5},
        {"sistema": "EAN", "codigo": f"789{marca}1"},
        {"sistema": "OMIE_PRODUTO", "codigo": f"63{marca}", "fator": 2},
        {"sistema": "OMIE", "codigo": f"F{marca}", "id_fornecedor": id_forn, "fator": 1.5},
    ]}, token=token)
checar("move", st == 200 and len(r.get("movidos", [])) == 4, (st, r))
checar("e leva o item da nota aberta junto", r.get("itens_de_nota") == 1, r)

with get_cursor() as cur:
    checar("a nota acha o destino pelo código do Omie da antiga coluna",
           conciliar_item(cur, {"codigo_omie": f"61{marca}"}, None)[0] == destino)
    checar("pelo apelido do bag",
           conciliar_item(cur, {"codigo_omie": f"63{marca}"}, None)[0] == destino)
    checar("pelo EAN",
           conciliar_item(cur, {"codigo_barras": f"789{marca}1"}, None)[0] == destino)
    checar("pelo código no fornecedor (primeiro degrau)",
           conciliar_item(cur, {"codigo_fornecedor": f"F{marca}"}, id_forn)[0] == destino)
    # 🔑 O coração: 1 bag NÃO entra como 3,8 kg (o fator de compra do destino).
    f_bag = _fator_do_item(cur, destino, None, None, "UN", f"63{marca}")
    checar("1 bag entra como 2 kg, não 3,8", float(f_bag) == 2, f_bag)
    f_col = _fator_do_item(cur, destino, None, None, "UN", f"61{marca}")
    checar("o código da antiga coluna entra com o fator dito (1,5)", float(f_col) == 1.5, f_col)
    cur.execute("SELECT codigo_omie, codigo_barras, observacao FROM produtos WHERE id = %s",
                (origem,))
    o = cur.fetchone()
    checar("a coluna da origem foi zerada", not o["codigo_omie"] and not o["codigo_barras"], o)
    checar("e a origem diz para onde foram", "movidos para" in (o["observacao"] or ""), o)
    cur.execute("SELECT codigo_omie FROM produtos WHERE id = %s", (destino,))
    checar("o principal do destino não mudou",
           cur.fetchone()["codigo_omie"] == f"62{marca}")
    cur.execute("SELECT id_produto, quantidade_convertida FROM nota_itens WHERE id = %s",
                (item_aberto,))
    it = cur.fetchone()
    checar("o item da nota aberta é do destino", it["id_produto"] == destino, it)
    checar("e foi recalculado: 3 bags = 6 kg", float(it["quantidade_convertida"] or 0) == 6, it)
    cur.execute("SELECT id_produto FROM nota_itens WHERE id_nota = %s", (nota_lancada,))
    checar("a nota LANÇADA não muda", cur.fetchone()["id_produto"] == origem)
    cur.execute("""SELECT count(*) AS n FROM codigos_externos
                    WHERE id_produto = %s AND origem_vinculo = 'MOVIDO'""", (destino,))
    checar("as linhas no destino dizem 'MOVIDO'", cur.fetchone()["n"] == 4)

print("\n5. destino inativo")
st, r = chamar("DELETE", f"/produtos/{origem}", token=token)
st, pv = chamar("GET", f"/produtos/{destino}/codigos/mudanca/previa?id_destino={origem}",
                token=token)
checar("a prévia diz que não pode", pv.get("pode") is False and pv.get("impedimentos"), pv)

print(f"\n{ok} ok, {len(falhas)} falha(s)")
if falhas:
    for f in falhas:
        print("  -", f)
    sys.exit(1)
