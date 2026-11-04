"""Os três painéis que vieram do LeadsFood (04/11/2026).

🔑 **Pedido do dono:** *"uma tela com todos os indicadores que são apresentados lá"*.
1. `services/clientes_painel.py` — base, novos por mês e por dia, idade × gênero, cidades, origem;
2. `services/fidelidade.graficos` — check-ins por mês (com clientes únicos), por dia e rankings;
3. `services/reservas_painel._historia` — ano contra ano e sazonalidade.

⚠️ **Confere DIFERENÇAS**, como `smoke_painel_reservas`: mede, grava um cenário conhecido direto
no banco (cadastro com data no passado, check-in e reserva no passado — a tela não deixa) e mede
de novo. Telefone com DDD 00 (prefixo `00900004`), que ninguém tem; a limpeza apaga só ele.

    python tests/smoke_paineis_leadsfood.py        (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import preservar_reserva  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402
from relogio import agora_da_casa  # noqa: E402
from services import fidelidade, reservas_painel  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
PREFIXO = "00900004"
CASA = ZoneInfo("America/Sao_Paulo")
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


def limpar():
    with get_cursor() as cur:
        cur.execute(f"""DELETE FROM fidelidade_checkins WHERE id_cliente IN
                          (SELECT id FROM reserva_clientes WHERE telefone LIKE '{PREFIXO}%%')""")
        cur.execute(f"DELETE FROM reservas WHERE telefone LIKE '{PREFIXO}%%'")
        cur.execute(f"DELETE FROM reserva_clientes WHERE telefone LIKE '{PREFIXO}%%'")


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()
_st, eu = chamar("GET", "/auth/me", token=token)
U = (eu.get("unidades") or [{}])[0].get("id") or 1
preservar_reserva(U)
chamar("PUT", f"/unidades/{U}/parametros", {"reservas_ligado": True}, token)
limpar()

HOJE = agora_da_casa().date()


def get(caminho):
    st, p = chamar("GET", caminho, token=token)
    assert st == 200, (caminho, st, p)
    return p


def anos_atras(anos: int, dias: int = 10) -> date:
    """Quem faz `anos` anos há `dias` dias (sem cair em 29/02)."""
    return date(HOJE.year - anos, HOJE.month, min(HOJE.day, 28)) - timedelta(days=dias)


def meio_dia(d: date) -> datetime:
    return datetime.combine(d, time(12), CASA)


try:
    # ── 1. clientes ──────────────────────────────────────────────────────────────
    antes = get("/reservas/clientes/painel")
    # (sufixo, gênero, nascimento, cidade, origem, cadastrado em)
    ORIGEM_NOVA = "Origem do teste 04/11"
    CLIENTES = [
        ("01", "FEMININO", anos_atras(30), "Blumenau", None, HOJE),
        ("02", "MASCULINO", anos_atras(76), " blumenau ", "Conversão", HOJE - timedelta(days=10)),
        ("03", None, anos_atras(22), None, ORIGEM_NOVA, HOJE - timedelta(days=70)),
        ("04", "FEMININO", anos_atras(120), "BLUMENAU", None, HOJE - timedelta(days=400)),
        ("05", "FEMININO", anos_atras(10), "Blumenau", "  ", HOJE - timedelta(days=3)),
    ]
    ids = {}
    with get_cursor() as cur:
        for suf, gen, nasc, cid, ori, criado in CLIENTES:
            cur.execute("""INSERT INTO reserva_clientes (nome, telefone, genero, nascimento, cidade,
                                                         origem, criado_em)
                           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                        (f"Painel Leads {suf}", PREFIXO + suf + "0", gen, nasc, cid, ori, meio_dia(criado)))
            ids[suf] = cur.fetchone()["id"]
    depois = get("/reservas/clientes/painel")

    def d(bloco, chave):
        return depois[bloco][chave] - antes[bloco][chave]

    criados = [c[5] for c in CLIENTES]
    print("1. Painel de clientes")
    checar("base +5", d("resumo", "base") == 5, d("resumo", "base"))
    checar("novos hoje +1", d("resumo", "hoje") == 1)
    checar("novos no mês e no ano contam pela data de cadastro, não pela de hoje",
           d("resumo", "no_mes") == sum(c >= HOJE.replace(day=1) for c in criados)
           and d("resumo", "no_ano") == sum(c.year == HOJE.year for c in criados),
           (d("resumo", "no_mes"), d("resumo", "no_ano")))
    dias_a = {x["dia"]: x["n"] for x in antes["por_dia"]}
    dias_d = {x["dia"]: x["n"] for x in depois["por_dia"]}
    esperado_dia = {c.isoformat() for c in criados if (HOJE - c).days < 14}
    checar("cada cadastro no seu dia (14 dias, todos, terminando hoje)",
           len(depois["por_dia"]) == 14 and depois["por_dia"][-1]["dia"] == HOJE.isoformat()
           and all(dias_d[k] - dias_a[k] == (1 if k in esperado_dia else 0) for k in dias_d),
           esperado_dia)
    meses_a = {x["mes"]: x["n"] for x in antes["por_mes"]}
    meses_d = {x["mes"]: x["n"] for x in depois["por_mes"]}
    esperado_mes: dict[str, int] = {}
    for c in criados:
        esperado_mes[c.strftime("%Y-%m")] = esperado_mes.get(c.strftime("%Y-%m"), 0) + 1
    checar("cada cadastro no seu mês (6 meses, o atual parcial)",
           len(depois["por_mes"]) == 6 and depois["por_mes"][-1]["parcial"]
           and all(meses_d[m] - meses_a[m] == esperado_mes.get(m, 0) for m in meses_d), esperado_mes)
    checar("gênero: +3 mulheres, +1 homem, +1 não informado",
           (d("genero", "feminino"), d("genero", "masculino"), d("genero", "nao_informado")) == (3, 1, 1),
           depois["genero"])

    def faixa(p, nome):
        return next((x for x in p["idade"] if x["faixa"] == nome),
                    {"feminino": 0, "masculino": 0, "outros": 0})

    checar("30 anos é 30-34 (mulher), 76 é 75+ (homem), 22 sem gênero é 20-24 em 'outros'",
           faixa(depois, "30-34")["feminino"] - faixa(antes, "30-34")["feminino"] == 1
           and faixa(depois, "75+")["masculino"] - faixa(antes, "75+")["masculino"] == 1
           and faixa(depois, "20-24")["outros"] - faixa(antes, "20-24")["outros"] == 1)
    checar("10 anos aparece em 'até 14', no fim da pirâmide",
           faixa(depois, "até 14")["feminino"] - faixa(antes, "até 14")["feminino"] == 1
           and depois["idade"][-1]["faixa"] == "até 14" and depois["idade"][0]["faixa"] == "75+")
    checar("120 anos conta como sem data de nascimento", depois["sem_idade"] - antes["sem_idade"] == 1)

    def cidade(p, nome):
        return next((x["n"] for x in p["cidades"]["top"] if x["cidade"].lower() == nome), 0)

    checar("'Blumenau', ' blumenau ' e 'BLUMENAU' são uma cidade só (+4)",
           cidade(depois, "blumenau") - cidade(antes, "blumenau") == 4
           and sum(x["cidade"].strip().lower() == "blumenau" for x in depois["cidades"]["top"]) == 1)
    checar("sem cidade +1", d("cidades", "sem_cidade") == 1)

    def origem(p, nome):
        return next((x["n"] for x in p["origens"] if x["origem"] == nome), 0)

    checar("sem origem (ou em branco) é 'Cadastro no Botané' (+3)",
           origem(depois, "Cadastro no Botané") - origem(antes, "Cadastro no Botané") == 3)
    checar("origem do LeadsFood conta pelo nome (+1 Conversão, nova origem 1)",
           origem(depois, "Conversão") - origem(antes, "Conversão") == 1
           and origem(depois, ORIGEM_NOVA) == 1)

    # ── 2. fidelidade ────────────────────────────────────────────────────────────
    print("\n2. Fidelidade: check-ins e quem mais vem")
    with get_cursor() as cur:
        g_antes = fidelidade.graficos(cur, top=100000)
    a_api = get("/fidelidade/painel/graficos")
    # (cliente, dias atrás, parte): parte 1 = selo manual, que não é visita
    CHECKINS = [("01", 0, 0), ("01", 5, 0), ("01", 40, 0), ("01", 0, 1), ("02", 5, 0)]
    with get_cursor() as cur:
        for suf, dias, parte in CHECKINS:
            cur.execute("""INSERT INTO fidelidade_checkins (id_cliente, id_unidade, data, parte, origem)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (ids[suf], U, HOJE - timedelta(days=dias), parte,
                         "MANUAL" if parte else "VISITA"))
        g = fidelidade.graficos(cur, top=100000)
    d_api = get("/fidelidade/painel/graficos")
    visitas = [c for c in CHECKINS if c[2] == 0]
    dia_a = {x["dia"]: x["n"] for x in g_antes["por_dia"]}
    esperado_d: dict[str, int] = {}
    for _s, dias, _p in visitas:
        if dias < 14:
            k = (HOJE - timedelta(days=dias)).isoformat()
            esperado_d[k] = esperado_d.get(k, 0) + 1
    checar("por dia: cada visita no seu dia; o selo manual não conta",
           all(x["n"] - dia_a[x["dia"]] == esperado_d.get(x["dia"], 0) for x in g["por_dia"]), esperado_d)
    mes_a = {x["mes"]: x for x in g_antes["por_mes"]}
    mes_atual = HOJE.strftime("%Y-%m")
    m_hoje = next(x for x in g["por_mes"] if x["mes"] == mes_atual)
    vis_mes = [c for c in visitas if (HOJE - timedelta(days=c[1])).strftime("%Y-%m") == mes_atual]
    checar("por mês: check-ins e clientes únicos (o mesmo cliente duas vezes conta um)",
           m_hoje["checkins"] - mes_a[mes_atual]["checkins"] == len(vis_mes)
           and m_hoje["clientes"] - mes_a[mes_atual]["clientes"] == len({c[0] for c in vis_mes}),
           (m_hoje, mes_a[mes_atual], vis_mes))

    def no_top(lista, suf):
        return next((x for x in lista if x["id"] == ids[suf]), None)

    t1, t30 = no_top(g["top_sempre"], "01"), no_top(g["top_30_dias"], "01")
    checar("ranking de sempre: 3 visitas, última hoje", t1 and t1["visitas"] == 3
           and t1["ultima"] == HOJE.isoformat(), t1)
    checar("ranking de 30 dias: 2 visitas (a de 40 dias fica de fora)", t30 and t30["visitas"] == 2, t30)
    checar("a rota devolve 6 meses, 14 dias e até 10 em cada ranking",
           len(d_api["por_mes"]) == 6 and len(d_api["por_dia"]) == 14
           and len(d_api["top_sempre"]) <= 10 and len(d_api["top_30_dias"]) <= 10)
    checar("o ranking vem do maior para o menor",
           all(d_api["top_sempre"][i]["visitas"] >= d_api["top_sempre"][i + 1]["visitas"]
               for i in range(len(d_api["top_sempre"]) - 1)))
    checar("e a rota mudou junto com o serviço",
           sum(x["n"] for x in d_api["por_dia"]) - sum(x["n"] for x in a_api["por_dia"])
           == sum(esperado_d.values()))

    # ── 3. reservas: ano contra ano e sazonalidade ───────────────────────────────
    print("\n3. Reservas: ano contra ano e sazonalidade")
    r_antes = get("/reservas/painel?meses=12")
    ano = r_antes["ano_contra_ano"]["ano"]
    # (data, pessoas, status)
    RESERVAS = [
        (date(ano, 1, 15), 4, "ENCERRADA"),
        (date(ano - 1, 1, 10), 3, "ENCERRADA"),
        (date(ano - 1, 1, 20), 3, "CHEGOU"),
        (date(ano - 1, 1, 25), 5, "NAO_COMPARECEU"),
        (date(ano - 1, 1, 26), 9, "CANCELADA"),
        (HOJE, 2, "ENCERRADA"),
    ]
    with get_cursor() as cur:
        for i, (dia, pessoas, status) in enumerate(RESERVAS):
            cur.execute(
                """INSERT INTO reservas (id_unidade, data, hora, pessoas, status, origem, nome, telefone)
                   VALUES (%s, %s, '12:00', %s, %s, 'BALCAO', 'Painel leads', %s)""",
                (U, dia, pessoas, status, f"{PREFIXO}9{i:02d}"))
    r_dep = get("/reservas/painel?meses=12")
    aa_a, aa_d = r_antes["ano_contra_ano"], r_dep["ano_contra_ano"]
    jan_a, jan_d = aa_a["meses"][0], aa_d["meses"][0]
    checar(f"janeiro de {ano}: +1 reserva, +4 pessoas",
           (jan_d["atual"]["reservas"] - jan_a["atual"]["reservas"],
            jan_d["atual"]["pessoas"] - jan_a["atual"]["pessoas"]) == (1, 4), jan_d)
    checar(f"janeiro de {ano - 1}: +3 reservas (a falta conta, a cancelada não), +6 pessoas (a falta não traz)",
           (jan_d["anterior"]["reservas"] - jan_a["anterior"]["reservas"],
            jan_d["anterior"]["pessoas"] - jan_a["anterior"]["pessoas"]) == (3, 6), jan_d)
    tot = {k: sum(x["atual"]["reservas"] for x in aa_d["meses"]) if k == "a"
           else sum(x["anterior"]["reservas"] for x in aa_d["meses"]) for k in ("a", "b")}
    checar("a variação é a dos totais, com uma casa",
           aa_d["variacao"]["reservas"] == round((tot["a"] / tot["b"] - 1) * 100, 1), (aa_d["variacao"], tot))
    checar("só meses fechados: o mês corrente não entra no ano contra ano",
           aa_d["ate_mes"] == (HOJE.month - 1 if HOJE.month > 1 else 12)
           and len(aa_d["meses"]) == aa_d["ate_mes"])

    def soma_saz(p, mes):
        x = p["sazonalidade"][mes - 1]
        return (x["reservas"] or 0) * x["anos"]

    checar("sazonalidade de janeiro: a soma dos janeiros cresce 4 (1 + 3)",
           abs(soma_saz(r_dep, 1) - soma_saz(r_antes, 1) - 4) < 0.1 * max(1, r_dep["sazonalidade"][0]["anos"]),
           (r_antes["sazonalidade"][0], r_dep["sazonalidade"][0]))
    checar("a reserva de hoje não mexe na sazonalidade do mês corrente",
           abs(soma_saz(r_dep, HOJE.month) - soma_saz(r_antes, HOJE.month)) < 0.1 * max(1, r_dep["sazonalidade"][HOJE.month - 1]["anos"]))
    with get_cursor() as cur:
        vazio = reservas_painel._historia(cur, 999999, HOJE)
        janeiro = reservas_painel._historia(cur, U, date(HOJE.year + 1, 1, 15))
    checar("loja sem histórico: sem variação (None, nada de +0%) e sem sazonalidade",
           vazio["ano_contra_ano"]["variacao"] == {"reservas": None, "pessoas": None}
           and vazio["sazonalidade"] == [])
    checar("em janeiro, compara o ano passado inteiro com o retrasado",
           janeiro["ano_contra_ano"]["ano"] == HOJE.year and janeiro["ano_contra_ano"]["ate_mes"] == 12
           and len(janeiro["ano_contra_ano"]["meses"]) == 12)

    # ── 4. permissão ─────────────────────────────────────────────────────────────
    print("\n4. sem login, as rotas recusam")
    checar("401 nas duas rotas novas",
           chamar("GET", "/reservas/clientes/painel")[0] == 401
           and chamar("GET", "/fidelidade/painel/graficos")[0] == 401)
finally:
    limpar()

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print(f"  - {x}")
sys.exit(1 if falhas else 0)
