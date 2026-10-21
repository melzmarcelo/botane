"""O painel de vendas — o estudo do que a casa vendeu, num recorte escolhido.

🔑 **Pedido do dono (21/10/2026):** *"gostaria de uma página de dashboard [...]
ao clicar sobre os registros das vendas na tela de início, iria para esta nova
tela, com o filtro por dia [...] pela semana, mês, período, produtos mais
vendidos, podendo ter valores e gráficos, e com base nesta estrutura de filtros,
montar um relatório que pode ser baixado"*. A tela inicial responde "como foi o
dia"; esta responde "como foi o período, e por quê".

🔑 **Uma função, duas saídas.** A tela (`GET /vendas/painel`) e o relatório
(`exportacao_catalogo`, chave `vendas`) chamam ESTA função. Duas consultas para o
mesmo número divergiriam na primeira correção feita só de um lado — e o arquivo
baixado deixaria de bater com a tela de onde ele saiu.

As regras são as do painel de início, e pelo mesmo motivo:

* ⚠️ **Receita LÍQUIDA sem recorte: a soma dos itens menos o desconto do
  cupom.** O desconto é um fato do CUPOM e sai de uma subconsulta — somá-lo no
  join com os itens o multiplicaria pelo número de linhas.
* ⚠️ **COM recorte (categoria, setor, produto), a receita é a BRUTA dos itens
  escolhidos**, e a resposta diz isso (`desconto` nulo, `bruta` verdadeiro). O
  desconto do cupom não pertence a nenhum item, e reparti-lo seria inventar.
  É a mesma regra da receita por produto do CMV, que sempre foi bruta.
* ⚠️ **Cupom cancelado e consumo interno ficam de fora** de toda soma. Os
  cancelados aparecem CONTADOS, à parte — é o que faz a conferência com o PDV
  fechar.
* ⚠️ **Ticket médio é receita ÷ CUPONS**, e nulo sem cupom. Com recorte, os
  cupons são os que TÊM item do recorte: "quanto gasta, em bebidas, quem pede
  bebida".
* ⚠️ **Número verdadeiro ou nenhum**: percentual sobre base zero vem nulo, não
  "+∞%" nem zero.
"""

from datetime import date, timedelta
from decimal import Decimal

AGRUPAMENTOS = {"dia": "Dia", "semana": "Semana", "mes": "Mês"}
ORDENS = {"receita": "Receita", "quantidade": "Quantidade"}
SEMANA = ["domingo", "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
          "sexta-feira", "sábado"]


def _f(v) -> float:
    return float(v or 0)


def _pct(parte, todo) -> float | None:
    return round(float(parte) / float(todo) * 100, 1) if todo else None


def _variacao(agora, antes) -> float | None:
    return round((float(agora) / float(antes) - 1) * 100, 1) if antes else None


def _recorte(categorias, setores, produtos) -> tuple[str, dict, bool]:
    """O filtro dos ITENS, e se há recorte."""
    p = {"cats": categorias or None, "sets": setores or None, "prods": produtos or None}
    sql = """AND (%(cats)s::int[] IS NULL OR p.id_categoria = ANY(%(cats)s))
             AND (%(sets)s::int[] IS NULL OR p.id_setor = ANY(%(sets)s))
             AND (%(prods)s::int[] IS NULL OR vi.id_produto = ANY(%(prods)s))"""
    return sql, p, bool(categorias or setores or produtos)


# ⚠️ Os itens do recorte: o JOIN com `produtos` é LEFT, e item sem vínculo
# (prato que o PDV vendeu e ninguém casou) entra sem recorte e sai com ele — sem
# categoria, ele não é "de categoria nenhuma escolhida".
_JUNTA_PRODUTO = "LEFT JOIN produtos p ON p.id = vi.id_produto"
_ITENS = f"""
  FROM vendas v
  JOIN venda_itens vi ON vi.id_venda = v.id
  {_JUNTA_PRODUTO}
 WHERE v.id_unidade = %(u)s AND v.data BETWEEN %(i)s AND %(f)s
   AND NOT v.cancelada AND NOT v.consumo_interno
"""


def _totais(cur, id_unidade: int, inicio: date, fim: date, filtro: str, par: dict,
            com_recorte: bool) -> dict:
    cur.execute(
        f"""SELECT count(DISTINCT v.id) AS cupons,
                   count(DISTINCT v.data) AS dias,
                   coalesce(sum(vi.valor_total), 0) AS bruta,
                   coalesce(sum(vi.quantidade), 0) AS itens
              {_ITENS} {filtro}""",
        {**par, "u": id_unidade, "i": inicio, "f": fim},
    )
    r = dict(cur.fetchone())
    desconto = None
    if not com_recorte:
        cur.execute(
            """SELECT coalesce(sum(desconto), 0) AS d FROM vendas
                WHERE id_unidade = %s AND data BETWEEN %s AND %s
                  AND NOT cancelada AND NOT consumo_interno""",
            (id_unidade, inicio, fim),
        )
        desconto = cur.fetchone()["d"]
    receita = Decimal(r["bruta"]) - (desconto or 0)
    return {
        "cupons": r["cupons"],
        "dias": r["dias"],
        "itens": _f(r["itens"]),
        "bruta": _f(r["bruta"]),
        "desconto": None if desconto is None else _f(desconto),
        "receita": _f(receita),
        "ticket_medio": _f(receita / r["cupons"]) if r["cupons"] else None,
        "media_por_dia": _f(receita / r["dias"]) if r["dias"] else None,
    }


def _anterior(inicio: date, fim: date) -> tuple[date, date, str]:
    """O período com que se compara.

    🔑 **Um dia compara com o MESMO dia da semana anterior**, como na tela
    inicial: terça contra terça diz se o dia foi bom, terça contra segunda não.
    Um período maior compara com o de MESMO TAMANHO logo antes dele.
    """
    if inicio == fim:
        d = inicio - timedelta(days=7)
        return d, d, "o mesmo dia da semana anterior"
    n = (fim - inicio).days + 1
    return inicio - timedelta(days=n), inicio - timedelta(days=1), \
        f"os {n} dias anteriores"


def painel(cur, id_unidade: int, inicio: date, fim: date, agrupar: str = "dia",
           categorias: list[int] | None = None, setores: list[int] | None = None,
           produtos: list[int] | None = None, ordem: str = "receita",
           limite: int = 20) -> dict:
    """Tudo o que a tela de estudo de vendas mostra, numa resposta só.

    ⚠️ Uma resposta, e não uma por quadro: painel que faz seis requisições pisca
    seis vezes e mostra número velho ao lado de número novo enquanto carrega.
    """
    agrupar = agrupar if agrupar in AGRUPAMENTOS else "dia"
    ordem = ordem if ordem in ORDENS else "receita"
    filtro, par, com_recorte = _recorte(categorias, setores, produtos)
    base = {**par, "u": id_unidade, "i": inicio, "f": fim}

    totais = _totais(cur, id_unidade, inicio, fim, filtro, par, com_recorte)

    a_ini, a_fim, a_rotulo = _anterior(inicio, fim)
    antes = _totais(cur, id_unidade, a_ini, a_fim, filtro, par, com_recorte)
    comparacao = {
        "inicio": a_ini, "fim": a_fim, "rotulo": a_rotulo,
        "receita": antes["receita"], "cupons": antes["cupons"],
        "ticket_medio": antes["ticket_medio"],
        # Nulo quando o período anterior não vendeu: "+∞%" não é número.
        "pct_receita": _variacao(totais["receita"], antes["receita"]) if antes["cupons"] else None,
        "pct_cupons": _variacao(totais["cupons"], antes["cupons"]) if antes["cupons"] else None,
        "pct_ticket": (_variacao(totais["ticket_medio"], antes["ticket_medio"])
                       if antes["ticket_medio"] and totais["ticket_medio"] is not None else None),
    }

    # Os cancelados, contados à parte — só sem recorte: "cupom cancelado de
    # bebida" não existe, o cancelamento é do cupom inteiro.
    canceladas = None
    if not com_recorte:
        cur.execute(
            """SELECT count(DISTINCT v.id) AS n, coalesce(sum(vi.valor_total), 0) AS valor
                 FROM vendas v LEFT JOIN venda_itens vi ON vi.id_venda = v.id
                WHERE v.id_unidade = %s AND v.cancelada AND v.data BETWEEN %s AND %s""",
            (id_unidade, inicio, fim),
        )
        c = cur.fetchone()
        canceladas = {"cupons": c["n"], "valor": _f(c["valor"])}

    def desconto_por(expr: str) -> dict:
        """O desconto dos cupons agrupado como o quadro — vazio com recorte.

        🔑 **Sem recorte, todo quadro é LÍQUIDO**: a soma das barras da evolução,
        do dia da semana e da hora tem de dar o total do cabeçalho, senão o painel
        discorda de si mesmo. ⚠️ Consulta PRÓPRIA sobre o cabeçalho: o join com os
        itens multiplicaria o desconto pelo número de linhas do cupom.
        """
        if com_recorte:
            return {}
        cur.execute(
            f"""SELECT {expr} AS chave, sum(v.desconto) AS d FROM vendas v
                 WHERE v.id_unidade = %(u)s AND v.data BETWEEN %(i)s AND %(f)s
                   AND NOT v.cancelada AND NOT v.consumo_interno
                 GROUP BY 1""",
            base,
        )
        return {r["chave"]: Decimal(r["d"] or 0) for r in cur.fetchall()}

    def liquido(bruta, chave, descontos: dict) -> float:
        return _f(Decimal(bruta or 0) - descontos.get(chave, 0))

    # ── a evolução no tempo ─────────────────────────────────────────────────
    # ⚠️ **Sem recorte, cada ponto também é LÍQUIDO** — senão a soma das barras
    # não daria o total do cabeçalho, e o painel discordaria de si mesmo.
    # ⚠️ `date_trunc('week')` começa na SEGUNDA (ISO), que é como a casa conta.
    trunc = {"dia": "v.data", "semana": "date_trunc('week', v.data)::date",
             "mes": "date_trunc('month', v.data)::date"}[agrupar]
    cur.execute(
        f"""SELECT {trunc} AS periodo,
                   count(DISTINCT v.id) AS cupons,
                   sum(vi.valor_total) AS bruta,
                   sum(vi.quantidade) AS itens
              {_ITENS} {filtro}
             GROUP BY 1 ORDER BY 1""",
        base,
    )
    pontos = [dict(r) for r in cur.fetchall()]
    descontos = desconto_por(trunc)
    serie = []
    for r in pontos:
        receita = Decimal(r["bruta"] or 0) - descontos.get(r["periodo"], 0)
        serie.append({"periodo": r["periodo"], "cupons": r["cupons"], "receita": _f(receita),
                      "itens": _f(r["itens"]),
                      "ticket_medio": _f(receita / r["cupons"]) if r["cupons"] else None})

    # ── dia da semana: a MÉDIA por dia, não a soma ──────────────────────────
    # ⚠️ Um mês tem cinco sábados e quatro segundas: somar faria o sábado
    # parecer melhor só por aparecer mais vezes. Divide-se pelos dias daquele
    # dia da semana que TIVERAM venda (dia fechado não é dia ruim).
    cur.execute(
        f"""SELECT extract(dow FROM v.data)::int AS dow,
                   count(DISTINCT v.data) AS dias,
                   count(DISTINCT v.id) AS cupons,
                   sum(vi.valor_total) AS bruta
              {_ITENS} {filtro}
             GROUP BY 1 ORDER BY 1""",
        base,
    )
    linhas_dow = [dict(r) for r in cur.fetchall()]
    desc_dow = desconto_por("extract(dow FROM v.data)::int")
    por_semana = []
    for r in linhas_dow:
        receita = liquido(r["bruta"], r["dow"], desc_dow)
        por_semana.append({
            "dia_semana": r["dow"], "nome": SEMANA[r["dow"]], "dias": r["dias"],
            "cupons": r["cupons"], "receita": receita,
            "media_receita": receita / r["dias"],
            "media_cupons": r["cupons"] / r["dias"],
        })

    # ── hora do cupom ───────────────────────────────────────────────────────
    # ⚠️ Venda digitada não tem hora (nunca "00:00"): ela é contada à parte, e
    # não empilhada na meia-noite.
    cur.execute(
        f"""SELECT extract(hour FROM v.hora)::int AS hora,
                   count(DISTINCT v.id) AS cupons, sum(vi.valor_total) AS bruta
              {_ITENS} {filtro}
             GROUP BY 1 ORDER BY 1""",
        base,
    )
    linhas_hora = [dict(r) for r in cur.fetchall()]
    desc_hora = desconto_por("extract(hour FROM v.hora)::int")
    por_hora, sem_hora = [], None
    for r in linhas_hora:
        linha = {"hora": r["hora"], "cupons": r["cupons"],
                 "receita": liquido(r["bruta"], r["hora"], desc_hora)}
        if r["hora"] is None:
            sem_hora = linha
        else:
            por_hora.append(linha)

    # ── os grupos: categoria e setor ────────────────────────────────────────
    def grupos(coluna: str, tabela: str, sem: str) -> list[dict]:
        juncao = _ITENS.replace(
            _JUNTA_PRODUTO, f"{_JUNTA_PRODUTO} LEFT JOIN {tabela} g ON g.id = p.{coluna}")
        cur.execute(
            f"""SELECT g.id, coalesce(g.nome, '{sem}') AS nome,
                       count(DISTINCT v.id) AS cupons,
                       sum(vi.quantidade) AS quantidade, sum(vi.valor_total) AS receita
                  {juncao} {filtro}
                 GROUP BY g.id, g.nome ORDER BY receita DESC""",
            base,
        )
        linhas = [dict(r) for r in cur.fetchall()]
        total = sum(_f(l["receita"]) for l in linhas)
        return [{"id": l["id"], "nome": l["nome"], "cupons": l["cupons"],
                 "quantidade": _f(l["quantidade"]), "receita": _f(l["receita"]),
                 "participacao_pct": _pct(l["receita"], total)} for l in linhas]

    por_categoria = grupos("id_categoria", "categorias", "Sem categoria")
    por_setor = grupos("id_setor", "setores", "Sem setor")

    # ── os produtos ─────────────────────────────────────────────────────────
    # ⚠️ **Item sem vínculo agrupa pelo CÓDIGO do PDV**, não some num "Sem
    # vínculo" só: dez pratos diferentes sem cadastro não são um prato.
    # ⚠️ A participação é sobre a receita BRUTA dos itens — a dos produtos não
    # tem desconto (ver o topo do arquivo), e dividir bruto por líquido daria
    # uma soma acima de 100%.
    ordem_sql = "receita DESC, quantidade DESC" if ordem == "receita" \
        else "quantidade DESC, receita DESC"
    juncao = _ITENS.replace(
        _JUNTA_PRODUTO, f"{_JUNTA_PRODUTO} LEFT JOIN categorias c ON c.id = p.id_categoria "
                        "LEFT JOIN setores s ON s.id = p.id_setor")
    sem_vinculo = ("CASE WHEN vi.id_produto IS NULL "
                   "THEN coalesce(vi.codigo_pdv, vi.descricao_pdv) END")
    cur.execute(
        f"""SELECT vi.id_produto, {sem_vinculo} AS codigo_pdv,
                   max(p.codigo) AS codigo,
                   coalesce(max(p.nome), max(vi.descricao_pdv), max(vi.codigo_pdv),
                            'Sem vínculo') AS produto,
                   max(p.nome_curto) AS produto_curto,
                   max(c.nome) AS categoria, max(s.nome) AS setor,
                   count(DISTINCT v.id) AS cupons,
                   sum(vi.quantidade) AS quantidade, sum(vi.valor_total) AS receita,
                   count(*) OVER () AS total_linhas
              {juncao} {filtro}
             GROUP BY vi.id_produto, {sem_vinculo}
             ORDER BY {ordem_sql}
             LIMIT %(lim)s""",
        {**base, "lim": limite},
    )
    rows = [dict(r) for r in cur.fetchall()]
    produtos_saida = [{
        "id_produto": r["id_produto"], "codigo": r["codigo"] or r["codigo_pdv"],
        "produto": r["produto"], "produto_curto": r["produto_curto"],
        "categoria": r["categoria"], "setor": r["setor"],
        "cupons": r["cupons"], "quantidade": _f(r["quantidade"]),
        "receita": _f(r["receita"]),
        "preco_medio": _f(r["receita"]) / _f(r["quantidade"]) if _f(r["quantidade"]) else None,
        "participacao_pct": _pct(r["receita"], totais["bruta"]),
    } for r in rows]

    return {
        "inicio": inicio, "fim": fim, "agrupar": agrupar, "ordem": ordem,
        "recorte": com_recorte, "bruta": com_recorte,
        "totais": totais, "comparacao": comparacao, "canceladas": canceladas,
        "serie": serie, "por_dia_semana": por_semana,
        "por_hora": por_hora, "sem_hora": sem_hora,
        "por_categoria": por_categoria, "por_setor": por_setor,
        "produtos": produtos_saida,
        "produtos_total": rows[0]["total_linhas"] if rows else 0,
    }
