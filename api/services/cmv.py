"""CMV — quanto custou o que se vendeu, e onde está a diferença.

    CMV real     = estoque inicial + compras − estoque final
    CMV teórico  = Σ (quantidade vendida × custo da ficha na data da venda)
    variância    = real − teórico

A variância é o número que interessa: ela nomeia o que a soma esconde. Positiva
quer dizer que saiu mais do estoque do que as receitas justificam — perda,
porção fora do padrão ou desvio. Negativa costuma ser prato vendido sem ficha
(ou ficha exagerada).

**O valor do estoque numa data vem do próprio razão**: para cada produto e local,
o último movimento antes do corte já carrega `saldo_apos` e `custo_medio_apos`.
Não se recalcula série nenhuma — é para isso que a fotografia existe.
"""

from datetime import date, timedelta
from decimal import Decimal

from services.custos import dec

# O que é compra de verdade (entra dinheiro novo no estoque). Transferência e
# produção são transformação interna: não entram na conta.
TIPOS_COMPRA = ("ENTRADA_NF", "ENTRADA_MANUAL")


def tipos_fora_do_cmv(cur) -> list[str]:
    """Os tipos de produto que a casa tirou do CMV real.

    ⚠️ **Sair é sair da conta INTEIRA.** O CMV real é
    `inicial + compras − final`; tirar só as compras deixaria o estoque de
    detergente do começo e do fim dentro da conta, e a diferença entre os dois
    viraria custo de comida do mesmo jeito — com sinal imprevisível. Quem sai,
    sai das três pontas, e aí a contribuição do grupo se anula por completo.

    ⚠️ Devolve `[]` quando não há nenhum, e quem chama trata isso como "não
    filtra nada". Um `NOT IN ()` vazio no Postgres é erro de sintaxe, e um
    `<> ALL('{}')` é verdadeiro para todos — dependia de qual se escrevesse
    primeiro. Aqui a resposta é uma só.
    """
    cur.execute(
        """SELECT t.tipo FROM cmv_grupo_tipos t
             JOIN cmv_grupos g ON g.id = t.id_grupo
            WHERE g.ativo AND NOT g.considerar_no_cmv"""
    )
    return [r["tipo"] for r in cur.fetchall()]


def valor_do_estoque(cur, id_unidade: int, ate: date | None = None,
                     fora: list[str] | None = None) -> Decimal:
    """Valor do estoque no fim do dia `ate` (ou agora, se None).

    `fora` são os tipos de produto que a casa tirou do CMV real. Quando vem, o
    valor sai **sem eles** — é o mesmo filtro nas três pontas da conta.

    ⚠️ **Data de hoje (ou adiante) responde pelo SALDO, não pelo razão.** Os dois
    dão o mesmo número — `estoque_saldos` é a fotografia corrente, e o razão não
    aceita movimento no futuro —, mas o caminho é outro: o saldo é uma linha por
    produto e local, o razão é um `DISTINCT ON` sobre tudo o que já aconteceu.
    Com 400.000 movimentos, 837 ms contra alguns milissegundos. E é o caso mais
    comum: o mês corrente termina hoje, então toda apuração de mês aberto passa
    por aqui.
    """
    # ⚠️ O filtro entra como `(%(fora)s IS NULL OR ...)` em vez de o SQL mudar
    # de forma conforme haja ou não tipos de fora: duas consultas para a mesma
    # pergunta divergem no primeiro ajuste que alguém faz só numa delas.
    p = {"u": id_unidade, "fora": fora or None}

    if ate is None or ate >= date.today():
        cur.execute(
            """SELECT coalesce(sum(s.quantidade * s.custo_medio), 0) AS valor
                 FROM estoque_saldos s
                 JOIN produtos pr ON pr.id = s.id_produto
                WHERE s.id_unidade = %(u)s
                  AND (%(fora)s::varchar[] IS NULL OR pr.tipo <> ALL(%(fora)s))""",
            p,
        )
        return dec(cur.fetchone()["valor"])

    cur.execute(
        """
        WITH ultimo AS (
            SELECT DISTINCT ON (m.id_produto, m.id_local)
                   m.id_produto, m.id_local, m.saldo_apos, m.custo_medio_apos
              FROM estoque_movimentos m
              JOIN produtos pr ON pr.id = m.id_produto
             WHERE m.id_unidade = %(u)s AND m.data_movimento < %(ate)s
               AND (%(fora)s::varchar[] IS NULL OR pr.tipo <> ALL(%(fora)s))
             ORDER BY m.id_produto, m.id_local, m.id DESC
        )
        SELECT coalesce(sum(saldo_apos * custo_medio_apos), 0) AS valor FROM ultimo
        """,
        {**p, "ate": ate + timedelta(days=1)},
    )
    return dec(cur.fetchone()["valor"])


def movimentacao_por_produto(cur, id_unidade: int, inicio: date, fim: date) -> list[dict]:
    """O que cada produto tinha, o que entrou, o que saiu e o que sobrou.

    O CMV do mês é uma linha só e diz o RESULTADO; esta é a conta por produto,
    que é o que se confere e o que se manda ao contador.

    Três decisões que mudam o número:

    * **O saldo inicial e o final saem da fotografia do razão** (`saldo_apos` e
      `custo_medio_apos` do último movimento antes do corte), não de uma soma
      de quantidades. Somar entradas menos saídas daria a mesma quantidade e
      **outro valor**, porque o custo médio muda a cada entrada.
    * **Entradas e saídas são TODAS**, não só compras e vendas: produção,
      transferência e ajuste também movem o estoque, e quem confere a contagem
      precisa ver por onde a diferença passou. (A soma que vira CMV continua
      sendo só a de compras — são perguntas diferentes.)
    * Produto que **não se mexeu no mês mas tem saldo** entra na lista: sumir
      dele faria o total da coluna não fechar com o estoque.
    """
    limite = fim + timedelta(days=1)
    cur.execute(
        """
        WITH inicial AS (
            SELECT DISTINCT ON (id_produto, id_local)
                   id_produto, id_local, saldo_apos, custo_medio_apos
              FROM estoque_movimentos
             WHERE id_unidade = %(u)s AND data_movimento < %(inicio)s
             ORDER BY id_produto, id_local, id DESC
        ),
        final AS (
            -- ⚠️ Quando o período termina HOJE — o caso do mês aberto, que é o
            -- que se olha todo dia — a fotografia final é o próprio saldo:
            -- `estoque_saldos` é uma linha por produto e local, contra um
            -- `DISTINCT ON` sobre o razão inteiro. A resposta é a mesma; o
            -- caminho, não. Data passada continua pelo razão, que é o único
            -- que sabe como as coisas estavam antes.
            SELECT id_produto, id_local, quantidade AS saldo_apos,
                   custo_medio AS custo_medio_apos
              FROM estoque_saldos
             WHERE id_unidade = %(u)s AND %(fim_e_hoje)s
            UNION ALL
            -- O `DISTINCT ON` mora numa subconsulta: o `ORDER BY` de um lado da
            -- união seria lido como ordenação do resultado inteiro.
            SELECT id_produto, id_local, saldo_apos, custo_medio_apos FROM (
                SELECT DISTINCT ON (id_produto, id_local)
                       id_produto, id_local, saldo_apos, custo_medio_apos
                  FROM estoque_movimentos
                 WHERE id_unidade = %(u)s AND NOT %(fim_e_hoje)s
                   AND data_movimento < %(limite)s
                 ORDER BY id_produto, id_local, id DESC
            ) AS _pelo_razao
        ),
        no_periodo AS (
            SELECT id_produto,
                   sum(CASE WHEN quantidade > 0 THEN quantidade ELSE 0 END) AS qtd_entradas,
                   sum(CASE WHEN quantidade > 0 THEN abs(custo_total) ELSE 0 END)
                       AS valor_entradas,
                   sum(CASE WHEN quantidade < 0 THEN -quantidade ELSE 0 END) AS qtd_saidas,
                   sum(CASE WHEN quantidade < 0 THEN abs(custo_total) ELSE 0 END)
                       AS valor_saidas
              FROM estoque_movimentos
             WHERE id_unidade = %(u)s
               AND data_movimento >= %(inicio)s AND data_movimento < %(limite)s
             GROUP BY id_produto
        ),
        ini AS (
            SELECT id_produto, sum(saldo_apos) AS qtd,
                   sum(saldo_apos * custo_medio_apos) AS valor
              FROM inicial GROUP BY id_produto
        ),
        fim AS (
            SELECT id_produto, sum(saldo_apos) AS qtd,
                   sum(saldo_apos * custo_medio_apos) AS valor
              FROM final GROUP BY id_produto
        ),
        envolvidos AS (
            SELECT id_produto FROM ini
            UNION SELECT id_produto FROM fim
            UNION SELECT id_produto FROM no_periodo
        )
        SELECT e.id_produto, p.codigo, p.nome AS produto, p.um_estoque,
               c.nome AS categoria, s.nome AS setor,
               coalesce(ini.qtd, 0) AS qtd_inicial,
               round(coalesce(ini.valor, 0), 2) AS valor_inicial,
               coalesce(np.qtd_entradas, 0) AS qtd_entradas,
               round(coalesce(np.valor_entradas, 0), 2) AS valor_entradas,
               coalesce(np.qtd_saidas, 0) AS qtd_saidas,
               round(coalesce(np.valor_saidas, 0), 2) AS valor_saidas,
               coalesce(fim.qtd, 0) AS qtd_final,
               round(coalesce(fim.valor, 0), 2) AS valor_final,
               CASE WHEN coalesce(fim.qtd, 0) <> 0
                    THEN round(coalesce(fim.valor, 0) / fim.qtd, 6) ELSE 0 END
                   AS custo_medio_final
          FROM envolvidos e
          JOIN produtos p ON p.id = e.id_produto
          LEFT JOIN categorias c ON c.id = p.id_categoria
          LEFT JOIN setores s ON s.id = p.id_setor
          LEFT JOIN ini ON ini.id_produto = e.id_produto
          LEFT JOIN fim ON fim.id_produto = e.id_produto
          LEFT JOIN no_periodo np ON np.id_produto = e.id_produto
         WHERE coalesce(ini.qtd, 0) <> 0 OR coalesce(fim.qtd, 0) <> 0
               OR np.id_produto IS NOT NULL
         ORDER BY lower(p.nome)
        """,
        {"u": id_unidade, "inicio": inicio, "limite": limite,
         "fim_e_hoje": fim >= date.today()},
    )
    return [dict(r) for r in cur.fetchall()]


def congelar_movimentacao(cur, id_fechamento: int, id_unidade: int,
                          inicio: date, fim: date) -> int:
    """Grava a movimentação do mês no fechamento. Devolve quantas linhas.

    Nome, código, categoria e setor vão GRAVADOS junto: renomear o produto ou
    trocá-lo de categoria depois não pode reescrever o relatório de um mês que
    já foi fechado.
    """
    cur.execute("DELETE FROM cmv_movimentacao WHERE id_fechamento = %s", (id_fechamento,))
    linhas = movimentacao_por_produto(cur, id_unidade, inicio, fim)
    for l in linhas:
        cur.execute(
            """INSERT INTO cmv_movimentacao
                   (id_fechamento, id_produto, codigo, produto, um_estoque, categoria, setor,
                    qtd_inicial, valor_inicial, qtd_entradas, valor_entradas,
                    qtd_saidas, valor_saidas, qtd_final, valor_final, custo_medio_final)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (id_fechamento, l["id_produto"], l["codigo"], l["produto"], l["um_estoque"],
             l["categoria"], l["setor"], l["qtd_inicial"], l["valor_inicial"],
             l["qtd_entradas"], l["valor_entradas"], l["qtd_saidas"], l["valor_saidas"],
             l["qtd_final"], l["valor_final"], l["custo_medio_final"]),
        )
    return len(linhas)


def movimentacao_congelada(cur, id_fechamento: int) -> list[dict]:
    """A movimentação como ficou no fechamento — não se recalcula."""
    cur.execute(
        """SELECT id_produto, codigo, produto, um_estoque, categoria, setor,
                  qtd_inicial, valor_inicial, qtd_entradas, valor_entradas,
                  qtd_saidas, valor_saidas, qtd_final, valor_final, custo_medio_final
             FROM cmv_movimentacao WHERE id_fechamento = %s
            ORDER BY lower(produto)""",
        (id_fechamento,),
    )
    return [dict(r) for r in cur.fetchall()]


def _soma_movimentos(cur, id_unidade: int, inicio: date, fim: date, tipos,
                    fora: list[str] | None = None) -> Decimal:
    cur.execute(
        """SELECT coalesce(sum(abs(m.custo_total)), 0) AS valor
             FROM estoque_movimentos m
             JOIN produtos pr ON pr.id = m.id_produto
            WHERE m.id_unidade = %(u)s AND m.tipo = ANY(%(tipos)s)
              AND m.data_movimento >= %(inicio)s AND m.data_movimento < %(limite)s
              AND (%(fora)s::varchar[] IS NULL OR pr.tipo <> ALL(%(fora)s))""",
        {"u": id_unidade, "tipos": list(tipos), "inicio": inicio,
         "limite": fim + timedelta(days=1), "fora": fora or None},
    )
    return dec(cur.fetchone()["valor"])


def apurar(cur, id_unidade: int, inicio: date, fim: date) -> dict:
    """A conta do período inteiro, com os pedaços que explicam a variância."""
    # ⚠️ **Os tipos que a casa tirou do CMV saem das TRÊS pontas.** Detergente e
    # marmita não são comida, e o food cost é o número que vira decisão de
    # cardápio. Tirar só as compras deixaria o estoque de limpeza do começo e do
    # fim na conta, e a diferença entre os dois viraria custo de comida do mesmo
    # jeito — com sinal imprevisível. Saindo das três, a contribuição do grupo
    # se anula por completo.
    fora = tipos_fora_do_cmv(cur)

    estoque_inicial = valor_do_estoque(cur, id_unidade, inicio - timedelta(days=1), fora)
    estoque_final = valor_do_estoque(cur, id_unidade, fim, fora)
    compras = _soma_movimentos(cur, id_unidade, inicio, fim, TIPOS_COMPRA, fora)

    cmv_real = estoque_inicial + compras - estoque_final

    perdas = _soma_movimentos(cur, id_unidade, inicio, fim, ("SAIDA_PERDA",), fora)
    consumo = _soma_movimentos(cur, id_unidade, inicio, fim, ("SAIDA_CONSUMO_INTERNO",), fora)
    cur.execute(
        """SELECT coalesce(sum(m.custo_total
                               * CASE WHEN m.quantidade > 0 THEN 1 ELSE -1 END), 0) AS valor
             FROM estoque_movimentos m
             JOIN produtos pr ON pr.id = m.id_produto
            WHERE m.id_unidade = %(u)s AND m.tipo LIKE 'AJUSTE_INVENTARIO%%'
              AND m.data_movimento >= %(inicio)s AND m.data_movimento < %(limite)s
              AND (%(fora)s::varchar[] IS NULL OR pr.tipo <> ALL(%(fora)s))""",
        {"u": id_unidade, "inicio": inicio, "limite": fim + timedelta(days=1),
         "fora": fora or None},
    )
    ajustes = dec(cur.fetchone()["valor"])

    # Receita e CMV teórico saem das vendas do período.
    cur.execute(
        """SELECT coalesce(sum(vi.valor_total), 0) AS receita,
                  coalesce(sum(vi.quantidade * coalesce(vi.custo_ficha_unitario, 0)), 0) AS teorico,
                  count(*) FILTER (WHERE vi.custo_ficha_unitario IS NULL) AS itens_sem_custo,
                  coalesce(sum(vi.valor_total) FILTER (WHERE vi.custo_ficha_unitario IS NOT NULL), 0)
                      AS receita_com_custo,
                  count(DISTINCT v.id) AS vendas
             FROM venda_itens vi
             JOIN vendas v ON v.id = vi.id_venda
            WHERE v.id_unidade = %s AND NOT v.cancelada
              AND v.data BETWEEN %s AND %s""",
        (id_unidade, inicio, fim),
    )
    v = cur.fetchone()
    receita = dec(v["receita"])
    cmv_teorico = dec(v["teorico"])

    cobertura = (
        (dec(v["receita_com_custo"]) / receita * 100) if receita else Decimal(0)
    )

    return {
        "inicio": inicio,
        "fim": fim,
        "estoque_inicial": estoque_inicial,
        "compras": compras,
        "estoque_final": estoque_final,
        "cmv_real": cmv_real,
        "cmv_teorico": cmv_teorico,
        "variancia": cmv_real - cmv_teorico,
        "perdas": perdas,
        "consumo_interno": consumo,
        "ajustes": ajustes,
        "receita": receita,
        "vendas": v["vendas"],
        "itens_sem_custo": v["itens_sem_custo"],
        # Sem isto o CMV teórico mente por omissão: metade dos pratos sem ficha
        # dá um teórico pela metade e uma variância enorme que não existe.
        "cobertura_ficha_pct": cobertura,
        # Os tipos que ficaram de fora — a tela precisa dizer isso ao lado do
        # número, senão o CMV parece menor sem explicação.
        "tipos_fora_do_cmv": fora,
        "food_cost_pct": (cmv_real / receita * 100) if receita else None,
    }


def curva_abc(cur, id_unidade: int, inicio: date, fim: date, limite: int = 50) -> list[dict]:
    """Onde o dinheiro do estoque foi parar no período — 80/95/100."""
    cur.execute(
        """SELECT m.id_produto, p.codigo, p.nome AS produto, p.um_estoque,
                  sum(abs(m.quantidade)) AS quantidade,
                  sum(abs(m.custo_total)) AS valor
             FROM estoque_movimentos m
             JOIN produtos p ON p.id = m.id_produto
            WHERE m.id_unidade = %s AND m.quantidade < 0
              AND m.tipo NOT IN ('TRANSFERENCIA_SAIDA', 'ESTORNO_SAIDA')
              AND m.data_movimento >= %s AND m.data_movimento < %s
            GROUP BY m.id_produto, p.codigo, p.nome, p.um_estoque
            ORDER BY valor DESC
            LIMIT %s""",
        (id_unidade, inicio, fim + timedelta(days=1), limite),
    )
    linhas = [dict(r) for r in cur.fetchall()]
    total = sum(dec(l["valor"]) for l in linhas) or Decimal(1)

    acumulado = Decimal(0)
    for l in linhas:
        valor = dec(l["valor"])
        acumulado += valor
        participacao = valor / total * 100
        acumulada = acumulado / total * 100
        l["valor"] = float(valor)
        l["quantidade"] = float(dec(l["quantidade"]))
        l["participacao_pct"] = float(participacao)
        l["acumulada_pct"] = float(acumulada)
        l["classe"] = "A" if acumulada <= 80 else ("B" if acumulada <= 95 else "C")
    return linhas


def margem_por_prato(cur, id_unidade: int, inicio: date, fim: date, limite: int = 50) -> list[dict]:
    """O que cada prato vendeu, custou e deixou — a base da engenharia de cardápio."""
    cur.execute(
        """SELECT vi.id_produto, coalesce(p.nome, vi.descricao_pdv, 'Sem vínculo') AS produto,
                  p.codigo,
                  sum(vi.quantidade) AS quantidade,
                  sum(vi.valor_total) AS receita,
                  sum(vi.quantidade * coalesce(vi.custo_ficha_unitario, 0)) AS custo,
                  bool_or(vi.custo_ficha_unitario IS NULL) AS sem_custo
             FROM venda_itens vi
             JOIN vendas v ON v.id = vi.id_venda
             LEFT JOIN produtos p ON p.id = vi.id_produto
            WHERE v.id_unidade = %s AND NOT v.cancelada AND v.data BETWEEN %s AND %s
            GROUP BY vi.id_produto, coalesce(p.nome, vi.descricao_pdv, 'Sem vínculo'), p.codigo
            ORDER BY receita DESC
            LIMIT %s""",
        (id_unidade, inicio, fim, limite),
    )
    linhas = []
    for r in cur.fetchall():
        receita, custo = dec(r["receita"]), dec(r["custo"])
        margem = receita - custo
        linhas.append({
            "id_produto": r["id_produto"],
            "produto": r["produto"],
            "codigo": r["codigo"],
            "quantidade": float(dec(r["quantidade"])),
            "receita": float(receita),
            "custo": float(custo),
            "margem": float(margem),
            "margem_pct": float(margem / receita * 100) if receita else None,
            "food_cost_pct": float(custo / receita * 100) if receita else None,
            "sem_custo": r["sem_custo"],
        })
    return linhas


def custo_teorico_do_produto(cur, id_produto: int,
                            _nivel: int = 0) -> tuple[Decimal | None, str]:
    """Quanto uma unidade vendida deste produto deveria custar.

    Três regras, nesta ordem:

    * **Kit/combo**: a soma dos componentes, cada um resolvido por esta mesma
      função — é o que faz o combo do PDV deixar de entrar sem custo.
    * **Produção própria**: pela ficha homologada vigente.
    * **Revenda**: pelo custo médio do estoque, que é o que ela custou mesmo.
    """
    from services import custos  # ciclo de import: só aqui dentro

    cur.execute("SELECT tipo FROM produtos WHERE id = %s", (id_produto,))
    linha = cur.fetchone()
    if linha and linha["tipo"] == "KIT":
        from services import kits

        valor, origem, _detalhe = kits.custo(cur, id_produto, _nivel)
        return valor, origem

    cur.execute(
        """SELECT f.id, f.rendimento_qtd
             FROM fichas_tecnicas f
            WHERE f.id_produto = %s AND f.status = 'HOMOLOGADA' AND f.vigente_ate IS NULL""",
        (id_produto,),
    )
    ficha = cur.fetchone()
    if ficha:
        calculo = custos.custo_da_ficha(cur, ficha["id"])
        if calculo["completo"] or calculo["custo_total"] > 0:
            rendimento = dec(ficha["rendimento_qtd"]) or Decimal(1)
            return (calculo["custo_total"] / rendimento), (
                "ficha" if calculo["completo"] else "ficha_parcial"
            )
        return None, "ficha_sem_custo"

    unitario, origem = custos.custo_do_insumo(cur, id_produto)
    return unitario, origem
