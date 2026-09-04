"""O ciclo do consumo: abre, acumula, fecha no pagamento.

🔑 **O pedido do dono (04/09/2026):** o administrador abre um período de tal a
tal dia, o consumo do pessoal cai nele, e quando o pagamento acontece o período
é fechado. Quem consumiu consulta o próprio saldo em *Meu consumo*.

⚠️ **"Em aberto" é a venda SEM carimbo de período** — não uma conta de datas.
Fosse por data, corrigir as datas de um período depois moveria dívida já paga de
volta para aberto, e o saldo de quem já acertou mudaria sozinho. O carimbo
(`vendas.id_consumo_periodo`) é um fato do fechamento.

⚠️ **O fechamento varre TUDO que está em aberto até a data final**, e não apenas
o que cai dentro do início. É deliberado, e é a decisão menos ruim: deixar de
fora um consumo de agosto ainda não pago, enquanto se marca setembro como pago,
faria o saldo daquela pessoa ficar errado para sempre — e ninguém olharia para
trás. Como isso pode surpreender, `previa_do_fechamento` separa o que vem de
antes do início, a tela mostra, e o fechamento diz na resposta.
"""

from datetime import date

# As colunas que descrevem o consumo de uma pessoa, sempre nesta ordem.
# ⚠️ O preço cheio NULO cai no cobrado: nulo é "a política não tocou nesta
# linha", e tratá-lo como zero anunciaria 100% de desconto em toda linha comum.
_SOMAS = """
    count(DISTINCT v.id) AS cupons,
    count(*) AS itens,
    sum(vi.quantidade * coalesce(vi.valor_unitario_cheio, vi.valor_unitario)) AS total_cheio,
    sum(vi.valor_total) AS itens_total
"""


def periodo_aberto(cur, id_unidade: int) -> dict | None:
    """O ciclo em curso — ou nada, que é o estado de quem nunca abriu um."""
    cur.execute(
        """SELECT id, nome, inicio, fim, status, aberto_em
             FROM consumo_periodos
            WHERE id_unidade = %s AND status = 'ABERTO'""",
        (id_unidade,),
    )
    linha = cur.fetchone()
    return dict(linha) if linha else None


def em_aberto_por_pessoa(cur, id_unidade: int,
                         id_pessoa: int | None = None) -> list[dict]:
    """O que cada pessoa deve hoje: vendas com pessoa e sem período.

    ⚠️ **Cupom cancelado fica de fora.** Ele existe na base para a conferência
    com o PDV fechar, mas cobrar alguém por um cupom cancelado seria cobrar o
    que não foi consumido.
    """
    cur.execute(
        f"""WITH cupom AS (
                SELECT v.id, v.id_pessoa, v.desconto,
                       sum(vi.quantidade * coalesce(vi.valor_unitario_cheio,
                                                    vi.valor_unitario)) AS cheio,
                       sum(vi.valor_total) AS itens_total,
                       count(*) AS itens,
                       min(v.data) AS primeira, max(v.data) AS ultima
                  FROM vendas v
                  JOIN venda_itens vi ON vi.id_venda = v.id
                 WHERE v.id_unidade = %s AND NOT v.cancelada
                   AND v.id_pessoa IS NOT NULL
                   AND v.id_consumo_periodo IS NULL
                   AND (%s::int IS NULL OR v.id_pessoa = %s)
                 GROUP BY v.id, v.id_pessoa, v.desconto
            )
            SELECT f.id AS id_pessoa, f.nome AS pessoa,
                   f.cupom_base, f.cupom_desconto_pct,
                   count(*) AS cupons,
                   sum(c.itens) AS itens,
                   sum(c.cheio) AS total_cheio,
                   sum(c.itens_total - c.desconto) AS total,
                   sum(c.cheio - c.itens_total + c.desconto) AS desconto,
                   min(c.primeira) AS desde, max(c.ultima) AS ate
              FROM cupom c
              JOIN fornecedores f ON f.id = c.id_pessoa
             GROUP BY f.id, f.nome, f.cupom_base, f.cupom_desconto_pct
             ORDER BY sum(c.itens_total - c.desconto) DESC, f.nome""",
        (id_unidade, id_pessoa, id_pessoa),
    )
    return [dict(r) for r in cur.fetchall()]


def cupons_em_aberto(cur, id_unidade: int, id_pessoa: int) -> list[dict]:
    """Os cupons ainda não fechados de UMA pessoa — o extrato de *Meu consumo*."""
    cur.execute(
        """SELECT v.id, v.data, v.hora, v.documento,
                  sum(vi.quantidade * coalesce(vi.valor_unitario_cheio,
                                               vi.valor_unitario)) AS total_cheio,
                  sum(vi.valor_total) - v.desconto AS total,
                  count(*) AS itens
             FROM vendas v
             JOIN venda_itens vi ON vi.id_venda = v.id
            WHERE v.id_unidade = %s AND NOT v.cancelada
              AND v.id_pessoa = %s AND v.id_consumo_periodo IS NULL
            GROUP BY v.id, v.data, v.hora, v.documento, v.desconto
            ORDER BY v.data DESC, v.hora DESC NULLS LAST, v.id DESC""",
        (id_unidade, id_pessoa),
    )
    return [dict(r) for r in cur.fetchall()]


def previa_do_fechamento(cur, id_unidade: int, periodo: dict) -> dict:
    """O que este fechamento vai carimbar — antes de carimbar.

    🔑 **Separa o que vem de ANTES do início**, porque é a parte que surpreende:
    o administrador abriu o ciclo de 01 a 15 e o fechamento leva junto um
    consumo de agosto que ninguém pagou. Levar é o certo; não avisar é que não
    seria.
    """
    cur.execute(
        """SELECT count(*) FILTER (WHERE v.data < %s) AS anteriores,
                  count(*) FILTER (WHERE v.data BETWEEN %s AND %s) AS no_periodo,
                  count(*) FILTER (WHERE v.data > %s) AS depois,
                  min(v.data) AS desde
             FROM vendas v
            WHERE v.id_unidade = %s AND NOT v.cancelada
              AND v.id_pessoa IS NOT NULL AND v.id_consumo_periodo IS NULL
              AND v.data <= %s""",
        (periodo["inicio"], periodo["inicio"], periodo["fim"], periodo["fim"],
         id_unidade, periodo["fim"]),
    )
    r = dict(cur.fetchone() or {})
    # ⚠️ Venda com data POSTERIOR ao fim não entra — ela pertence ao próximo
    # ciclo. Carimbá-la cobraria hoje um consumo de amanhã.
    r["depois"] = r.get("depois") or 0
    return r


def fechar(cur, id_unidade: int, id_periodo: int, id_usuario: int | None,
           observacao: str | None = None) -> dict:
    """Carimba as vendas em aberto e grava o recibo por pessoa.

    ⚠️ **A ordem importa: primeiro o RECIBO, depois o carimbo.** O recibo é
    calculado sobre as vendas que ainda estão em aberto; carimbar antes faria a
    consulta não achar mais nenhuma e gravar um recibo de zero para todo mundo.
    """
    cur.execute(
        """SELECT id, nome, inicio, fim, status FROM consumo_periodos
            WHERE id = %s AND id_unidade = %s FOR UPDATE""",
        (id_periodo, id_unidade),
    )
    periodo = cur.fetchone()
    if not periodo:
        return {"erro": "Período não encontrado."}
    if periodo["status"] != "ABERTO":
        return {"erro": "Este período já está fechado."}

    # 1. o recibo, com o que está em aberto até a data final
    cur.execute(
        """WITH cupom AS (
               SELECT v.id, v.id_pessoa, v.desconto,
                      sum(vi.quantidade * coalesce(vi.valor_unitario_cheio,
                                                   vi.valor_unitario)) AS cheio,
                      sum(vi.valor_total) AS itens_total,
                      count(*) AS itens
                 FROM vendas v
                 JOIN venda_itens vi ON vi.id_venda = v.id
                WHERE v.id_unidade = %s AND NOT v.cancelada
                  AND v.id_pessoa IS NOT NULL AND v.id_consumo_periodo IS NULL
                  AND v.data <= %s
                GROUP BY v.id, v.id_pessoa, v.desconto
           )
           INSERT INTO consumo_periodo_pessoas
                  (id_periodo, id_pessoa, cupons, itens, total_cheio, desconto, total)
           SELECT %s, c.id_pessoa, count(*), sum(c.itens), sum(c.cheio),
                  sum(c.cheio - c.itens_total + c.desconto),
                  sum(c.itens_total - c.desconto)
             FROM cupom c
            GROUP BY c.id_pessoa
           ON CONFLICT (id_periodo, id_pessoa) DO NOTHING""",
        (id_unidade, periodo["fim"], id_periodo),
    )

    # 2. o carimbo
    cur.execute(
        """UPDATE vendas SET id_consumo_periodo = %s
            WHERE id_unidade = %s AND NOT cancelada
              AND id_pessoa IS NOT NULL AND id_consumo_periodo IS NULL
              AND data <= %s""",
        (id_periodo, id_unidade, periodo["fim"]),
    )
    carimbadas = cur.rowcount

    cur.execute(
        """UPDATE consumo_periodos
              SET status = 'FECHADO', fechado_em = now(), id_usuario_fechou = %s,
                  observacao = coalesce(%s, observacao)
            WHERE id = %s""",
        (id_usuario, observacao, id_periodo),
    )

    cur.execute(
        """SELECT count(*) AS pessoas, coalesce(sum(total), 0) AS total
             FROM consumo_periodo_pessoas WHERE id_periodo = %s""",
        (id_periodo,),
    )
    resumo = dict(cur.fetchone() or {})
    return {"cupons": carimbadas, "pessoas": resumo.get("pessoas") or 0,
            "total": float(resumo.get("total") or 0)}


def reabrir(cur, id_unidade: int, id_periodo: int) -> dict:
    """Desfaz um fechamento: tira o carimbo e apaga o recibo.

    🔑 **Existe porque fechar sem volta seria um beco.** O fechamento é um
    clique que reescreve centenas de vendas, e fechar o ciclo errado — ou antes
    de conferir — é o engano mais provável desta tela. Sem reabrir, o conserto
    seria no banco, à mão.

    ⚠️ **Só o ÚLTIMO fechado se reabre.** Reabrir um período antigo devolveria
    para "em aberto" vendas que os ciclos seguintes já cobraram, e a mesma
    dívida seria cobrada duas vezes.
    """
    cur.execute(
        """SELECT id, status, fechado_em FROM consumo_periodos
            WHERE id = %s AND id_unidade = %s FOR UPDATE""",
        (id_periodo, id_unidade),
    )
    periodo = cur.fetchone()
    if not periodo:
        return {"erro": "Período não encontrado."}
    if periodo["status"] != "FECHADO":
        return {"erro": "Este período não está fechado."}

    cur.execute(
        """SELECT count(*) AS n FROM consumo_periodos
            WHERE id_unidade = %s AND status = 'FECHADO' AND fechado_em > %s""",
        (id_unidade, periodo["fechado_em"]),
    )
    if (cur.fetchone() or {}).get("n"):
        return {"erro": "Só o último período fechado pode ser reaberto — "
                        "há fechamento mais recente."}

    cur.execute(
        """SELECT count(*) AS n FROM consumo_periodos
            WHERE id_unidade = %s AND status = 'ABERTO'""",
        (id_unidade,),
    )
    if (cur.fetchone() or {}).get("n"):
        return {"erro": "Já existe um período aberto. Feche-o antes de reabrir este."}

    cur.execute("UPDATE vendas SET id_consumo_periodo = NULL WHERE id_consumo_periodo = %s",
                (id_periodo,))
    devolvidas = cur.rowcount
    cur.execute("DELETE FROM consumo_periodo_pessoas WHERE id_periodo = %s", (id_periodo,))
    cur.execute(
        """UPDATE consumo_periodos
              SET status = 'ABERTO', fechado_em = NULL, id_usuario_fechou = NULL
            WHERE id = %s""",
        (id_periodo,),
    )
    return {"cupons": devolvidas}
