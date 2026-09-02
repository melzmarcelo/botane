"""A memória de cálculo — como cada número da apuração foi obtido.

🔑 **Pedido da contabilidade (02/09/2026).** O sistema já dizia o RESULTADO (a
apuração do CMV, dez linhas) e já provava a IDENTIDADE (a movimentação por
produto, onde `inicial + entradas − saídas = final` fecha na própria planilha).
O que faltava era o passo do meio: **os documentos que compõem cada linha**.
Perguntado "estes R$ X de compras, de quais notas são?", o sistema não tinha
resposta — era preciso abrir a lista de Compras, filtrar o período e somar à mão.

⚠️ **E somar as notas à mão dá OUTRO número, de propósito** — este módulo existe
tanto para abrir a conta quanto para explicar essa diferença. A linha "Compras"
não é a soma dos totais das notas: ela soma os MOVIMENTOS de entrada, que trazem
frete, IPI e ST já rateados por item; tira os grupos que a casa pôs fora do CMV
(limpeza, embalagem, utensílio); e soma a remessa recebida de outra loja. Sem a
conciliação, o contador que soma as notas encontra diferença e ela parece erro.

⚠️ **Nada aqui recalcula.** Todo número sai das mesmas consultas que a apuração
usa — `cmv.valor_do_estoque` para as pontas e os mesmos tipos de movimento para
o meio. Uma segunda implementação divergiria no primeiro caso de borda, e o
sintoma seria a memória de cálculo discordando do número que ela existe para
explicar: pior que não ter memória nenhuma.
"""

from datetime import date, timedelta
from decimal import Decimal

from services import cmv as motor
from services import estoque as estoque_motor
from services.custos import dec

# Os movimentos que a apuração conta como compra. Importado do motor para não
# haver duas listas: acrescentar um tipo lá e esquecer aqui faria a conciliação
# acusar diferença onde não há.
TIPOS_COMPRA = motor.TIPOS_COMPRA


def estoque_em(cur, id_unidade: int, ate: date | None,
               fora: list[str] | None = None) -> list[dict]:
    """A composição do estoque numa data: produto, quantidade, custo e valor.

    🔑 **Espelha `cmv.valor_do_estoque` passo a passo, inclusive no atalho.**
    Aquela função responde por dois caminhos — `estoque_saldos` para hoje (uma
    linha por produto e local) e a fotografia do razão para data passada (um
    `DISTINCT ON` sobre tudo o que já aconteceu) — e os dois dão o mesmo número.
    Escrever aqui uma terceira consulta faria a soma desta lista discordar da
    linha da apuração no primeiro caso de borda, que é exatamente o defeito que
    uma memória de cálculo não pode ter.

    ⚠️ **A linha é o PRODUTO, não a prateleira.** O documento contábil responde
    "quanto vale o item", e o mesmo café pode estar em duas prateleiras com
    médios diferentes — o custo unitário sai ponderado (`valor ÷ quantidade`),
    que é o único que reconstrói o valor.

    ⚠️ **Produto com saldo ZERO fica de fora.** Ele não compõe valor nenhum, e
    numa base real são milhares de linhas de ruído entre as que importam.
    Quantidade negativa ENTRA: saldo negativo existe (a saída que não achou
    estoque) e esconder a linha faria a soma não fechar.
    """
    p = {"u": id_unidade, "fora": fora or None}

    if ate is None or ate >= date.today():
        cur.execute(
            """SELECT s.id_produto, pr.codigo, pr.nome AS produto, pr.um_estoque,
                      c.nome AS categoria, g.nome AS setor,
                      sum(s.quantidade) AS quantidade,
                      sum(s.quantidade * s.custo_medio) AS valor
                 FROM estoque_saldos s
                 JOIN produtos pr ON pr.id = s.id_produto
                 LEFT JOIN categorias c ON c.id = pr.id_categoria
                 LEFT JOIN setores g ON g.id = pr.id_setor
                WHERE s.id_unidade = %(u)s
                  AND (%(fora)s::varchar[] IS NULL OR pr.tipo <> ALL(%(fora)s))
                GROUP BY s.id_produto, pr.codigo, pr.nome, pr.um_estoque, c.nome, g.nome
               HAVING sum(s.quantidade) <> 0
                ORDER BY pr.nome""",
            p,
        )
    else:
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
            SELECT u.id_produto, pr.codigo, pr.nome AS produto, pr.um_estoque,
                   c.nome AS categoria, g.nome AS setor,
                   sum(u.saldo_apos) AS quantidade,
                   sum(u.saldo_apos * u.custo_medio_apos) AS valor
              FROM ultimo u
              JOIN produtos pr ON pr.id = u.id_produto
              LEFT JOIN categorias c ON c.id = pr.id_categoria
              LEFT JOIN setores g ON g.id = pr.id_setor
             GROUP BY u.id_produto, pr.codigo, pr.nome, pr.um_estoque, c.nome, g.nome
            HAVING sum(u.saldo_apos) <> 0
             ORDER BY pr.nome
            """,
            {**p, "ate": ate + timedelta(days=1)},
        )

    linhas = []
    for r in cur.fetchall():
        qtd, valor = dec(r["quantidade"]), dec(r["valor"])
        linhas.append({
            **dict(r),
            "quantidade": qtd,
            "valor": valor,
            # ⚠️ Ponderado, e não a média dos médios: é o único custo unitário
            # que multiplicado pela quantidade devolve o valor da linha.
            "custo_unitario": (valor / qtd) if qtd else Decimal(0),
        })
    return linhas


def compras_por_nota(cur, id_unidade: int, inicio: date, fim: date,
                     fora: list[str] | None = None) -> list[dict]:
    """As entradas do período agrupadas pelo DOCUMENTO que as originou.

    🔑 É a resposta para *"estes R$ X de compras, de quais notas são?"* — a
    pergunta que a contabilidade faz primeiro e que o sistema não respondia.

    ⚠️ **O valor da linha é o que entrou no RAZÃO, não o total da nota.** São
    números diferentes e ambos aparecem, lado a lado, porque a diferença é a
    coisa mais perguntada da reunião: o razão recebe a mercadoria com frete, IPI
    e ST rateados por item e **sem** os itens de tipo que a casa tirou do CMV.

    ⚠️ **Entrada manual não tem nota**, e aparece agrupada como tal — omiti-la
    faria a soma das linhas não fechar com a linha "Compras".
    """
    cur.execute(
        """SELECT n.id AS id_nota, n.numero, n.serie, n.data_emissao, n.data_entrada,
                  n.valor_total AS valor_da_nota, n.valor_frete, n.valor_outros,
                  n.origem AS origem_da_nota,
                  coalesce(f.nome, n.nome_emitente) AS fornecedor,
                  m.tipo,
                  count(*) AS itens,
                  sum(abs(m.custo_total)) AS valor_no_razao
             FROM estoque_movimentos m
             JOIN produtos pr ON pr.id = m.id_produto
             LEFT JOIN notas_entrada n
                    ON n.id = m.origem_id AND m.origem_tipo = 'NOTA'
             LEFT JOIN fornecedores f ON f.id = n.id_fornecedor
            WHERE m.id_unidade = %(u)s AND m.tipo = ANY(%(tipos)s)
              AND m.data_movimento >= %(inicio)s AND m.data_movimento < %(limite)s
              AND (%(fora)s::varchar[] IS NULL OR pr.tipo <> ALL(%(fora)s))
            GROUP BY n.id, n.numero, n.serie, n.data_emissao, n.data_entrada,
                     n.valor_total, n.valor_frete, n.valor_outros, n.origem,
                     f.nome, n.nome_emitente, m.tipo
            ORDER BY n.data_entrada NULLS LAST, n.numero NULLS LAST""",
        {"u": id_unidade, "tipos": list(TIPOS_COMPRA), "inicio": inicio,
         "limite": fim + timedelta(days=1), "fora": fora or None},
    )
    linhas = []
    for r in cur.fetchall():
        d = dict(r)
        no_razao = dec(d["valor_no_razao"])
        da_nota = dec(d["valor_da_nota"]) if d["valor_da_nota"] is not None else None
        linhas.append({
            **d,
            "documento": (f"NF {d['numero']}" + (f"/{d['serie']}" if d["serie"] else "")
                          if d["numero"] else "sem nota (entrada manual)"),
            "valor_no_razao": no_razao,
            "valor_da_nota": da_nota,
            # ⚠️ Só quando há nota: sem ela a diferença não existe, e um zero
            # ali afirmaria que a entrada manual bate com um documento.
            "diferenca": (no_razao - da_nota) if da_nota is not None else None,
        })
    return linhas


def conciliacao_compras(cur, id_unidade: int, inicio: date, fim: date,
                        fora: list[str] | None = None) -> list[dict]:
    """De quanto somam as notas do período até a linha "Compras" da apuração.

    🔑 **É a peça que faltava, e a que evita a discussão.** O contador soma os
    totais das notas fiscais do período, compara com a linha "Compras" e acha
    diferença — porque são grandezas diferentes. Cada parcela da diferença tem
    causa conhecida, e esta função as escreve uma a uma, em ordem, terminando
    exatamente no número da apuração.
    """
    limite = fim + timedelta(days=1)
    base = {"u": id_unidade, "inicio": inicio, "limite": limite}

    # 1. O que as notas LANÇADAS no período dizem valer, pelo total delas.
    cur.execute(
        """SELECT coalesce(sum(n.valor_total), 0) AS total, count(*) AS quantas
             FROM notas_entrada n
            WHERE n.id_unidade = %(u)s AND n.status = 'LANCADA'
              AND coalesce(n.data_entrada, n.data_emissao) >= %(inicio)s
              AND coalesce(n.data_entrada, n.data_emissao) < %(limite)s""",
        base,
    )
    r = cur.fetchone()
    total_notas, quantas = dec(r["total"]), r["quantas"]

    # 2. O que dessas notas de fato entrou no razão, sem filtro de tipo.
    cur.execute(
        """SELECT coalesce(sum(abs(m.custo_total)), 0) AS valor
             FROM estoque_movimentos m
            WHERE m.id_unidade = %(u)s AND m.tipo = 'ENTRADA_NF'
              AND m.data_movimento >= %(inicio)s AND m.data_movimento < %(limite)s""",
        base,
    )
    no_razao_tudo = dec(cur.fetchone()["valor"])

    # 3. Quanto disso é de produto que a casa tirou do CMV.
    excluido = Decimal(0)
    if fora:
        cur.execute(
            """SELECT coalesce(sum(abs(m.custo_total)), 0) AS valor
                 FROM estoque_movimentos m
                 JOIN produtos pr ON pr.id = m.id_produto
                WHERE m.id_unidade = %(u)s AND m.tipo = ANY(%(tipos)s)
                  AND m.data_movimento >= %(inicio)s AND m.data_movimento < %(limite)s
                  AND pr.tipo = ANY(%(fora)s)""",
            {**base, "tipos": list(TIPOS_COMPRA), "fora": fora},
        )
        excluido = dec(cur.fetchone()["valor"])

    # 4. Entrada digitada sem nota nenhuma atrás.
    cur.execute(
        """SELECT coalesce(sum(abs(m.custo_total)), 0) AS valor
             FROM estoque_movimentos m
             JOIN produtos pr ON pr.id = m.id_produto
            WHERE m.id_unidade = %(u)s AND m.tipo = 'ENTRADA_MANUAL'
              AND m.data_movimento >= %(inicio)s AND m.data_movimento < %(limite)s
              AND (%(fora)s::varchar[] IS NULL OR pr.tipo <> ALL(%(fora)s))""",
        {**base, "fora": fora or None},
    )
    manual = dec(cur.fetchone()["valor"])

    remessa = motor._transferencia_entre_lojas(cur, id_unidade, inicio, fim, fora)
    compras = motor._soma_movimentos(cur, id_unidade, inicio, fim, TIPOS_COMPRA, fora)

    def cent(v) -> Decimal:
        return Decimal(str(v)).quantize(Decimal("0.01"))

    # ⚠️ **O sinal vai no VALOR, não no rótulo.** A primeira versão escrevia
    # "(−) o que não vira mercadoria" e somava um número positivo: quem lesse
    # via a conta andar para o lado contrário do que o texto dizia. Aqui a
    # diferença pode ir para os dois lados — item ignorado tira, rateio de
    # acessórias põe — e só o número sabe para qual.
    linhas = [
        {"linha": f"Soma dos totais das {quantas} nota(s) lançada(s) no período",
         "valor": cent(total_notas)},
        {"linha": "(±) Diferença entre o total da nota e o que virou mercadoria no "
                  "estoque (item ignorado, desconto, frete e IPI/ST rateados)",
         "valor": cent(no_razao_tudo - total_notas)},
        {"linha": "(=) Entradas por nota, como entraram no razão",
         "valor": cent(no_razao_tudo)},
        {"linha": "(−) Compras de tipo fora do CMV (limpeza, embalagem, utensílio)",
         "valor": cent(-excluido)},
        {"linha": "(+) Entradas digitadas sem nota", "valor": cent(manual)},
        {"linha": "(+) Remessa recebida de outra loja, menos a enviada",
         "valor": cent(remessa)},
        {"linha": "(=) Linha “Compras” da apuração", "valor": cent(compras + remessa)},
    ]
    return linhas


def memoria_do_produto(cur, id_unidade: int, id_produto: int,
                       inicio: date, fim: date) -> list[dict]:
    """Um insumo, movimento a movimento, com a CONTA do custo médio à vista.

    🔑 **É a resposta para "como você chegou nesse custo unitário?".** O razão já
    guardava `saldo_apos` e `custo_medio_apos` de cada movimento — o que faltava
    era mostrar a aritmética entre um e outro:

        (saldo anterior × médio anterior + quantidade × custo) ÷ novo saldo

    Sem a conta escrita, o número aparece já pronto e não se confere. Com ela, o
    contador refaz a linha na calculadora.

    ⚠️ **A conta é reconstruída do que ficou GRAVADO**, nunca recalculada: o
    médio anterior é o `custo_medio_apos` do movimento anterior, não uma média
    refeita agora. Recalcular daria uma segunda verdade sobre o passado — e o
    razão é append-only justamente para não ter duas.

    ⚠️ **A saída não muda o médio**, e a linha diz isso em vez de repetir a
    fórmula: é a propriedade que faz o custo médio ser *móvel* e não *do dia*.
    """
    cur.execute(
        """SELECT m.id, m.data_movimento, m.tipo, l.nome AS local,
                  m.quantidade, m.custo_unitario, m.custo_total,
                  m.saldo_apos, m.custo_medio_apos, m.custo_provisorio,
                  m.documento, m.observacao, u.nome AS usuario
             FROM estoque_movimentos m
             JOIN locais_estoque l ON l.id = m.id_local
             LEFT JOIN usuarios u ON u.id = m.id_usuario
            WHERE m.id_unidade = %s AND m.id_produto = %s
              AND m.data_movimento >= %s AND m.data_movimento < %s
            ORDER BY m.id""",
        (id_unidade, id_produto, inicio, fim + timedelta(days=1)),
    )
    movimentos = [dict(r) for r in cur.fetchall()]

    # O saldo com que o período começa: a fotografia do último movimento antes
    # dele. É a mesma fonte de `valor_do_estoque` para data passada.
    cur.execute(
        """SELECT DISTINCT ON (m.id_local) m.id_local, m.saldo_apos, m.custo_medio_apos
             FROM estoque_movimentos m
            WHERE m.id_unidade = %s AND m.id_produto = %s AND m.data_movimento < %s
            ORDER BY m.id_local, m.id DESC""",
        (id_unidade, id_produto, inicio),
    )
    antes = cur.fetchall()
    saldo = sum((dec(r["saldo_apos"]) for r in antes), Decimal(0))
    valor = sum((dec(r["saldo_apos"]) * dec(r["custo_medio_apos"]) for r in antes), Decimal(0))
    medio = (valor / saldo) if saldo else Decimal(0)

    linhas = [{
        "data": inicio,
        "movimento": "Saldo de abertura",
        "local": "",
        "quantidade": saldo,
        "custo_unitario": medio,
        "valor": valor,
        "saldo_apos": saldo,
        "custo_medio_apos": medio,
        "conta": "o saldo com que o período começa",
    }]

    anterior_saldo, anterior_medio = saldo, medio
    for m in movimentos:
        qtd = dec(m["quantidade"])
        novo_saldo, novo_medio = dec(m["saldo_apos"]), dec(m["custo_medio_apos"])
        if qtd > 0 and novo_saldo:
            conta = (f"({_n(anterior_saldo)} × {_r(anterior_medio)}"
                     f" + {_n(qtd)} × {_r(dec(m['custo_unitario']))})"
                     f" ÷ {_n(novo_saldo)} = {_r(novo_medio)}")
        elif qtd < 0:
            conta = f"saída pelo médio vigente ({_r(anterior_medio)}) — não altera o custo médio"
        else:
            # Reavaliação: quantidade zero, valor diferente de zero.
            conta = f"reavaliação de custo — o médio passa a {_r(novo_medio)}"
        linhas.append({
            "data": m["data_movimento"],
            # ⚠️ O rótulo vem de `estoque.ROTULOS`, que é a lista viva — escrever
            # "Entrada por nota" aqui criaria a segunda tradução do mesmo tipo.
            "movimento": estoque_motor.ROTULOS.get(m["tipo"], m["tipo"]),
            "local": m["local"],
            "quantidade": qtd,
            "custo_unitario": dec(m["custo_unitario"]),
            "valor": dec(m["custo_total"]),
            "saldo_apos": novo_saldo,
            "custo_medio_apos": novo_medio,
            "documento": m["documento"],
            "provisorio": "sim" if m["custo_provisorio"] else None,
            "conta": conta,
        })
        anterior_saldo, anterior_medio = novo_saldo, novo_medio

    linhas.append({
        "data": fim,
        "movimento": "Saldo de fechamento",
        "local": "",
        "quantidade": anterior_saldo,
        "custo_unitario": anterior_medio,
        "valor": anterior_saldo * anterior_medio,
        "saldo_apos": anterior_saldo,
        "custo_medio_apos": anterior_medio,
        "conta": "quantidade × custo médio do fim do período",
    })
    return linhas


def _n(v: Decimal) -> str:
    """Quantidade sem os zeros à direita que não informam nada."""
    return f"{Decimal(str(v)).normalize():f}"


def _r(v: Decimal) -> str:
    return f"{Decimal(str(v)):.6f}".rstrip("0").rstrip(".")
