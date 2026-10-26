"""Os documentos que não são venda, por MOTIVO — quadros, comparativo e impressão.

🔑 **Pedido do dono (26/10/2026):** *"no painel de documentos filtros e quadros por
motivos, onde podemos realizar a impressão e comparativos"*. O motivo nasceu na 1.1.136
(migração 134): Consumo interno, Perda, Prêmio, Brinde/Aniversário e Outros.

🔑 **Uma função, duas saídas**, como o painel de vendas: a tela (`GET /vendas/motivos`)
e o relatório (`exportacao_catalogo`, chave `vendas-motivos`) chamam ESTA função — o
arquivo baixado tem de bater com a tela, número a número.

As regras:

* 🔑 **O custo é o que SAIU DO ESTOQUE** — os movimentos `SAIDA_CONSUMO_INTERNO` e
  `SAIDA_PERDA` de origem VENDA, **líquidos de estorno** (o estorno que a troca de data
  ou o cancelamento fazem). É a mesma conta das linhas de consumo interno e de perdas do
  CMV. ⚠️ A diferença: aqui o documento conta na DATA DELE, e o CMV conta o movimento na
  data do movimento — iguais, a não ser na baixa atrasada de um mês para o outro.
* ⚠️ **O custo pela FICHA vai ao lado**, congelado no item: produto que não controla
  estoque não sai do razão, e sem esse número o documento dele pareceria de graça.
* ⚠️ **O valor de referência é o preço digitado** — fica fora da receita (é isso que o
  motivo quer dizer), aparece só para informação.
* ⚠️ **Documento cancelado fica de fora** de tudo: o estorno já devolveu o estoque.
* 🔑 **A perda lançada em Ajustes entra como REFERÊNCIA**, numa linha à parte: o painel
  de Estoque é o dono dela; aqui ela serve para comparar com a perda lançada como
  documento. Só sem filtro de pessoa e com a Perda entre os motivos escolhidos.
* ⚠️ **Número verdadeiro ou nenhum**: variação sobre base zero vem nula.
"""

from datetime import date

from services.painel_vendas import _anterior

ROTULOS = {
    "CONSUMO_INTERNO": "Consumo interno",
    "PERDA": "Perda",
    "PREMIO": "Prêmio",
    "BRINDE": "Brinde/Aniversário",
    "OUTROS": "Outros",
}
AGRUPAMENTOS = {"dia": "Dia", "semana": "Semana", "mes": "Mês"}
_TIPOS = ["SAIDA_CONSUMO_INTERNO", "SAIDA_PERDA"]
_TRUNC = {"dia": "d.data", "semana": "date_trunc('week', d.data)::date",
          "mes": "date_trunc('month', d.data)::date"}

# Os documentos do recorte, e o que cada um custou. ⚠️ O estorno se acha pelo
# `id_estorno_de` (ele nasce com origem ESTORNO), como no detalhe da venda.
_DOCS = """
WITH docs AS (
    SELECT v.id, v.data, v.documento, v.motivo, v.motivo_observacao, v.id_pessoa,
           v.id_motivo_perda
      FROM vendas v
     WHERE v.id_unidade = %(u)s AND v.data BETWEEN %(i)s AND %(f)s
       AND NOT v.cancelada AND v.motivo IS NOT NULL
       AND (%(motivos)s::text[] IS NULL OR v.motivo = ANY(%(motivos)s))
       AND (%(pessoas)s::int[] IS NULL OR v.id_pessoa = ANY(%(pessoas)s))
), mov AS (
    SELECT m.origem_id AS id_venda, m.id_produto,
           abs(m.custo_total) AS custo, abs(m.quantidade) AS quantidade
      FROM estoque_movimentos m
     WHERE m.origem_tipo = 'VENDA' AND m.tipo = ANY(%(tipos)s)
       AND m.origem_id IN (SELECT id FROM docs)
    UNION ALL
    SELECT o.origem_id, o.id_produto, -abs(e.custo_total), -abs(e.quantidade)
      FROM estoque_movimentos e
      JOIN estoque_movimentos o ON o.id = e.id_estorno_de
     WHERE o.origem_tipo = 'VENDA' AND o.tipo = ANY(%(tipos)s)
       AND o.origem_id IN (SELECT id FROM docs)
), itens AS (
    SELECT vi.id_venda, sum(vi.quantidade) AS itens, sum(vi.valor_total) AS referencia,
           sum(vi.quantidade * coalesce(vi.custo_ficha_unitario, 0)) AS custo_ficha,
           count(*) FILTER (WHERE vi.custo_ficha_unitario IS NULL) AS sem_custo
      FROM venda_itens vi
     WHERE vi.id_venda IN (SELECT id FROM docs)
     GROUP BY vi.id_venda
), custo AS (
    SELECT id_venda, sum(custo) AS custo FROM mov GROUP BY id_venda
)
"""


def _f(v) -> float:
    return float(v or 0)


def _variacao(agora, antes) -> float | None:
    return round((float(agora) / float(antes) - 1) * 100, 1) if antes else None


def _par(id_unidade: int, inicio: date, fim: date, motivos, pessoas) -> dict:
    return {"u": id_unidade, "i": inicio, "f": fim, "tipos": _TIPOS,
            "motivos": list(motivos) if motivos else None,
            "pessoas": [int(p) for p in pessoas] if pessoas else None}


def _por_motivo(cur, par: dict) -> dict[str, dict]:
    cur.execute(
        _DOCS + """
        SELECT d.motivo, count(*) AS documentos,
               coalesce(sum(i.itens), 0) AS itens,
               coalesce(sum(c.custo), 0) AS custo,
               coalesce(sum(i.custo_ficha), 0) AS custo_ficha,
               coalesce(sum(i.referencia), 0) AS referencia
          FROM docs d
          LEFT JOIN itens i ON i.id_venda = d.id
          LEFT JOIN custo c ON c.id_venda = d.id
         GROUP BY d.motivo""",
        par,
    )
    return {r["motivo"]: dict(r) for r in cur.fetchall()}


def _perdas_por_ajuste(cur, id_unidade: int, inicio: date, fim: date) -> float:
    """A perda lançada FORA de documento (Ajustes, etiqueta), líquida de estorno."""
    cur.execute(
        """SELECT coalesce(sum(v), 0) AS valor FROM (
               SELECT abs(m.custo_total) AS v FROM estoque_movimentos m
                WHERE m.id_unidade = %(u)s AND m.tipo = 'SAIDA_PERDA'
                  AND m.origem_tipo IS DISTINCT FROM 'VENDA'
                  AND m.data_movimento::date BETWEEN %(i)s AND %(f)s
               UNION ALL
               SELECT -abs(e.custo_total) FROM estoque_movimentos e
                 JOIN estoque_movimentos o ON o.id = e.id_estorno_de
                WHERE e.id_unidade = %(u)s AND o.tipo = 'SAIDA_PERDA'
                  AND o.origem_tipo IS DISTINCT FROM 'VENDA'
                  AND e.data_movimento::date BETWEEN %(i)s AND %(f)s) x""",
        {"u": id_unidade, "i": inicio, "f": fim},
    )
    return _f(cur.fetchone()["valor"])


def painel(cur, id_unidade: int, inicio: date, fim: date,
           motivos: list[str] | None = None, pessoas: list[int] | None = None,
           agrupar: str = "semana", limite_documentos: int = 500) -> dict:
    """Tudo o que a tela "Por motivo" mostra, numa resposta só."""
    agrupar = agrupar if agrupar in AGRUPAMENTOS else "semana"
    motivos = [m for m in (motivos or []) if m in ROTULOS] or None
    par = _par(id_unidade, inicio, fim, motivos, pessoas)
    a_ini, a_fim, a_rotulo = _anterior(inicio, fim)
    par_a = _par(id_unidade, a_ini, a_fim, motivos, pessoas)

    agora = _por_motivo(cur, par)
    antes = _por_motivo(cur, par_a)

    linhas = []
    for m, rotulo in ROTULOS.items():
        if motivos and m not in motivos:
            continue
        x, y = agora.get(m, {}), antes.get(m, {})
        linhas.append({
            "motivo": m, "rotulo": rotulo,
            "documentos": int(x.get("documentos") or 0),
            "itens": _f(x.get("itens")),
            "custo": _f(x.get("custo")),
            "custo_ficha": _f(x.get("custo_ficha")),
            "referencia": _f(x.get("referencia")),
            "anterior": {"documentos": int(y.get("documentos") or 0),
                         "custo": _f(y.get("custo"))},
            "pct_custo": _variacao(_f(x.get("custo")), _f(y.get("custo"))),
        })

    def soma(campo, fonte):
        return sum(_f(v.get(campo)) for v in fonte.values())

    totais = {
        "documentos": int(soma("documentos", agora)),
        "itens": soma("itens", agora),
        "custo": soma("custo", agora),
        "custo_ficha": soma("custo_ficha", agora),
        "referencia": soma("referencia", agora),
    }
    comparacao = {
        "inicio": a_ini, "fim": a_fim, "rotulo": a_rotulo,
        "documentos": int(soma("documentos", antes)),
        "custo": soma("custo", antes),
        "pct_custo": _variacao(totais["custo"], soma("custo", antes)),
        "pct_documentos": _variacao(totais["documentos"], soma("documentos", antes)),
    }

    # ── a evolução, empilhada por motivo ─────────────────────────────────────
    cur.execute(
        _DOCS + f"""
        SELECT {_TRUNC[agrupar]} AS periodo, d.motivo,
               count(*) AS documentos, coalesce(sum(c.custo), 0) AS custo
          FROM docs d LEFT JOIN custo c ON c.id_venda = d.id
         GROUP BY 1, 2 ORDER BY 1""",
        par,
    )
    serie: dict = {}
    for r in cur.fetchall():
        p = serie.setdefault(r["periodo"], {"periodo": r["periodo"], "custo": 0.0,
                                            "documentos": 0, "por_motivo": {}})
        p["custo"] += _f(r["custo"])
        p["documentos"] += r["documentos"]
        p["por_motivo"][r["motivo"]] = _f(r["custo"])

    # ── o que saiu do estoque, por produto (o do MOVIMENTO: kit sai pelos componentes) ──
    cur.execute(
        _DOCS + """
        SELECT mv.id_produto, p.codigo, p.nome AS produto, p.um_estoque,
               sum(mv.quantidade) AS quantidade, sum(mv.custo) AS custo,
               count(DISTINCT mv.id_venda) AS documentos
          FROM mov mv JOIN produtos p ON p.id = mv.id_produto
         GROUP BY mv.id_produto, p.codigo, p.nome, p.um_estoque
        HAVING abs(sum(mv.custo)) >= 0.005 OR abs(sum(mv.quantidade)) > 0
         ORDER BY sum(mv.custo) DESC, p.nome""",
        par,
    )
    produtos = [{**dict(r), "quantidade": _f(r["quantidade"]), "custo": _f(r["custo"])}
                for r in cur.fetchall()]

    # ── por pessoa ───────────────────────────────────────────────────────────
    cur.execute(
        _DOCS + """
        SELECT d.id_pessoa, f.nome, count(*) AS documentos,
               coalesce(sum(c.custo), 0) AS custo,
               coalesce(sum(i.referencia), 0) AS referencia
          FROM docs d
          LEFT JOIN fornecedores f ON f.id = d.id_pessoa
          LEFT JOIN itens i ON i.id_venda = d.id
          LEFT JOIN custo c ON c.id_venda = d.id
         GROUP BY d.id_pessoa, f.nome
         ORDER BY 4 DESC, f.nome NULLS LAST""",
        par,
    )
    por_pessoa = [{"id_pessoa": r["id_pessoa"], "nome": r["nome"] or "sem pessoa",
                "documentos": r["documentos"], "custo": _f(r["custo"]),
                "referencia": _f(r["referencia"])} for r in cur.fetchall()]

    # ── a perda, pelo motivo da perda ────────────────────────────────────────
    cur.execute(
        _DOCS + """
        SELECT d.id_motivo_perda AS id, pm.nome, count(*) AS documentos,
               coalesce(sum(c.custo), 0) AS custo
          FROM docs d
          LEFT JOIN perda_motivos pm ON pm.id = d.id_motivo_perda
          LEFT JOIN custo c ON c.id_venda = d.id
         WHERE d.motivo = 'PERDA'
         GROUP BY d.id_motivo_perda, pm.nome
         ORDER BY 4 DESC, pm.nome""",
        par,
    )
    motivos_perda = [{"id": r["id"], "nome": r["nome"] or "sem motivo",
                      "documentos": r["documentos"], "custo": _f(r["custo"])}
                     for r in cur.fetchall()]

    # ── os documentos, com a observação ─────────────────────────────────────
    cur.execute(
        _DOCS + """
        SELECT d.id, d.data, d.documento, d.motivo, d.motivo_observacao,
               f.nome AS pessoa, pm.nome AS motivo_perda,
               coalesce(i.itens, 0) AS itens, coalesce(c.custo, 0) AS custo,
               coalesce(i.custo_ficha, 0) AS custo_ficha,
               coalesce(i.referencia, 0) AS referencia, coalesce(i.sem_custo, 0) AS sem_custo
          FROM docs d
          LEFT JOIN fornecedores f ON f.id = d.id_pessoa
          LEFT JOIN perda_motivos pm ON pm.id = d.id_motivo_perda
          LEFT JOIN itens i ON i.id_venda = d.id
          LEFT JOIN custo c ON c.id_venda = d.id
         ORDER BY d.data DESC, d.id DESC
         LIMIT %(lim)s""",
        {**par, "lim": limite_documentos},
    )
    documentos = [{**dict(r), "rotulo": ROTULOS.get(r["motivo"], r["motivo"]),
                   "itens": _f(r["itens"]), "custo": _f(r["custo"]),
                   "custo_ficha": _f(r["custo_ficha"]), "referencia": _f(r["referencia"])}
                  for r in cur.fetchall()]

    perdas_ajuste = None
    if not pessoas and (not motivos or "PERDA" in motivos):
        perdas_ajuste = {
            "custo": _perdas_por_ajuste(cur, id_unidade, inicio, fim),
            "anterior": _perdas_por_ajuste(cur, id_unidade, a_ini, a_fim),
        }
        perdas_ajuste["pct_custo"] = _variacao(perdas_ajuste["custo"],
                                               perdas_ajuste["anterior"])

    return {
        "inicio": inicio, "fim": fim, "agrupar": agrupar,
        "motivos_filtro": motivos, "pessoas_filtro": par["pessoas"],
        "rotulos": ROTULOS,
        "totais": totais, "comparacao": comparacao,
        "por_motivo": linhas,
        "serie": sorted(serie.values(), key=lambda s: s["periodo"]),
        "produtos": produtos, "pessoas": por_pessoa, "motivos_perda": motivos_perda,
        "documentos": documentos,
        "documentos_cortados": totais["documentos"] > len(documentos),
        "perdas_ajuste": perdas_ajuste,
    }
