"""Ordem de compra — pedir, marcar como comprado e voltar à lista.

🔑 **Pedir, aprovar e comprar são três chaves**, e ver os pedidos de todos é uma quarta (166):
sem ela, quem só pede vê os próprios. Toda a equipe avisa o que falta; o pedido de
quem não aprova espera aprovação (migração 165); quem marca é quem compra. Nada aqui toca o
estoque: ver `services/ordens_compra.py`.
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

import auditoria
from database import get_cursor
from models.ordens_compra import (
    OrdemAprovarRequest,
    OrdemComprarRequest,
    OrdemItemCreate,
    OrdemItemUpdate,
    OrdemLoteRequest,
    OrdemRecusarRequest,
    OrdemVoltarRequest,
)
from paginacao import pagina
from seguranca import Contexto, requer_permissao, unidade_atual
from services import ordens_compra as servico

router = APIRouter(prefix="/ordens-compra", tags=["ordem de compra"])

SOLICITAR, COMPRAR = "compras.ordem_solicitar", "compras.ordem_comprar"
APROVAR = "compras.ordem_aprovar"
_ver = requer_permissao(SOLICITAR, COMPRAR, APROVAR)
_aprovar = requer_permissao(APROVAR)
_solicitar = requer_permissao(SOLICITAR)
_comprar = requer_permissao(COMPRAR)


@router.get("")
def listar(resposta: Response,
           status: Literal["AGUARDANDO", "A_COMPRAR", "COMPRADO", "RECUSADO"] = "A_COMPRAR",
           de: date | None = None, ate: date | None = None,
           busca: str | None = Query(None, max_length=80),
           agrupar_fornecedor: bool = False,
           limite: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
           ctx: Contexto = Depends(_ver)) -> list[dict]:
    with get_cursor() as cur:
        sql, params = servico.consulta_da_lista(unidade_atual(cur, ctx), [status], de, ate, busca,
                                                servico.so_de(ctx.pode, ctx.id_usuario),
                                                agrupar_fornecedor)
        return pagina(cur, sql, params, limite=limite, offset=offset, resposta=resposta)


@router.get("/resumo")
def resumo(ctx: Contexto = Depends(_ver)) -> dict:
    with get_cursor() as cur:
        return servico.resumo(cur, unidade_atual(cur, ctx), servico.so_de(ctx.pode, ctx.id_usuario))


@router.get("/produto/{id_produto}")
def opcoes_do_produto(id_produto: int, ctx: Contexto = Depends(_ver)) -> dict:
    with get_cursor() as cur:
        return servico.opcoes_do_produto(cur, unidade_atual(cur, ctx), id_produto,
                                         servico.so_de(ctx.pode, ctx.id_usuario))


@router.get("/sugestoes")
def sugestoes(ctx: Contexto = Depends(_ver)) -> list[dict]:
    """O que está abaixo do mínimo e se compra, já na unidade de pedir (etapa 2)."""
    with get_cursor() as cur:
        return servico.sugestoes(cur, unidade_atual(cur, ctx))


@router.post("/lote", status_code=201)
def adicionar_lote(body: OrdemLoteRequest, ctx: Contexto = Depends(_solicitar)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.adicionar_lote(cur, id_unidade, ctx.id_usuario,
                                   [i.model_dump() for i in body.itens], ctx.pode(APROVAR))
        for item, pedido in zip(r.pop("itens"), body.itens):
            auditoria.registrar(
                cur, ctx.id_usuario, "ordem_compra", item["id"],
                "somar" if item["somado"] else "pedir",
                depois={"item": item["item"], "quantidade": str(pedido.quantidade),
                        "um": pedido.um, "origem": "sugestao", "status": item["status"]},
                id_unidade=id_unidade)
    return r


@router.post("", status_code=201)
def adicionar(body: OrdemItemCreate, ctx: Contexto = Depends(_solicitar)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.adicionar(cur, id_unidade, ctx.id_usuario, body.model_dump(),
                             ctx.pode(APROVAR))
        auditoria.registrar(
            cur, ctx.id_usuario, "ordem_compra", r["id"], "somar" if r["somado"] else "pedir",
            depois={"item": r["item"], "quantidade": str(body.quantidade), "um": body.um,
                    "status": r["status"]},
            id_unidade=id_unidade)
    return r


@router.post("/comprar", status_code=201)
def comprar(body: OrdemComprarRequest, ctx: Contexto = Depends(_comprar)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.comprar(cur, id_unidade, ctx.id_usuario,
                            [i.model_dump() for i in body.itens], body.id_fornecedor)
        for id_item in r["ids"]:
            auditoria.registrar(cur, ctx.id_usuario, "ordem_compra", id_item, "comprar",
                                depois={"id_fornecedor": body.id_fornecedor},
                                id_unidade=id_unidade)
    return r


@router.post("/voltar", status_code=201)
def voltar(body: OrdemVoltarRequest, ctx: Contexto = Depends(_comprar)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.voltar(cur, id_unidade, body.ids)
        for id_item in r["ids"]:
            auditoria.registrar(cur, ctx.id_usuario, "ordem_compra", id_item, "voltar",
                                id_unidade=id_unidade)
    return r


@router.post("/aprovar", status_code=201)
def aprovar(body: OrdemAprovarRequest, ctx: Contexto = Depends(_aprovar)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.aprovar(cur, id_unidade, ctx.id_usuario, body.ids)
        for id_item in r["ids"]:
            auditoria.registrar(cur, ctx.id_usuario, "ordem_compra", id_item, "aprovar",
                                id_unidade=id_unidade)
    return r


@router.post("/recusar", status_code=201)
def recusar(body: OrdemRecusarRequest, ctx: Contexto = Depends(_aprovar)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.recusar(cur, id_unidade, ctx.id_usuario, body.ids, body.motivo)
        for id_item in r["ids"]:
            auditoria.registrar(cur, ctx.id_usuario, "ordem_compra", id_item, "recusar",
                                depois={"motivo": body.motivo}, id_unidade=id_unidade)
    return r


@router.put("/{id_item}")
def corrigir(id_item: int, body: OrdemItemUpdate, ctx: Contexto = Depends(_ver)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.corrigir(cur, id_unidade, id_item, ctx.id_usuario, ctx.pode(COMPRAR),
                             body.model_dump(), ctx.pode(APROVAR))
        antes = r.pop("antes")
        auditoria.registrar(
            cur, ctx.id_usuario, "ordem_compra", id_item, "corrigir",
            antes={**antes, "quantidade": str(antes["quantidade"])},
            depois={"quantidade": str(body.quantidade), "um": body.um,
                    "observacao": body.observacao, "urgencia": body.urgencia},
            id_unidade=id_unidade)
    return r


@router.post("/{id_item}/cancelar", status_code=201)
def cancelar(id_item: int, ctx: Contexto = Depends(_ver)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.cancelar(cur, id_unidade, id_item, ctx.id_usuario, ctx.pode(COMPRAR),
                             ctx.pode(APROVAR))
        auditoria.registrar(cur, ctx.id_usuario, "ordem_compra", id_item, "cancelar",
                            depois={"item": r["item"]}, id_unidade=id_unidade)
    return r
