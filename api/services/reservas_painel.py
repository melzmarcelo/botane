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
