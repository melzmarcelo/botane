"""Os relatórios que o dono usa para decidir.

Dois, e cada um responde uma pergunta que o total sozinho não responde:

* **CMV por setor / por categoria** — "a cozinha está pesando mais que o bar?".
  É a mesma equação do CMV (`inicial + compras − final`), produto a produto,
  somada por grupo. Não é rateio: cada real vem do movimento de um produto que
  pertence a um grupo, e a soma dos grupos é o CMV do período.
* **Evolução de preço por insumo** — "o que subiu, e quanto isso me custa?".
  É o relatório que serve para sentar com o fornecedor.

Ficam fora de `cmv.py` de propósito: aquele arquivo é a apuração, e apuração é
uma conta só. Isto aqui é leitura.
"""

from datetime import date, timedelta

from services.cmv import TIPOS_COMPRA
from services.custos import dec


def cmv_por_grupo(cur, id_unidade: int, inicio: date, fim: date,
                  agrupar: str = "setor") -> list[dict]:
    """A conta do CMV quebrada por setor, por categoria ou pelos grupos da casa.

    Não é rateio: é a mesma conta (`inicial + compras − final`) restrita a cada
    grupo, e a soma dos grupos fecha com o CMV do período — o teste cobra isso.

    O que não tem grupo aparece como "Sem setor" em vez de sumir — produto sem
    classificação é justamente o que ninguém olha, e some da conta se a junção
    for interna.

    ⚠️ `agrupar="grupo"` usa os **grupos do CMV** que a casa montou por tipo de
    produto (`cmv_grupos` + `cmv_grupo_tipos`), que é como o dono separa o que
    não é comida — detergente e marmita entram no custo pela mesma porta dos
    insumos e somem no total.
    """
    if agrupar not in ("setor", "categoria", "grupo"):
        raise ValueError("agrupar deve ser 'setor', 'categoria' ou 'grupo'")

    junta = {
        "setor": "LEFT JOIN setores g ON g.id = p.id_setor",
        "categoria": "LEFT JOIN categorias g ON g.id = p.id_categoria",
        # ⚠️ O grupo do CMV é por TIPO de produto, não por uma coluna do
        # produto: quem diz que EMBALAGEM e MATERIAL_LIMPEZA andam juntos é a
        # casa, em `cmv_grupo_tipos`. A junção passa pelo tipo justamente para
        # que mudar a configuração reclassifique o passado inteiro sem tocar em
        # produto nenhum — o contrário (gravar o grupo no produto) exigiria
        # varrer o cadastro a cada mudança e deixaria os antigos para trás.
        "grupo": """LEFT JOIN cmv_grupo_tipos gt ON gt.tipo = p.tipo
                    LEFT JOIN cmv_grupos g ON g.id = gt.id_grupo AND g.ativo""",
    }[agrupar]
    rotulo = {"setor": "Sem setor", "categoria": "Sem categoria",
              "grupo": "Sem grupo"}[agrupar]

    cur.execute(
        f"""
        WITH inicial AS (
            SELECT DISTINCT ON (id_produto, id_local)
                   id_produto, saldo_apos * custo_medio_apos AS valor
              FROM estoque_movimentos
             WHERE id_unidade = %s AND data_movimento < %s
             ORDER BY id_produto, id_local, id DESC
        ),
        final AS (
            SELECT DISTINCT ON (id_produto, id_local)
                   id_produto, saldo_apos * custo_medio_apos AS valor
              FROM estoque_movimentos
             WHERE id_unidade = %s AND data_movimento < %s
             ORDER BY id_produto, id_local, id DESC
        ),
        compras AS (
            SELECT id_produto, sum(abs(custo_total)) AS valor
              FROM estoque_movimentos
             WHERE id_unidade = %s AND tipo = ANY(%s)
               AND data_movimento >= %s AND data_movimento < %s
             GROUP BY id_produto
        ),
        perdas AS (
            SELECT id_produto, sum(abs(custo_total)) AS valor
              FROM estoque_movimentos
             WHERE id_unidade = %s AND tipo = 'SAIDA_PERDA'
               AND data_movimento >= %s AND data_movimento < %s
             GROUP BY id_produto
        )
        SELECT coalesce(g.nome, %s) AS grupo,
               coalesce(sum(i.valor), 0) AS estoque_inicial,
               coalesce(sum(c.valor), 0) AS compras,
               coalesce(sum(f.valor), 0) AS estoque_final,
               coalesce(sum(i.valor), 0) + coalesce(sum(c.valor), 0)
                   - coalesce(sum(f.valor), 0) AS cmv,
               coalesce(sum(pd.valor), 0) AS perdas,
               count(DISTINCT p.id) FILTER (
                   WHERE coalesce(i.valor, 0) <> 0 OR coalesce(c.valor, 0) <> 0
                      OR coalesce(f.valor, 0) <> 0) AS produtos
          FROM produtos p
          {junta}
          LEFT JOIN (SELECT id_produto, sum(valor) AS valor FROM inicial GROUP BY 1) i
                 ON i.id_produto = p.id
          LEFT JOIN (SELECT id_produto, sum(valor) AS valor FROM final GROUP BY 1) f
                 ON f.id_produto = p.id
          LEFT JOIN compras c ON c.id_produto = p.id
          LEFT JOIN perdas pd ON pd.id_produto = p.id
         GROUP BY 1
        HAVING coalesce(sum(i.valor), 0) <> 0 OR coalesce(sum(c.valor), 0) <> 0
            OR coalesce(sum(f.valor), 0) <> 0
         ORDER BY 5 DESC
        """,
        (id_unidade, inicio, id_unidade, fim + timedelta(days=1),
         id_unidade, list(TIPOS_COMPRA), inicio, fim + timedelta(days=1),
         id_unidade, inicio, fim + timedelta(days=1), rotulo),
    )
    linhas = [dict(r) for r in cur.fetchall()]
    total = sum(dec(l["cmv"]) for l in linhas)
    for l in linhas:
        l["participacao_pct"] = float(dec(l["cmv"]) / total * 100) if total else 0.0
    return linhas


def evolucao_de_preco(cur, id_unidade: int, inicio: date, fim: date,
                      limite: int = 40) -> list[dict]:
    """Quanto cada insumo subiu (ou caiu) entre as notas do período.

    Ordena pelo **impacto em reais**, não pela variação percentual: um item que
    subiu 60% e se compra uma vez por trimestre importa menos que um que subiu
    8% e entra toda semana.

    A base é o **custo de aquisição** — frete rateado dentro, desconto abatido —
    e não o valor de tabela da nota: é o número que de fato vira CMV.
    """
    cur.execute(
        """
        WITH itens AS (
            SELECT ni.id_produto,
                   ni.custo_aquisicao_unitario AS preco,
                   coalesce(ni.quantidade_convertida, ni.quantidade) AS qtd,
                   coalesce(n.data_entrada, n.data_emissao) AS data,
                   coalesce(f.nome, n.nome_emitente) AS fornecedor,
                   row_number() OVER (
                       PARTITION BY ni.id_produto
                       ORDER BY coalesce(n.data_entrada, n.data_emissao), n.id) AS pos_ini,
                   row_number() OVER (
                       PARTITION BY ni.id_produto
                       ORDER BY coalesce(n.data_entrada, n.data_emissao) DESC, n.id DESC) AS pos_fim
              FROM nota_itens ni
              JOIN notas_entrada n ON n.id = ni.id_nota
              LEFT JOIN fornecedores f ON f.id = n.id_fornecedor
             WHERE n.id_unidade = %s AND n.status = 'LANCADA'
               AND ni.id_produto IS NOT NULL
               AND ni.custo_aquisicao_unitario > 0
               AND coalesce(n.data_entrada, n.data_emissao) BETWEEN %s AND %s
        )
        SELECT i.id_produto, p.codigo, p.nome AS produto, p.um_estoque,
               count(*) AS compras,
               min(i.preco) AS menor,
               max(i.preco) AS maior,
               sum(i.qtd) AS quantidade,
               sum(i.qtd * i.preco) AS valor_comprado,
               max(i.preco) FILTER (WHERE i.pos_ini = 1) AS primeiro,
               max(i.preco) FILTER (WHERE i.pos_fim = 1) AS ultimo,
               max(i.data) FILTER (WHERE i.pos_fim = 1) AS data_ultimo,
               max(i.fornecedor) FILTER (WHERE i.pos_fim = 1) AS fornecedor_ultimo,
               (array_agg(i.fornecedor ORDER BY i.preco))[1] AS fornecedor_mais_barato
          FROM itens i
          JOIN produtos p ON p.id = i.id_produto
         GROUP BY i.id_produto, p.codigo, p.nome, p.um_estoque
        HAVING count(*) >= 2
         ORDER BY abs((max(i.preco) FILTER (WHERE i.pos_fim = 1)
                     - max(i.preco) FILTER (WHERE i.pos_ini = 1)) * sum(i.qtd)) DESC
         LIMIT %s
        """,
        (id_unidade, inicio, fim, limite),
    )
    linhas = []
    for r in cur.fetchall():
        l = dict(r)
        primeiro, ultimo, menor = dec(l["primeiro"]), dec(l["ultimo"]), dec(l["menor"])
        qtd = dec(l["quantidade"])
        l["variacao_pct"] = float((ultimo - primeiro) / primeiro * 100) if primeiro else 0.0
        # O que transforma percentual em conversa: quanto a variação custa no
        # volume que a casa realmente comprou.
        l["impacto"] = float((ultimo - primeiro) * qtd)
        # E quanto daria para economizar pagando sempre o menor preço já pago.
        l["economia_possivel"] = float((ultimo - menor) * qtd)
        linhas.append(l)
    return linhas


def historico_de_preco(cur, id_unidade: int, id_produto: int, limite: int = 60) -> list[dict]:
    """A série de compras de um insumo — o detalhe por trás da variação."""
    cur.execute(
        """SELECT coalesce(n.data_entrada, n.data_emissao) AS data,
                  n.numero, n.id AS id_nota,
                  coalesce(f.nome, n.nome_emitente) AS fornecedor,
                  coalesce(ni.quantidade_convertida, ni.quantidade) AS quantidade,
                  ni.custo_aquisicao_unitario AS preco,
                  ni.variacao_preco_pct AS variacao_pct
             FROM nota_itens ni
             JOIN notas_entrada n ON n.id = ni.id_nota
             LEFT JOIN fornecedores f ON f.id = n.id_fornecedor
            WHERE n.id_unidade = %s AND n.status = 'LANCADA' AND ni.id_produto = %s
              AND ni.custo_aquisicao_unitario > 0
            ORDER BY coalesce(n.data_entrada, n.data_emissao) DESC, n.id DESC
            LIMIT %s""",
        (id_unidade, id_produto, limite),
    )
    return [dict(r) for r in cur.fetchall()]
