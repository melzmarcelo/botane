"""O painel dos clientes — quem é a base: quantos, quando chegaram, idade, gênero, cidade, origem.

🔑 **Pedido do dono (04/11/2026):** *"uma tela com todos os indicadores que são apresentados
lá"* — o painel "Leads" do LeadsFood: novos contatos, contatos no ano, base; novos por mês e
por dia; pirâmide de idade por gênero; top 10 cidades; origem.

🔑 **A base é da REDE**, como o grid de Clientes: o telefone é único desde a 087, e o mesmo
cliente reserva numa loja e pega selo na outra. Por isso não há filtro de loja aqui.

⚠️ **"Chegou" é o `criado_em`**, e a importação do LeadsFood grava nele a "Data de criação" de
lá (o primeiro contato foi lá) — sem isso, os 3,6 mil importados cairiam todos em 30/10/2026.

⚠️ **Idade fora de 0 a 110 anos conta como "sem data"**: nascimento digitado errado (o ano da
reserva no lugar do de nascimento) não pode virar uma barra de bebês.
"""

from datetime import date, timedelta

from relogio import agora_da_casa

# As faixas do LeadsFood (de 5 em 5, de 15 a 75+). Menos de 15 aparece só se houver alguém.
FAIXAS = [(i, f"{i}-{i + 4}") for i in range(15, 75, 5)] + [(75, "75+")]
TOP_CIDADES = 10
# Cliente sem origem é o que se cadastrou AQUI (site, reserva, fidelidade, cardápio): a
# origem só existe para o que veio do LeadsFood.
SEM_ORIGEM = "Cadastro no Botané"
DIA_LOCAL = "(criado_em AT TIME ZONE 'America/Sao_Paulo')::date"


def _mes(m: int) -> str:
    return f"{m // 12:04d}-{m % 12 + 1:02d}"


def painel(cur, meses: int = 6, dias: int = 14) -> dict:
    hoje = agora_da_casa().date()
    inicio_mes = hoje.replace(day=1)
    m0 = hoje.year * 12 + hoje.month - 1 - (meses - 1)
    de_mes = date(m0 // 12, m0 % 12 + 1, 1)
    de_dia = hoje - timedelta(days=dias - 1)

    cur.execute(f"""
        SELECT count(*) AS base,
               count(*) FILTER (WHERE {DIA_LOCAL} >= %(mes)s) AS no_mes,
               count(*) FILTER (WHERE {DIA_LOCAL} >= %(ano)s) AS no_ano,
               count(*) FILTER (WHERE {DIA_LOCAL} = %(hoje)s) AS hoje
          FROM reserva_clientes""",
                {"mes": inicio_mes, "ano": hoje.replace(month=1, day=1), "hoje": hoje})
    resumo = {k: int(v) for k, v in dict(cur.fetchone()).items()}

    cur.execute(f"""SELECT to_char({DIA_LOCAL}, 'YYYY-MM') AS mes, count(*) AS n
                      FROM reserva_clientes WHERE {DIA_LOCAL} >= %s GROUP BY 1""", (de_mes,))
    por_mes = {x["mes"]: int(x["n"]) for x in cur.fetchall()}
    cur.execute(f"""SELECT {DIA_LOCAL} AS dia, count(*) AS n
                      FROM reserva_clientes WHERE {DIA_LOCAL} >= %s GROUP BY 1""", (de_dia,))
    por_dia = {x["dia"]: int(x["n"]) for x in cur.fetchall()}

    return {
        "hoje": hoje.isoformat(),
        "resumo": resumo,
        # ⚠️ Os meses e os dias vêm TODOS, com zero: um dia sem cadastro é informação.
        "por_mes": [{"mes": _mes(m0 + i), "n": por_mes.get(_mes(m0 + i), 0),
                     "parcial": i == meses - 1} for i in range(meses)],
        "por_dia": [{"dia": (de_dia + timedelta(days=i)).isoformat(),
                     "n": por_dia.get(de_dia + timedelta(days=i), 0)} for i in range(dias)],
        **_idade_e_genero(cur, hoje),
        "cidades": _cidades(cur),
        "origens": _origens(cur),
        "aniversariantes": _aniversariantes(cur, hoje),
    }


def nome_da_casa(cur, id_unidade: int) -> str | None:
    """O nome que o CLIENTE conhece (o fantasia da empresa), para a mensagem de parabéns.

    ⚠️ Mesma regra do Plano de ação: o apelido da loja ("Matriz") é nome interno.
    """
    cur.execute(
        """SELECT coalesce(nullif(trim((SELECT nome_fantasia FROM empresa LIMIT 1)), ''),
                           u.nome) AS loja
             FROM unidades u WHERE u.id = %s""", (id_unidade,))
    return (cur.fetchone() or {}).get("loja")


def _no_ano(nasc: date, ano: int) -> date:
    """O aniversário naquele ano. ⚠️ Quem nasceu em 29/02 comemora em 28/02 no ano comum."""
    try:
        return nasc.replace(year=ano)
    except ValueError:
        return date(ano, 2, 28)


def _aniversariantes(cur, hoje: date) -> dict:
    """Quem faz aniversário neste mês e no próximo, e quantos fazem em cada mês do ano.

    🔑 **Pedido do dono (04/11/2026):** aniversariantes no Painel de clientes, como os filtros
    prontos do LeadsFood (hoje, 7 dias, mês). A lista cobre o mês corrente INTEIRO (inclusive
    quem já fez: dá para mandar um "atrasado") e o seguinte, para planejar; as abas da tela
    recortam dela. ⚠️ A mesma régua de idade da pirâmide: nascimento fora de 0 a 110 anos é
    erro de digitação e fica de fora.
    """
    proximo = (hoje.replace(day=1) + timedelta(days=32)).replace(day=1)
    cur.execute(
        """SELECT id, nome, telefone, nascimento, whatsapp_optout_em IS NOT NULL AS nao_quer_whatsapp
             FROM reserva_clientes
            WHERE nascimento IS NOT NULL
              AND extract(year FROM age(%s, nascimento)) BETWEEN 0 AND 110""", (hoje,))
    por_mes = [0] * 12
    lista = []
    for c in cur.fetchall():
        nasc = c["nascimento"]
        por_mes[nasc.month - 1] += 1
        if nasc.month not in (hoje.month, proximo.month):
            continue
        # O mês seguinte de dezembro é janeiro do ano que vem.
        dia = _no_ano(nasc, hoje.year if nasc.month == hoje.month else proximo.year)
        lista.append({"id": c["id"], "nome": c["nome"], "telefone": c["telefone"],
                      "dia": dia.isoformat(), "faz": dia.year - nasc.year,
                      "faltam": (dia - hoje).days, "nao_quer_whatsapp": c["nao_quer_whatsapp"]})
    lista.sort(key=lambda x: (x["dia"], (x["nome"] or "").lower()))
    no_mes = [x for x in lista if x["dia"][:7] == hoje.isoformat()[:7]]
    return {
        "hoje": sum(x["faltam"] == 0 for x in lista),
        "semana": sum(0 <= x["faltam"] < 7 for x in lista),
        "no_mes": len(no_mes),
        "proximo_mes": len(lista) - len(no_mes),
        "por_mes": por_mes,
        "lista": lista,
    }


def _idade_e_genero(cur, hoje: date) -> dict:
    cur.execute("""
        SELECT CASE WHEN genero IN ('FEMININO', 'MASCULINO') THEN genero END AS genero,
               CASE WHEN nascimento IS NULL THEN NULL
                    ELSE extract(year FROM age(%s, nascimento))::int END AS idade,
               count(*) AS n
          FROM reserva_clientes GROUP BY 1, 2""", (hoje,))
    generos = {"FEMININO": 0, "MASCULINO": 0, None: 0}
    faixas = {r: {"faixa": r, "FEMININO": 0, "MASCULINO": 0, "outros": 0}
              for r in ["<15"] + [r for _, r in FAIXAS]}
    sem_idade = 0
    for x in cur.fetchall():
        g, idade, n = x["genero"], x["idade"], int(x["n"])
        generos[g] += n
        if idade is None or not 0 <= idade <= 110:
            sem_idade += n
            continue
        rotulo = "<15" if idade < 15 else next(r for i, r in reversed(FAIXAS) if idade >= i)
        faixas[rotulo][g or "outros"] += n
    lista = [f for f in faixas.values() if f["faixa"] != "<15" or any(
        f[k] for k in ("FEMININO", "MASCULINO", "outros"))]
    # A pirâmide lê de cima para baixo: os mais velhos em cima, como no LeadsFood.
    lista.reverse()
    return {
        "genero": {"feminino": generos["FEMININO"], "masculino": generos["MASCULINO"],
                   "nao_informado": generos[None]},
        "idade": [{"faixa": f["faixa"] if f["faixa"] != "<15" else "até 14",
                   "feminino": f["FEMININO"], "masculino": f["MASCULINO"],
                   "outros": f["outros"]} for f in lista],
        "sem_idade": sem_idade,
    }


def _cidades(cur) -> dict:
    """As dez maiores, pela grafia mais usada de cada uma; o resto somado; o vazio à parte.

    ⚠️ Agrupa por `lower(trim())`: "Blumenau", "blumenau" e "Blumenau " são a mesma cidade, e
    três barras para ela esconderiam a segunda colocada.
    """
    cur.execute("""
        SELECT mode() WITHIN GROUP (ORDER BY trim(cidade)) AS cidade, count(*) AS n
          FROM reserva_clientes WHERE nullif(trim(cidade), '') IS NOT NULL
         GROUP BY lower(trim(cidade)) ORDER BY 2 DESC, 1""")
    todas = [{"cidade": x["cidade"], "n": int(x["n"])} for x in cur.fetchall()]
    cur.execute("SELECT count(*) AS n FROM reserva_clientes WHERE nullif(trim(cidade), '') IS NULL")
    return {"top": todas[:TOP_CIDADES],
            "outras": sum(x["n"] for x in todas[TOP_CIDADES:]),
            "outras_cidades": max(0, len(todas) - TOP_CIDADES),
            "sem_cidade": int(cur.fetchone()["n"])}


def _origens(cur) -> list[dict]:
    cur.execute("""SELECT coalesce(nullif(trim(origem), ''), %s) AS origem, count(*) AS n
                     FROM reserva_clientes GROUP BY 1 ORDER BY 2 DESC, 1""", (SEM_ORIGEM,))
    return [{"origem": x["origem"], "n": int(x["n"])} for x in cur.fetchall()]
