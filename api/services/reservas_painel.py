"""O painel das reservas — como a agenda andou: dia da semana, mês, objetivo, horário e grupos.

🔑 **Pedido do dono (30/10/2026):** *"seguir para os gráficos"*, depois do Plano de ação — a
"Análise de desempenho" e os "Grupos grandes" do BI de reservas do LeadsFood.

🔑 **As três contas, e por que não são a mesma:**
- **Reserva válida** = a que ocupou agenda: CONFIRMADA, CHEGOU, ENCERRADA ou NAO_COMPARECEU,
  em data que já passou (ou hoje). É a mesma conta do LeadsFood ("170 reservas válidas", com as
  faltas dentro). Cancelada não ocupou; PENDENTE no passado nunca foi aprovada.
- **Pessoas que passaram** = as pessoas das válidas que NÃO faltaram. Somar as faltas diria
  que vieram pessoas que não vieram.
- **No-show** = NAO_COMPARECEU sobre as válidas.
⚠️ Só o PASSADO: reserva de amanhã ainda pode cancelar ou faltar, e entrar com ela faria o mês
corrente parecer melhor do que foi.

⚠️ **Os meses vêm TODOS, com zero onde não houve reserva.** Ao contrário da venda por dia (onde
buraco é dia fechado), um mês sem reserva é informação: é o vale da sazonalidade.
"""

from datetime import date

from services.reservas_plano import FONE, FONE_JUNTAS

MESES = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez")
DIAS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")  # ISO: 1 = segunda
VALIDAS = "('CONFIRMADA', 'CHEGOU', 'ENCERRADA', 'NAO_COMPARECEU')"
# Objetivos além destes viram "Outros": a reserva do balcão aceita texto livre, e uma lista de
# trinta grafias diferentes não é gráfico.
MAX_OBJETIVOS = 7


def inicio_do_periodo(hoje: date, meses: int) -> date:
    """O dia 1 do mês, `meses - 1` meses antes do atual (12 meses = o atual e os 11 anteriores)."""
    m = hoje.year * 12 + hoje.month - 1 - (meses - 1)
    return date(m // 12, m % 12 + 1, 1)


def painel(cur, id_unidade: int, meses: int, grupo_pessoas: int) -> dict:
    cur.execute("SELECT current_date AS hoje")
    hoje = cur.fetchone()["hoje"]
    de = inicio_do_periodo(hoje, meses)
    p = {"u": id_unidade, "de": de, "grupo": grupo_pessoas}
    base = f"""
        SELECT r.data, r.hora, r.pessoas, r.status, r.objetivo,
               r.status = 'NAO_COMPARECEU' AS faltou,
               r.pessoas >= %(grupo)s AS grupo,
               {FONE} AS fone, lower(trim(r.nome)) AS nome
          FROM reservas r
          {FONE_JUNTAS}
         WHERE r.id_unidade = %(u)s AND r.data BETWEEN %(de)s AND current_date
           AND r.status IN {VALIDAS}"""
    soma = """count(*) AS reservas,
              coalesce(sum(pessoas) FILTER (WHERE NOT faltou), 0) AS pessoas,
              count(*) FILTER (WHERE faltou) AS faltas"""

    cur.execute(f"""
        WITH b AS ({base})
        SELECT {soma},
               count(DISTINCT CASE WHEN length(fone) BETWEEN 10 AND 11 THEN fone
                                   ELSE 'n:' || nome END) AS clientes,
               count(*) FILTER (WHERE grupo) AS grupos,
               coalesce(sum(pessoas) FILTER (WHERE grupo AND NOT faltou), 0) AS grupos_pessoas,
               coalesce(max(pessoas) FILTER (WHERE grupo AND NOT faltou), 0) AS grupos_maior,
               count(*) FILTER (WHERE grupo AND faltou) AS grupos_faltas
          FROM b""", p)
    r = dict(cur.fetchone())
    cur.execute("""SELECT count(*) AS n FROM reservas
                    WHERE id_unidade = %(u)s AND status = 'CANCELADA'
                      AND data BETWEEN %(de)s AND current_date""", p)
    r["canceladas"] = cur.fetchone()["n"]

    cur.execute(f"""WITH b AS ({base})
        SELECT extract(isodow FROM data)::int AS dia, {soma} FROM b GROUP BY 1""", p)
    por_dia = {x["dia"]: x for x in cur.fetchall()}

    cur.execute(f"""WITH b AS ({base})
        SELECT to_char(data, 'YYYY-MM') AS mes, {soma},
               count(*) FILTER (WHERE grupo) AS grupos,
               coalesce(sum(pessoas) FILTER (WHERE grupo AND NOT faltou), 0) AS grupos_pessoas
          FROM b GROUP BY 1""", p)
    por_mes = {x["mes"]: x for x in cur.fetchall()}

    cur.execute(f"""WITH b AS ({base})
        SELECT min(trim(objetivo)) AS objetivo, {soma}
          FROM b GROUP BY lower(trim(coalesce(objetivo, '')))
         ORDER BY count(*) DESC, 1""", p)
    objetivos = [dict(x) for x in cur.fetchall()]

    cur.execute(f"""WITH b AS ({base})
        SELECT extract(hour FROM hora)::int AS hora, {soma} FROM b GROUP BY 1 ORDER BY 1""", p)
    por_hora = [dict(x) for x in cur.fetchall()]

    vazio = {"reservas": 0, "pessoas": 0, "faltas": 0}
    meses_lista = []
    for i in range(meses):
        m = de.year * 12 + de.month - 1 + i
        chave = f"{m // 12:04d}-{m % 12 + 1:02d}"
        x = por_mes.get(chave, {})
        meses_lista.append({
            "mes": chave, "parcial": chave == hoje.strftime("%Y-%m"),
            **{k: x.get(k, 0) for k in ("reservas", "pessoas", "faltas", "grupos",
                                         "grupos_pessoas")},
        })

    return {
        "de": de.isoformat(), "ate": hoje.isoformat(), "meses": meses,
        "grupo_pessoas": grupo_pessoas,
        "resumo": {
            "reservas": r["reservas"], "clientes": r["clientes"], "pessoas": r["pessoas"],
            "faltas": r["faltas"], "canceladas": r["canceladas"],
        },
        "grupos": {
            "reservas": r["grupos"], "pessoas": r["grupos_pessoas"], "maior": r["grupos_maior"],
            "faltas": r["grupos_faltas"],
        },
        "por_dia_semana": [{"dia": d, "nome": DIAS[d - 1],
                            **{k: por_dia.get(d, vazio)[k] for k in vazio}}
                           for d in range(1, 8)],
        "por_mes": meses_lista,
        "por_objetivo": _objetivos(objetivos),
        "por_hora": por_hora,
        **_historia(cur, id_unidade, hoje),
    }


def _historia(cur, id_unidade: int, hoje: date) -> dict:
    """O ano contra ano e a sazonalidade — sobre a HISTÓRIA INTEIRA, não sobre o período.

    🔑 Pedido do dono (04/11/2026), o que faltava do BI do LeadsFood. Os dois olham só
    MESES FECHADOS: o mês corrente pela metade puxaria a média e o ano para baixo.
    - **Ano contra ano**: de janeiro ao último mês fechado, este ano × o anterior (em janeiro,
      o ano passado inteiro × o retrasado). ⚠️ Sem nada no ano anterior a variação é `None`:
      o LeadsFood escreve "+0%" com 0 contra 154, e isso não é crescimento zero.
    - **Sazonalidade**: a média de cada mês do calendário, do primeiro mês com reserva até o
      último fechado — com ZERO onde não houve reserva (mês vazio é o vale, não um buraco).
    """
    cur.execute(f"""
        SELECT to_char(data, 'YYYY-MM') AS mes, count(*) AS reservas,
               coalesce(sum(pessoas) FILTER (WHERE status <> 'NAO_COMPARECEU'), 0) AS pessoas
          FROM reservas
         WHERE id_unidade = %s AND status IN {VALIDAS} AND data < %s
         GROUP BY 1""", (id_unidade, hoje.replace(day=1)))
    por_mes = {x["mes"]: {"reservas": int(x["reservas"]), "pessoas": int(x["pessoas"])}
               for x in cur.fetchall()}
    zero = {"reservas": 0, "pessoas": 0}

    ano, ate = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)
    meses_aa = [{"mes": m, "nome": MESES[m - 1],
                 "atual": por_mes.get(f"{ano:04d}-{m:02d}", zero),
                 "anterior": por_mes.get(f"{ano - 1:04d}-{m:02d}", zero)}
                for m in range(1, ate + 1)]

    def variacao(k: str) -> float | None:
        a = sum(x["anterior"][k] for x in meses_aa)
        return None if not a else round((sum(x["atual"][k] for x in meses_aa) / a - 1) * 100, 1)

    sazonal = []
    if por_mes:
        primeiro = min(por_mes)
        p = int(primeiro[:4]) * 12 + int(primeiro[5:]) - 1
        u = hoje.year * 12 + hoje.month - 2  # o último mês fechado
        contas = {m: [] for m in range(1, 13)}
        for i in range(p, u + 1):
            contas[i % 12 + 1].append(por_mes.get(f"{i // 12:04d}-{i % 12 + 1:02d}", zero))
        sazonal = [{"mes": m, "nome": MESES[m - 1], "anos": len(v),
                    **{k: round(sum(x[k] for x in v) / len(v), 1) if v else None
                       for k in ("reservas", "pessoas")}}
                   for m, v in contas.items()]
    return {
        "ano_contra_ano": {"ano": ano, "anterior": ano - 1, "ate_mes": ate, "meses": meses_aa,
                           "variacao": {k: variacao(k) for k in ("reservas", "pessoas")}},
        "sazonalidade": sazonal,
    }


def _objetivos(linhas: list[dict]) -> list[dict]:
    """Os mais frequentes, o resto em "Outros", e o vazio como "Não informado" no fim."""
    sem = [x for x in linhas if not x["objetivo"]]
    com = [x for x in linhas if x["objetivo"]]
    saida = com[:MAX_OBJETIVOS]
    resto = com[MAX_OBJETIVOS:]
    if resto:
        saida.append({"objetivo": "Outros",
                      **{k: sum(x[k] for x in resto) for k in ("reservas", "pessoas", "faltas")}})
    for x in sem:
        saida.append({**x, "objetivo": "Não informado"})
    return saida
