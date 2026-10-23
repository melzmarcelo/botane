"""Contas a receber do consumo — o que está em aberto, os lotes de cobrança e a baixa.

🔑 **Pedido do dono (22/10/2026):** substitui o período de consumo. O consumo se
lança em qualquer data; num dia escolhido a casa gera o LOTE de cada pessoa com o
que ela tem em aberto, manda o relatório (baixado aqui e enviado por fora) e,
quando recebe, dá baixa no lote inteiro. Regras em `services/receber.py`.

⚠️ **As chaves são as do antigo período, de propósito**: quem abria e fechava
período é quem gera lote e dá baixa (`consumo.periodos`), e quem só via vê
(`cmv.relatorios`). `cmv.painel` NÃO abre: aqui está o que cada PESSOA deve, e a
chave do painel é a mais larga da casa.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

import auditoria
from database import get_cursor
from models.consumo import LoteReceber, LotesGerar
from seguranca import Contexto, requer_permissao, unidade_atual
from services import consumo_pessoa
from services import receber as motor

router = APIRouter(prefix="/receber", tags=["contas a receber"])

_ver = requer_permissao("consumo.periodos", "cmv.relatorios")
_gerir = requer_permissao("consumo.periodos")


def _falhou(r: dict) -> None:
    if "erro" in r:
        raise HTTPException(status_code=r.get("status", 409), detail=r["erro"])


def _somas(linhas: list[dict]) -> dict:
    return {
        "total": round(sum(float(l["total"] or 0) for l in linhas), 2),
        "total_cheio": round(sum(float(l["total_cheio"] or 0) for l in linhas), 2),
        "desconto": round(sum(float(l["desconto"] or 0) for l in linhas), 2),
    }


@router.get("/em-aberto")
def em_aberto(de: date | None = None, ate: date | None = None,
              id_pessoa: int | None = None, ctx: Contexto = Depends(_ver)) -> dict:
    """O que cada pessoa deve e ainda não foi cobrado — com o recorte de datas.

    🔑 É o "relatório dos valores em aberto num determinado período" do pedido. A
    coluna "em cobrança" vem junto: quem olha a dívida de alguém quer saber também
    o que já foi mandado a ele e ainda não voltou.
    """
    if de and ate and ate < de:
        raise HTTPException(status_code=400, detail="A data final é anterior à inicial.")
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        linhas = motor.em_aberto(cur, id_unidade, de, ate, [id_pessoa] if id_pessoa else None)
        cobranca = motor.em_cobranca_por_pessoa(cur, id_unidade)
        for l in linhas:
            c = cobranca.get(l["id_pessoa"]) or {}
            l["em_cobranca"] = float(c.get("total") or 0)
            l["lotes_em_cobranca"] = c.get("lotes") or 0
        return {
            "de": de, "ate": ate,
            "linhas": linhas,
            **_somas(linhas),
            "em_cobranca": round(sum(float(c["total"] or 0) for c in cobranca.values()), 2),
            "lotes_em_cobranca": sum(c["lotes"] for c in cobranca.values()),
            "formas": motor.FORMAS,
        }


@router.get("/em-aberto/{id_pessoa}")
def em_aberto_da_pessoa(id_pessoa: int, de: date | None = None, ate: date | None = None,
                        ctx: Contexto = Depends(_ver)) -> dict:
    """Os documentos em aberto de UMA pessoa, com os itens — para escolher o lote.

    ⚠️ A MESMA consulta do relatório (`consumo_pessoa.apurar`): o que a tela
    oferece para o lote é o que o arquivo do lote vai mostrar.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        docs = consumo_pessoa.apurar(cur, id_unidade, {"situacao": "aberto", "de": de, "ate": ate},
                                     [id_pessoa], "documento_itens")
        return {"documentos": docs, **_somas(docs)}


@router.get("/lotes")
def listar_lotes(status: list[str] | None = Query(default=None),
                 id_pessoa: int | None = None,
                 limite: int = Query(default=200, ge=1, le=1000),
                 ctx: Contexto = Depends(_ver)) -> dict:
    """Os lotes, o mais novo primeiro — em cobrança, recebidos e cancelados."""
    validos = [s for s in (status or []) if s in motor.SITUACOES]
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        return {"lotes": motor.lotes(cur, id_unidade, validos or None, id_pessoa, limite),
                "formas": motor.FORMAS}


@router.get("/lotes/{id_lote}")
def detalhe_lote(id_lote: int, ctx: Contexto = Depends(_ver)) -> dict:
    """Um lote: o cabeçalho congelado e os documentos, com os itens."""
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        lote = motor.lote(cur, id_unidade, id_lote)
        if not lote:
            raise HTTPException(status_code=404, detail="Lote não encontrado")
        docs = consumo_pessoa.apurar(cur, id_unidade, {"id_lote": id_lote}, None,
                                     "documento_itens")
        return {"lote": lote, "documentos": docs, "formas": motor.FORMAS}


@router.post("/lotes", status_code=201)
def gerar_lotes(body: LotesGerar, ctx: Contexto = Depends(_gerir)) -> dict:
    """Gera os lotes de cobrança — um por pessoa."""
    if body.de and body.ate < body.de:
        raise HTTPException(status_code=400, detail="A data final é anterior à inicial.")
    if body.ids_venda and len(body.ids_pessoa or []) != 1:
        raise HTTPException(status_code=400,
                            detail="Escolher documentos a dedo só vale para uma pessoa.")
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        criados = motor.gerar(cur, id_unidade, ctx.id_usuario, body.ate, body.ids_pessoa,
                              body.de, body.ids_venda, body.observacao)
        if not criados:
            raise HTTPException(status_code=409,
                                detail="Não há documento em aberto nesse recorte — nenhum "
                                       "lote foi gerado.")
        for c in criados:
            auditoria.registrar(cur, ctx.id_usuario, "consumo_lote", c["id"], "gerar",
                                depois={**c, "ate": str(body.ate),
                                        "de": str(body.de) if body.de else None},
                                id_unidade=id_unidade)
        total = round(sum(c["total"] for c in criados), 2)
        return {
            "lotes": criados,
            "total": total,
            "message": (f"Lote nº {criados[0]['id']} gerado" if len(criados) == 1
                        else f"{len(criados)} lotes gerados")
                       + f" · {sum(c['cupons'] for c in criados)} documento(s), "
                         f"total {total:.2f}",
        }


@router.post("/lotes/{id_lote}/receber")
def receber(id_lote: int, body: LoteReceber, ctx: Contexto = Depends(_gerir)) -> dict:
    """A baixa do lote inteiro."""
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = motor.receber(cur, id_unidade, id_lote, ctx.id_usuario, body.recebido_em,
                          body.forma_pagamento, body.observacao)
        _falhou(r)
        auditoria.registrar(cur, ctx.id_usuario, "consumo_lote", id_lote, "receber",
                            depois={"recebido_em": str(body.recebido_em),
                                    "forma": body.forma_pagamento, "total": r["total"]},
                            id_unidade=id_unidade)
        return {**r, "message": f"Baixa do lote nº {id_lote} · {r['total']:.2f} "
                                f"({motor.FORMAS[body.forma_pagamento]})"}


@router.post("/lotes/{id_lote}/estornar-baixa")
def estornar_baixa(id_lote: int, ctx: Contexto = Depends(_gerir)) -> dict:
    """Desfaz a baixa: o lote volta a estar em cobrança."""
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = motor.estornar_baixa(cur, id_unidade, id_lote)
        _falhou(r)
        auditoria.registrar(cur, ctx.id_usuario, "consumo_lote", id_lote, "estornar_baixa",
                            id_unidade=id_unidade)
        return {**r, "message": f"Baixa estornada — o lote nº {id_lote} voltou para cobrança"}


@router.post("/lotes/{id_lote}/cancelar")
def cancelar(id_lote: int, ctx: Contexto = Depends(_gerir)) -> dict:
    """Desfaz o lote em cobrança: os documentos voltam para em aberto."""
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = motor.cancelar(cur, id_unidade, id_lote, ctx.id_usuario)
        _falhou(r)
        auditoria.registrar(cur, ctx.id_usuario, "consumo_lote", id_lote, "cancelar",
                            depois={"vendas": r["vendas"]}, id_unidade=id_unidade)
        return {**r, "message": f"Lote nº {id_lote} cancelado · {len(r['vendas'])} "
                                "documento(s) voltaram para em aberto"}


@router.delete("/lotes/{id_lote}/documentos/{id_venda}")
def tirar_documento(id_lote: int, id_venda: int, ctx: Contexto = Depends(_gerir)) -> dict:
    """Tira um documento do lote em cobrança — ele volta para em aberto."""
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = motor.tirar_documento(cur, id_unidade, id_lote, id_venda, ctx.id_usuario)
        _falhou(r)
        auditoria.registrar(cur, ctx.id_usuario, "consumo_lote", id_lote, "tirar_documento",
                            depois={"id_venda": id_venda, **r}, id_unidade=id_unidade)
        return {**r, "message": ("Era o último documento — o lote foi cancelado"
                                 if r["cancelado"]
                                 else f"Documento fora do lote · novo total {r['total']:.2f}")}
