"""O motor do estoque — custo médio ponderado móvel.

**Toda escrita no razão passa por `lancar`.** Nenhum router monta INSERT em
`estoque_movimentos` por fora: é aqui que mora a trava de concorrência, o
cálculo do médio e a fotografia do saldo.

Duas coisas que o leitor de amanhã precisa saber:

1. **O médio segue a ordem de LANÇAMENTO, não a data do movimento.** Uma nota
   lançada hoje com data de ontem entra depois no razão — a data serve ao
   relatório, a sequência serve ao custo. Recalcular por data exigiria refazer
   a série inteira a cada correção, e o CMV de ontem mudaria sozinho.
2. **Saída sem saldo é permitida** (a cozinha usa antes de a nota chegar), usa o
   último médio conhecido e fica marcada como `custo_provisorio`.
"""

from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException

from services.custos import CASAS_CUSTO, dec

ENTRADAS = {
    "ENTRADA_NF", "ENTRADA_MANUAL", "ENTRADA_PRODUCAO", "ENTRADA_DEVOLUCAO",
    "TRANSFERENCIA_ENTRADA", "AJUSTE_INVENTARIO_ENTRADA", "ESTORNO_ENTRADA",
}
SAIDAS = {
    "SAIDA_VENDA", "SAIDA_PRODUCAO", "SAIDA_PERDA", "SAIDA_CONSUMO_INTERNO",
    "TRANSFERENCIA_SAIDA", "AJUSTE_INVENTARIO_SAIDA", "ESTORNO_SAIDA",
}
TIPOS = ENTRADAS | SAIDAS

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
}


def _parametros(cur, id_unidade: int) -> dict:
    cur.execute(
        """SELECT permitir_saldo_negativo, exigir_motivo_perda, exigir_local_movimento,
                  bloquear_retroativo
             FROM parametros WHERE id_unidade = %s""",
        (id_unidade,),
    )
    p = cur.fetchone()
    return dict(p) if p else {
        "permitir_saldo_negativo": True,
        "exigir_motivo_perda": True,
        "exigir_local_movimento": True,
        "bloquear_retroativo": True,
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
        """SELECT competencia FROM cmv_fechamentos
            WHERE id_unidade = %s AND status = 'FECHADO' AND %s BETWEEN inicio AND fim""",
        (id_unidade, data),
    )
    fechado = cur.fetchone()
    if fechado:
        raise HTTPException(
            status_code=400,
            detail=(
                f"O período de {fechado['competencia'].strftime('%m/%Y')} está fechado. "
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


def _ultimo_medio_conhecido(cur, id_produto: int, id_unidade: int) -> Decimal:
    """Para saída sem saldo: o médio de outro local, ou o último do razão."""
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
    return dec(linha["custo_medio_apos"]) if linha else Decimal(0)


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

    par = _parametros(cur, id_unidade)
    if id_local is None:
        id_local = local_padrao(cur, id_unidade)
    if data_movimento is not None and par.get("bloquear_retroativo", True):
        _travar_periodo_fechado(cur, id_unidade, data_movimento, pode_retroativo)
    if tipo == "SAIDA_PERDA" and par["exigir_motivo_perda"] and not id_motivo_perda:
        raise HTTPException(status_code=400, detail="Informe o motivo da perda.")

    saldo = _travar_saldo(cur, id_unidade, id_local, id_produto)
    saldo_atual, medio_atual = dec(saldo["quantidade"]), dec(saldo["custo_medio"])
    provisorio = False

    if tipo in ENTRADAS:
        unitario = dec(custo_unitario) if custo_unitario is not None else medio_atual
        saldo_novo = saldo_atual + qtd
        if saldo_novo > 0:
            valor = (saldo_atual * medio_atual) + (qtd * unitario)
            medio_novo = (valor / saldo_novo).quantize(CASAS_CUSTO)
        else:
            medio_novo = unitario
        sinal = qtd
    else:
        if saldo_atual <= 0 and medio_atual == 0:
            unitario = _ultimo_medio_conhecido(cur, id_produto, id_unidade)
            provisorio = True
        else:
            unitario = medio_atual
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
        # A saída não mexe no médio — só o esvazia quando zera de fato.
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


def transferir(cur, *, id_unidade: int, id_produto: int, quantidade, id_local_origem: int,
               id_local_destino: int, id_usuario: int, observacao: str | None = None) -> dict:
    """Sai de um local e entra no outro **pelo mesmo custo** — transferência não
    cria nem destrói valor."""
    if id_local_origem == id_local_destino:
        raise HTTPException(status_code=400, detail="Origem e destino são o mesmo local.")

    saida = lancar(
        cur, id_unidade=id_unidade, id_local=id_local_origem, id_produto=id_produto,
        tipo="TRANSFERENCIA_SAIDA", quantidade=quantidade, origem_tipo="TRANSFERENCIA",
        observacao=observacao, id_usuario=id_usuario,
    )
    entrada = lancar(
        cur, id_unidade=id_unidade, id_local=id_local_destino, id_produto=id_produto,
        tipo="TRANSFERENCIA_ENTRADA", quantidade=quantidade,
        custo_unitario=saida["custo_unitario"], origem_tipo="TRANSFERENCIA",
        origem_id=saida["id"], observacao=observacao, id_usuario=id_usuario,
    )
    cur.execute(
        "UPDATE estoque_movimentos SET origem_id = %s WHERE id = %s",
        (entrada["id"], saida["id"]),
    )
    return {"saida": saida, "entrada": entrada}


def previsao_producao(cur, id_unidade: int, id_produto: int, quantidade,
                      id_local: int | None = None) -> dict:
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
        """SELECT f.id, f.versao, f.rendimento_qtd, f.rendimento_um, p.nome AS produto,
                  p.codigo, p.um_estoque, p.id_local_padrao
             FROM fichas_tecnicas f JOIN produtos p ON p.id = f.id_produto
            WHERE f.id_produto = %s AND f.status = 'HOMOLOGADA' AND f.vigente_ate IS NULL""",
        (id_produto,),
    )
    ficha = cur.fetchone()
    if not ficha:
        raise HTTPException(status_code=400, detail="Este produto não tem ficha homologada.")

    qtd = dec(quantidade)
    rendimento = dec(ficha["rendimento_qtd"]) or Decimal(1)
    lotes = qtd / rendimento
    ums = custos._carregar_ums(cur)
    # O local de reserva se resolve como na PRODUÇÃO. Sem isto, o saldo era
    # procurado num local nulo, nada casava e a folha dizia que faltava tudo.
    if id_local is None:
        id_local = local_padrao(cur, id_unidade)

    cur.execute(
        """SELECT fi.id_insumo, fi.id_subficha, fi.qtd_bruta, fi.um, fi.observacao,
                  p.um_estoque, p.nome, p.codigo, p.id_local_padrao
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

        onde = local_item or id_local
        cur.execute(
            """SELECT coalesce(sum(quantidade), 0) AS aqui,
                      coalesce(sum(quantidade) FILTER (WHERE id_local = %s), 0) AS no_local,
                      max(custo_medio) FILTER (WHERE quantidade > 0) AS custo
                 FROM estoque_saldos
                WHERE id_produto = %s AND id_unidade = %s""",
            (onde, id_alvo, id_unidade),
        )
        saldo = cur.fetchone()
        unitario, _origem = custos.custo_do_insumo(cur, id_alvo)
        necessario = convertida if convertida is not None else None
        custo_linha = (necessario * unitario) if (necessario and unitario) else None
        if custo_linha:
            custo_total += custo_linha
        # Falta é sobre o LOCAL de onde a produção vai tirar — ter no depósito
        # não ajuda quem está na bancada da cozinha.
        falta = (necessario - dec(saldo["no_local"])) if necessario is not None else None
        if falta is not None and falta > 0:
            faltam += 1

        linhas.append({
            "id_produto": id_alvo, "produto": nome, "codigo": codigo,
            "preparo": eh_preparo,
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
        "quantidade": float(qtd), "rendimento_qtd": float(rendimento),
        "rendimento_um": ficha["rendimento_um"], "lotes": float(lotes),
        "itens": linhas, "itens_faltando": faltam,
        "custo_total": float(custo_total),
        "custo_unitario": float(custo_total / qtd) if qtd else 0.0,
    }


def produzir(cur, *, id_unidade: int, id_produto: int, quantidade, id_local: int | None,
             id_usuario: int, observacao: str | None = None) -> dict:
    """Consome a ficha homologada e devolve o produzido ao estoque.

    O custo do produzido é **o que realmente saiu** — não o custo teórico da
    ficha. Se um insumo estava mais caro hoje, o prato produzido hoje custa mais.
    """
    cur.execute(
        """SELECT id, versao, rendimento_qtd, rendimento_um FROM fichas_tecnicas
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
    rendimento = dec(ficha["rendimento_qtd"]) or Decimal(1)
    # Quantas vezes a receita inteira foi feita.
    lotes = qtd / rendimento

    from services import custos  # importado aqui para não criar ciclo de módulos

    ums = {}
    cur.execute("SELECT sigla, grandeza, fator_base FROM unidades_medida")
    for r in cur.fetchall():
        ums[r["sigla"]] = dict(r)

    cur.execute(
        """SELECT fi.id_insumo, fi.id_subficha, fi.qtd_bruta, fi.um, p.um_estoque, p.nome,
                  p.id_local_padrao
             FROM ficha_itens fi
             LEFT JOIN produtos p ON p.id = fi.id_insumo
            WHERE fi.id_ficha = %s ORDER BY fi.ordem, fi.id""",
        (ficha["id"],),
    )
    itens = [dict(r) for r in cur.fetchall()]
    if not itens:
        raise HTTPException(status_code=400, detail="A ficha não tem ingredientes.")

    cur.execute(
        """INSERT INTO producoes (id_unidade, id_local, id_produto, id_ficha, versao_ficha,
                                  quantidade, observacao, id_usuario)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (id_unidade, id_local, id_produto, ficha["id"], ficha["versao"], qtd, observacao,
         id_usuario),
    )
    id_producao = cur.fetchone()["id"]

    custo_consumido = Decimal(0)
    consumos = []
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
        # Cada insumo sai de ONDE ELE MORA. Uma receita usa leite da câmara e
        # café do estoque seco ao mesmo tempo: um local só para a produção
        # inteira faria a saída bater num local sem saldo — o razão registrava
        # a baixa num lugar por onde o insumo nunca passou, e o saldo do lugar
        # certo continuava cheio. É a mesma regra da nota de entrada.
        r = lancar(
            cur, id_unidade=id_unidade, id_local=local_do_item or id_local,
            id_produto=id_alvo,
            tipo="SAIDA_PRODUCAO", quantidade=convertida, origem_tipo="PRODUCAO",
            origem_id=id_producao, id_usuario=id_usuario,
            observacao=f"Produção #{id_producao}",
        )
        custo_consumido += dec(r["custo_exato"])
        consumos.append({"id_produto": id_alvo, "nome": nome,
                         "quantidade": float(convertida), "custo": float(r["custo_total"])})

    unitario = (custo_consumido / qtd).quantize(CASAS_CUSTO) if qtd else Decimal(0)
    # O produzido também entra no local dele: o molho vai para a câmara, não
    # para onde por acaso se lançou a produção.
    cur.execute("SELECT id_local_padrao FROM produtos WHERE id = %s", (id_produto,))
    local_produzido = (cur.fetchone() or {}).get("id_local_padrao")
    entrada = lancar(
        cur, id_unidade=id_unidade, id_local=local_produzido or id_local,
        id_produto=id_produto,
        tipo="ENTRADA_PRODUCAO", quantidade=qtd, custo_unitario=unitario,
        origem_tipo="PRODUCAO", origem_id=id_producao, id_usuario=id_usuario,
        observacao=observacao,
    )
    cur.execute(
        "UPDATE producoes SET custo_total = %s, custo_unitario = %s WHERE id = %s",
        (custo_consumido.quantize(Decimal("0.01")), unitario, id_producao),
    )

    return {
        "id": id_producao,
        "versao_ficha": ficha["versao"],
        "quantidade": float(qtd),
        "custo_total": float(custo_consumido),
        "custo_unitario": float(unitario),
        "consumos": consumos,
        "movimento_entrada": entrada["id"],
        # Onde o produzido entrou — quem produz por causa de uma venda precisa
        # dar a baixa no MESMO local, senão o saldo fica preso lá.
        "id_local": local_produzido or id_local,
    }
