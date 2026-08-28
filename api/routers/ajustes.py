"""Ajuste de CUSTO — corrigir o custo médio sem mexer na quantidade.

É a única porta que grava movimento de valor. Quantidade tem porta própria e
mais antiga: `/estoque/entradas`, `/estoque/saidas`, `/estoque/transferencias`.

⚠️ Permissão à parte (`estoque.custo`): mexer na quantidade é dizer que a
prateleira tem outra coisa; mexer no custo é dizer que o dinheiro é outro, e
isso altera o CMV do período sem que nada tenha entrado ou saído.
"""

from fastapi import APIRouter, Depends, Query

import auditoria
from database import get_cursor
from models.ajustes import AjusteCustoRequest, PreviaCustoRequest
from seguranca import Contexto, requer_permissao, unidade_atual
from services import ajustes as servico

router = APIRouter(prefix="/ajustes", tags=["ajustes"])


@router.post("/custo/previa")
def previa_de_custo(
    body: PreviaCustoRequest,
    ctx: Contexto = Depends(requer_permissao("estoque.custo")),
) -> dict:
    """O que o ajuste faria, sem fazer — uma linha por produto.

    Ajuste de custo não tem desfazer barato: entra no razão e só sai por
    estorno. Quem confirma precisa ver a diferença em reais antes.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        linhas = [
            servico.previa_custo(cur, id_unidade, l.id_produto, l.id_local, l.custo_novo)
            for l in body.linhas
        ]
    return {
        "linhas": linhas,
        "diferenca_total": round(sum(l["diferenca"] for l in linhas), 2),
        # O sinal invertido da diferença: é o que acontece com o CMV.
        "efeito_no_cmv": round(sum(l["efeito_no_cmv"] for l in linhas), 2),
    }


@router.post("/custo", status_code=201)
def lote_de_custo(
    body: AjusteCustoRequest,
    ctx: Contexto = Depends(requer_permissao("estoque.custo")),
) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.lancar_custo(
            cur,
            id_unidade=id_unidade,
            linhas=[l.model_dump() for l in body.linhas],
            observacao=body.observacao,
            documento=body.documento,
            id_usuario=ctx.id_usuario,
            pode_retroativo=ctx.pode("estoque.retroativo"),
        )
        # ⚠️ O ANTES e o DEPOIS de cada custo vão para a auditoria. É dinheiro
        # mudando sem mercadoria se mover: sem os dois valores, o registro diria
        # que houve um ajuste e não quanto ele valeu.
        auditoria.registrar(
            cur, ctx.id_usuario, "ajuste_lote", r["id_lote"], "ajuste_custo",
            antes={l["produto"]: l["custo_anterior"] for l in r["linhas"]},
            depois={l["produto"]: l["custo_novo"] for l in r["linhas"]},
            id_unidade=id_unidade,
        )
    return {
        "id_lote": r["id_lote"],
        "lancados": r["lancados"],
        "diferenca_total": r["diferenca_total"],
        "linhas": r["linhas"],
        "message": f"{r['lancados']} custo(s) corrigido(s)",
    }


@router.get("/lotes")
def lotes(
    natureza: str | None = Query(None, pattern="^(ESTOQUE|CUSTO)$"),
    limite: int = Query(50, le=200),
    offset: int = 0,
    ctx: Contexto = Depends(requer_permissao("estoque.saldos")),
) -> list[dict]:
    """O histórico dos lotes — quem lançou, quando, quantas linhas e quanto deu."""
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        return servico.listar_lotes(cur, id_unidade, natureza, limite, offset)
