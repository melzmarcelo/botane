"""Nota com produto INATIVO: achar, avisar e dar entrada só com confirmação.

🔑 **Pedido do dono (06/11/2026):** *"quando vem um produto desativado em alguma nota ele
não encontra … o usuário não entende por que o produto não foi criado e a nota está
faltando o item … caso quiser, pode dar entrada mesmo inativado"*.

Confere: a linha pendente aponta o inativo que casaria (pelo EAN e pelo código no
fornecedor), o fundido não é oferecido, lançar sem confirmar recusa nomeando o produto,
confirmado entra no razão e o cadastro continua inativo.

    python tests/smoke_nota_produto_inativo.py      (API de pé; BOTANE_API muda a porta)
"""

import json
import os
import random
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from database import get_cursor, init_pool  # noqa: E402

BASE = os.environ.get("BOTANE_API", "http://127.0.0.1:9200")
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []
marca = uuid.uuid4().hex[:6].upper()
produtos: list[int] = []
notas: list[int] = []
pessoas: list[int] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + urllib.parse.quote(caminho, safe="/?=&"), method=metodo)
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


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


def ean13() -> str:
    corpo = "29" + "".join(random.choice("0123456789") for _ in range(10))
    soma = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(corpo))
    return corpo + str((10 - soma % 10) % 10)


def novo_produto(nome, **extra):
    _st, r = chamar("POST", "/produtos", {
        "nome": f"{nome} {marca}", "tipo": "INSUMO", "um_estoque": "UN",
        "status": "ATIVO", "controla_estoque": True, **extra,
    }, token)
    pid = (r or {}).get("id")
    if pid:
        produtos.append(pid)
    return pid


def nota_com(descricao, codigo, ean=None):
    """Nota digitada de um item. O EAN é plantado depois (a digitada não tem o campo)
    e a nota relida — a conciliação já correu e deixou o item pendente."""
    _st, r = chamar("POST", "/notas", {
        "id_fornecedor": forn, "numero": uuid.uuid4().hex[:8].upper(),
        "serie": "1", "data_emissao": "2026-11-05",
        "itens": [{"descricao": descricao, "codigo_fornecedor": codigo,
                   "quantidade": 3, "valor_unitario": 4, "um": "UN"}],
    }, token)
    id_nota = (r or {}).get("id")
    if id_nota:
        notas.append(id_nota)
    if ean:
        with get_cursor() as cur:
            cur.execute("UPDATE nota_itens SET codigo_barras = %s WHERE id_nota = %s",
                        (ean, id_nota))
    _st, n = chamar("GET", f"/notas/{id_nota}", token=token)
    return id_nota, (n.get("itens") or [{}])[0]


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()
_st, f = chamar("POST", "/fornecedores", {"nome": f"Distribuidora {marca}", "fornecedor": True},
                token)
forn = (f or {}).get("id")
if forn:
    pessoas.append(forn)

print("\n1. a linha pendente aponta o produto inativo")
ean = ean13()
inativo = novo_produto("Farinha Desativada", codigo_barras=ean)
st, _r = chamar("DELETE", f"/produtos/{inativo}", token=token)
with get_cursor() as cur:
    cur.execute("SELECT ativo FROM produtos WHERE id = %s", (inativo,))
    checar("o produto foi desativado", cur.fetchone()["ativo"] is False, st)
id_nota, item = nota_com("FARINHA TIPO 1", f"F{marca}", ean)
checar("o item não casa sozinho (fica pendente)", item.get("id_produto") is None, item)
achado = item.get("inativo_encontrado") or {}
checar("mas a linha diz que o produto EXISTE e está inativo (pelo EAN)",
       achado.get("id") == inativo and marca in (achado.get("nome") or ""), achado)

cod = f"C{marca}"
inativo2 = novo_produto("Fermento Desativado")
with get_cursor() as cur:
    cur.execute("""INSERT INTO produto_fornecedor (id_produto, id_fornecedor, codigo_no_fornecedor)
                   VALUES (%s, %s, %s)""", (inativo2, forn, cod))
chamar("DELETE", f"/produtos/{inativo2}", token=token)
_n2, item2 = nota_com("FERMENTO SECO", cod)
checar("pelo código no fornecedor também acha",
       (item2.get("inativo_encontrado") or {}).get("id") == inativo2, item2)

print("\n2. o absorvido de fusão não é oferecido")
ean_f = ean13()
principal = novo_produto("Acucar Principal")
fundido = novo_produto("Acucar Fundido", codigo_barras=ean_f)
with get_cursor() as cur:
    cur.execute("UPDATE produtos SET ativo = false, status = 'ARQUIVADO', fundido_em = %s "
                "WHERE id = %s", (principal, fundido))
_n3, item3 = nota_com("ACUCAR REFINADO", f"A{marca}", ean_f)
checar("fundido não aparece como inativo encontrado",
       item3.get("inativo_encontrado") is None, item3.get("inativo_encontrado"))

print("\n3. usar mesmo inativo e lançar")
st, r = chamar("POST", f"/notas/itens/{item['id']}/vincular",
               {"id_produto": inativo, "aprender": False}, token)
checar("vincular ao inativo é aceito", st == 200, (st, r))
_st, n = chamar("GET", f"/notas/{id_nota}", token=token)
linha = (n.get("itens") or [{}])[0]
checar("a linha marca o produto como inativo",
       linha.get("id_produto") == inativo and linha.get("produto_ativo") is False, linha)
st, r = chamar("POST", f"/notas/{id_nota}/lancar", {}, token)
checar("lançar SEM confirmar é recusado (409) e nomeia o produto",
       st == 409 and "inativo" in str(r.get("detail")) and marca in str(r.get("detail")),
       (st, r))
with get_cursor() as cur:
    cur.execute("SELECT status FROM notas_entrada WHERE id = %s", (id_nota,))
    checar("e a nota segue aberta", cur.fetchone()["status"] != "LANCADA")
st, r = chamar("POST", f"/notas/{id_nota}/lancar", {"aceitar_inativos": True}, token)
checar("confirmado, lança", st == 200 and r.get("itens_lancados") == 1, (st, r))
with get_cursor() as cur:
    cur.execute("""SELECT count(*) AS n FROM estoque_movimentos
                    WHERE id_produto = %s AND tipo = 'ENTRADA_NF' AND origem_id = %s""",
                (inativo, id_nota))
    checar("a entrada está no razão, no produto inativo", cur.fetchone()["n"] == 1)
    cur.execute("SELECT ativo FROM produtos WHERE id = %s", (inativo,))
    checar("e o cadastro continua inativo", cur.fetchone()["ativo"] is False)

print("\n4. fundido segue recusado mesmo confirmado")
with get_cursor() as cur:
    cur.execute("UPDATE nota_itens SET id_produto = %s WHERE id = %s", (fundido, item3["id"]))
st, r = chamar("POST", f"/notas/{_n3}/lancar", {"aceitar_inativos": True}, token)
checar("recusa e aponta o principal",
       st == 400 and "fundido" in str(r.get("detail")), (st, r))

print("\n5. limpeza")
for nid in reversed(notas):
    chamar("POST", f"/notas/{nid}/estornar", {}, token)
    chamar("DELETE", f"/notas/{nid}", token=token)
with get_cursor() as cur:
    cur.execute("DELETE FROM produto_fornecedor WHERE id_fornecedor = %s", (forn,))
    cur.execute("UPDATE produtos SET codigo_barras = NULL WHERE id = ANY(%s)", (produtos,))
for pid in produtos:
    chamar("DELETE", f"/produtos/{pid}", token=token)
for sid in pessoas:
    chamar("DELETE", f"/fornecedores/{sid}", token=token)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
