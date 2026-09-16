"""O motor do estoque — custo médio ponderado móvel.

**Toda escrita no razão passa por `lancar`.** Nenhum router monta INSERT em
`estoque_movimentos` por fora: é aqui que mora a trava de concorrência, o
cálculo do médio e a fotografia do saldo.

Duas coisas que o leitor de amanhã precisa saber:

1. **O médio segue a ordem de LANÇAMENTO, não a data do movimento.** Uma nota
   lançada hoje com data de ontem entra depois no razão — a data serve ao
   relatório, a sequência serve ao custo. Recalcular por data exigiria refazer
   a série inteira a cada correção, e o CMV de ontem mudaria sozinho.
2. **Saída sem saldo é permitida** (a cozinha usa antes de a nota chegar), sai
   pelo melhor custo que o sistema conhece — o último médio do razão e, quando
   nem isso existe, a cascata de `custos.custo_do_insumo` — e fica marcada como
   `custo_provisorio`.
"""

from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException

from services.custos import CASAS_CUSTO, custo_do_insumo, dec

ENTRADAS = {
    "ENTRADA_NF", "ENTRADA_MANUAL", "ENTRADA_PRODUCAO", "ENTRADA_DEVOLUCAO",
    "TRANSFERENCIA_ENTRADA", "AJUSTE_INVENTARIO_ENTRADA", "ESTORNO_ENTRADA",
}
SAIDAS = {
    "SAIDA_VENDA", "SAIDA_PRODUCAO", "SAIDA_PERDA", "SAIDA_CONSUMO_INTERNO",
    "TRANSFERENCIA_SAIDA", "AJUSTE_INVENTARIO_SAIDA", "ESTORNO_SAIDA",
}
# 🔑 **`AJUSTE_CUSTO` não é entrada nem saída** — é o único movimento que mexe
# no VALOR sem mexer na quantidade. Fica fora dos dois conjuntos de propósito:
# somá-lo às entradas o faria virar "compra" no CMV, e às saídas, "consumo".
# Ele é a terceira coisa, e o painel o mostra em linha própria.
AJUSTE_CUSTO = "AJUSTE_CUSTO"
TIPOS = ENTRADAS | SAIDAS | {AJUSTE_CUSTO}

ROTULOS = {
    "ENTRADA_NF": "Entrada por nota",
    "ENTRADA_MANUAL": "Entrada manual",
    "ENTRADA_PRODUCAO": "Produção",
    "ENTRADA_DEVOLUCAO": "Devolução",
    "TRANSFERENCIA_ENTRADA": "Transferência (entrada)",
    "AJUSTE_INVENTARIO_ENTRADA": "Ajuste de inventário (sobra)",
    "ESTORNO_ENTRADA": "Estorno (entrada)",
    "SAIDA_VENDA": "Venda",
    "SAIDA_PRODUCAO": "Consumo em produção",
    "SAIDA_PERDA": "Perda",
    "SAIDA_CONSUMO_INTERNO": "Consumo interno",
    "TRANSFERENCIA_SAIDA": "Transferência (saída)",
    "AJUSTE_INVENTARIO_SAIDA": "Ajuste de inventário (falta)",
    "ESTORNO_SAIDA": "Estorno (saída)",
    "AJUSTE_CUSTO": "Ajuste de custo",
}


def _parametros(cur, id_unidade: int) -> dict:
    cur.execute(
        """SELECT permitir_saldo_negativo, exigir_motivo_perda, exigir_local_movimento,
                  bloquear_retroativo, custo_por_local
             FROM parametros WHERE id_unidade = %s""",
        (id_unidade,),
    )
    p = cur.fetchone()
    return dict(p) if p else {
        "permitir_saldo_negativo": True,
        "exigir_motivo_perda": True,
        "exigir_local_movimento": True,
        "bloquear_retroativo": True,
        # ⚠️ O padrão do dicionário tem de ser o MESMO da coluna (migração 064),
        # senão uma loja sem linha de parâmetros se comporta diferente de uma
        # com a linha recém-criada — e a diferença apareceria como custo.
        "custo_por_local": False,
    }


def local_padrao(cur, id_unidade: int) -> int:
    cur.execute(
        """SELECT id FROM locais_estoque
            WHERE id_unidade = %s AND ativo ORDER BY principal DESC, id LIMIT 1""",
        (id_unidade,),
    )
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=400, detail="Nenhum local de estoque cadastrado.")
    return linha["id"]


def _travar_periodo_fechado(cur, id_unidade: int, quando, pode_retroativo: bool) -> None:
    """Mês fechado não recebe lançamento novo — é o que dá sentido ao fechamento.

    Quem tem `estoque.retroativo` passa; a auditoria registra quem foi.
    """
    if pode_retroativo:
        return
    data = quando.date() if hasattr(quando, "date") else quando
    cur.execute(
        """SELECT inicio, fim, ciclo FROM cmv_fechamentos
            WHERE id_unidade = %s AND status = 'FECHADO' AND %s BETWEEN inicio AND fim""",
        (id_unidade, data),
    )
    fechado = cur.fetchone()
    if fechado:
        # ⚠️ A frase nomeia o PERÍODO, não o mês. Com fechamento semanal, dizer
        # "o período de 08/2026 está fechado" mandaria quem lança procurar um
        # mês inteiro na lista — e a semana que está travando o lançamento é uma
        # linha de sete dias que ele não encontraria.
        from services import periodos

        nome = periodos.rotulo(fechado["inicio"], fechado["fim"], fechado["ciclo"] or "MENSAL")
        raise HTTPException(
            status_code=400,
            detail=(
                f"O período de {nome} está fechado. "
                "Reabra o período ou lance na data de hoje."
            ),
        )


def _travar_saldo(cur, id_unidade: int, id_local: int, id_produto: int) -> dict:
    """Cria a linha se não existir e a trava até o fim da transação.

    Sem este FOR UPDATE, dois lançamentos simultâneos do mesmo produto leem o
    mesmo saldo e o segundo sobrescreve o médio do primeiro.
    """
    cur.execute(
        """INSERT INTO estoque_saldos (id_unidade, id_local, id_produto)
           VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
        (id_unidade, id_local, id_produto),
    )
    cur.execute(
        """SELECT quantidade, custo_medio FROM estoque_saldos
            WHERE id_unidade = %s AND id_local = %s AND id_produto = %s
            FOR UPDATE""",
        (id_unidade, id_local, id_produto),
    )
    return dict(cur.fetchone())


def _travar_custo_da_loja(cur, id_unidade: int, id_produto: int) -> tuple[Decimal, Decimal]:
    """Trava TODAS as prateleiras do produto e devolve (quantidade, médio) da loja.

    🔑 **É a base do custo médio quando ele é geral** (migração 064). O médio
    móvel precisa de um saldo e um valor anteriores; com o custo da loja, esses
    dois são a soma das prateleiras, não os da prateleira em que a mercadoria
    está entrando.

    ⚠️ **A trava vem ANTES e pega tudo, em ordem de `id_local`.** Travar a linha
    do movimento primeiro e as outras depois deixaria duas requisições do mesmo
    produto se cruzarem em ordens diferentes — que é a receita do impasse. Com a
    ordem fixa, a segunda espera a primeira e nenhuma trava a outra.

    ⚠️ **Só prateleira POSITIVA e com custo entra na base**, que é o mesmo
    recorte da cascata (`custos.custo_do_insumo`) e o que a tela adotou: saldo
    negativo é dívida, não mercadoria, e o custo dele é provisório — deixá-lo
    pesar no médio seria uma estimativa corrigindo o que a casa pagou de fato.

    ⚠️ **Devolve o ponderado mesmo que as prateleiras discordem.** Enquanto os
    produtos antigos não forem unificados pelo botão, elas discordam — e é
    melhor que a primeira entrada já as reconcilie do que esperar.
    """
    cur.execute(
        """SELECT quantidade, custo_medio FROM estoque_saldos
            WHERE id_unidade = %s AND id_produto = %s
            ORDER BY id_local
            FOR UPDATE""",
        (id_unidade, id_produto),
    )
    linhas = cur.fetchall()
    quantidade = valor = Decimal(0)
    for l in linhas:
        q, c = dec(l["quantidade"]), dec(l["custo_medio"])
        if q > 0 and c > 0:
            quantidade += q
            valor += q * c
    if quantidade > 0:
        return quantidade, (valor / quantidade).quantize(CASAS_CUSTO)
    # Nenhuma prateleira valorada: fica o maior custo conhecido, que é melhor
    # que zero e é o que `_ultimo_medio_conhecido` também faria.
    conhecidos = [dec(l["custo_medio"]) for l in linhas if dec(l["custo_medio"]) > 0]
    return Decimal(0), (max(conhecidos) if conhecidos else Decimal(0))


def _ultimo_medio_conhecido(cur, id_produto: int, id_unidade: int) -> Decimal:
    """Para saída sem saldo: o médio de outro local, o último do razão — e,
    se o razão nunca soube, a MESMA cascata que todo o resto do sistema usa.

    🔑 **O razão não pode ser o único a não saber o custo.** Os dois primeiros
    degraus abaixo só olhavam para dentro do próprio razão, então um produto que nunca recebeu
    nota saía por ZERO. E é o caso mais comum da casa: catálogo importado do
    Omie, custo de referência trazido junto, PDV vendendo antes de a primeira
    nota chegar. O cupom mostrava R$ 2,76 (o item de venda congela o custo pela
    cascata de `custos.custo_do_insumo`) enquanto o mesmo produto saía do
    estoque a R$ 0,00 — duas respostas para a mesma pergunta, na mesma venda.
    Quem conferisse Saldos e movimentos veria o custo sumir.

    ⚠️ **Zero continua sendo possível, e aí é verdade**: ninguém sabe quanto
    custa. O que não pode é zero por o razão estar olhando só para si mesmo,
    com o número guardado a uma consulta de distância.

    ⚠️ **A saída segue PROVISÓRIA de qualquer forma** — quem chama marca
    `custo_provisorio`. Preço de fornecedor e referência são a melhor estimativa
    disponível, não o que a casa pagou; quando a nota entrar, o médio vira o de
    verdade e o alerta de custo provisório é o que aponta as saídas a rever.
    """
    cur.execute(
        """SELECT custo_medio FROM estoque_saldos
            WHERE id_produto = %s AND id_unidade = %s AND custo_medio > 0
            ORDER BY quantidade DESC LIMIT 1""",
        (id_produto, id_unidade),
    )
    linha = cur.fetchone()
    if linha:
        return dec(linha["custo_medio"])
    cur.execute(
        """SELECT custo_medio_apos FROM estoque_movimentos
            WHERE id_produto = %s AND custo_medio_apos > 0
            ORDER BY id DESC LIMIT 1""",
        (id_produto,),
    )
    linha = cur.fetchone()
    if linha:
        return dec(linha["custo_medio_apos"])
    # Os degraus que faltavam: último preço do fornecedor e custo de referência.
    # A cascata inteira mora em `custos.custo_do_insumo` — repetir as duas
    # consultas aqui criaria a segunda versão da mesma regra.
    valor, _origem = custo_do_insumo(cur, id_produto, id_unidade)
    return valor if valor is not None else Decimal(0)


def lancar(
    cur,
    *,
    id_unidade: int,
    id_produto: int,
    tipo: str,
    quantidade,
    id_local: int | None = None,
    custo_unitario=None,
    data_movimento: datetime | None = None,
    origem_tipo: str | None = None,
    origem_id: int | None = None,
    id_motivo_perda: int | None = None,
    documento: str | None = None,
    observacao: str | None = None,
    id_usuario: int | None = None,
    id_estorno_de: int | None = None,
    lote: str | None = None,
    validade=None,
    pode_retroativo: bool = False,
    _lotes_espelho: list | None = None,
) -> dict:
    """Grava UM movimento e devolve o que ficou. Quantidade sempre positiva."""
    if tipo not in TIPOS:
        raise HTTPException(status_code=400, detail=f"Tipo de movimento inválido: {tipo}")
    # ⚠️ O ajuste de custo NÃO passa por aqui: ele tem quantidade zero, e todo
    # este corpo pressupõe mercadoria se movendo (saldo, FEFO, lote, custo
    # médio ponderado). Quem o lança é `services.ajustes.lancar_custo`.
    if tipo == AJUSTE_CUSTO:
        raise HTTPException(
            status_code=400,
            detail="Ajuste de custo se lança em Estoque ▸ Ajustes ▸ Custo.",
        )

    qtd = dec(quantidade)
    if qtd <= 0:
        raise HTTPException(status_code=400, detail="Quantidade precisa ser maior que zero.")

    cur.execute(
        "SELECT nome, controla_estoque, controla_lote, ativo FROM produtos WHERE id = %s",
        (id_produto,),
    )
    produto = cur.fetchone()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    if not produto["controla_estoque"]:
        raise HTTPException(
            status_code=400,
            detail=f"{produto['nome']} não controla estoque — ligue isso no cadastro do produto.",
        )

    # 🔑 **Entrada NOVA não ressuscita cadastro arquivado.** A coluna `ativo`
    # era lida nesta consulta e nunca perguntada: a cascata de conciliação
    # recusa CASAR nota nova com produto arquivado ("amarrar nota nova nele o
    # ressuscitaria na compra sem ninguém ter decidido"), mas nada recusava
    # LANÇAR quando o item já estava apontado de antes da fusão — e aí o
    # estoque entrava no cadastro morto, fora da ficha e fora do custo do
    # sobrevivente. A frase diz para onde ir, porque quem lança não tem como
    # saber quem absorveu quem.
    # ⚠️ **Só a entrada por NOTA, e a mira estreita é deliberada.** `ENTRADAS`
    # tem seis tipos, e quase todos descrevem mercadoria que se MOVEU de
    # verdade: receber uma transferência de produto arquivado, contar a mais
    # num inventário, aceitar uma devolução — barrar isso deixaria a remessa
    # presa e a contagem sem como fechar. Saída e estorno idem: é assim que se
    # esvazia o saldo de um absorvido e que se desfaz um lançamento errado.
    # O que não pode é a COMPRA nova entrar num cadastro que ninguém mais usa.
    if tipo == "ENTRADA_NF" and not produto["ativo"]:
        cur.execute("SELECT codigo, nome FROM produtos WHERE id = ("
                    "SELECT fundido_em FROM produtos WHERE id = %s)", (id_produto,))
        destino = cur.fetchone()
        para_onde = (f" Este cadastro foi fundido em {destino['codigo']} — "
                     f"{destino['nome']}; a entrada é lá." if destino else
                     " Reative o cadastro ou aponte o item para o que está em uso.")
        raise HTTPException(
            status_code=400,
            detail=f"{produto['nome']} está arquivado e não recebe entrada.{para_onde}",
        )

    par = _parametros(cur, id_unidade)
    if id_local is None:
        id_local = local_padrao(cur, id_unidade)
    if data_movimento is not None:
        # ⚠️ **Movimento no futuro não aconteceu.** A trava do período fechado
        # olha para trás; para a frente não olhava ninguém, e uma data errada
        # entrava calada. Aconteceu de verdade: uma venda datada com o dia de
        # UTC (às 22h35 de Brasília, já é o dia seguinte) caiu fora do mês, e o
        # relatório de movimentação deixou de fechar com o saldo — a busca foi
        # atrás de um erro de cálculo que não existia. O razão é append-only:
        # data errada aqui não se conserta, só se estorna.
        cur.execute("SELECT (%s::timestamptz)::date > current_date AS futuro", (data_movimento,))
        if cur.fetchone()["futuro"]:
            raise HTTPException(
                status_code=400,
                detail="Data no futuro: um movimento de estoque só existe depois de acontecer.",
            )
        if par.get("bloquear_retroativo", True):
            _travar_periodo_fechado(cur, id_unidade, data_movimento, pode_retroativo)
    if tipo == "SAIDA_PERDA" and par["exigir_motivo_perda"] and not id_motivo_perda:
        raise HTTPException(status_code=400, detail="Informe o motivo da perda.")

    saldo = _travar_saldo(cur, id_unidade, id_local, id_produto)
    saldo_atual, medio_atual = dec(saldo["quantidade"]), dec(saldo["custo_medio"])
    provisorio = False

    # 🔑 **Quem entra na conta do médio: a loja ou a prateleira** (migração 064).
    # No modo geral — o padrão — o médio móvel é calculado sobre o saldo somado
    # de todas as prateleiras e gravado em todas elas: o mesmo açúcar não custa
    # uma coisa na despensa e outra no bar. No modo por local, nada muda.
    #
    # ⚠️ **A QUANTIDADE continua sendo sempre da prateleira**, nos dois modos:
    # o razão registra de onde a mercadoria saiu, e `saldo_apos` é o que aquele
    # local passou a ter. Só o custo é que é da loja.
    geral = not par.get("custo_por_local", False)
    if geral:
        base_qtd, base_medio = _travar_custo_da_loja(cur, id_unidade, id_produto)
    else:
        base_qtd, base_medio = saldo_atual, medio_atual

    if tipo in ENTRADAS:
        unitario = dec(custo_unitario) if custo_unitario is not None else base_medio
        saldo_novo = saldo_atual + qtd
        base_nova = base_qtd + qtd
        if base_nova > 0:
            valor = (base_qtd * base_medio) + (qtd * unitario)
            medio_novo = (valor / base_nova).quantize(CASAS_CUSTO)
        else:
            medio_novo = unitario
        sinal = qtd
    else:
        if base_qtd <= 0 and base_medio == 0:
            unitario = _ultimo_medio_conhecido(cur, id_produto, id_unidade)
            provisorio = True
        else:
            unitario = base_medio
        # ⚠️ A conferência de saldo insuficiente é da PRATELEIRA, sempre: não se
        # tira da despensa o que está no bar. É o custo que é geral, não o saldo.
        if qtd > saldo_atual:
            if not par["permitir_saldo_negativo"]:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Saldo insuficiente de {produto['nome']}: "
                        f"há {saldo_atual}, saída de {qtd}."
                    ),
                )
            provisorio = True
        saldo_novo = saldo_atual - qtd
        # A saída não mexe no médio — só o esvazia quando zera de fato. No modo
        # geral quem decide "zerou" é a LOJA: esvaziar o bar não pode apagar o
        # custo do que continua na despensa.
        base_nova = base_qtd - qtd
        if geral:
            medio_novo = base_medio if base_nova > 0 else (base_medio or unitario)
        else:
            medio_novo = medio_atual if saldo_novo > 0 else (medio_atual or unitario)
        sinal = -qtd

    # O razão guarda dinheiro em centavos — é o que se soma numa nota. Mas quem
    # ENCADEIA custo (a produção soma consumos para achar o custo do prato)
    # precisa do valor sem arredondar: meio centavo por movimento vira erro de
    # verdade quando multiplicado por mil pratos.
    custo_exato = qtd * unitario
    custo_total = custo_exato.quantize(Decimal("0.01"))

    cur.execute(
        """INSERT INTO estoque_movimentos
               (id_unidade, id_local, id_produto, data_movimento, tipo, quantidade,
                custo_unitario, custo_total, saldo_apos, custo_medio_apos, custo_provisorio,
                origem_tipo, origem_id, id_estorno_de, id_motivo_perda, documento,
                observacao, id_usuario)
           VALUES (%s, %s, %s, coalesce(%s, now()), %s, %s, %s, %s, %s, %s, %s,
                   %s, %s, %s, %s, %s, %s, %s)
           RETURNING id, data_movimento""",
        (id_unidade, id_local, id_produto, data_movimento, tipo, sinal, unitario, custo_total,
         saldo_novo, medio_novo, provisorio, origem_tipo, origem_id, id_estorno_de,
         id_motivo_perda, documento, observacao, id_usuario),
    )
    movimento = cur.fetchone()

    cur.execute(
        """UPDATE estoque_saldos SET quantidade = %s, custo_medio = %s, atualizado_em = now()
            WHERE id_unidade = %s AND id_local = %s AND id_produto = %s""",
        (saldo_novo, medio_novo, id_unidade, id_local, id_produto),
    )
    if geral:
        # 🔑 **A entrada REDISTRIBUI valor entre as prateleiras, e os dois lados
        # precisam aparecer no razão.** Duas versões disto estiveram erradas
        # antes desta, e a bateria mediu as duas:
        #
        # 1. propagar por `UPDATE` calado — `estoque_saldos` é a fotografia de
        #    HOJE, mas quem responde pelo passado (estoque inicial e final do
        #    CMV, movimentação por produto, valor numa data) é o
        #    `saldo_apos`/`custo_medio_apos` do último movimento da prateleira.
        #    Os dois passaram a discordar em R$ 273,20 e a soma dos grupos
        #    deixou de fechar com o CMV do período.
        # 2. lançar só nas OUTRAS prateleiras — a que recebeu a mercadoria também
        #    é reavaliada: 10 unidades entrando a R$ 30 numa loja cujo médio vira
        #    R$ 24,76 valem R$ 247,62, não R$ 300. Faltava exatamente o outro
        #    lado, e a identidade `inicial + entradas − saídas = final` abria no
        #    mesmo valor que a prateleira vizinha tinha ganhado.
        #
        # ⚠️ **A soma destes ajustes é ZERO, e é o que prova que estão certos**:
        # a entrada não criou nem destruiu valor, só o espalhou pela loja. Cada
        # linha diz quanto AQUELA prateleira passou a valer.
        #
        # ⚠️ **Saída não gera ajuste nenhum**: ela não mexe no médio, então
        # `medio_novo` é o de antes e nenhuma diferença aparece. As linhas só
        # surgem quando uma entrada muda o médio — uma por prateleira com saldo,
        # por nota.
        #
        # ⚠️ **Quantidade zero não gera linha**: não há valor a reavaliar (zero
        # vezes qualquer coisa é zero) e a fotografia continua batendo. Ela só
        # recebe o `UPDATE` — e é isso que faz o local que ainda não viu o
        # produto já nascer sabendo o custo dele, que é o caso que o dono
        # relatou.
        cur.execute(
            """SELECT id_local, quantidade, custo_medio FROM estoque_saldos
                WHERE id_unidade = %s AND id_produto = %s
                ORDER BY id_local""",
            (id_unidade, id_produto),
        )
        for prateleira in cur.fetchall():
            dela = prateleira["id_local"] == id_local
            # A prateleira do movimento já foi atualizada logo acima; para as
            # outras, o valor registrado é o que elas valiam antes.
            q = saldo_novo if dela else dec(prateleira["quantidade"])
            registrado = ((saldo_atual * medio_atual) + (sinal * unitario) if dela
                          else q * dec(prateleira["custo_medio"]))
            diferenca = ((q * medio_novo) - registrado).quantize(Decimal("0.01"))
            if q != 0 and diferenca != 0:
                cur.execute(
                    """INSERT INTO estoque_movimentos
                           (id_unidade, id_local, id_produto, data_movimento, tipo,
                            quantidade, custo_unitario, custo_total, saldo_apos,
                            custo_medio_apos, origem_tipo, origem_id, observacao,
                            id_usuario)
                       VALUES (%s, %s, %s, coalesce(%s, now()), %s, 0, %s, %s, %s, %s,
                               'CUSTO_GERAL', %s, %s, %s)""",
                    (id_unidade, prateleira["id_local"], id_produto, data_movimento,
                     AJUSTE_CUSTO, medio_novo, diferenca, q, medio_novo,
                     movimento["id"],
                     "Reavaliação pelo custo único da loja", id_usuario),
                )
            if not dela:
                cur.execute(
                    """UPDATE estoque_saldos SET custo_medio = %s, atualizado_em = now()
                        WHERE id_unidade = %s AND id_local = %s AND id_produto = %s""",
                    (medio_novo, id_unidade, prateleira["id_local"], id_produto),
                )

    lotes_movidos = []
    if produto["controla_lote"]:
        if _lotes_espelho is not None:
            # Estorno: desfaz exatamente os lotes do movimento original. Deixar o
            # FEFO escolher aqui devolveria a mercadoria ao lote errado.
            lotes_movidos = _espelhar_lotes(cur, movimento["id"], _lotes_espelho,
                                            entrada=tipo in ENTRADAS)
        elif lote or validade:
            _mover_lote(cur, movimento["id"], id_unidade, id_local, id_produto,
                        lote, validade, qtd if tipo in ENTRADAS else -qtd)
            lotes_movidos = _lotes_do_movimento(cur, movimento["id"])
        elif tipo not in ENTRADAS:
            # Saída sem lote informado: o sistema escolhe — o que vence antes
            # sai antes.
            lotes_movidos = _consumir_fefo(cur, movimento["id"], id_unidade, id_local,
                                           id_produto, qtd)

    return {
        "id": movimento["id"],
        "quantidade": sinal,
        "custo_unitario": unitario,
        "custo_total": custo_total,
        "custo_exato": custo_exato,
        "saldo_apos": saldo_novo,
        "custo_medio_apos": medio_novo,
        "custo_provisorio": provisorio,
        "lotes": lotes_movidos,
    }


def _espelhar_lotes(cur, id_movimento: int, lotes: list, entrada: bool) -> list[dict]:
    """Repete os lotes de um movimento, com o sinal trocado. É o estorno."""
    movidos = []
    for l in lotes:
        qtd = dec(l["quantidade"]) * (1 if entrada else -1)
        cur.execute(
            "UPDATE estoque_lotes SET quantidade = quantidade + %s WHERE id = %s RETURNING lote, validade",
            (qtd, l["id_lote"]),
        )
        linha = cur.fetchone()
        cur.execute(
            "INSERT INTO movimento_lotes (id_movimento, id_lote, quantidade) VALUES (%s, %s, %s)",
            (id_movimento, l["id_lote"], qtd),
        )
        movidos.append({"id_lote": l["id_lote"], "lote": linha["lote"],
                        "validade": linha["validade"], "quantidade": abs(qtd)})
    return movidos


def _lotes_do_movimento(cur, id_movimento: int) -> list[dict]:
    cur.execute(
        """SELECT l.lote, l.validade, abs(ml.quantidade) AS quantidade, l.id AS id_lote
             FROM movimento_lotes ml JOIN estoque_lotes l ON l.id = ml.id_lote
            WHERE ml.id_movimento = %s
            ORDER BY l.validade NULLS LAST, l.id""",
        (id_movimento,),
    )
    return [dict(r) for r in cur.fetchall()]


def _consumir_fefo(cur, id_movimento: int, id_unidade: int, id_local: int, id_produto: int,
                   qtd) -> list[dict]:
    """Baixa a saída dos lotes, o que vence primeiro na frente (FEFO).

    Três decisões que valem mais que o algoritmo:

    * **Isto nunca barra a saída.** O lote é camada de CONTROLE; quem manda no
      saldo é o razão. Entrada antiga sem lote informado (o campo é opcional) faz
      a soma dos lotes ser menor que o saldo — e a cozinha não pode ficar
      impedida de produzir por causa de um papel que ninguém preencheu. O que
      sobra sai como "sem lote" e pronto.
    * **Sem validade vai para o fim da fila.** Lote sem data não se sabe se vence
      antes ou depois; consumir o que tem data conhecida primeiro é o que faz o
      alerta de vencimento parar de mentir.
    * **Uma saída pode quebrar em vários lotes.** Cada pedaço vira uma linha em
      `movimento_lotes`, então dá para responder "essas 8 unidades saíram 5 do
      lote que vence dia 20 e 3 do que vence dia 27".
    """
    restante = dec(qtd)
    cur.execute(
        """SELECT id, lote, validade, quantidade FROM estoque_lotes
            WHERE id_unidade = %s AND id_local = %s AND id_produto = %s AND quantidade > 0
            ORDER BY validade NULLS LAST, id
            FOR UPDATE""",
        (id_unidade, id_local, id_produto),
    )
    consumidos = []
    for linha in cur.fetchall():
        if restante <= 0:
            break
        leva = min(restante, dec(linha["quantidade"]))
        cur.execute(
            "UPDATE estoque_lotes SET quantidade = quantidade - %s WHERE id = %s",
            (leva, linha["id"]),
        )
        cur.execute(
            "INSERT INTO movimento_lotes (id_movimento, id_lote, quantidade) VALUES (%s, %s, %s)",
            (id_movimento, linha["id"], -leva),
        )
        consumidos.append({"id_lote": linha["id"], "lote": linha["lote"],
                           "validade": linha["validade"], "quantidade": leva})
        restante -= leva
    return consumidos


def _mover_lote(cur, id_movimento, id_unidade, id_local, id_produto, lote, validade, qtd) -> None:
    cur.execute(
        """INSERT INTO estoque_lotes (id_unidade, id_local, id_produto, lote, validade, quantidade)
           VALUES (%s, %s, %s, %s, %s, 0)
           ON CONFLICT (id_unidade, id_local, id_produto,
                        COALESCE(lote, ''), COALESCE(validade, '9999-12-31'))
           DO NOTHING""",
        (id_unidade, id_local, id_produto, lote, validade),
    )
    cur.execute(
        # O `::date` no parâmetro não é enfeite: sem ele, `validade` nula chega
        # ao Postgres sem tipo, o COALESCE vira texto e a comparação estoura com
        # "operador não existe: date = text". Lote com validade passava; lote
        # SEM validade dava erro 500 — e nenhum teste passava por esse caminho.
        """UPDATE estoque_lotes SET quantidade = quantidade + %s
            WHERE id_unidade = %s AND id_local = %s AND id_produto = %s
              AND COALESCE(lote, '') = COALESCE(%s, '')
              AND COALESCE(validade, '9999-12-31') = COALESCE(%s::date, '9999-12-31')
          RETURNING id""",
        (qtd, id_unidade, id_local, id_produto, lote, validade),
    )
    linha = cur.fetchone()
    if linha:
        cur.execute(
            """INSERT INTO movimento_lotes (id_movimento, id_lote, quantidade)
               VALUES (%s, %s, %s)""",
            (id_movimento, linha["id"], qtd),
        )


def reprocessar(cur, *, id_unidade: int, id_produto: int, aplicar: bool = False,
                pode_retroativo: bool = False, id_usuario: int | None = None) -> dict:
    """Relê o razão deste produto em ordem de data e refaz o que é DERIVADO.

    🔑 **Pedido do dono (15/09/2026):** *"em saldos e movimentos, criar uma opção
    de reprocessar, caso tenha alterações, disponibilizar a opção de reprocessar
    o estoque, filtrando por produto"*.

    🔑 **O caso que ele existe para consertar é o LANÇAMENTO RETROATIVO.** A nota
    do dia 9 é lançada hoje, depois de a venda do dia 12 já ter saído: a venda
    saiu com custo provisório (não havia saldo) e o saldo ficou negativo, e nada
    disso se conserta sozinho — o custo médio é calculado no momento do
    lançamento, com o que a prateleira sabia naquele instante. Reprocessar põe a
    corrente na ordem da DATA: entra a nota a R$ 64,00, depois sai a venda pelo
    mesmo custo.

    ⚠️ **Isto NÃO fura o append-only, e a fronteira é a que importa.** O que se
    reescreve é o que o razão DERIVA: `saldo_apos`, `custo_medio_apos`, o
    `custo_provisorio` e o custo das SAÍDAS — que nunca foi um fato, é a média
    do momento. O que não se toca: tipo, quantidade, data, origem, e o **custo
    das ENTRADAS**, que é o que a casa pagou. Nenhum movimento é criado nem
    apagado.

    ⚠️ **E não é porta dos fundos para trocar unidade.** Quem já tem razão não
    troca de unidade (`services/troca_de_unidade.py`): as quantidades históricas
    estão gravadas na unidade antiga. Reprocessar recalcula sobre os números que
    estão lá, não os converte.

    ⚠️ **Recusa quando a loja usa CUSTO GERAL e o produto anda em mais de uma
    prateleira.** Nesse modo a entrada redistribui valor entre as prateleiras e
    grava uma linha de reavaliação por prateleira — refazer isso numa ordem
    diferente exigiria CRIAR e APAGAR linhas do razão, que é exatamente o que
    esta função promete não fazer. Melhor recusar com a frase do que devolver
    dinheiro aproximado.

    ⚠️ **Período fechado trava**, pela mesma razão do lançamento: ele foi
    congelado e já foi ao contador. Quem tem `estoque.retroativo` passa, e a
    auditoria registra.

    Com `aplicar=False` devolve a PRÉVIA — o que mudaria, sem gravar nada. É o
    padrão da casa para operação que reescreve número que alguém já leu.
    """
    cur.execute(
        "SELECT nome, um_estoque, controla_estoque FROM produtos WHERE id = %s",
        (id_produto,),
    )
    produto = cur.fetchone()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    par = _parametros(cur, id_unidade)
    geral = not par.get("custo_por_local", False)

    # ⚠️ **A trava vem antes de ler os movimentos**, e é a mesma do `lancar`: sem
    # ela, uma entrada lançada no meio do reprocessamento entraria com o saldo
    # velho e o resultado sairia errado dos dois lados.
    cur.execute(
        """SELECT id_local, quantidade, custo_medio FROM estoque_saldos
            WHERE id_unidade = %s AND id_produto = %s
            ORDER BY id_local FOR UPDATE""",
        (id_unidade, id_produto),
    )
    saldos_antes = {r["id_local"]: r for r in cur.fetchall()}

    cur.execute(
        """SELECT id, id_local, data_movimento, tipo, quantidade, custo_unitario,
                  custo_total, saldo_apos, custo_medio_apos, custo_provisorio, origem_tipo,
                  id_estorno_de
             FROM estoque_movimentos
            WHERE id_unidade = %s AND id_produto = %s
            ORDER BY data_movimento, id""",
        (id_unidade, id_produto),
    )
    movimentos = cur.fetchall()
    if not movimentos:
        return {
            "produto": produto["nome"], "movimentos": 0, "mudam": 0, "linhas": [],
            "saldos": [], "aplicado": False,
            "message": f"{produto['nome']} não tem movimento nesta loja — nada a reprocessar.",
        }

    prateleiras = {m["id_local"] for m in movimentos}
    if geral and len(prateleiras) > 1:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{produto['nome']} tem movimento em {len(prateleiras)} prateleiras e esta "
                "loja usa custo único por loja. Nesse modo cada entrada redistribui valor "
                "entre as prateleiras, e refazer isso exigiria criar e apagar linhas do "
                "razão — que é o que o reprocessamento não faz. Ajuste o custo à mão em "
                "Estoque ▸ Ajustes ▸ Custo."
            ),
        )

    # A corrente de cada prateleira: saldo, custo médio e o VALOR já registrado
    # nela (o que a soma dos movimentos diz que ela vale). O valor registrado é o
    # que permite recalcular a linha de reavaliação do custo geral sem inventar
    # número: a diferença dela é exatamente `saldo × médio − valor registrado`.
    corrente: dict[int, list] = {}
    mudancas: list[dict] = []
    # 🔑 **O estorno de uma SAÍDA custa o que a saída custou** — e por isso ele
    # acompanha o recálculo dela. Reprocessar reescreve o custo da saída (que
    # nunca foi fato, é a média do momento) e deixava o espelho dela como
    # estava: o par que devolvia exatamente o que tirou passava a devolver
    # outro valor, e a diferença ficava pendurada no estoque para sempre.
    # Medido: uma saída de 2,712 KG reprecificada de R$ 63 para R$ 315 com o
    # estorno parado em R$ 63 abria um buraco de R$ 683,42 num produto só.
    # ⚠️ Vale só para o estorno de saída. O estorno de uma ENTRADA é uma saída,
    # e saída custa a média do momento — é o caminho de baixo, não este.
    custo_da_saida: dict[int, Decimal] = {}

    for m in movimentos:
        local = m["id_local"]
        saldo, medio, registrado = corrente.get(local, [Decimal(0), Decimal(0), Decimal(0)])
        qtd = dec(m["quantidade"])
        unitario = dec(m["custo_unitario"] or 0)
        total = dec(m["custo_total"] or 0)
        provisorio = bool(m["custo_provisorio"])
        espelha = custo_da_saida.get(m["id_estorno_de"])
        if espelha is not None:
            unitario = espelha

        if m["tipo"] == AJUSTE_CUSTO and m["origem_tipo"] == "CUSTO_GERAL":
            # A reavaliação que a entrada espalhou. Ela não move mercadoria: o
            # que ela diz é quanto a prateleira passou a valer.
            total = ((saldo * medio) - registrado).quantize(Decimal("0.01"))
            unitario = medio
            registrado += total
        elif m["tipo"] == AJUSTE_CUSTO:
            # Ajuste de custo à mão: o médio passa a ser o que alguém declarou, e
            # a diferença de valor é o que o movimento registra.
            # ⚠️ O custo declarado é FATO — foi uma decisão de gente. O que se
            # recalcula é a diferença, que depende do saldo daquele instante.
            total = (saldo * (unitario - medio)).quantize(Decimal("0.01"))
            medio = unitario
            registrado += total
        elif qtd > 0:
            # ⚠️ Entrada: o custo unitário é o que a casa pagou e não se toca.
            novo_saldo = saldo + qtd
            if novo_saldo > 0:
                medio = (((saldo * medio) + (qtd * unitario)) / novo_saldo).quantize(CASAS_CUSTO)
            else:
                medio = unitario
            saldo = novo_saldo
            total = (qtd * unitario).quantize(Decimal("0.01"))
            registrado += total
            provisorio = False
        else:
            # Saída: o custo É a média do momento — e é isto que o reprocessamento
            # acerta. ⚠️ Sem média conhecida na corrente, mantém o que o
            # movimento já tinha: reprocessar não inventa história que o razão
            # não tem.
            if saldo <= 0 and medio == 0:
                provisorio = True
            else:
                unitario = medio
                provisorio = saldo + qtd < 0
            saldo = saldo + qtd
            if saldo <= 0:
                medio = medio or unitario
            total = (abs(qtd) * unitario).quantize(Decimal("0.01"))
            registrado -= total
            custo_da_saida[m["id"]] = unitario

        corrente[local] = [saldo, medio, registrado]

        antes = (dec(m["saldo_apos"]), dec(m["custo_medio_apos"] or 0),
                 dec(m["custo_unitario"] or 0), dec(m["custo_total"] or 0),
                 bool(m["custo_provisorio"]))
        agora = (saldo, medio, unitario, total, provisorio)
        if antes != agora:
            mudancas.append({
                "id": m["id"],
                "data": m["data_movimento"],
                "tipo": m["tipo"],
                "id_local": local,
                "saldo_de": antes[0], "saldo_para": saldo,
                "medio_de": antes[1], "medio_para": medio,
                "custo_de": antes[2], "custo_para": unitario,
                "total_de": antes[3], "total_para": total,
                "provisorio_de": antes[4], "provisorio_para": provisorio,
            })

    # ⚠️ **O período fechado é conferido sobre o que MUDA**, não sobre tudo: um
    # produto com anos de histórico tem movimento em período fechado quase
    # sempre, e travar por isso deixaria o recurso inútil justamente para quem
    # mais precisa dele.
    if mudancas and not pode_retroativo:
        datas = [c["data"] for c in mudancas]
        cur.execute(
            """SELECT inicio, fim, ciclo FROM cmv_fechamentos
                WHERE id_unidade = %s AND status = 'FECHADO'
                  AND (%s::date BETWEEN inicio AND fim OR %s::date BETWEEN inicio AND fim
                       OR (inicio BETWEEN %s::date AND %s::date))
                ORDER BY inicio LIMIT 1""",
            (id_unidade, min(datas), max(datas), min(datas), max(datas)),
        )
        fechado = cur.fetchone()
        if fechado:
            from services import periodos

            nome = periodos.rotulo(fechado["inicio"], fechado["fim"],
                                   fechado["ciclo"] or "MENSAL")
            raise HTTPException(
                status_code=400,
                detail=(
                    f"O reprocessamento mudaria movimento dentro do período de {nome}, "
                    "que está fechado. Reabra o período — ou peça a quem tem permissão "
                    "de lançamento retroativo."
                ),
            )

    resumo_saldos = []
    for local, (saldo, medio, _v) in sorted(corrente.items()):
        antes = saldos_antes.get(local)
        resumo_saldos.append({
            "id_local": local,
            "quantidade_de": dec(antes["quantidade"]) if antes else None,
            "quantidade_para": saldo,
            "custo_medio_de": dec(antes["custo_medio"]) if antes else None,
            "custo_medio_para": medio,
        })

    if aplicar and mudancas:
        for c in mudancas:
            cur.execute(
                """UPDATE estoque_movimentos
                      SET saldo_apos = %s, custo_medio_apos = %s, custo_unitario = %s,
                          custo_total = %s, custo_provisorio = %s
                    WHERE id = %s""",
                (c["saldo_para"], c["medio_para"], c["custo_para"], c["total_para"],
                 c["provisorio_para"], c["id"]),
            )
        for s in resumo_saldos:
            # ⚠️ `INSERT … ON CONFLICT`: a prateleira pode ter perdido a linha de
            # saldo (o produto foi contado e zerado), e o razão continua sabendo
            # dela. Sem isto, o reprocessamento deixaria o razão e a fotografia
            # discordando — que é o defeito que ele existe para fechar.
            cur.execute(
                """INSERT INTO estoque_saldos
                       (id_unidade, id_local, id_produto, quantidade, custo_medio, atualizado_em)
                   VALUES (%s, %s, %s, %s, %s, now())
                   ON CONFLICT (id_unidade, id_local, id_produto)
                   DO UPDATE SET quantidade = excluded.quantidade,
                                 custo_medio = excluded.custo_medio,
                                 atualizado_em = now()""",
                (id_unidade, s["id_local"], id_produto, s["quantidade_para"],
                 s["custo_medio_para"]),
            )

    return {
        "produto": produto["nome"],
        "um_estoque": produto["um_estoque"],
        "movimentos": len(movimentos),
        "mudam": len(mudancas),
        "linhas": mudancas[:200],
        "saldos": resumo_saldos,
        "aplicado": bool(aplicar and mudancas),
        "message": (
            f"{len(mudancas)} movimento(s) de {produto['nome']} "
            + ("foram reprocessados." if aplicar and mudancas else "mudariam.")
            if mudancas else f"{produto['nome']} já está em ordem — nada mudaria."
        ),
    }


def estornar(cur, id_movimento: int, id_usuario: int, motivo: str | None = None) -> dict:
    """Movimento não se apaga: nasce o contrário dele, apontando para o original."""
    cur.execute(
        """SELECT id, id_unidade, id_local, id_produto, tipo, quantidade, custo_unitario,
                  id_estorno_de
             FROM estoque_movimentos WHERE id = %s""",
        (id_movimento,),
    )
    m = cur.fetchone()
    if not m:
        raise HTTPException(status_code=404, detail="Movimento não encontrado")
    if m["id_estorno_de"]:
        raise HTTPException(status_code=400, detail="Estorno de estorno não se faz.")
    cur.execute(
        "SELECT id FROM estoque_movimentos WHERE id_estorno_de = %s", (id_movimento,)
    )
    if cur.fetchone():
        raise HTTPException(status_code=400, detail="Este movimento já foi estornado.")

    era_entrada = m["tipo"] in ENTRADAS
    # Os lotes do original vêm junto: o estorno tem de devolver (ou retirar) do
    # MESMO lote, não de um que o FEFO escolhesse agora.
    cur.execute(
        "SELECT id_lote, abs(quantidade) AS quantidade FROM movimento_lotes WHERE id_movimento = %s",
        (id_movimento,),
    )
    lotes_originais = [dict(r) for r in cur.fetchall()]

    return lancar(
        cur,
        id_unidade=m["id_unidade"],
        id_local=m["id_local"],
        id_produto=m["id_produto"],
        tipo="ESTORNO_SAIDA" if era_entrada else "ESTORNO_ENTRADA",
        quantidade=abs(dec(m["quantidade"])),
        custo_unitario=m["custo_unitario"],
        origem_tipo="ESTORNO",
        origem_id=id_movimento,
        id_estorno_de=id_movimento,
        observacao=motivo or f"Estorno do movimento #{id_movimento}",
        id_usuario=id_usuario,
        _lotes_espelho=lotes_originais or None,
    )


def _unidade_do_local(cur, id_local: int, padrao: int) -> int:
    cur.execute("SELECT id_unidade FROM locais_estoque WHERE id = %s", (id_local,))
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=404, detail="Local não encontrado")
    return linha["id_unidade"] or padrao


def transferir(cur, *, id_unidade: int, id_produto: int, quantidade, id_local_origem: int,
               id_local_destino: int, id_usuario: int, observacao: str | None = None) -> dict:
    """Sai de um local e entra no outro **pelo mesmo custo** — transferência não
    cria nem destrói valor.

    🔑 **Cada lado é lançado na LOJA do seu próprio local.** A versão anterior
    usava a mesma loja nos dois: escolhendo um local da outra, o razão gravava
    saída e entrada sob a loja de quem estava na tela — o saldo das duas ficava
    errado e **nada denunciava**. Numa casa com duas lojas, mandar produção da
    matriz para a filial é o que se faz toda semana.

    🔑 **O custo ATRAVESSA a fronteira**: a entrada usa o `custo_unitario` que a
    saída apurou, que é o médio da origem. É isso que mantém a identidade
    `inicial + entradas − saídas = final` fechando **nas duas** — a origem perde
    exatamente o valor que o destino ganha. Transferência não cria nem destrói
    dinheiro, e entre lojas ela também não pode criar.
    ⚠️ **E não é receita de ninguém.** O tipo continua sendo
    `TRANSFERENCIA_SAIDA`/`ENTRADA`, que a apuração já sabe que é transformação
    interna e não entra na conta de compras.
    """
    if id_local_origem == id_local_destino:
        raise HTTPException(status_code=400, detail="Origem e destino são o mesmo local.")

    unidade_origem = _unidade_do_local(cur, id_local_origem, id_unidade)
    unidade_destino = _unidade_do_local(cur, id_local_destino, id_unidade)

    saida = lancar(
        cur, id_unidade=unidade_origem, id_local=id_local_origem, id_produto=id_produto,
        tipo="TRANSFERENCIA_SAIDA", quantidade=quantidade, origem_tipo="TRANSFERENCIA",
        observacao=observacao, id_usuario=id_usuario,
    )
    entrada = lancar(
        cur, id_unidade=unidade_destino, id_local=id_local_destino, id_produto=id_produto,
        tipo="TRANSFERENCIA_ENTRADA", quantidade=quantidade,
        custo_unitario=saida["custo_unitario"], origem_tipo="TRANSFERENCIA",
        origem_id=saida["id"], observacao=observacao, id_usuario=id_usuario,
    )
    cur.execute(
        "UPDATE estoque_movimentos SET origem_id = %s WHERE id = %s",
        (entrada["id"], saida["id"]),
    )
    return {"saida": saida, "entrada": entrada,
            "entre_lojas": unidade_origem != unidade_destino,
            "id_unidade_origem": unidade_origem, "id_unidade_destino": unidade_destino}


def _rendimento_em_estoque(rendimento, porcoes, rendimento_um: str | None,
                           um_estoque: str | None, ums: dict) -> Decimal:
    """Quantas unidades de ESTOQUE do produto uma receita inteira rende.

    🔑 **As duas pontas falam unidades diferentes, e isso quebrava a conta**
    (15/09/2026, relatado pelo dono: *"a ficha produz 65 porções, coloquei para
    produzir 2 e no estoque só entraram 2 UN"*). A quantidade está na unidade de
    ESTOQUE do produto (UN de cookie); o rendimento, na unidade da RECEITA
    (8,535 KG de massa). `qtd / rendimento` dividia unidade por quilo e devolvia
    **0,234 receita** -- 23% dos ingredientes para fazer dois cookies, quando o
    certo eram 2/65 = **3,08%**. Sete vezes e meia a mais de manteiga, farinha e
    chocolate saindo do estoque, e o custo do cookie inflado na mesma medida.

    A ponte, em ordem:

    1. **As duas unidades são a mesma** — a receita rende o próprio rendimento,
       que é o caso da ficha que rende em KG de um produto estocado em KG.
    2. **As PORÇÕES** — é exatamente "quantas unidades do produto esta receita
       rende". A ficha do cookie diz 65, e o produto é contado em UN.
    3. **A grandeza** (KG↔G, L↔ML), para quando as duas são de peso ou volume
       com siglas diferentes.

    ⚠️ **Sem nenhuma das três, é RECUSA.** Produzir com um fator inventado é
    o que custou sete vezes o ingrediente certo — e o erro não aparece na hora:
    aparece no inventário do mês seguinte, como falta.
    """
    from services import custos

    r = dec(rendimento) or Decimal(1)
    um_r = (rendimento_um or "").strip().upper()
    um_p = (um_estoque or "").strip().upper()
    if not um_r or not um_p or um_r == um_p:
        return r

    # 2. As porções do MODO que está valendo. ⚠️ Elas chegam resolvidas de cima
    #    (`modo_da_producao`): a ponte não pergunta ao banco qual modo é, porque
    #    quem decide isso é quem produz, na tela, e essa resposta tem de ser a
    #    mesma da prévia, da agenda e do custo.
    if porcoes and dec(porcoes) > 0:
        return dec(porcoes)

    # 3. A grandeza: o rendimento traduzido para a unidade do produto.
    convertida = custos.converter(r, um_r, um_p, ums)
    if convertida is not None and convertida > 0:
        return convertida

    raise HTTPException(
        status_code=400,
        detail=(
            f"A receita rende em {um_r} e este produto é estocado em {um_p}, e o sistema não "
            f"sabe quantos {um_p} a receita faz. Informe as PORÇÕES na ficha — ou no modo de "
            f"rendimento que está sendo usado —, que é o número que liga as duas pontas."
        ),
    )


# As duas maneiras de pedir uma produção. `PORCOES` é a unidade de ESTOQUE do
# produto (130 cookies); `RECEITAS` são voltas inteiras da ficha (2 receitas de
# 65).
#
# 🔑 **Pedido do dono (15/09/2026):** *"na producao podemos ter como informar
# se vamos produzir X porções ou X rendimentos — a ficha tem rendimento de 10 KG
# sendo 60 porções; informar 2 rendimento gera 120 porções"*. As duas contas
# sempre existiram no fundo (uma é o inverso da outra); o que faltava era a
# pessoa poder dizer QUAL das duas ela está digitando. Sem isso, "2" era
# ambíguo — e foi exatamente a ambiguidade que fez dois cookies entrarem onde
# se esperavam cento e trinta.
MEDIDAS_DE_PRODUCAO = ("PORCOES", "RECEITAS")


def _quanto_produzir(quantidade, medida: str | None, rendimento, porcoes,
                     rendimento_um: str | None, um_estoque: str | None,
                     ums: dict) -> tuple[Decimal, Decimal, Decimal]:
    """Traduz o pedido em `(quantidade de estoque, lotes, rendimento em estoque)`.

    ⚠️ **A quantidade gravada no razão é SEMPRE na unidade de estoque** —
    `RECEITAS` é um jeito de dizer quanto, não outra unidade de medida. Gravar
    "2" com a etiqueta de receita faria o saldo do cookie contar receitas e o
    inventário da prateleira contar cookies.
    """
    por_receita = _rendimento_em_estoque(rendimento, porcoes, rendimento_um, um_estoque, ums)
    pedida = dec(quantidade)
    if (medida or "PORCOES").upper() == "RECEITAS":
        lotes = pedida
        # 4 casas: é a escala de `estoque_movimentos.quantidade`. Arredondar aqui
        # e não lá embaixo mantém o que a tela mostrou igual ao que entrou.
        qtd = (lotes * por_receita).quantize(Decimal("0.0001"))
    else:
        qtd = pedida
        lotes = qtd / por_receita
    return qtd, lotes, por_receita


def quantidade_de_estoque(cur, id_unidade: int, id_produto: int, quantidade,
                         id_local: int | None = None, medida: str | None = None,
                         id_modo: int | None = None) -> dict:
    """Traduz "X receitas" em quantidade de estoque. `{quantidade, lotes, porcoes_por_receita}`.

    🔑 **A tradução acontece UMA vez, na porta.** Quem agenda "2 receitas" grava
    130 UN na agenda, e daí para dentro tudo — o resumo do dia, a folha da
    bancada, a produção que fecha a linha — continua falando a única unidade que
    o razão conhece. Guardar "2" com uma etiqueta faria cada consulta ter de
    lembrar de traduzir, e a primeira que esquecesse produziria dois cookies.
    """
    cur.execute(
        """SELECT f.id, f.rendimento_qtd, f.rendimento_um, f.porcoes, p.um_estoque
             FROM fichas_tecnicas f JOIN produtos p ON p.id = f.id_produto
            WHERE f.id_produto = %s AND f.status = 'HOMOLOGADA' AND f.vigente_ate IS NULL""",
        (id_produto,),
    )
    ficha = cur.fetchone()
    if not ficha:
        raise HTTPException(status_code=400, detail="Este produto não tem ficha homologada.")
    if id_local is None:
        id_local = local_padrao(cur, id_unidade)

    from services import custos

    modo = modo_da_producao(cur, ficha["id"], id_local, id_modo, ficha["rendimento_qtd"],
                            ficha["porcoes"])
    qtd, lotes, por_receita = _quanto_produzir(
        quantidade, medida, modo["rendimento_qtd"], modo["porcoes"], ficha["rendimento_um"],
        ficha["um_estoque"], custos._carregar_ums(cur))
    return {"quantidade": float(qtd), "lotes": float(lotes),
            "porcoes_por_receita": float(por_receita), "um_estoque": ficha["um_estoque"],
            # Quem agenda precisa gravar QUAL modo foi planejado: cumprir a linha
            # três dias depois pelo rendimento padrão seria a quantidade certa
            # saindo da receita errada.
            "id_modo": modo["id_modo"], "modo": modo["modo"]}


def modo_da_producao(cur, id_ficha: int, id_local: int | None, id_modo: int | None,
                     rendimento_da_ficha, porcoes_da_ficha=None) -> dict:
    """Qual MODO de rendimento vale nesta produção.

    🔑 **Pedido do dono (16/09/2026):** *"podemos criar mais modos de rendimento
    para diferentes setores, com um nome, e este será o modo selecionado ao
    agendar ou produzir. Modo padrão é a receita toda para estoque; podemos ter
    um Modo Consumo, com o setor Bar e 30 porções; ou outro onde as porções são
    menores."* Antes disso o modo existia sem nome (`ficha_locais`, migração
    066) e era **adivinhado** a partir da prateleira de destino.

    🔑 **O que o modo muda de verdade não é escala, é a PORÇÃO.** Produzir 30 em
    vez de 65 sempre funcionou — a quantidade é livre e o consumo é proporcional.
    O que não existia era a mesma massa render *outra coisa*: os mesmos 8,535 KG
    em 130 unidades menores, que é outro custo unitário e outra contagem.

    A ordem, e ela importa:

    1. **O modo ESCOLHIDO** — quem produz decidiu, e decisão de gente ganha de
       qualquer regra.
    2. **O modo desta PRATELEIRA** — é o comportamento da migração 066, que
       continua valendo para quem nunca vai escolher nada.
    3. **O modo deste SETOR** — a prateleira do Bar herda o "Consumo — Bar" sem
       ninguém ter de repetir o cadastro em cada prateleira dele.
    4. **A própria ficha**, o Modo padrão. ⚠️ Ele NÃO é linha em `ficha_modos`:
       materializá-lo custaria uma linha por ficha da base para não mudar
       comportamento nenhum.

    ⚠️ **O rendimento DIVIDE o consumo** (`lotes = quantidade ÷ rendimento`), por
    isso quem chama devolve na resposta qual modo valeu: sem isso a pessoa
    produz achando que gastou outro tanto, e a diferença só aparece na contagem.
    """
    padrao = {
        "id_modo": None, "modo": "Padrão",
        "rendimento_qtd": dec(rendimento_da_ficha) or Decimal(1),
        "porcoes": dec(porcoes_da_ficha) if porcoes_da_ficha else None,
        "quantidade_sugerida": None,
        # Mantido com o nome antigo: a tela e a bateria já liam este campo, e o
        # que ele diz continua verdade — "não é o rendimento da ficha".
        "rendimento_do_local": False,
    }

    def montar(linha):
        return {
            "id_modo": linha["id"], "modo": linha["nome"],
            "rendimento_qtd": dec(linha["rendimento_qtd"]) or Decimal(1),
            "porcoes": dec(linha["porcoes"]) if linha["porcoes"] else None,
            "quantidade_sugerida": (dec(linha["quantidade_sugerida"])
                                    if linha["quantidade_sugerida"] else None),
            "rendimento_do_local": True,
        }

    campos = ("id, nome, rendimento_qtd, porcoes, quantidade_sugerida, id_local, id_setor")

    if id_modo:
        cur.execute(
            f"SELECT {campos} FROM ficha_modos WHERE id = %s AND id_ficha = %s AND ativo",
            (id_modo, id_ficha),
        )
        linha = cur.fetchone()
        # ⚠️ **Modo que não é desta ficha é RECUSA, não silêncio.** Cair no padrão
        # produziria com outro rendimento do que a tela mostrou, e ninguém veria.
        if not linha:
            raise HTTPException(
                status_code=400,
                detail="O modo de rendimento escolhido não é desta ficha, ou foi desativado.",
            )
        return montar(linha)

    if id_local is not None:
        cur.execute(
            f"""SELECT {campos} FROM ficha_modos
                 WHERE id_ficha = %s AND id_local = %s AND ativo
                 ORDER BY ordem, id LIMIT 1""",
            (id_ficha, id_local),
        )
        linha = cur.fetchone()
        if linha:
            return montar(linha)
        cur.execute(
            f"""SELECT m.id, m.nome, m.rendimento_qtd, m.porcoes, m.quantidade_sugerida,
                       m.id_local, m.id_setor
                  FROM ficha_modos m
                  JOIN locais_estoque l ON l.id_setor = m.id_setor
                 WHERE m.id_ficha = %s AND l.id = %s AND m.ativo AND m.id_local IS NULL
                 ORDER BY m.ordem, m.id LIMIT 1""",
            (id_ficha, id_local),
        )
        linha = cur.fetchone()
        if linha:
            return montar(linha)

    return padrao


def modos_da_ficha(cur, id_ficha: int) -> list[dict]:
    """Os modos cadastrados, para a tela oferecer a escolha. O padrão não entra.

    ⚠️ Só os ATIVOS: modo desativado continua existindo porque produções antigas
    apontam para ele, e oferecê-lo de novo desfaria a desativação.
    """
    cur.execute(
        """SELECT m.id, m.nome, m.rendimento_qtd, m.porcoes, m.porcao_qtd,
                  m.quantidade_sugerida, m.id_local, l.nome AS local,
                  m.id_setor, s.nome AS setor, m.observacao
             FROM ficha_modos m
             LEFT JOIN locais_estoque l ON l.id = m.id_local
             LEFT JOIN setores s ON s.id = m.id_setor
            WHERE m.id_ficha = %s AND m.ativo
            ORDER BY m.ordem, m.id""",
        (id_ficha,),
    )
    return [dict(r) for r in cur.fetchall()]


def previsao_producao(cur, id_unidade: int, id_produto: int, quantidade,
                      id_local: int | None = None, medida: str | None = None,
                      id_modo: int | None = None) -> dict:
    """O que uma produção VAI precisar, sem produzir nada.

    É a folha que a cozinha leva para a bancada: para 22 massas, 4,4 KG de
    farinha — e se tem 4,4 KG. Roda a MESMA conta da produção (rendimento,
    conversão de embalagem, local de cada insumo) porque prever com outra regra
    seria prever outra coisa.

    ⚠️ Sub-ficha aparece como o PRODUTO dela, não explodida em ingredientes: é
    isso que a produção consome de fato. Explodir aqui mostraria uma lista que
    o razão nunca vai registrar.
    """
    from services import custos

    cur.execute(
        """SELECT f.id, f.versao, f.rendimento_qtd, f.rendimento_um, f.porcoes,
                  -- 🔑 **O MODO DE PREPARO vem junto** (16/09/2026, pedido do dono:
                  -- *"quem vai ver esta tela precisa saber as quantidades e o modo
                  -- de preparo, não os custos"*). A folha que vai para a bancada
                  -- sem o preparo é meia folha: a pessoa levava a lista de
                  -- ingredientes e abria a ficha noutra tela para saber o que
                  -- fazer com eles.
                  f.modo_preparo, f.tempo_preparo_min, f.alergenos,
                  f.observacao AS ficha_observacao,
                  p.nome AS produto, p.codigo, p.um_estoque, p.id_local_padrao
             FROM fichas_tecnicas f JOIN produtos p ON p.id = f.id_produto
            WHERE f.id_produto = %s AND f.status = 'HOMOLOGADA' AND f.vigente_ate IS NULL""",
        (id_produto,),
    )
    ficha = cur.fetchone()
    if not ficha:
        raise HTTPException(status_code=400, detail="Este produto não tem ficha homologada.")

    qtd = dec(quantidade)
    # ⚠️ **O local se resolve ANTES do rendimento, e a ordem importa.** Na
    # primeira versão desta mudança o rendimento era lido com `id_local` ainda
    # nulo e o local só era resolvido três linhas abaixo: a prévia usava o
    # rendimento da ficha e a produção usava o do local, para o mesmo pedido.
    # O local de reserva se resolve como na PRODUÇÃO. Sem isto, o saldo era
    # procurado num local nulo, nada casava e a folha dizia que faltava tudo.
    if id_local is None:
        id_local = local_padrao(cur, id_unidade)
    # ⚠️ **O MESMO modo da produção**, escolhido ou herdado da prateleira: a
    # massa que vai ao forno para a vitrine não rende o mesmo que a que vai crua
    # para a câmara, e prever por um modo e produzir por outro seria prever
    # outra coisa.
    modo = modo_da_producao(cur, ficha["id"], id_local, id_modo, ficha["rendimento_qtd"],
                            ficha["porcoes"])
    rendimento = modo["rendimento_qtd"]
    rend_do_local = modo["rendimento_do_local"]
    ums = custos._carregar_ums(cur)
    # ⚠️ A MESMA ponte da produção: prever com outra regra seria prever outra
    # coisa — e foi assim que a folha da bancada passou a pedir sete vezes mais
    # ingrediente do que a receita precisa. Inclusive a leitura da MEDIDA: a
    # folha de "2 receitas" tem de pedir o mesmo que a produção de "2 receitas".
    qtd, lotes, por_receita = _quanto_produzir(
        qtd, medida, rendimento, modo["porcoes"], ficha["rendimento_um"],
        ficha["um_estoque"], ums)

    cur.execute(
        """SELECT fi.id AS id_item, fi.id_insumo, fi.id_subficha, fi.qtd_bruta, fi.um,
                  fi.observacao, p.um_estoque, p.nome, p.codigo, p.id_local_padrao
             FROM ficha_itens fi
             LEFT JOIN produtos p ON p.id = fi.id_insumo
            WHERE fi.id_ficha = %s ORDER BY fi.ordem, fi.id""",
        (ficha["id"],),
    )
    itens = [dict(r) for r in cur.fetchall()]

    linhas, custo_total, faltam = [], Decimal(0), 0
    for item in itens:
        if item["id_subficha"]:
            cur.execute(
                """SELECT p.id, p.nome, p.codigo, p.um_estoque, p.id_local_padrao
                     FROM fichas_tecnicas f JOIN produtos p ON p.id = f.id_produto
                    WHERE f.id = %s""",
                (item["id_subficha"],),
            )
            alvo = cur.fetchone()
            if not alvo:
                continue
            id_alvo, nome, codigo = alvo["id"], alvo["nome"], alvo["codigo"]
            um_destino, local_item = alvo["um_estoque"], alvo["id_local_padrao"]
            eh_preparo = True
        else:
            id_alvo, nome, codigo = item["id_insumo"], item["nome"], item["codigo"]
            um_destino, local_item = item["um_estoque"], item["id_local_padrao"]
            eh_preparo = False

        por_lote = dec(item["qtd_bruta"])
        bruta = por_lote * lotes
        convertida, como = custos.converter_para_estoque(
            cur, bruta, id_alvo, item["um"], um_destino, ums)

        # ⚠️ **A folha resolve o local do MESMO jeito que a produção.** Prever
        # com outra regra seria prever outra coisa: a folha diria que falta
        # açúcar no central enquanto a produção o tiraria da Confeitaria, e
        # quem lesse a previsão iria comprar o que já tem.
        onde = _de_onde_sai(cur, id_alvo, id_unidade, id_local,
                            local_item or id_local, convertida or 0)
        cur.execute(
            """SELECT coalesce(sum(quantidade), 0) AS aqui,
                      coalesce(sum(quantidade) FILTER (WHERE id_local = %s), 0) AS no_local,
                      max(custo_medio) FILTER (WHERE quantidade > 0) AS custo
                 FROM estoque_saldos
                WHERE id_produto = %s AND id_unidade = %s""",
            (onde, id_alvo, id_unidade),
        )
        saldo = cur.fetchone()
        unitario, _origem = custos.custo_do_insumo(cur, id_alvo, id_unidade)
        necessario = convertida if convertida is not None else None
        custo_linha = (necessario * unitario) if (necessario and unitario) else None
        if custo_linha:
            custo_total += custo_linha
        # Falta é sobre o LOCAL de onde a produção vai tirar — ter no depósito
        # não ajuda quem está na bancada da cozinha.
        falta = (necessario - dec(saldo["no_local"])) if necessario is not None else None
        if falta is not None and falta > 0:
            faltam += 1

        # 🔑 **As unidades que ESTE insumo aceita**, para a coluna do que foi
        # realmente usado poder trocar de unidade. ⚠️ São as mesmas que a
        # conversão conhece — oferecer uma que ela não sabe traduzir seria
        # convidar a recusa.
        cur.execute(
            """SELECT upper(um) AS um FROM produto_unidades WHERE id_produto = %s
                UNION SELECT upper(um_compra) FROM produtos
                        WHERE id = %s AND um_compra IS NOT NULL""",
            (id_alvo, id_alvo),
        )
        unidades = [um_destino] if um_destino else []
        if item["um"] and item["um"].upper() not in {u.upper() for u in unidades}:
            unidades.append(item["um"])
        for r in cur.fetchall():
            if r["um"] and r["um"] not in {u.upper() for u in unidades}:
                unidades.append(r["um"])

        linhas.append({
            # A chave da correção é a LINHA da receita, não o produto: a mesma ficha
            # pode listar o mesmo insumo duas vezes.
            "id_item": item["id_item"],
            "id_produto": id_alvo, "produto": nome, "codigo": codigo,
            "preparo": eh_preparo,
            "unidades": unidades,
            "um_ficha": item["um"], "um_estoque": um_destino,
            "por_unidade": float(por_lote / rendimento),
            "na_ficha": float(bruta),
            "necessario": float(necessario) if necessario is not None else None,
            "conversao": como,
            "saldo_no_local": float(saldo["no_local"]),
            "saldo_total": float(saldo["aqui"]),
            "falta": float(falta) if falta is not None and falta > 0 else 0.0,
            "custo_unitario": float(unitario) if unitario is not None else None,
            "custo": float(custo_linha) if custo_linha is not None else None,
            "observacao": item["observacao"],
        })

    return {
        "id_ficha": ficha["id"], "versao": ficha["versao"], "id_produto": id_produto,
        "produto": ficha["produto"], "codigo": ficha["codigo"],
        "um_estoque": ficha["um_estoque"],
        # O que a bancada precisa saber além das quantidades.
        "modo_preparo": ficha["modo_preparo"],
        "tempo_preparo_min": ficha["tempo_preparo_min"],
        "alergenos": ficha["alergenos"],
        "ficha_observacao": ficha["ficha_observacao"],
        "quantidade": float(qtd), "rendimento_qtd": float(rendimento),
        "rendimento_um": ficha["rendimento_um"], "lotes": float(lotes),
        # Quantas unidades de estoque UMA receita rende. É o número que traduz
        # um jeito de pedir no outro, e a tela mostra os dois lados com ele.
        "porcoes_por_receita": float(por_receita),
        # ⚠️ **Quem produz tem de saber QUAL rendimento valeu.** Ele divide o
        # consumo: sem isto a pessoa produz 10 achando que gastou um lote e gastou
        # 1,25 — e a diferença só aparece na contagem.
        "rendimento_do_local": rend_do_local,
        "id_modo": modo["id_modo"], "modo": modo["modo"],
        "quantidade_sugerida": (float(modo["quantidade_sugerida"])
                                if modo["quantidade_sugerida"] else None),
        # Os modos cadastrados nesta ficha, para a tela oferecer a escolha sem
        # precisar de uma segunda chamada a cada troca de produto.
        "modos": [{"id": m["id"], "nome": m["nome"],
                   "rendimento_qtd": float(m["rendimento_qtd"]),
                   "porcoes": float(m["porcoes"]) if m["porcoes"] else None,
                   "quantidade_sugerida": (float(m["quantidade_sugerida"])
                                           if m["quantidade_sugerida"] else None),
                   "local": m["local"], "setor": m["setor"]}
                  for m in modos_da_ficha(cur, ficha["id"])],
        "itens": linhas, "itens_faltando": faltam,
        "custo_total": float(custo_total),
        "custo_unitario": float(custo_total / qtd) if qtd else 0.0,
    }


def _local_desta_loja(cur, id_local: int | None, id_unidade: int, alternativo: int) -> int:
    """O local do produto, mas só se ele for DESTA loja.

    🔑 **`produtos.id_local_padrao` é um local só, e local pertence a UMA loja.**
    A produção usava esse local direto, com o `id_unidade` da loja que estava
    produzindo: a filial que fizesse um molho cujo local padrão é a câmara da
    MATRIZ gravaria o movimento com a loja da filial e a prateleira da matriz.
    O saldo tem chave `(loja, local, produto)`, então nascia uma linha
    fantasma — e o produto ficava num lugar onde ninguém o encontra.
    ⚠️ Não é o cadastro que está errado: o local padrão é a resposta certa na
    loja dona dele. Fora dela, a resposta é o local principal de quem produz.
    """
    if not id_local:
        return alternativo
    cur.execute("SELECT id_unidade FROM locais_estoque WHERE id = %s", (id_local,))
    linha = cur.fetchone()
    return id_local if linha and linha["id_unidade"] == id_unidade else alternativo


def _de_onde_sai(cur, id_produto: int, id_unidade: int, id_local_producao: int | None,
                 id_local_do_produto: int, quantidade) -> int:
    """O local de quem PRODUZ, quando o insumo está lá; senão, o do produto.

    🔑 **A ordem é o processo da casa** (01/09/2026): o açúcar entra no Estoque
    Central e de manhã cada setor leva um pacote para o seu canto. Se a
    Confeitaria produz, o açúcar tem de sair do estoque DELA — senão o que ela
    pegou de manhã nunca baixa, e a contagem do fim da semana acusa uma sobra
    que não existe.

    ⚠️ **A reserva não é conveniência, é um caso real.** Uma receita usa leite
    da câmara e café do seco ao mesmo tempo: forçar tudo no local de quem
    produz faria a saída bater num lugar por onde o insumo nunca passou, com
    saldo NEGATIVO e custo provisório — e custo provisório contamina o custo do
    prato produzido, que é justamente o número que a produção existe para
    apurar.

    ⚠️ **Pergunta pelo saldo do dia, não pelo cadastro.** Se a Confeitaria tem
    açúcar, sai de lá; se acabou, sai do central. Decidir pelo cadastro faria a
    produção falhar no dia em que o pacote da manhã acabou no meio da tarde.
    """
    if not id_local_producao or id_local_producao == id_local_do_produto:
        return id_local_do_produto
    cur.execute(
        """SELECT quantidade FROM estoque_saldos
            WHERE id_unidade = %s AND id_local = %s AND id_produto = %s""",
        (id_unidade, id_local_producao, id_produto),
    )
    linha = cur.fetchone()
    if linha and dec(linha["quantidade"]) >= dec(quantidade):
        return id_local_producao
    return id_local_do_produto


def produzir(cur, *, id_unidade: int, id_produto: int, quantidade, id_local: int | None,
             id_usuario: int, observacao: str | None = None,
             medida: str | None = None, id_modo: int | None = None,
             consumos: list[dict] | None = None) -> dict:
    """Consome a ficha homologada e devolve o produzido ao estoque.

    O custo do produzido é **o que realmente saiu** — não o custo teórico da
    ficha. Se um insumo estava mais caro hoje, o prato produzido hoje custa mais.

    `medida` diz em que a `quantidade` foi digitada: `PORCOES` (o padrão — a
    unidade de estoque do produto) ou `RECEITAS` (voltas inteiras da ficha).
    Ver `_quanto_produzir`.

    🔑 **`consumos` corrige o que REALMENTE saiu** (16/09/2026, pedido do dono:
    *"na lista de insumos, ter uma nova coluna com o que realmente foi usado —
    por padrão a mesma quantidade, mas o usuário pode alterar, inclusive a
    unidade; na receita vão 5 ovos, mas por um acaso usei 6"*). Cada entrada é
    `{id_item, quantidade, um}` e substitui a quantidade calculada daquela linha
    da receita. O razão já era capaz disso; o que faltava era a porta — quem
    usava seis ovos lançava cinco, e o sexto sumia do controle até aparecer no
    inventário como falta sem causa.

    ⚠️ **A chave é o ITEM da ficha, não o produto.** A mesma receita pode listar
    o mesmo insumo duas vezes (a manteiga da massa e a de untar), e corrigir "a
    manteiga" mexeria nas duas.

    ⚠️ **A unidade passa pela MESMA conversão de sempre** (embalagem do produto,
    depois grandeza). Sem caminho, é recusa: aceitar 1:1 faria "usei 2 CX" baixar
    duas unidades.

    ⚠️ **Zero é aceito e não vira movimento.** "Não usei" é uma resposta
    legítima (acabou, substituí), e uma linha de quantidade zero no razão diria
    que algo se moveu.
    """
    cur.execute(
        """SELECT id, versao, rendimento_qtd, rendimento_um, porcoes FROM fichas_tecnicas
            WHERE id_produto = %s AND status = 'HOMOLOGADA' AND vigente_ate IS NULL""",
        (id_produto,),
    )
    ficha = cur.fetchone()
    if not ficha:
        raise HTTPException(
            status_code=400,
            detail="Este produto não tem ficha homologada — homologue a ficha antes de produzir.",
        )
    if id_local is None:
        id_local = local_padrao(cur, id_unidade)

    qtd = dec(quantidade)
    # ⚠️ O modo sai do ESCOLHIDO, senão da prateleira, senão do setor dela — e o
    # `id_local` já foi resolvido acima, então aqui ele nunca é nulo.
    modo = modo_da_producao(cur, ficha["id"], id_local, id_modo, ficha["rendimento_qtd"],
                            ficha["porcoes"])
    rendimento = modo["rendimento_qtd"]
    rend_do_local = modo["rendimento_do_local"]

    from services import custos  # importado aqui para não criar ciclo de módulos

    ums = {}
    cur.execute("SELECT sigla, grandeza, fator_base FROM unidades_medida")
    for r in cur.fetchall():
        ums[r["sigla"]] = dict(r)

    # Quantas vezes a receita inteira foi feita, e quanto isso dá na unidade de
    # estoque — ver `_quanto_produzir`: a quantidade pedida pode vir em PORÇÕES
    # (a unidade do produto) ou em RECEITAS (voltas inteiras da ficha).
    cur.execute("SELECT um_estoque FROM produtos WHERE id = %s", (id_produto,))
    um_estoque_produto = (cur.fetchone() or {}).get("um_estoque")
    qtd, lotes, por_receita = _quanto_produzir(
        qtd, medida, rendimento, modo["porcoes"], ficha["rendimento_um"],
        um_estoque_produto, ums)

    cur.execute(
        """SELECT fi.id AS id_item, fi.id_insumo, fi.id_subficha, fi.qtd_bruta, fi.um,
                  p.um_estoque, p.nome, p.id_local_padrao
             FROM ficha_itens fi
             LEFT JOIN produtos p ON p.id = fi.id_insumo
            WHERE fi.id_ficha = %s ORDER BY fi.ordem, fi.id""",
        (ficha["id"],),
    )
    itens = [dict(r) for r in cur.fetchall()]
    if not itens:
        raise HTTPException(status_code=400, detail="A ficha não tem ingredientes.")

    # ⚠️ Pela linha da RECEITA, não pelo produto: a mesma ficha pode listar o
    # mesmo insumo duas vezes, e corrigir "a manteiga" mexeria nas duas.
    ajustes = {int(c["id_item"]): c for c in (consumos or []) if c.get("id_item")}
    ajustou = False

    cur.execute(
        """INSERT INTO producoes (id_unidade, id_local, id_produto, id_ficha, versao_ficha,
                                  quantidade, observacao, id_usuario, id_modo)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (id_unidade, id_local, id_produto, ficha["id"], ficha["versao"], qtd, observacao,
         id_usuario,
         # 🔑 **O modo fica congelado junto com a versão da ficha**, e pela
         # mesma razão: o rendimento divide o consumo, e o número tem de se
         # reproduzir daqui a seis meses.
         modo["id_modo"]),
    )
    id_producao = cur.fetchone()["id"]

    custo_consumido = Decimal(0)
    # ⚠️ Nome próprio: `consumos` é o que ENTROU (a correção de quem produziu),
    # e isto é o que SAIU. Com o mesmo nome, o segundo apagava o primeiro.
    linhas_consumo = []
    for item in itens:
        if item["id_subficha"]:
            # Sub-ficha na produção: consome o PRODUTO dela, que precisa ter
            # sido produzido antes. É o que mantém o razão fiel ao que existe.
            cur.execute(
                "SELECT id_produto FROM fichas_tecnicas WHERE id = %s", (item["id_subficha"],)
            )
            alvo = cur.fetchone()
            if not alvo:
                continue
            id_alvo, um_origem, um_destino = alvo["id_produto"], item["um"], None
            cur.execute("SELECT um_estoque, nome, id_local_padrao FROM produtos WHERE id = %s",
                        (id_alvo,))
            p = cur.fetchone()
            um_destino, nome, local_do_item = p["um_estoque"], p["nome"], p["id_local_padrao"]
        else:
            id_alvo, um_origem, um_destino, nome = (
                item["id_insumo"], item["um"], item["um_estoque"], item["nome"]
            )
            local_do_item = item.get("id_local_padrao")

        bruta = dec(item["qtd_bruta"]) * lotes
        # A MESMA regra da ficha e da nota de entrada: embalagem do produto
        # primeiro, grandeza depois. Baixar 1 onde a receita pede uma caixa de
        # 12 some com 11 do razão sem ninguém ver.
        convertida, _como = custos.converter_para_estoque(
            cur, bruta, id_alvo, um_origem, um_destino, ums)
        if convertida is None:
            raise HTTPException(
                status_code=400,
                detail=(f"{nome}: {um_origem or '?'} não converte para "
                        f"{um_destino or '?'}. Cadastre esta unidade de compra no produto."),
            )
        pedida = convertida

        # 🔑 **O que REALMENTE saiu manda.** A receita diz cinco ovos; quem
        # estava na banca usou seis, e é o sexto que some do controle quando a
        # tela não deixa corrigir.
        ajuste = ajustes.pop(item["id_item"], None)
        if ajuste is not None:
            usada = dec(ajuste.get("quantidade"))
            um_usada = (ajuste.get("um") or um_destino)
            convertida, _c = custos.converter_para_estoque(
                cur, usada, id_alvo, um_usada, um_destino, ums)
            if convertida is None:
                raise HTTPException(
                    status_code=400,
                    detail=(f"{nome}: {um_usada} não converte para {um_destino or '?'}. "
                            f"Cadastre esta unidade no produto, ou informe em "
                            f"{um_destino or 'unidade de estoque'}."),
                )
            if convertida != pedida:
                ajustou = True

        # ⚠️ **Zero não vira movimento.** "Não usei" é resposta legítima —
        # acabou, substituí — e uma linha de quantidade zero no razão diria que
        # algo se moveu.
        if convertida <= 0:
            linhas_consumo.append({"id_item": item["id_item"], "id_produto": id_alvo,
                                   "nome": nome, "quantidade": 0.0, "custo": 0.0,
                                   "pedida": float(pedida)})
            continue
        # 🔑 **O insumo sai de ONDE SE PRODUZ, quando ele está lá.** A casa
        # trabalha assim: o açúcar entra no Estoque Central e de manhã cada
        # setor leva um pacote para o seu canto — Bar, Confeitaria, Cozinha. Se
        # a Confeitaria produz, o açúcar tem de sair do estoque DELA, senão o
        # que ela pegou de manhã nunca baixa e a contagem do fim da semana
        # acusa uma sobra que não existe.
        # ⚠️ **Mas só quando há saldo lá.** A regra anterior — cada insumo sai
        # do local DELE — existe por um caso igualmente real: uma receita usa
        # leite da câmara e café do seco ao mesmo tempo, e forçar tudo no local
        # de quem produz faria a saída bater num lugar por onde o insumo nunca
        # passou, com saldo negativo e custo provisório. Então a ordem é: o
        # local de quem produz primeiro, o local do produto como reserva.
        onde = _de_onde_sai(cur, id_alvo, id_unidade, id_local,
                            _local_desta_loja(cur, local_do_item, id_unidade, id_local),
                            convertida)
        r = lancar(
            cur, id_unidade=id_unidade,
            id_local=onde,
            id_produto=id_alvo,
            tipo="SAIDA_PRODUCAO", quantidade=convertida, origem_tipo="PRODUCAO",
            origem_id=id_producao, id_usuario=id_usuario,
            # ⚠️ O razão diz quando a linha se afastou da receita: quem for
            # conferir o movimento seis meses depois não tem a ficha ao lado.
            observacao=(f"Produção #{id_producao}"
                        + (" · quantidade corrigida" if convertida != pedida else "")),
        )
        custo_consumido += dec(r["custo_exato"])
        linhas_consumo.append({"id_item": item["id_item"], "id_produto": id_alvo, "nome": nome,
                               "quantidade": float(convertida), "custo": float(r["custo_total"]),
                               # Quanto a receita pedia: é a comparação que diz se
                               # a ficha está certa.
                               "pedida": float(pedida)})

    # ⚠️ **Sobrou correção sem linha correspondente**: a tela mandou um item que
    # esta ficha não tem (ou uma versão nova mudou a receita entre abrir a folha e
    # produzir). Ignorar seria gravar uma produção que não é a que a pessoa viu.
    if ajustes:
        raise HTTPException(
            status_code=400,
            detail=("A receita mudou desde que esta folha foi aberta — recarregue a tela "
                    "antes de produzir."),
        )

    unitario = (custo_consumido / qtd).quantize(CASAS_CUSTO) if qtd else Decimal(0)
    # O produzido também entra no local dele: o molho vai para a câmara, não
    # para onde por acaso se lançou a produção.
    cur.execute("SELECT id_local_padrao FROM produtos WHERE id = %s", (id_produto,))
    local_produzido = (cur.fetchone() or {}).get("id_local_padrao")
    local_produzido = _local_desta_loja(cur, local_produzido, id_unidade, id_local)
    entrada = lancar(
        cur, id_unidade=id_unidade, id_local=local_produzido,
        id_produto=id_produto,
        tipo="ENTRADA_PRODUCAO", quantidade=qtd, custo_unitario=unitario,
        origem_tipo="PRODUCAO", origem_id=id_producao, id_usuario=id_usuario,
        observacao=observacao,
    )
    cur.execute(
        """UPDATE producoes SET custo_total = %s, custo_unitario = %s,
                                consumo_ajustado = %s
            WHERE id = %s""",
        (custo_consumido.quantize(Decimal("0.01")), unitario, ajustou, id_producao),
    )

    return {
        "id": id_producao,
        "versao_ficha": ficha["versao"],
        # ⚠️ **Sempre na unidade de ESTOQUE**, mesmo quando o pedido veio em
        # receitas: é o que entrou na prateleira, e é o número que a tela
        # confirma de volta para quem clicou.
        "quantidade": float(qtd),
        "lotes": float(lotes),
        "porcoes_por_receita": float(por_receita),
        # Qual rendimento dividiu o consumo, e de qual MODO ele veio. A tela
        # precisa dizer: sem isso a pessoa produz achando que gastou outro tanto.
        "rendimento_qtd": float(rendimento),
        "rendimento_do_local": rend_do_local,
        "id_modo": modo["id_modo"], "modo": modo["modo"],
        "custo_total": float(custo_consumido),
        "custo_unitario": float(unitario),
        "consumos": linhas_consumo,
        # 🔑 Produção que se afasta da receita com frequência é ficha errada, e
        # essa pergunta tem de poder ser feita olhando a lista.
        "consumo_ajustado": ajustou,
        "movimento_entrada": entrada["id"],
        # Onde o produzido entrou — quem produz por causa de uma venda precisa
        # dar a baixa no MESMO local, senão o saldo fica preso lá.
        "id_local": local_produzido,
    }
