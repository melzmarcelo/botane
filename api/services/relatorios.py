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

    🔑 **O SETOR vem do LOCAL do movimento, não do cadastro do produto**
    (01/09/2026). O processo da casa põe o mesmo insumo em vários setores: o
    açúcar entra no Estoque Central e de manhã Bar, Confeitaria, Cozinha e
    Cafeteria levam um pacote cada. Enquanto isto saía de `produtos.id_setor` —
    um setor só —, **todo o consumo de açúcar era atribuído a um deles**, e a
    resposta para "a confeitaria está pesando mais que o bar?" era ficção. Quem
    sabe de onde a mercadoria saiu é o MOVIMENTO, e ele guarda `id_local` desde
    sempre; o que faltava era o local dizer a que setor pertence (migração 051).

    ⚠️ **A reserva é o setor do PRODUTO**, não "Sem setor". O Estoque Central
    não pertence a setor nenhum, e sem a reserva toda casa que ainda não
    classificou as prateleiras veria o relatório inteiro virar uma linha só.
    Assim, quem não configurou nada continua vendo exatamente o que via.

    🔑 **O grão da conta virou `(produto, local)`, e é isso que preserva a
    identidade.** Somar é associativo: agregar no grão fino e enrolar depois
    pelo grupo dá exatamente os mesmos totais que agregar por produto — então
    `categoria` e `grupo`, que são atributos do PRODUTO, não mudam um centavo.
    Só o setor passa a ler outra coluna.

    ⚠️ `agrupar="grupo"` usa os **grupos do CMV** que a casa montou por tipo de
    produto (`cmv_grupos` + `cmv_grupo_tipos`), que é como o dono separa o que
    não é comida — detergente e marmita entram no custo pela mesma porta dos
    insumos e somem no total.
    """
    if agrupar not in ("setor", "categoria", "grupo"):
        raise ValueError("agrupar deve ser 'setor', 'categoria' ou 'grupo'")

    junta = {
        # ⚠️ `coalesce(l.id_setor, p.id_setor)`: o setor de ONDE saiu, e o do
        # cadastro como reserva para a prateleira que não declarou nenhum.
        "setor": """LEFT JOIN locais_estoque l ON l.id = k.id_local
                    LEFT JOIN setores g ON g.id = coalesce(l.id_setor, p.id_setor)""",
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
                   id_produto, id_local, saldo_apos * custo_medio_apos AS valor
              FROM estoque_movimentos
             WHERE id_unidade = %s AND data_movimento < %s
             ORDER BY id_produto, id_local, id DESC
        ),
        final AS (
            SELECT DISTINCT ON (id_produto, id_local)
                   id_produto, id_local, saldo_apos * custo_medio_apos AS valor
              FROM estoque_movimentos
             WHERE id_unidade = %s AND data_movimento < %s
             ORDER BY id_produto, id_local, id DESC
        ),
        compras AS (
            SELECT id_produto, id_local, sum(abs(custo_total)) AS valor
              FROM estoque_movimentos
             WHERE id_unidade = %s AND tipo = ANY(%s)
               AND data_movimento >= %s AND data_movimento < %s
             GROUP BY 1, 2
        ),
        -- 🔑 **A remessa entre lojas conta como compra aqui também.** A
        -- apuração passou a somá-la (entrada) e subtraí-la (saída) — sem a
        -- mesma linha neste relatório, **a soma dos grupos deixa de fechar com
        -- o CMV do período**, que é a propriedade que dá sentido ao corte por
        -- grupo. Foi o que a bateria acusou: R$ 1.120,00 de diferença.
        -- ⚠️ Só o que ATRAVESSA a fronteira: a transferência entre dois locais
        -- da mesma loja continua se anulando sozinha.
        transferencias AS (
            SELECT m.id_produto, m.id_local,
                   sum(CASE WHEN m.tipo = 'TRANSFERENCIA_ENTRADA' THEN m.custo_total
                            ELSE -m.custo_total END) AS valor
              FROM estoque_movimentos m
              JOIN estoque_movimentos o ON o.id = m.origem_id
             WHERE m.id_unidade = %s
               AND m.tipo IN ('TRANSFERENCIA_ENTRADA', 'TRANSFERENCIA_SAIDA')
               AND m.origem_tipo = 'TRANSFERENCIA'
               AND o.id_unidade <> m.id_unidade
               AND m.data_movimento >= %s AND m.data_movimento < %s
             GROUP BY 1, 2
        ),
        perdas AS (
            SELECT id_produto, id_local, sum(abs(custo_total)) AS valor
              FROM estoque_movimentos
             WHERE id_unidade = %s AND tipo = 'SAIDA_PERDA'
               AND data_movimento >= %s AND data_movimento < %s
             GROUP BY 1, 2
        ),
        -- ⚠️ **O grão da conta é (produto, LOCAL).** Antes era só o produto, e
        -- era por isso que o setor tinha de vir do cadastro. Somar é
        -- associativo, então o total por categoria e por grupo é idêntico ao
        -- de antes — só o setor passa a ler outra coluna.
        chaves AS (
            SELECT id_produto, id_local FROM inicial
            UNION SELECT id_produto, id_local FROM final
            UNION SELECT id_produto, id_local FROM compras
            UNION SELECT id_produto, id_local FROM transferencias
            UNION SELECT id_produto, id_local FROM perdas
        )
        SELECT coalesce(g.nome, %s) AS grupo,
               coalesce(sum(i.valor), 0) AS estoque_inicial,
               coalesce(sum(c.valor), 0) + coalesce(sum(t.valor), 0) AS compras,
               coalesce(sum(f.valor), 0) AS estoque_final,
               -- ⚠️ A remessa entre lojas entra AQUI também, não só na coluna
               -- de compras: é o `cmv` que precisa fechar com a apuração, e
               -- somá-la de um lado e esquecer do outro foi o que abriu os
               -- R$ 1.120,00 que a bateria acusou.
               coalesce(sum(i.valor), 0) + coalesce(sum(c.valor), 0)
                   + coalesce(sum(t.valor), 0) - coalesce(sum(f.valor), 0) AS cmv,
               coalesce(sum(pd.valor), 0) AS perdas,
               count(DISTINCT p.id) FILTER (
                   WHERE coalesce(i.valor, 0) <> 0 OR coalesce(c.valor, 0) <> 0
                      OR coalesce(f.valor, 0) <> 0) AS produtos
          FROM chaves k
          JOIN produtos p ON p.id = k.id_produto
          {junta}
          LEFT JOIN inicial i
                 ON i.id_produto = k.id_produto AND i.id_local = k.id_local
          LEFT JOIN final f
                 ON f.id_produto = k.id_produto AND f.id_local = k.id_local
          LEFT JOIN compras c
                 ON c.id_produto = k.id_produto AND c.id_local = k.id_local
          LEFT JOIN transferencias t
                 ON t.id_produto = k.id_produto AND t.id_local = k.id_local
          LEFT JOIN perdas pd
                 ON pd.id_produto = k.id_produto AND pd.id_local = k.id_local
         GROUP BY 1
        -- ⚠️ A remessa entra no HAVING: um grupo cujo único movimento no período
        -- foi uma transferência entre lojas tem CMV, e sumiria da lista.
        HAVING coalesce(sum(i.valor), 0) <> 0 OR coalesce(sum(c.valor), 0) <> 0
            OR coalesce(sum(f.valor), 0) <> 0 OR coalesce(sum(t.valor), 0) <> 0
         ORDER BY 5 DESC
        """,
        (id_unidade, inicio, id_unidade, fim + timedelta(days=1),
         id_unidade, list(TIPOS_COMPRA), inicio, fim + timedelta(days=1),
         id_unidade, inicio, fim + timedelta(days=1),
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
