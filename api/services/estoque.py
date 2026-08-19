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

    custo_total = (qtd * unitario).quantize(Decimal("0.01"))

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

    if produto["controla_lote"] and (lote or validade):
        _mover_lote(cur, movimento["id"], id_unidade, id_local, id_produto,
                    lote, validade, qtd if tipo in ENTRADAS else -qtd)

    return {
        "id": movimento["id"],
        "quantidade": sinal,
        "custo_unitario": unitario,
        "custo_total": custo_total,
        "saldo_apos": saldo_novo,
        "custo_medio_apos": medio_novo,
        "custo_provisorio": provisorio,
    }


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
        """UPDATE estoque_lotes SET quantidade = quantidade + %s
            WHERE id_unidade = %s AND id_local = %s AND id_produto = %s
              AND COALESCE(lote, '') = COALESCE(%s, '')
              AND COALESCE(validade, '9999-12-31') = COALESCE(%s, '9999-12-31')
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
        """SELECT fi.id_insumo, fi.id_subficha, fi.qtd_bruta, fi.um, p.um_estoque, p.nome
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
            cur.execute("SELECT um_estoque, nome FROM produtos WHERE id = %s", (id_alvo,))
            p = cur.fetchone()
            um_destino, nome = p["um_estoque"], p["nome"]
        else:
            id_alvo, um_origem, um_destino, nome = (
                item["id_insumo"], item["um"], item["um_estoque"], item["nome"]
            )

        bruta = dec(item["qtd_bruta"]) * lotes
        convertida = custos.converter(bruta, um_origem, um_destino, ums)
        if convertida is None:
            raise HTTPException(
                status_code=400,
                detail=f"{nome}: {um_origem or '?'} não converte para {um_destino or '?'}.",
            )
        r = lancar(
            cur, id_unidade=id_unidade, id_local=id_local, id_produto=id_alvo,
            tipo="SAIDA_PRODUCAO", quantidade=convertida, origem_tipo="PRODUCAO",
            origem_id=id_producao, id_usuario=id_usuario,
            observacao=f"Produção #{id_producao}",
        )
        custo_consumido += dec(r["custo_total"])
        consumos.append({"id_produto": id_alvo, "nome": nome,
                         "quantidade": float(convertida), "custo": float(r["custo_total"])})

    unitario = (custo_consumido / qtd).quantize(CASAS_CUSTO) if qtd else Decimal(0)
    entrada = lancar(
        cur, id_unidade=id_unidade, id_local=id_local, id_produto=id_produto,
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
    }
