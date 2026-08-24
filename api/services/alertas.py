"""O que precisa de atenção hoje.

Um sistema de CMV sabe muita coisa que ninguém vai procurar: o insumo que
acabou, o lote que vence sexta, a nota que não entrou porque falta vincular um
item. Este módulo junta tudo isso num lugar só, com severidade e link — para o
dono abrir uma tela e ver o que fazer, em vez de descobrir no fim do mês.

Cada alerta responde três coisas: **o que é**, **quanto é** e **o que fazer**.
"""

from datetime import date, timedelta

from services.custos import dec

CRITICO, ATENCAO, AVISO = "critico", "atencao", "aviso"


def _um(cur, sql: str, params: tuple = ()) -> dict:
    cur.execute(sql, params)
    linha = cur.fetchone()
    return dict(linha) if linha else {}


def levantar(cur, id_unidade: int) -> list[dict]:
    alertas: list[dict] = []

    def juntar(chave, severidade, titulo, quantidade, detalhe, acao, href, valor=None):
        if quantidade:
            alertas.append({
                "chave": chave, "severidade": severidade, "titulo": titulo,
                "quantidade": int(quantidade), "detalhe": detalhe, "acao": acao,
                "href": href, "valor": float(valor) if valor is not None else None,
            })

    dias = _um(cur, "SELECT alerta_validade_dias FROM parametros WHERE id_unidade = %s",
               (id_unidade,)).get("alerta_validade_dias", 15)

    # ---------------------------------------------------------------- estoque
    r = _um(cur, """
        SELECT count(*) AS n FROM estoque_saldos s
          JOIN produtos p ON p.id = s.id_produto
         WHERE s.id_unidade = %s AND p.ativo AND s.quantidade < 0""", (id_unidade,))
    juntar("estoque.negativo", CRITICO, "Produto com saldo negativo", r.get("n"),
           "Saiu mais do que havia — falta lançar uma entrada ou a contagem está errada.",
           "conferir no estoque", "/estoque")

    r = _um(cur, """
        SELECT count(*) AS n FROM estoque_saldos s
          JOIN produtos p ON p.id = s.id_produto
         WHERE s.id_unidade = %s AND p.ativo AND p.estoque_minimo IS NOT NULL
           AND s.quantidade >= 0 AND s.quantidade < p.estoque_minimo""", (id_unidade,))
    juntar("estoque.minimo", ATENCAO, "Abaixo do estoque mínimo", r.get("n"),
           "Vai faltar antes da próxima entrega se ninguém comprar.",
           "ver quais", "/estoque")

    # O que falta e a casa PRODUZ não se resolve comprando: entra na agenda.
    # Separado do alerta acima de propósito — a ação é outra, e um alerta que
    # aponta para o lugar errado é um alerta que ninguém segue.
    r = _um(cur, """
        SELECT count(*) AS n FROM produtos p
         WHERE p.ativo AND p.producao_propria AND p.modo_producao = 'PARA_ESTOQUE'
           AND p.estoque_minimo IS NOT NULL
           AND EXISTS (SELECT 1 FROM fichas_tecnicas f
                        WHERE f.id_produto = p.id AND f.status = 'HOMOLOGADA')
           AND NOT EXISTS (SELECT 1 FROM producao_agenda a
                            WHERE a.id_produto = p.id AND a.status = 'PLANEJADA'
                              AND a.data_prevista >= current_date)
           AND coalesce((SELECT sum(s.quantidade) FROM estoque_saldos s
                          WHERE s.id_produto = p.id AND s.id_unidade = %s), 0)
               < p.estoque_minimo""", (id_unidade,))
    juntar("producao.agendar", ATENCAO, "Produzido abaixo do mínimo, sem agenda", r.get("n"),
           "A cozinha faz isto — mas ninguém marcou quando. Vai faltar no meio do serviço.",
           "pôr na agenda", "/producao")

    r = _um(cur, """
        SELECT count(*) AS n FROM producao_agenda
         WHERE id_unidade = %s AND status = 'PLANEJADA' AND data_prevista < current_date""",
            (id_unidade,))
    juntar("producao.atrasada", ATENCAO, "Produção planejada e não feita", r.get("n"),
           "O dia passou e a linha continua na agenda — ou se produz, ou se cancela.",
           "ver a agenda", "/producao")

    r = _um(cur, """
        SELECT count(*) AS n, coalesce(sum(el.quantidade * s.custo_medio), 0) AS valor
          FROM estoque_lotes el
          JOIN produtos p ON p.id = el.id_produto
          LEFT JOIN estoque_saldos s
                 ON s.id_produto = el.id_produto AND s.id_local = el.id_local
         WHERE el.id_unidade = %s AND el.quantidade > 0 AND el.validade IS NOT NULL
           AND el.validade < current_date""", (id_unidade,))
    juntar("estoque.vencido", CRITICO, "Lote vencido no estoque", r.get("n"),
           "Já passou da validade e continua contando como estoque bom.",
           "dar baixa como perda", "/estoque", r.get("valor"))

    r = _um(cur, """
        SELECT count(*) AS n FROM estoque_lotes el
         WHERE el.id_unidade = %s AND el.quantidade > 0 AND el.validade IS NOT NULL
           AND el.validade >= current_date AND el.validade <= current_date + %s""",
            (id_unidade, dias))
    juntar("estoque.vencendo", ATENCAO, f"Vence nos próximos {dias} dias", r.get("n"),
           "Dá tempo de usar antes de virar perda.", "ver os lotes", "/alertas")

    r = _um(cur, """
        SELECT count(*) AS n FROM estoque_movimentos
         WHERE id_unidade = %s AND custo_provisorio
           AND data_movimento >= current_date - 30""", (id_unidade,))
    juntar("estoque.provisorio", AVISO, "Saída com custo provisório", r.get("n"),
           "Saiu sem saldo e usou o último custo conhecido — o CMV do período fica aproximado.",
           "ver os movimentos", "/estoque")

    # ---------------------------------------------------------------- compras
    r = _um(cur, """
        SELECT count(DISTINCT i.id_nota) AS n FROM nota_itens i
          JOIN notas_entrada n ON n.id = i.id_nota
         WHERE n.id_unidade = %s AND i.id_produto IS NULL AND NOT i.ignorado
           AND n.status <> 'CANCELADA'""", (id_unidade,))
    juntar("compras.pendencias", ATENCAO, "Nota parada esperando conciliação", r.get("n"),
           "Tem item sem produto vinculado — a nota inteira não entra no estoque assim.",
           "conciliar agora", "/compras")

    r = _um(cur, """
        SELECT count(*) AS n, coalesce(sum(valor_total), 0) AS valor FROM notas_entrada
         WHERE id_unidade = %s AND status = 'CONCILIADA'""", (id_unidade,))
    juntar("compras.nao_lancadas", ATENCAO, "Nota conciliada, ainda não lançada", r.get("n"),
           "Já está pronta: falta o clique que transforma em estoque.",
           "lançar", "/compras", r.get("valor"))

    # ---------------------------------------------------------------- cadastro
    r = _um(cur, "SELECT count(*) AS n FROM produtos WHERE status = 'RASCUNHO' AND ativo")
    juntar("cadastro.rascunho", ATENCAO, "Produto em rascunho", r.get("n"),
           "Falta a unidade de estoque e o fator — sem isso ele não entra no estoque.",
           "completar cadastro", "/produtos?status=RASCUNHO")

    r = _um(cur, """
        SELECT count(*) AS n FROM produtos p
         WHERE p.ativo AND p.producao_propria
           AND NOT EXISTS (SELECT 1 FROM fichas_tecnicas f
                            WHERE f.id_produto = p.id AND f.status = 'HOMOLOGADA'
                              AND f.vigente_ate IS NULL)""")
    juntar("fichas.faltando", ATENCAO, "Produto de produção própria sem ficha homologada",
           r.get("n"),
           "Sem ficha ele não tem custo teórico e não pode ser produzido.",
           "criar a ficha", "/fichas")

    # ---------------------------------------------------------------- CMV
    r = _um(cur, """
        SELECT count(DISTINCT coalesce(vi.codigo_pdv, vi.descricao_pdv)) AS n,
               coalesce(sum(vi.valor_total), 0) AS valor
          FROM venda_itens vi JOIN vendas v ON v.id = vi.id_venda
         WHERE v.id_unidade = %s AND NOT v.cancelada AND vi.id_produto IS NULL""",
            (id_unidade,))
    juntar("cmv.sem_vinculo", ATENCAO, "Item vendido sem produto no cadastro", r.get("n"),
           "Essa receita não entra no CMV teórico, e a variância fica maior do que é.",
           "ver a fila", "/vendas", r.get("valor"))

    hoje = date.today()
    anterior = (hoje.replace(day=1) - timedelta(days=1)).replace(day=1)
    r = _um(cur, """
        SELECT count(*) AS n FROM cmv_fechamentos
         WHERE id_unidade = %s AND competencia = %s AND status = 'FECHADO'""",
            (id_unidade, anterior))
    if not r.get("n"):
        cur.execute("SELECT count(*) AS n FROM vendas WHERE id_unidade = %s AND data >= %s",
                    (id_unidade, anterior))
        # Só cobra o fechamento se houve movimento no mês — casa nova não é cobrada.
        if cur.fetchone()["n"]:
            juntar("cmv.mes_aberto", AVISO,
                   f"Mês de {anterior.strftime('%m/%Y')} ainda não foi fechado", 1,
                   "Fechar congela o período e evita que alguém lance para trás.",
                   "fechar o mês", "/cmv")

    ordem = {CRITICO: 0, ATENCAO: 1, AVISO: 2}
    alertas.sort(key=lambda a: (ordem[a["severidade"]], -a["quantidade"]))
    return alertas


def vencimentos(cur, id_unidade: int, dias: int | None = None) -> list[dict]:
    """Detalhe do que vence — a lista que o alerta resume."""
    if dias is None:
        dias = _um(cur, "SELECT alerta_validade_dias FROM parametros WHERE id_unidade = %s",
                   (id_unidade,)).get("alerta_validade_dias", 15)
    cur.execute(
        """SELECT el.id, el.lote, el.validade, el.quantidade,
                  (el.validade - current_date) AS dias_restantes,
                  p.nome AS produto, p.codigo, p.um_estoque, l.nome AS local,
                  coalesce(s.custo_medio, 0) AS custo_medio,
                  round(el.quantidade * coalesce(s.custo_medio, 0), 2) AS valor
             FROM estoque_lotes el
             JOIN produtos p ON p.id = el.id_produto
             JOIN locais_estoque l ON l.id = el.id_local
             LEFT JOIN estoque_saldos s
                    ON s.id_produto = el.id_produto AND s.id_local = el.id_local
            WHERE el.id_unidade = %s AND el.quantidade > 0 AND el.validade IS NOT NULL
              AND el.validade <= current_date + %s
            ORDER BY el.validade""",
        (id_unidade, dias),
    )
    return [dict(r) for r in cur.fetchall()]


def abaixo_do_minimo(cur, id_unidade: int) -> list[dict]:
    cur.execute(
        """SELECT p.id, p.codigo, p.nome AS produto, p.um_estoque, p.estoque_minimo,
                  sum(s.quantidade) AS saldo,
                  (p.estoque_minimo - sum(s.quantidade)) AS faltam,
                  f.nome AS fornecedor
             FROM produtos p
             JOIN estoque_saldos s ON s.id_produto = p.id AND s.id_unidade = %s
             LEFT JOIN produto_fornecedor pf
                    ON pf.id_produto = p.id AND pf.preferencial
             LEFT JOIN fornecedores f ON f.id = pf.id_fornecedor
            WHERE p.ativo AND p.estoque_minimo IS NOT NULL
            GROUP BY p.id, p.codigo, p.nome, p.um_estoque, p.estoque_minimo, f.nome
           HAVING sum(s.quantidade) < p.estoque_minimo
            ORDER BY (sum(s.quantidade) / nullif(p.estoque_minimo, 0))""",
        (id_unidade,),
    )
    return [dict(r) for r in cur.fetchall()]
