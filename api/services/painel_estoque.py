"""O painel de estoque — a visão para decidir, não para conferir linha a linha.

🔑 **Pedido do dono (22/10/2026):** *"gostaria de algo assim [o painel de vendas] para o
estoque, para ter uma visão geral de como está o estoque em uma tela mais intuitiva e fácil
para tomada de decisão"* — com três perguntas: o que está negativo ou abaixo do mínimo (e, ao
clicar, a listagem para agir), como anda cada produto (gráfico e dados fáceis) e onde estão
as perdas e por quê.

As três respostas moram aqui, e as regras são as do resto do módulo:

* 🔑 **O número do cartão é o número da listagem.** "Abaixo do mínimo" é por PRODUTO (a soma
  das prateleiras da loja, como `saldos-agrupados?abaixo_do_minimo`), e "negativo" é por
  PRATELEIRA (como `saldos?negativos`): o cartão leva para a lista, e a lista tem de ter
  exatamente o que o cartão contou. O alerta da tela inicial usa as MESMAS consultas
  (`contagens`), senão três lugares diriam três números.
* ⚠️ **Perda e consumo são LÍQUIDOS de estorno**, como no CMV (`cmv._soma_movimentos`): a perda
  lançada por engano e estornada não pode aparecer como perda. O estorno entra na data DELE,
  com os atributos do movimento ORIGINAL (motivo, produto, prateleira).
* ⚠️ **A fotografia do saldo numa data é o ÚLTIMO movimento da corrente** antes dela —
  `coalesce(ordem_cadeia, id)`, a regra das sete leituras de `estoque.md`. Ordenar por `id`
  reabriria o defeito do retroativo reprocessado.
* ⚠️ **Número verdadeiro ou nenhum**: cobertura sem consumo é nula (não "infinita"), e
  percentual sobre base zero também.
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import relogio
from services import estoque as motor

AGRUPAMENTOS = ("dia", "semana", "mes")

# O que CONSOME o estoque — é a base do "consumo por dia" e da cobertura. ⚠️ Fora ficam a
# transferência (muda de lugar, não some), o ajuste de inventário (é correção, não uso) e
# a conversão de unidade (é a mesma mercadoria).
CONSUMO = ("SAIDA_VENDA", "SAIDA_PRODUCAO", "SAIDA_PERDA", "SAIDA_CONSUMO_INTERNO")

# Sem saída de consumo há este tempo, o produto conta como PARADO.
DIAS_PARADO = 60

# As origens de uma perda, em palavras: é o que diz por qual porta ela entrou.
ORIGENS_PERDA = {
    "MANUAL": "Lançada em Ajustes",
    "ETIQUETA": "Descarte pela etiqueta",
    "REMESSA": "Remessa que não chegou",
    "INVENTARIO": "Inventário",
}


def _f(v) -> float:
    return float(v or 0)


def _pct(parte, todo) -> float | None:
    return round(float(parte) / float(todo) * 100, 1) if todo else None


def _variacao(agora, antes) -> float | None:
    return round((float(agora) / float(antes) - 1) * 100, 1) if antes else None


def _limite(fim: date) -> datetime:
    """O instante logo depois do fim: `data_movimento` guarda a HORA, e `<= fim` cortaria
    o que foi lançado às 14h do próprio dia (a regra do razão)."""
    return datetime.combine(fim + timedelta(days=1), time.min)


# ------------------------------------------------------------------ as contagens

# ⚠️ As três condições vivem UMA vez, aqui: o painel, o alerta da tela inicial e o filtro
# da listagem de saldos contam a mesma coisa.
SQL_NEGATIVOS = """
    SELECT count(*) AS prateleiras, count(DISTINCT s.id_produto) AS produtos
      FROM estoque_saldos s JOIN produtos p ON p.id = s.id_produto
     WHERE s.id_unidade = %s AND p.ativo AND s.quantidade < 0"""

SQL_ABAIXO = """
    SELECT count(*) AS produtos FROM (
        SELECT s.id_produto FROM estoque_saldos s JOIN produtos p ON p.id = s.id_produto
         WHERE s.id_unidade = %s AND p.ativo AND p.estoque_minimo IS NOT NULL
         GROUP BY s.id_produto, p.estoque_minimo
        HAVING sum(s.quantidade) < p.estoque_minimo) x"""


def contagens(cur, id_unidade: int) -> dict:
    """Quantas prateleiras estão negativas (em quantos produtos) e quantos produtos estão
    abaixo do mínimo. Ver o cabeçalho do módulo: é o número que o cartão, o alerta e a
    listagem compartilham."""
    cur.execute(SQL_NEGATIVOS, (id_unidade,))
    neg = cur.fetchone()
    cur.execute(SQL_ABAIXO, (id_unidade,))
    abaixo = cur.fetchone()
    return {"negativos": {"prateleiras": neg["prateleiras"], "produtos": neg["produtos"]},
            "abaixo_do_minimo": abaixo["produtos"]}


# ------------------------------------------------------------------ líquido de estorno

def _movimentos_liquidos(tipos_param: str) -> str:
    """Os movimentos destes tipos no período, e os ESTORNOS deles com sinal trocado.

    O estorno herda do original o tipo, o motivo e a origem — é o original que diz o que
    a coisa foi; o estorno só a desfaz.
    """
    return f"""
        SELECT m.id, m.id_produto, m.id_local, m.data_movimento, m.tipo,
               abs(m.quantidade) AS qtd, abs(m.custo_total) AS valor, 1 AS sinal,
               m.id_motivo_perda, m.origem_tipo, m.observacao, m.id_usuario
          FROM estoque_movimentos m
         WHERE m.id_unidade = %(u)s AND m.tipo = ANY({tipos_param})
           AND m.data_movimento >= %(i)s AND m.data_movimento < %(lim)s
        UNION ALL
        SELECT e.id, e.id_produto, e.id_local, e.data_movimento, o.tipo,
               -abs(e.quantidade), -abs(e.custo_total), -1,
               o.id_motivo_perda, o.origem_tipo, o.observacao, e.id_usuario
          FROM estoque_movimentos e
          JOIN estoque_movimentos o ON o.id = e.id_estorno_de
         WHERE e.id_unidade = %(u)s AND o.tipo = ANY({tipos_param})
           AND e.data_movimento >= %(i)s AND e.data_movimento < %(lim)s"""


def _consumo_por_produto(cur, id_unidade: int, dias: int,
                         ids: list[int] | None = None) -> dict[int, float]:
    """Quanto cada produto CONSUMIU nos últimos `dias` dias (líquido), na unidade de estoque."""
    fim = relogio.hoje_da_casa()
    inicio = fim - timedelta(days=dias - 1)
    cur.execute(
        f"""SELECT x.id_produto, sum(x.qtd) AS qtd
              FROM ({_movimentos_liquidos('%(tipos)s')}) x
             WHERE (%(ids)s::int[] IS NULL OR x.id_produto = ANY(%(ids)s))
             GROUP BY x.id_produto""",
        {"u": id_unidade, "i": inicio, "lim": _limite(fim), "tipos": list(CONSUMO),
         "ids": ids},
    )
    return {r["id_produto"]: _f(r["qtd"]) for r in cur.fetchall()}


# ------------------------------------------------------------------ visão geral

def visao_geral(cur, id_unidade: int, limite: int = 15) -> dict:
    """Os números que pedem decisão, cada um com a lista dos mais urgentes.

    ⚠️ As listas são as do TOPO (`limite`), e o total vem junto: a lista inteira é a da
    tela de Saldos, para onde o cartão leva.
    """
    hoje = relogio.hoje_da_casa()
    cont = contagens(cur, id_unidade)

    # --- o patrimônio: tudo o que está em estoque_saldos (o estoque final do CMV)
    cur.execute(
        """SELECT coalesce(sum(s.quantidade * s.custo_medio), 0) AS valor,
                  -- ⚠️ Dito à parte: o total conta o INATIVO que ainda tem saldo (como o
                  -- CMV), e as listas de Saldos não — a armadilha de 01/09 em `estoque.md`.
                  coalesce(sum(s.quantidade * s.custo_medio) FILTER (WHERE NOT p.ativo), 0)
                      AS valor_inativos,
                  count(DISTINCT s.id_produto) FILTER (WHERE s.quantidade > 0 AND p.ativo)
                      AS produtos
             FROM estoque_saldos s JOIN produtos p ON p.id = s.id_produto
            WHERE s.id_unidade = %s""", (id_unidade,))
    patrimonio = cur.fetchone()

    # --- negativos: por prateleira, o mais negativo em valor primeiro
    cur.execute(
        """SELECT s.id_produto, p.codigo, p.nome AS produto, p.um_estoque,
                  s.id_local, l.nome AS local, s.quantidade, s.custo_medio,
                  round(s.quantidade * s.custo_medio, 2) AS valor,
                  (SELECT max(m.data_movimento) FROM estoque_movimentos m
                    WHERE m.id_unidade = s.id_unidade AND m.id_local = s.id_local
                      AND m.id_produto = s.id_produto) AS ultimo_movimento
             FROM estoque_saldos s
             JOIN produtos p ON p.id = s.id_produto
             JOIN locais_estoque l ON l.id = s.id_local
            WHERE s.id_unidade = %s AND p.ativo AND s.quantidade < 0
            ORDER BY s.quantidade * s.custo_medio, s.quantidade
            LIMIT %s""", (id_unidade, limite))
    negativos = [{**dict(r), "quantidade": _f(r["quantidade"]),
                  "custo_medio": _f(r["custo_medio"]), "valor": _f(r["valor"])}
                 for r in cur.fetchall()]

    # --- abaixo do mínimo: por produto, com o que ajuda a decidir
    cur.execute(
        """SELECT p.id AS id_produto, p.codigo, p.nome AS produto, p.um_estoque,
                  p.estoque_minimo, sum(s.quantidade) AS saldo,
                  -- O custo prudente: o ponderado do que tem, senão o maior conhecido.
                  coalesce(
                    sum(s.quantidade * s.custo_medio) FILTER (
                        WHERE s.quantidade > 0 AND s.custo_medio > 0)
                    / nullif(sum(s.quantidade) FILTER (
                        WHERE s.quantidade > 0 AND s.custo_medio > 0), 0),
                    max(s.custo_medio) FILTER (WHERE s.custo_medio > 0)) AS custo,
                  (p.producao_propria AND p.modo_producao = 'PARA_ESTOQUE') AS produz,
                  (SELECT f.nome FROM produto_fornecedor pf
                     JOIN fornecedores f ON f.id = pf.id_fornecedor
                    WHERE pf.id_produto = p.id
                    ORDER BY pf.preferencial DESC, f.nome LIMIT 1) AS fornecedor
             FROM estoque_saldos s JOIN produtos p ON p.id = s.id_produto
            WHERE s.id_unidade = %s AND p.ativo AND p.estoque_minimo IS NOT NULL
            GROUP BY p.id, p.codigo, p.nome, p.um_estoque, p.estoque_minimo,
                     p.producao_propria, p.modo_producao
           HAVING sum(s.quantidade) < p.estoque_minimo""", (id_unidade,))
    abaixo = [dict(r) for r in cur.fetchall()]
    consumo = _consumo_por_produto(cur, id_unidade, 30, [a["id_produto"] for a in abaixo])
    for a in abaixo:
        saldo, minimo = _f(a["saldo"]), _f(a["estoque_minimo"])
        por_dia = consumo.get(a["id_produto"], 0) / 30
        faltam = minimo - saldo
        a.update({
            "saldo": saldo, "estoque_minimo": minimo, "faltam": faltam,
            "custo": _f(a["custo"]) if a["custo"] is not None else None,
            "consumo_dia": round(por_dia, 4) if por_dia > 0 else None,
            # ⚠️ Nula sem consumo: "infinito" não é número, e zero diria que acabou.
            "cobertura_dias": (round(max(saldo, 0) / por_dia, 1) if por_dia > 0 else None),
            "valor_repor": round(faltam * _f(a["custo"]), 2) if a["custo"] else None,
            "acao": "produzir" if a.pop("produz") else "comprar",
        })
    # O que acaba primeiro vem primeiro: a menor cobertura; sem consumo, pela proporção.
    abaixo.sort(key=lambda a: (a["cobertura_dias"] is None,
                               a["cobertura_dias"] if a["cobertura_dias"] is not None
                               else a["saldo"] / (a["estoque_minimo"] or 1)))

    # --- vencidos e vencendo (a mesma janela dos alertas)
    cur.execute("SELECT alerta_validade_dias FROM parametros WHERE id_unidade = %s",
                (id_unidade,))
    dias_validade = (cur.fetchone() or {}).get("alerta_validade_dias") or 15
    cur.execute(
        """SELECT count(*) FILTER (WHERE el.validade < current_date) AS vencidos,
                  coalesce(sum(el.quantidade * s.custo_medio)
                           FILTER (WHERE el.validade < current_date), 0) AS valor_vencidos,
                  count(*) FILTER (WHERE el.validade >= current_date
                                     AND el.validade <= current_date + %s) AS vencendo,
                  coalesce(sum(el.quantidade * s.custo_medio)
                           FILTER (WHERE el.validade >= current_date
                                     AND el.validade <= current_date + %s), 0) AS valor_vencendo
             FROM estoque_lotes el
             LEFT JOIN estoque_saldos s ON s.id_produto = el.id_produto
                   AND s.id_local = el.id_local AND s.id_unidade = el.id_unidade
            WHERE el.id_unidade = %s AND el.quantidade > 0 AND el.validade IS NOT NULL""",
        (dias_validade, dias_validade, id_unidade))
    validade = cur.fetchone()

    # --- parado: tem saldo e não sai há DIAS_PARADO dias
    cur.execute(
        """WITH saldo AS (
               SELECT s.id_produto, sum(s.quantidade) AS qtd,
                      sum(s.quantidade * s.custo_medio) AS valor
                 FROM estoque_saldos s JOIN produtos p ON p.id = s.id_produto
                WHERE s.id_unidade = %(u)s AND p.ativo
                GROUP BY s.id_produto HAVING sum(s.quantidade) > 0),
           ultima AS (
               SELECT m.id_produto, max(m.data_movimento) AS em
                 FROM estoque_movimentos m
                WHERE m.id_unidade = %(u)s AND m.tipo = ANY(%(tipos)s)
                  AND m.id_estorno_de IS NULL
                GROUP BY m.id_produto)
           SELECT sa.id_produto, p.codigo, p.nome AS produto, p.um_estoque,
                  sa.qtd AS quantidade, round(sa.valor, 2) AS valor, u.em AS ultima_saida
             FROM saldo sa
             JOIN produtos p ON p.id = sa.id_produto
             LEFT JOIN ultima u ON u.id_produto = sa.id_produto
            WHERE u.em IS NULL OR u.em < %(corte)s
            ORDER BY sa.valor DESC""",
        {"u": id_unidade, "tipos": list(CONSUMO),
         "corte": datetime.combine(hoje - timedelta(days=DIAS_PARADO), time.min)})
    parados = [{**dict(r), "quantidade": _f(r["quantidade"]), "valor": _f(r["valor"])}
               for r in cur.fetchall()]

    # --- perdas do mês corrente, contra o mesmo número de dias logo antes
    ini_mes = hoje.replace(day=1)
    perdas_mes = _totais_perda(cur, id_unidade, ini_mes, hoje, {})
    a_ini, a_fim = _anterior(ini_mes, hoje)
    perdas_antes = _totais_perda(cur, id_unidade, a_ini, a_fim, {})

    # --- onde está o dinheiro: valor por categoria do produto
    # 🔑 **Inclusive o inativo, e numa linha PRÓPRIA**: a soma das barras é o valor do
    # cartão. Medido na base local: sem eles o cartão dizia R$ 97 mil e as barras R$ 15 mil,
    # e nada na tela explicava a diferença.
    cur.execute(
        """SELECT CASE WHEN p.ativo THEN c.id END AS id,
                  CASE WHEN NOT p.ativo THEN 'Produtos inativos (ainda com saldo)'
                       ELSE coalesce(c.nome, 'Sem categoria') END AS nome,
                  sum(s.quantidade * s.custo_medio) AS valor,
                  count(DISTINCT s.id_produto) FILTER (WHERE s.quantidade > 0) AS produtos
             FROM estoque_saldos s
             JOIN produtos p ON p.id = s.id_produto
             LEFT JOIN categorias c ON c.id = p.id_categoria
            WHERE s.id_unidade = %s
            GROUP BY 1, 2
           HAVING sum(s.quantidade * s.custo_medio) > 0
            ORDER BY 3 DESC""", (id_unidade,))
    por_categoria = [{**dict(r), "valor": _f(r["valor"])} for r in cur.fetchall()]
    total_cat = sum(c["valor"] for c in por_categoria)
    for c in por_categoria:
        c["participacao_pct"] = _pct(c["valor"], total_cat)

    return {
        "hoje": hoje,
        "valor_estoque": _f(patrimonio["valor"]),
        "valor_inativos": round(_f(patrimonio["valor_inativos"]), 2),
        "produtos_com_saldo": patrimonio["produtos"],
        "negativos": {**cont["negativos"], "lista": negativos},
        "abaixo_do_minimo": {"produtos": cont["abaixo_do_minimo"],
                             "valor_repor": round(sum(a["valor_repor"] or 0 for a in abaixo), 2),
                             "lista": abaixo[:limite]},
        "validade": {"dias": dias_validade, "vencidos": validade["vencidos"],
                     "valor_vencidos": _f(validade["valor_vencidos"]),
                     "vencendo": validade["vencendo"],
                     "valor_vencendo": _f(validade["valor_vencendo"])},
        "parados": {"dias": DIAS_PARADO, "produtos": len(parados),
                    "valor": round(sum(p["valor"] for p in parados), 2),
                    "lista": parados[:limite]},
        "perdas_mes": {"inicio": ini_mes, "fim": hoje, "valor": perdas_mes["valor"],
                       "ocorrencias": perdas_mes["ocorrencias"],
                       "valor_anterior": perdas_antes["valor"],
                       "pct_variacao": (_variacao(perdas_mes["valor"], perdas_antes["valor"])
                                        if perdas_antes["valor"] else None)},
        "por_categoria": por_categoria,
    }


# ------------------------------------------------------------------ por produto

def _inicios(inicio: date, fim: date, agrupar: str) -> list[date]:
    """O começo de cada ponto do gráfico, do primeiro que contém `inicio` até `fim`."""
    if agrupar == "mes":
        d = inicio.replace(day=1)
    elif agrupar == "semana":
        d = inicio - timedelta(days=inicio.weekday())   # a semana da casa começa na segunda
    else:
        d = inicio
    pontos = []
    while d <= fim:
        pontos.append(d)
        if agrupar == "mes":
            d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        else:
            d += timedelta(days=7 if agrupar == "semana" else 1)
    return pontos


def produto(cur, id_unidade: int, id_produto: int, inicio: date, fim: date,
            agrupar: str = "dia") -> dict | None:
    """Como anda o estoque de UM produto: hoje, no período e no gráfico."""
    agrupar = agrupar if agrupar in AGRUPAMENTOS else "dia"
    cur.execute(
        """SELECT p.id, p.codigo, p.nome, p.nome_curto, p.um_estoque, p.estoque_minimo,
                  p.controla_estoque, p.producao_propria, p.modo_producao, p.ativo, p.status,
                  c.nome AS categoria, se.nome AS setor
             FROM produtos p
             LEFT JOIN categorias c ON c.id = p.id_categoria
             LEFT JOIN setores se ON se.id = p.id_setor
            WHERE p.id = %s""", (id_produto,))
    cad = cur.fetchone()
    if not cad:
        return None
    cad = {**dict(cad), "estoque_minimo": (_f(cad["estoque_minimo"])
                                            if cad["estoque_minimo"] is not None else None)}

    # --- hoje, por prateleira
    cur.execute(
        """SELECT s.id_local, l.nome AS local, se.nome AS setor, s.quantidade, s.custo_medio,
                  round(s.quantidade * s.custo_medio, 2) AS valor
             FROM estoque_saldos s
             JOIN locais_estoque l ON l.id = s.id_local
             LEFT JOIN setores se ON se.id = l.id_setor
            WHERE s.id_unidade = %s AND s.id_produto = %s
            ORDER BY l.principal DESC, lower(l.nome)""", (id_unidade, id_produto))
    locais = [{**dict(r), "quantidade": _f(r["quantidade"]),
               "custo_medio": _f(r["custo_medio"]), "valor": _f(r["valor"])}
              for r in cur.fetchall()]
    saldo = sum(l["quantidade"] for l in locais)
    positivos = [l for l in locais if l["quantidade"] > 0 and l["custo_medio"] > 0]
    custo = (sum(l["quantidade"] * l["custo_medio"] for l in positivos)
             / sum(l["quantidade"] for l in positivos)) if positivos else (
        max((l["custo_medio"] for l in locais if l["custo_medio"] > 0), default=None))

    # --- a fotografia de antes do período, por prateleira (último da corrente)
    cur.execute(
        """SELECT DISTINCT ON (id_local) id_local, coalesce(ordem_cadeia, id) AS cadeia,
                  saldo_apos, custo_medio_apos
             FROM estoque_movimentos
            WHERE id_unidade = %s AND id_produto = %s AND data_movimento < %s
            ORDER BY id_local, coalesce(ordem_cadeia, id) DESC""",
        (id_unidade, id_produto, datetime.combine(inicio, time.min)))
    melhor: dict[int, tuple] = {r["id_local"]: (r["cadeia"], _f(r["saldo_apos"]),
                                                 _f(r["custo_medio_apos"]))
                                for r in cur.fetchall()}
    saldo_inicial = sum(v[1] for v in melhor.values())

    # --- os movimentos do período
    cur.execute(
        """SELECT m.id, m.data_movimento, m.tipo, m.quantidade, m.custo_total,
                  m.custo_unitario, m.id_local, l.nome AS local,
                  coalesce(m.ordem_cadeia, m.id) AS cadeia, m.saldo_apos, m.custo_medio_apos,
                  m.documento, m.observacao, m.id_estorno_de, pm.nome AS motivo
             FROM estoque_movimentos m
             JOIN locais_estoque l ON l.id = m.id_local
             LEFT JOIN perda_motivos pm ON pm.id = m.id_motivo_perda
            WHERE m.id_unidade = %s AND m.id_produto = %s
              AND m.data_movimento >= %s AND m.data_movimento < %s
            ORDER BY m.data_movimento, coalesce(m.ordem_cadeia, m.id)""",
        (id_unidade, id_produto, datetime.combine(inicio, time.min), _limite(fim)))
    movs = [dict(r) for r in cur.fetchall()]

    # --- a série: entradas, saídas e o saldo ao FIM de cada ponto
    # 🔑 O conjunto "o que aconteceu antes do fim do ponto" só cresce, então o último da
    # corrente de cada prateleira se acompanha numa passada só (máximo de `cadeia`).
    pontos = _inicios(inicio, fim, agrupar)
    serie, k = [], 0
    for n, p_ini in enumerate(pontos):
        p_fim = pontos[n + 1] if n + 1 < len(pontos) else fim + timedelta(days=1)
        ent = sai = ent_v = sai_v = 0.0
        # ⚠️ `.date()` na hora da CASA: a sessão do banco está em America/Sao_Paulo.
        while k < len(movs) and movs[k]["data_movimento"].date() < p_fim:
            m = movs[k]
            q = _f(m["quantidade"])
            if m["id_estorno_de"] is not None:
                # ⚠️ O estorno DESFAZ o original, não é um movimento novo: a devolução de
                # uma saída tira das saídas, e a de uma entrada tira das entradas — senão
                # as barras discordam do "por tipo", que é líquido.
                if q > 0:
                    sai -= q
                    sai_v -= abs(_f(m["custo_total"]))
                else:
                    ent -= -q
                    ent_v -= abs(_f(m["custo_total"]))
            elif m["tipo"] != motor.AJUSTE_CUSTO:
                if q > 0:
                    ent += q
                    ent_v += abs(_f(m["custo_total"]))
                else:
                    sai += -q
                    sai_v += abs(_f(m["custo_total"]))
            atual = melhor.get(m["id_local"])
            if atual is None or m["cadeia"] > atual[0]:
                melhor[m["id_local"]] = (m["cadeia"], _f(m["saldo_apos"]),
                                         _f(m["custo_medio_apos"]))
            k += 1
        saldo_fim = sum(v[1] for v in melhor.values())
        ultimo = max(melhor.values(), default=None, key=lambda v: v[0])
        serie.append({"periodo": p_ini, "entradas": round(ent, 4), "saidas": round(sai, 4),
                      "valor_entradas": round(ent_v, 2), "valor_saidas": round(sai_v, 2),
                      "saldo": round(saldo_fim, 4),
                      "custo_medio": round(ultimo[2], 6) if ultimo else None})

    # --- por tipo de movimento, LÍQUIDO de estorno (o estorno some na linha do original)
    cur.execute(
        f"""SELECT x.tipo, sum(x.qtd) AS qtd, sum(x.valor) AS valor,
                   count(*) FILTER (WHERE x.sinal = 1) - count(*) FILTER (WHERE x.sinal = -1)
                       AS vezes
              FROM ({_movimentos_liquidos('%(tipos)s')}) x
             WHERE x.id_produto = %(p)s
             GROUP BY x.tipo HAVING sum(x.qtd) <> 0 OR sum(x.valor) <> 0""",
        {"u": id_unidade, "i": datetime.combine(inicio, time.min), "lim": _limite(fim),
         # ⚠️ Os estornos saem da lista: eles entram pela segunda metade da união, na linha
         # do tipo ORIGINAL — listados aqui, contariam duas vezes.
         "tipos": sorted((motor.ENTRADAS | motor.SAIDAS)
                         - {"ESTORNO_ENTRADA", "ESTORNO_SAIDA"}),
         "p": id_produto})
    por_tipo = sorted(
        [{"tipo": r["tipo"], "rotulo": motor.ROTULOS.get(r["tipo"], r["tipo"]),
          "entrada": r["tipo"] in motor.ENTRADAS, "quantidade": _f(r["qtd"]),
          "valor": _f(r["valor"]), "vezes": r["vezes"]} for r in cur.fetchall()],
        key=lambda t: (not t["entrada"], -t["valor"]))

    dias = (fim - inicio).days + 1
    consumo = sum(t["quantidade"] for t in por_tipo if t["tipo"] in CONSUMO)
    consumo_valor = sum(t["valor"] for t in por_tipo if t["tipo"] in CONSUMO)
    perda = next((t for t in por_tipo if t["tipo"] == "SAIDA_PERDA"), None)
    compras = [t for t in por_tipo if t["tipo"] in ("ENTRADA_NF", "ENTRADA_MANUAL")]
    por_dia = consumo / dias if consumo > 0 else 0

    # --- a última entrada que trouxe mercadoria (de qualquer data)
    cur.execute(
        """SELECT m.data_movimento, m.tipo, m.quantidade, m.custo_unitario, m.documento
             FROM estoque_movimentos m
            WHERE m.id_unidade = %s AND m.id_produto = %s
              AND m.tipo IN ('ENTRADA_NF', 'ENTRADA_MANUAL', 'ENTRADA_PRODUCAO')
              AND m.id_estorno_de IS NULL
              AND NOT EXISTS (SELECT 1 FROM estoque_movimentos e WHERE e.id_estorno_de = m.id)
            ORDER BY m.data_movimento DESC LIMIT 1""", (id_unidade, id_produto))
    ult = cur.fetchone()

    return {
        "produto": cad,
        "inicio": inicio, "fim": fim, "agrupar": agrupar, "dias": dias,
        "atual": {"saldo": saldo, "custo_medio": round(custo, 6) if custo else None,
                  "valor": round(sum(l["valor"] for l in locais), 2), "locais": locais,
                  "abaixo_do_minimo": (cad["estoque_minimo"] is not None
                                       and saldo < cad["estoque_minimo"])},
        "indicadores": {
            "saldo_inicial": round(saldo_inicial, 4),
            "consumo": round(consumo, 4), "consumo_valor": round(consumo_valor, 2),
            "consumo_dia": round(por_dia, 4) if por_dia else None,
            "cobertura_dias": round(max(saldo, 0) / por_dia, 1) if por_dia else None,
            "compras": round(sum(t["quantidade"] for t in compras), 4),
            "compras_valor": round(sum(t["valor"] for t in compras), 2),
            "perda": perda["quantidade"] if perda else 0,
            "perda_valor": perda["valor"] if perda else 0,
            "perda_pct_do_consumo": _pct(perda["valor"], consumo_valor) if perda else None,
            "ultima_entrada": ({**dict(ult), "quantidade": _f(ult["quantidade"]),
                                "custo_unitario": _f(ult["custo_unitario"]),
                                "rotulo": motor.ROTULOS.get(ult["tipo"], ult["tipo"])}
                               if ult else None),
        },
        "serie": serie,
        "por_tipo": por_tipo,
        "ultimos": [{"id": m["id"], "data_movimento": m["data_movimento"], "tipo": m["tipo"],
                     "rotulo": motor.ROTULOS.get(m["tipo"], m["tipo"]),
                     "quantidade": _f(m["quantidade"]), "valor": abs(_f(m["custo_total"])),
                     "local": m["local"], "saldo_apos": _f(m["saldo_apos"]),
                     "documento": m["documento"], "motivo": m["motivo"],
                     "observacao": m["observacao"], "estorno": m["id_estorno_de"] is not None}
                    for m in reversed(movs[-15:])],
        "movimentos_no_periodo": len(movs),
    }


# ------------------------------------------------------------------ perdas

def _anterior(inicio: date, fim: date) -> tuple[date, date]:
    """O período de MESMO tamanho logo antes — a comparação do painel de vendas."""
    n = (fim - inicio).days + 1
    return inicio - timedelta(days=n), inicio - timedelta(days=1)


def _filtro_perda(f: dict, com_motivo: bool = True) -> tuple[str, dict]:
    """O recorte das perdas. ⚠️ `motivo = 0` é "sem motivo", que também é uma resposta.

    `com_motivo=False` é o mesmo recorte para o que NÃO é perda (o consumo e a contagem do
    mesmo pedaço da casa): ali o motivo não existe, e filtrar por ele zeraria tudo.
    """
    motivo = """AND (%(motivo)s::int IS NULL
                  OR (%(motivo)s = 0 AND x.id_motivo_perda IS NULL)
                  OR x.id_motivo_perda = %(motivo)s)""" if com_motivo else ""
    sql = motivo + """
             AND (%(categoria)s::int IS NULL OR p.id_categoria = %(categoria)s)
             AND (%(setor)s::int IS NULL OR coalesce(l.id_setor, p.id_setor) = %(setor)s)
             AND (%(local)s::int IS NULL OR x.id_local = %(local)s)
             AND (%(produto)s::int IS NULL OR x.id_produto = %(produto)s)"""
    return sql, {k: f.get(k) for k in ("motivo", "categoria", "setor", "local", "produto")}


def _perdas_sql(filtro: str) -> str:
    return f"""
        FROM ({_movimentos_liquidos("ARRAY['SAIDA_PERDA']::varchar[]")}) x
        JOIN produtos p ON p.id = x.id_produto
        JOIN locais_estoque l ON l.id = x.id_local
        WHERE true {filtro}"""


def _totais_perda(cur, id_unidade: int, inicio: date, fim: date, f: dict) -> dict:
    filtro, par = _filtro_perda(f)
    cur.execute(
        f"""SELECT coalesce(sum(x.valor), 0) AS valor, coalesce(sum(x.qtd), 0) AS qtd,
                   count(*) FILTER (WHERE x.sinal = 1) - count(*) FILTER (WHERE x.sinal = -1)
                       AS ocorrencias
              {_perdas_sql(filtro)}""",
        {**par, "u": id_unidade, "i": datetime.combine(inicio, time.min),
         "lim": _limite(fim)})
    r = dict(cur.fetchone())
    # ⚠️ Produto cuja perda foi toda estornada NÃO conta: é a mesma regra da lista de
    # produtos (`HAVING sum <> 0`), e o total tem de ser o tamanho dela.
    cur.execute(
        f"""SELECT count(*) AS n FROM (SELECT x.id_produto {_perdas_sql(filtro)}
                                        GROUP BY x.id_produto HAVING sum(x.valor) <> 0) y""",
        {**par, "u": id_unidade, "i": datetime.combine(inicio, time.min),
         "lim": _limite(fim)})
    r["produtos"] = cur.fetchone()["n"]
    return {"valor": round(_f(r["valor"]), 2), "ocorrencias": r["ocorrencias"],
            "produtos": r["produtos"]}


def perdas(cur, id_unidade: int, inicio: date, fim: date, agrupar: str = "dia",
           filtros: dict | None = None, limite: int = 20) -> dict:
    """Onde a casa perde mercadoria, e por quê — num recorte escolhido.

    🔑 **O que a tela compara**: as perdas REGISTRADAS (com motivo) e as faltas da contagem
    (`AJUSTE_INVENTARIO_SAIDA`), que são perda SEM nome — ninguém viu acontecer. Quando a
    segunda é grande, o problema não é o desperdício conhecido, é o que some sem registro.
    """
    agrupar = agrupar if agrupar in AGRUPAMENTOS else "dia"
    f = filtros or {}
    filtro, par = _filtro_perda(f)
    base = {**par, "u": id_unidade, "i": datetime.combine(inicio, time.min),
            "lim": _limite(fim)}
    corpo = _perdas_sql(filtro)

    totais = _totais_perda(cur, id_unidade, inicio, fim, f)
    a_ini, a_fim = _anterior(inicio, fim)
    antes = _totais_perda(cur, id_unidade, a_ini, a_fim, f)

    # 🔑 A perda contra o CONSUMO do mesmo recorte: R$ 300 perdidos dizem pouco sozinhos;
    # 3% de tudo o que saiu diz se é muito. ⚠️ Mesmo recorte de produto/local/setor.
    filtro_sem_motivo, _ = _filtro_perda(f, com_motivo=False)
    cur.execute(
        f"""SELECT coalesce(sum(x.valor), 0) AS valor
              FROM ({_movimentos_liquidos('%(tipos)s')}) x
              JOIN produtos p ON p.id = x.id_produto
              JOIN locais_estoque l ON l.id = x.id_local
             WHERE true {filtro_sem_motivo}""",
        {**base, "tipos": list(CONSUMO)})
    consumo_valor = _f(cur.fetchone()["valor"])

    # As faltas e sobras da contagem, no mesmo recorte de produto/local/setor.
    cur.execute(
        f"""SELECT x.tipo, coalesce(sum(x.valor), 0) AS valor
              FROM ({_movimentos_liquidos('%(tipos)s')}) x
              JOIN produtos p ON p.id = x.id_produto
              JOIN locais_estoque l ON l.id = x.id_local
             WHERE true {filtro_sem_motivo}
             GROUP BY x.tipo""",
        {**base, "tipos": ["AJUSTE_INVENTARIO_SAIDA", "AJUSTE_INVENTARIO_ENTRADA"]})
    inv = {r["tipo"]: _f(r["valor"]) for r in cur.fetchall()}

    def agrupado(chave: str, nome: str, extra_join: str = "", ordem: str = "3 DESC") -> list:
        cur.execute(
            f"""SELECT {chave} AS id, {nome} AS nome, sum(x.valor) AS valor,
                       sum(x.qtd) AS qtd,
                       count(*) FILTER (WHERE x.sinal = 1)
                         - count(*) FILTER (WHERE x.sinal = -1) AS ocorrencias
                  {corpo.replace('WHERE true', extra_join + ' WHERE true', 1)}
                 GROUP BY 1, 2 HAVING sum(x.valor) <> 0
                 ORDER BY {ordem}""", base)
        linhas = [{**dict(r), "valor": round(_f(r["valor"]), 2), "qtd": _f(r["qtd"])}
                  for r in cur.fetchall()]
        for l in linhas:
            l["participacao_pct"] = _pct(l["valor"], totais["valor"])
        return linhas

    por_motivo = agrupado("coalesce(x.id_motivo_perda, 0)",
                          "coalesce(pm.nome, 'Sem motivo')",
                          "LEFT JOIN perda_motivos pm ON pm.id = x.id_motivo_perda")
    por_categoria = agrupado("p.id_categoria", "coalesce(c.nome, 'Sem categoria')",
                             "LEFT JOIN categorias c ON c.id = p.id_categoria")
    # O setor de ONDE saiu (a prateleira), e o do produto quando a prateleira não tem — a
    # regra do CMV por setor.
    por_setor = agrupado("coalesce(l.id_setor, p.id_setor)", "coalesce(se.nome, 'Sem setor')",
                         "LEFT JOIN setores se ON se.id = coalesce(l.id_setor, p.id_setor)")
    por_local = agrupado("x.id_local", "l.nome")
    por_origem = [{**o, "nome": ORIGENS_PERDA.get(o["id"], o["id"] or "Outra")}
                  for o in agrupado("coalesce(x.origem_tipo, 'MANUAL')",
                                    "coalesce(x.origem_tipo, 'MANUAL')")]

    # Os produtos, com o motivo que mais pesou em cada um.
    cur.execute(
        f"""SELECT x.id_produto, p.codigo, p.nome AS produto, p.um_estoque,
                   sum(x.valor) AS valor, sum(x.qtd) AS qtd,
                   count(*) FILTER (WHERE x.sinal = 1)
                     - count(*) FILTER (WHERE x.sinal = -1) AS ocorrencias,
                   (SELECT coalesce(pm.nome, 'Sem motivo')
                      FROM ({_movimentos_liquidos("ARRAY['SAIDA_PERDA']::varchar[]")}) y
                      LEFT JOIN perda_motivos pm ON pm.id = y.id_motivo_perda
                     WHERE y.id_produto = x.id_produto
                     GROUP BY pm.nome ORDER BY sum(y.valor) DESC LIMIT 1) AS motivo_principal
              {corpo}
             GROUP BY x.id_produto, p.codigo, p.nome, p.um_estoque
            HAVING sum(x.valor) <> 0
             ORDER BY 5 DESC""", base)
    produtos = [{**dict(r), "valor": round(_f(r["valor"]), 2), "qtd": _f(r["qtd"]),
                 "participacao_pct": _pct(r["valor"], totais["valor"])}
                for r in cur.fetchall()]

    # A evolução no tempo.
    trunc = {"dia": "day", "semana": "week", "mes": "month"}[agrupar]
    cur.execute(
        f"""SELECT date_trunc('{trunc}', x.data_movimento)::date AS periodo,
                   sum(x.valor) AS valor,
                   count(*) FILTER (WHERE x.sinal = 1)
                     - count(*) FILTER (WHERE x.sinal = -1) AS ocorrencias
              {corpo}
             GROUP BY 1 ORDER BY 1""", base)
    feitos = {r["periodo"]: r for r in cur.fetchall()}
    serie = [{"periodo": d, "valor": round(_f(feitos[d]["valor"]), 2) if d in feitos else 0.0,
              "ocorrencias": feitos[d]["ocorrencias"] if d in feitos else 0}
             for d in _inicios(inicio, fim, agrupar)]

    # As mais recentes, para ver o que foi escrito.
    cur.execute(
        f"""SELECT x.id, x.data_movimento, x.id_produto, p.nome AS produto, p.um_estoque,
                   x.qtd, x.valor, x.sinal, l.nome AS local,
                   coalesce(pm.nome, 'Sem motivo') AS motivo, x.observacao,
                   coalesce(x.origem_tipo, 'MANUAL') AS origem, u.nome AS usuario
              {corpo.replace('WHERE true', '''LEFT JOIN perda_motivos pm ON pm.id = x.id_motivo_perda
                    LEFT JOIN usuarios u ON u.id = x.id_usuario WHERE true''', 1)}
             ORDER BY x.data_movimento DESC, x.id DESC LIMIT 25""", base)
    recentes = [{**dict(r), "qtd": _f(r["qtd"]), "valor": _f(r["valor"]),
                 "estorno": r["sinal"] == -1,
                 "origem_rotulo": ORIGENS_PERDA.get(r["origem"], r["origem"])}
                for r in cur.fetchall()]
    for r in recentes:
        r.pop("sinal")

    return {
        "inicio": inicio, "fim": fim, "agrupar": agrupar,
        "recorte": any(v is not None for v in par.values()),
        "totais": {**totais, "consumo_valor": round(consumo_valor, 2),
                   "pct_do_consumo": _pct(totais["valor"], consumo_valor),
                   "faltas_inventario": round(inv.get("AJUSTE_INVENTARIO_SAIDA", 0), 2),
                   "sobras_inventario": round(inv.get("AJUSTE_INVENTARIO_ENTRADA", 0), 2)},
        "comparacao": {"inicio": a_ini, "fim": a_fim, "valor": antes["valor"],
                       "ocorrencias": antes["ocorrencias"],
                       "pct_valor": (_variacao(totais["valor"], antes["valor"])
                                     if antes["valor"] else None)},
        "serie": serie,
        "por_motivo": por_motivo,
        "por_categoria": por_categoria,
        "por_setor": por_setor,
        "por_local": por_local,
        "por_origem": por_origem,
        "produtos": produtos[:limite],
        "produtos_total": len(produtos),
        "recentes": recentes,
    }
