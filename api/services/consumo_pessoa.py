"""O que cada pessoa consumiu, e quanto deixou de pagar.

🔑 **O caso do dono** (04/09/2026): "o funcionário vai comprar, lançamos e
depois cobramos o valor dele" — este é o documento dessa cobrança, e precisa
das duas colunas para ser aceito por quem paga: o que custaria e o que está
sendo cobrado.

⚠️ **A consulta mora AQUI, e não no router, porque tem dois consumidores**: a
tela `/vendas/por-pessoa` e o arquivo de `/exportar`. Escrita duas vezes, ela
divergiria — e o caso seria o pior possível: a tela mostraria um valor, o
arquivo entregue ao funcionário mostraria outro, e a diferença apareceria numa
discussão sobre dinheiro.
"""

from datetime import date


SITUACOES = ("aberto", "cobranca", "recebido", "todos")


def recorte(r: dict | None) -> tuple[str, tuple]:
    """O WHERE que isola o recorte, e os parametros dele.

    🔑 **Contas a receber (22/10/2026)**: o ciclo saiu, e o recorte e a SITUACAO
    do documento mais, se quiser, um intervalo de datas:
    - `aberto` -- sem lote: o que a casa tem a receber e ainda nao cobrou (padrao);
    - `cobranca` -- num lote ainda nao pago; `recebido` -- num lote com baixa;
    - `todos` -- tudo, com ou sem lote.
    🔑 **Com `id_lote`, o recorte e o LOTE**, e as datas e a situacao nao valem:
    e o documento da cobranca, e tem de mostrar exatamente o que foi cobrado --
    filtrar por data de novo poderia deixar de fora um documento dele.

    `None` e "tudo em aberto", sem recorte de data.
    """
    r = r or {}
    if r.get("id_lote"):
        return "AND v.id_consumo_lote = %s", (r["id_lote"],)
    situacao = r.get("situacao") or "aberto"
    partes, ps = [], []
    if situacao == "aberto":
        partes.append("AND v.id_consumo_lote IS NULL")
    elif situacao in ("cobranca", "recebido"):
        partes.append("AND v.id_consumo_lote IN (SELECT l.id FROM consumo_lotes l "
                      "WHERE l.status = %s)")
        ps.append("ABERTO" if situacao == "cobranca" else "RECEBIDO")
    if r.get("de"):
        partes.append("AND v.data >= %s")
        ps.append(r["de"])
    if r.get("ate"):
        partes.append("AND v.data <= %s")
        ps.append(r["ate"])
    return " ".join(partes), tuple(ps)


def apurar(cur, id_unidade: int, filtro: dict | None,
           ids_pessoa: list[int] | None = None,
           detalhe: str = "sintetico") -> list[dict]:
    """As linhas de um recorte — um total por pessoa, ou item a item.

    ⚠️ **O recorte e o da SITUACAO do documento, ou o LOTE** (ver `recorte`).

    ⚠️ **Cupom CANCELADO fica de fora.** Ele existe na base para a conferência
    com o PDV fechar, mas cobrar alguém por um cupom cancelado seria cobrar o
    que não foi consumido. É a mesma regra de todo lugar que soma dinheiro.

    ⚠️ **O preço cheio NULO cai no cobrado.** Nulo quer dizer "a política não
    tocou nesta linha"; tratá-lo como zero faria o relatório anunciar um
    desconto de 100% em cada linha comum.

    ⚠️ **As somas dos ITENS saem de uma CTE, nunca do mesmo SELECT do
    cabeçalho.** Juntar `vendas` com `venda_itens` repete o cabeçalho uma vez
    por linha, e um `sum(v.desconto)` ali multiplicaria o desconto pelo número
    de itens do cupom — a armadilha que já custou a conferência do dia 02/09.
    """
    ids = ids_pessoa or None
    onde, ps = recorte(filtro)
    params = (id_unidade, *ps, ids, ids)

    # 🔑 **Por DOCUMENTO** (26/09/2026, pedido do dono: *"criar mais opção de
    # impressão, agrupado por documento, agrupado por documento e destacando os
    # itens; ter estas possibilidades na tela também"*). Uma linha por cupom — é
    # como o funcionário confere: "este cupom é meu, este também".
    if detalhe in ("documento", "documento_itens"):
        cur.execute(
            f"""WITH cupom AS (
                   SELECT v.id, v.id_pessoa, v.data, v.hora, v.documento, v.desconto,
                          v.id_consumo_lote,
                          sum(vi.quantidade * coalesce(vi.valor_unitario_cheio,
                                                       vi.valor_unitario)) AS cheio,
                          sum(vi.valor_total) AS itens_total,
                          count(*) AS itens
                     FROM vendas v
                     JOIN venda_itens vi ON vi.id_venda = v.id
                    WHERE v.id_unidade = %s AND NOT v.cancelada
                      {onde}
                      AND (%s::int[] IS NULL OR v.id_pessoa = ANY(%s))
                      AND v.id_pessoa IS NOT NULL
                    GROUP BY v.id
               )
               SELECT c.id AS id_venda, c.data, c.hora, c.documento,
                      f.id AS id_pessoa, f.nome AS pessoa,
                      -- O lote em que o documento está (nulo = em aberto).
                      c.id_consumo_lote AS id_lote,
                      c.itens, c.cheio AS total_cheio,
                      -- ⚠️ O desconto do CABEÇALHO do cupom entra no total do
                      -- documento, como no sintético: é dinheiro que não se cobra.
                      c.itens_total - c.desconto AS total,
                      c.cheio - c.itens_total + c.desconto AS desconto
                 FROM cupom c
                 JOIN fornecedores f ON f.id = c.id_pessoa
                ORDER BY f.nome, c.data, c.hora NULLS LAST, c.id""",
            params,
        )
        documentos = [dict(r) for r in cur.fetchall()]
        if detalhe == "documento":
            return documentos
        # Os itens de cada documento, pela MESMA consulta do analítico — a linha
        # de um item não pode valer uma coisa aqui e outra no item a item.
        itens = apurar(cur, id_unidade, filtro, ids_pessoa, "analitico")
        por_venda: dict[int, list[dict]] = {}
        for i in itens:
            por_venda.setdefault(i["id_venda"], []).append(i)
        for d in documentos:
            d["itens_do_documento"] = por_venda.get(d["id_venda"], [])
        return documentos

    if detalhe == "analitico":
        cur.execute(
            f"""SELECT v.id AS id_venda, v.data, v.hora, v.documento,
                      f.id AS id_pessoa, f.nome AS pessoa,
                      v.cupom_base, v.cupom_desconto_pct,
                      coalesce(p.nome_curto, p.nome, vi.descricao_pdv) AS produto,
                      p.codigo AS produto_codigo,
                      vi.quantidade,
                      coalesce(vi.valor_unitario_cheio, vi.valor_unitario) AS unitario_cheio,
                      vi.valor_unitario AS unitario,
                      vi.quantidade * coalesce(vi.valor_unitario_cheio,
                                               vi.valor_unitario) AS total_cheio,
                      vi.valor_total AS total,
                      vi.quantidade * coalesce(vi.valor_unitario_cheio, vi.valor_unitario)
                          - vi.valor_total AS desconto
                 FROM vendas v
                 JOIN fornecedores f ON f.id = v.id_pessoa
                 JOIN venda_itens vi ON vi.id_venda = v.id
                 LEFT JOIN produtos p ON p.id = vi.id_produto
                WHERE v.id_unidade = %s AND NOT v.cancelada
                  {onde}
                  AND (%s::int[] IS NULL OR v.id_pessoa = ANY(%s))
                ORDER BY f.nome, v.data, v.hora NULLS LAST, v.id, vi.id""",
            params,
        )
        return [dict(r) for r in cur.fetchall()]

    cur.execute(
        f"""WITH cupom AS (
               SELECT v.id, v.id_pessoa, v.desconto,
                      sum(vi.quantidade * coalesce(vi.valor_unitario_cheio,
                                                   vi.valor_unitario)) AS cheio,
                      sum(vi.valor_total) AS itens_total,
                      count(*) AS itens
                 FROM vendas v
                 JOIN venda_itens vi ON vi.id_venda = v.id
                WHERE v.id_unidade = %s AND NOT v.cancelada
                  {onde}
                  AND (%s::int[] IS NULL OR v.id_pessoa = ANY(%s))
                  AND v.id_pessoa IS NOT NULL
                GROUP BY v.id, v.id_pessoa, v.desconto
           )
           SELECT f.id AS id_pessoa, f.nome AS pessoa,
                  f.cupom_base, f.cupom_desconto_pct,
                  count(*) AS cupons,
                  sum(c.itens) AS itens,
                  sum(c.cheio) AS total_cheio,
                  -- O que a casa vai cobrar: os itens já ajustados pela
                  -- política, menos o desconto que o cupom trouxer no cabeçalho.
                  sum(c.itens_total - c.desconto) AS total,
                  sum(c.cheio - c.itens_total + c.desconto) AS desconto
             FROM cupom c
             JOIN fornecedores f ON f.id = c.id_pessoa
            GROUP BY f.id, f.nome, f.cupom_base, f.cupom_desconto_pct
            ORDER BY sum(c.cheio - c.itens_total + c.desconto) DESC, f.nome""",
        params,
    )
    return [dict(r) for r in cur.fetchall()]
