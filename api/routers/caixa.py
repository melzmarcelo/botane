"""Conferência do caixa e taxas por forma de pagamento (migração 161).

🔑 Etapas 3 e 4 do estudo das finalizadoras (`docs/pdv-finalizadoras-estudo.md`). O esperado
sai das finalizadoras (`venda_pagamentos`); aqui só se grava o contado e a taxa de cada forma.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException

import auditoria
import relogio
from database import get_cursor
from models.caixa import ContadoRequest, TaxasRequest
from seguranca import Contexto, requer_permissao, unidade_atual
from services import caixa as servico

router = APIRouter(prefix="/caixa", tags=["caixa"])

_caixa = requer_permissao("vendas.caixa")
# As taxas são da configuração da loja (Precificação); ver é de quem confere ou precifica.
_ver_taxas = requer_permissao("vendas.caixa", "precificacao.analisar", "precificacao.configurar")
_mudar_taxas = requer_permissao("precificacao.configurar")


@router.get("/conferencia")
def conferencia(inicio: date | None = None, fim: date | None = None,
                ctx: Contexto = Depends(_caixa)) -> dict:
    """Dia a dia: dinheiro esperado na gaveta (recebido − troco), contado e diferença.

    Sem datas, os últimos 14 dias. ⚠️ Até um ano por vez.
    """
    fim = fim or relogio.hoje_da_casa()
    inicio = inicio or fim - timedelta(days=13)
    if fim < inicio:
        raise HTTPException(status_code=400, detail="O fim do período vem antes do início.")
    if (fim - inicio).days > 366:
        raise HTTPException(status_code=400, detail="Até um ano por vez — estreite o período.")
    with get_cursor() as cur:
        return servico.conferencia(cur, unidade_atual(cur, ctx), inicio, fim)


@router.put("/conferencia/{dia}")
def gravar_contado(dia: date, body: ContadoRequest, ctx: Contexto = Depends(_caixa)) -> dict:
    if dia > relogio.hoje_da_casa():
        raise HTTPException(status_code=422, detail="Não dá para conferir um dia que não chegou.")
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.gravar_contado(cur, id_unidade, dia, body.contado, body.observacao,
                                   ctx.id_usuario)
        auditoria.registrar(
            cur, ctx.id_usuario, "caixa", str(dia), "conferir",
            antes=({"contado": str(r["antes"]["contado"]), "observacao": r["antes"]["observacao"]}
                   if r["antes"] else None),
            depois={"contado": str(body.contado), "observacao": body.observacao},
            id_unidade=id_unidade)
    return {"data": dia, "contado": body.contado,
            "message": f"Caixa de {dia:%d/%m} conferido."}


@router.get("/taxas")
def taxas(ctx: Contexto = Depends(_ver_taxas)) -> dict:
    with get_cursor() as cur:
        return servico.taxas(cur, unidade_atual(cur, ctx))


@router.put("/taxas")
def gravar_taxas(body: TaxasRequest, ctx: Contexto = Depends(_mudar_taxas)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        servico.gravar_taxas(cur, id_unidade, [i.model_dump() for i in body.itens], ctx.id_usuario)
        auditoria.registrar(cur, ctx.id_usuario, "caixa", "taxas", "configurar_taxas",
                            depois={i.grupo: str(i.taxa_pct) if i.taxa_pct is not None else None
                                    for i in body.itens},
                            id_unidade=id_unidade)
        r = servico.taxas(cur, id_unidade)
    return {**r, "message": "Taxas das formas de pagamento salvas."}
