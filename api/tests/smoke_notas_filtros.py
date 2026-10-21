"""Teste de fumaça dos filtros da lista de notas e do resumo (`/notas/resumo`).

🔑 Pedido do dono (21/10/2026): "nas notas de entrada poderia ter mais filtros:
período, situação...".

O que este arquivo cobra:

1. situação em LISTA (`status=IMPORTADA&status=CONCILIADA`, o "a lançar") e um
   valor só continua valendo, em maiúscula ou não
2. origem, período (entrada, ou emissão sem entrada) e "só com item sem produto"
3. o resumo usa o MESMO filtro da lista: a contagem é o `X-Total`
4. o valor do resumo é o que é compra — sem cancelada nem não encontrada
5. a rota `/notas/resumo` não é engolida por `/{id_nota}`

⚠️ **A suíte trabalha num trecho dos anos 80 sem nota nenhuma**, conferido vazio
antes: a base tem milhares de notas, e qualquer total sobre ela muda sozinho.

    python tests/smoke_notas_filtros.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, "tests")
sys.path.insert(0, ".")
from database import get_cursor  # noqa: E402

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
            return r.status, json.loads(r.read() or b"null"), r.headers.get("X-Total")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null"), None
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")[:300]}, None


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


st, r, _ = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
assert st == 200, r
token = r["access_token"]
marca = str(time.time_ns() // 100)[-6:]
d0 = date(1986, 1, 6) + timedelta(weeks=int(marca) % 400)
JANELA = f"inicio={d0}&fim={d0 + timedelta(days=20)}"


def lista(q):
    st, r, total = chamar("GET", f"/notas?{JANELA}&{q}", token=token)
    return st, r or [], None if total is None else int(total)


def resumo(q):
    return chamar("GET", f"/notas/resumo?{JANELA}&{q}", token=token)[:2]


print("0. o trecho do calendario esta vazio")
st, r, total = lista("")
checar("a lista responde e o trecho nao tem nota", st == 200 and total == 0, (st, total))
st, r = resumo("")
checar("o resumo responde (nao foi engolido por /{id_nota})", st == 200 and r.get("notas") == 0, (st, r))

print("1. cinco notas, uma por situacao")
# (situacao, origem, dia de entrada, valor, com item sem produto?)
cenario = [
    ("IMPORTADA", "OMIE", 1, 100, True),
    ("CONCILIADA", "XML", 3, 200, False),
    ("LANCADA", "MANUAL", 5, 400, False),
    ("CANCELADA", "OMIE", 7, 800, False),
    ("NAO_ENCONTRADA", "OMIE", 9, 1600, False),
]
ids = {}
for situacao, origem, dia, valor, pendente in cenario:
    st, nota, _ = chamar("POST", "/notas", {
        "numero": f"F{marca}{dia}", "data_emissao": str(d0 + timedelta(days=dia)),
        "itens": [{"descricao": f"ITEM FILTRO {marca}", "quantidade": 1, "valor_unitario": valor}],
    }, token=token)
    checar(f"nota {situacao} criada", st in (200, 201) and nota.get("id"), (st, nota))
    ids[situacao] = nota.get("id")
# ⚠️ A situação e a origem vão por SQL: levar uma nota a "não encontrada no Omie"
# pela API exigiria o Omie. O que se testa aqui é o FILTRO, não o ciclo da nota.
with get_cursor() as cur:
    for situacao, origem, dia, valor, pendente in cenario:
        cur.execute("""UPDATE notas_entrada SET status = %s, origem = %s,
                              data_entrada = %s, valor_total = %s WHERE id = %s""",
                    (situacao, origem, d0 + timedelta(days=dia), valor, ids[situacao]))
        if not pendente:
            cur.execute("UPDATE nota_itens SET ignorado = true WHERE id_nota = %s", (ids[situacao],))

print("2. situacao")
st, r, total = lista("")
checar("sem filtro, as cinco", total == 5, total)
st, r, total = lista("status=IMPORTADA&status=CONCILIADA")
checar("'a lancar' (duas situacoes) traz duas", total == 2
       and {n["status"] for n in r} == {"IMPORTADA", "CONCILIADA"}, (total, r))
st, r, total = lista("status=lancada")
checar("uma situacao so, em minuscula, continua valendo", total == 1 and r[0]["id"] == ids["LANCADA"],
       (total, r))

print("3. origem, periodo e pendencia")
st, r, total = lista("origem=OMIE")
checar("origem Omie traz tres", total == 3, total)
st, r, total = lista("origem=XML&origem=MANUAL")
checar("e duas origens juntas, duas", total == 2, total)
st, r, total = chamar("GET", f"/notas?inicio={d0 + timedelta(days=2)}&fim={d0 + timedelta(days=6)}",
                      token=token)
checar("o periodo pela data de entrada (dias 2 a 6: a conciliada e a lancada)",
       {n["id"] for n in (r or [])} == {ids["CONCILIADA"], ids["LANCADA"]}, r)
st, r, total = lista("pendentes=true")
checar("so com item sem produto: a importada", total == 1 and r[0]["id"] == ids["IMPORTADA"], (total, r))

print("4. o resumo e o da lista")
st, r = resumo("")
checar("cinco notas no resumo", r.get("notas") == 5, r)
checar("o valor e o que e compra: 100+200+400, sem cancelada nem nao encontrada",
       r.get("valor") == 700, r)
checar("e o valor vai tambem por situacao",
       {p["status"]: p["valor"] for p in r.get("por_status", [])}.get("CANCELADA") == 800, r)
st, r = resumo("status=IMPORTADA&status=CONCILIADA")
checar("o resumo de 'a lancar' e 2 notas, R$ 300", r.get("notas") == 2 and r.get("valor") == 300, r)
st, r = resumo("origem=OMIE&pendentes=true")
checar("e combina os filtros como a lista", r.get("notas") == 1 and r.get("valor") == 100, r)

print("5. limpeza")
with get_cursor() as cur:
    cur.execute("DELETE FROM nota_itens WHERE id_nota = ANY(%s)", (list(ids.values()),))
    cur.execute("DELETE FROM notas_entrada WHERE id = ANY(%s)", (list(ids.values()),))
st, r, total = lista("")
checar("nada ficou na base", total == 0, total)

print(f"\n{ok} passaram, {len(falhas)} falharam")
sys.exit(1 if falhas else 0)
