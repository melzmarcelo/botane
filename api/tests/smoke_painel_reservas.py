"""O painel das reservas (services/reservas_painel.py).

🔑 **Pedido do dono (30/10/2026):** os gráficos do BI de reservas do LeadsFood — dia da semana,
mês, objetivo, horário e grupos grandes.

⚠️ **Confere DIFERENÇAS**: mede o painel, grava um cenário conhecido direto no banco (reservas
no passado — a rota recusa data passada) e mede de novo. Assim a suíte não depende do que a
base local já tem. `preservar_reserva` devolve a loja como estava.

    python tests/smoke_painel_reservas.py        (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import preservar_reserva  # noqa: E402
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
preservar_reserva(U)
chamar("PUT", f"/unidades/{U}/parametros", {"reservas_ligado": True}, token)

with get_cursor() as cur:
    cur.execute("SELECT current_date AS d")
    HOJE = cur.fetchone()["d"]


def painel(q="meses=24"):
    st, p = chamar("GET", f"/reservas/painel?{q}", token=token)
    assert st == 200, (st, p)
    return p


antes = painel()
antes9 = painel("meses=24&grupo_pessoas=9")

# (dias atrás, pessoas, status, telefone, hora, objetivo)
CENARIO = [
    (10, 2, "ENCERRADA", "00900002001", "12:00", "Aniversário"),
    (40, 2, "CHEGOU", "00900002001", "12:00", "Aniversário"),
    (70, 2, "CONFIRMADA", "00900002001", "12:00", "Aniversário"),
    (20, 4, "NAO_COMPARECEU", "00900002002", "12:00", " aniversário "),
    (30, 3, "CANCELADA", "00900002003", "12:00", None),
    (25, 2, "PENDENTE", "00900002003", "12:00", None),
    (-5, 2, "CONFIRMADA", "00900002003", "12:00", None),
    (50, 10, "ENCERRADA", "00900002004", "19:30", "Confraternização"),
    (60, 8, "NAO_COMPARECEU", "00900002005", "19:30", None),
    (800, 2, "ENCERRADA", "00900002006", "12:00", None),
]
with get_cursor() as cur:
    for dias, pessoas, status, fone, hora, objetivo in CENARIO:
        cur.execute(
            """INSERT INTO reservas (id_unidade, data, hora, pessoas, status, origem, nome,
                                     telefone, objetivo)
               VALUES (%s, %s, %s, %s, %s, 'BALCAO', 'Painel teste', %s, %s)""",
            (U, HOJE - timedelta(days=dias), hora, pessoas, status, fone, objetivo))

depois = painel()


def delta(chave, bloco="resumo"):
    return depois[bloco][chave] - antes[bloco][chave]


VALIDAS = [c for c in CENARIO if c[2] in ("ENCERRADA", "CHEGOU", "CONFIRMADA", "NAO_COMPARECEU")
           and 0 <= c[0] < 700]

print("1. os números do período (24 meses)")
checar("reservas válidas: 6 (sem cancelada, pendente, futura e fora do período)",
       delta("reservas") == 6, delta("reservas"))
checar("pessoas que passaram: 16 (as faltas não contam)", delta("pessoas") == 16, delta("pessoas"))
checar("no-shows: 2", delta("faltas") == 2)
checar("canceladas: 1", delta("canceladas") == 1)
checar("clientes únicos: 4 telefones", delta("clientes") == 4, delta("clientes"))

print("\n2. grupos grandes (6+)")
checar("2 reservas de grupo", delta("reservas", "grupos") == 2)
checar("10 pessoas trazidas (o grupo que faltou não conta)", delta("pessoas", "grupos") == 10)
checar("1 falta entre os grupos", delta("faltas", "grupos") == 1)
checar("o maior grupo é pelo menos 10", depois["grupos"]["maior"] >= 10)

print("\n3. por dia da semana, mês, objetivo e horário")
esperado_dia = {d: 0 for d in range(1, 8)}
esperado_mes: dict[str, int] = {}
for dias, *_ in VALIDAS:
    d = HOJE - timedelta(days=dias)
    esperado_dia[d.isoweekday()] += 1
    esperado_mes[d.strftime("%Y-%m")] = esperado_mes.get(d.strftime("%Y-%m"), 0) + 1
dia_ok = all(depois["por_dia_semana"][i]["reservas"] - antes["por_dia_semana"][i]["reservas"]
             == esperado_dia[i + 1] for i in range(7))
checar("cada reserva no seu dia da semana (1 = segunda)", dia_ok,
       [x["reservas"] for x in depois["por_dia_semana"]])
checar("os 7 dias vêm sempre, na ordem", [x["nome"] for x in depois["por_dia_semana"]]
       == ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"])
meses_d = {x["mes"]: x["reservas"] for x in depois["por_mes"]}
meses_a = {x["mes"]: x["reservas"] for x in antes["por_mes"]}
checar("cada reserva no seu mês", all(meses_d[m] - meses_a[m] == n for m, n in esperado_mes.items()),
       esperado_mes)
checar("24 meses, todos, com o atual marcado parcial",
       len(depois["por_mes"]) == 24 and depois["por_mes"][-1]["parcial"]
       and not depois["por_mes"][0]["parcial"])


def objetivo(p, nome):
    return next((x for x in p["por_objetivo"] if (x["objetivo"] or "").lower() == nome), None)


an, ad = objetivo(antes, "aniversário"), objetivo(depois, "aniversário")
checar("'Aniversário' e ' aniversário ' são o mesmo objetivo (4 reservas)",
       ad and ad["reservas"] - (an["reservas"] if an else 0) == 4, ad)
checar("sem objetivo vira 'Não informado', no fim",
       depois["por_objetivo"][-1]["objetivo"] == "Não informado")
h_a = {x["hora"]: x["reservas"] for x in antes["por_hora"]}
h_d = {x["hora"]: x["reservas"] for x in depois["por_hora"]}
checar("19h30 conta na hora 19 (2 reservas)", h_d.get(19, 0) - h_a.get(19, 0) == 2, h_d)

print("\n4. o período")
p1 = painel("meses=1")
checar("1 mês começa no dia 1 do mês atual", p1["de"] == HOJE.replace(day=1).isoformat()
       and len(p1["por_mes"]) == 1, (p1["de"], len(p1["por_mes"])))
st, _r = chamar("GET", "/reservas/painel?meses=0", token=token)
checar("período fora da faixa é recusado (422)", st == 422, st)
pg = painel("meses=24&grupo_pessoas=9")
checar("grupo a partir de 9: o de 8 deixa de ser grupo (só o de 10 entra)",
       pg["grupos"]["reservas"] - antes9["grupos"]["reservas"] == 1, pg["grupos"])

print("\n5. com o módulo desligado, a rota recusa")
chamar("PUT", f"/unidades/{U}/parametros", {"reservas_ligado": False}, token)
st, _r = chamar("GET", "/reservas/painel", token=token)
checar("409", st == 409, st)
chamar("PUT", f"/unidades/{U}/parametros", {"reservas_ligado": True}, token)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print(f"  - {x}")
sys.exit(1 if falhas else 0)
