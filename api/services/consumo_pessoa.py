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


def recorte(periodo: dict | None) -> tuple[str, tuple]:
    """O WHERE que isola um ciclo, e os parametros dele.

    🔑 **A selecao e pelo CARIMBO, nunca pelas datas** (`vendas.id_consumo_periodo`).
    E a mesma regra que a migracao 057 gravou, aplicada agora ao relatorio: o
    fechamento leva tudo que estava em aberto ate a data final, INCLUSIVE
    consumo anterior ao inicio do ciclo. Selecionar por data mostraria um
    conjunto diferente do que foi cobrado -- e este relatorio e o documento da
    cobranca, entao a diferenca apareceria numa discussao sobre dinheiro.

    ⚠️ O ciclo ABERTO ainda nao carimbou nada: o que pertence a ele e o que
    esta em aberto ate o `fim` dele, exatamente como `previa_do_fechamento` ja
    calcula. Venda posterior ao fim e do proximo ciclo.

    `None` e "tudo em aberto", sem recorte de data -- o que a casa tem a receber
    hoje, e o unico recorte possivel numa loja que nunca abriu um ciclo.
    """
    if periodo is None:
        return "AND v.id_consumo_periodo IS NULL", ()
    if periodo["status"] == "ABERTO":
        return "AND v.id_consumo_periodo IS NULL AND v.data <= %s", (periodo["fim"],)
    return "AND v.id_consumo_periodo = %s", (periodo["id"],)


def apurar(cur, id_unidade: int, periodo: dict | None,
           ids_pessoa: list[int] | None = None,
           detalhe: str = "sintetico") -> list[dict]:
    """As linhas de um ciclo — um total por pessoa, ou item a item.

    ⚠️ **O recorte e o do CARIMBO** (ver `recorte`), nao um intervalo de datas.

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
    onde, ps = recorte(periodo)
    filtro = (id_unidade, *ps, ids, ids)

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
            filtro,
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
        filtro,
    )
    return [dict(r) for r in cur.fetchall()]
