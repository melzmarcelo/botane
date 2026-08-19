"""O que precisa de atenção, e as listas por trás de cada alerta."""

from fastapi import APIRouter, Depends, HTTPException, Query

from database import get_cursor
from seguranca import Contexto, contexto_atual
from services import alertas as motor

router = APIRouter(prefix="/alertas", tags=["alertas"])


def _unidade(cur, ctx: Contexto) -> int:
    if ctx.unidades:
        return sorted(ctx.unidades)[0]
    cur.execute("SELECT id FROM unidades WHERE ativo ORDER BY matriz DESC, id LIMIT 1")
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=400, detail="Nenhuma loja cadastrada")
    return linha["id"]


# Cada alerta só aparece para quem pode fazer algo a respeito.
CHAVES = {
    "estoque.negativo": "estoque.saldos",
    "estoque.minimo": "estoque.saldos",
    "estoque.vencido": "estoque.saldos",
    "estoque.vencendo": "estoque.saldos",
    "estoque.provisorio": "estoque.saldos",
    "compras.pendencias": "compras.notas",
    "compras.nao_lancadas": "compras.notas",
    "cadastro.rascunho": "cadastros.produtos",
    "fichas.faltando": "fichas.visualizar",
    "cmv.sem_vinculo": "cmv.painel",
    "cmv.mes_aberto": "cmv.painel",
}


@router.get("")
def listar(ctx: Contexto = Depends(contexto_atual)) -> list[dict]:
    with get_cursor() as cur:
        todos = motor.levantar(cur, _unidade(cur, ctx))
    return [a for a in todos if ctx.pode(CHAVES.get(a["chave"], "estoque.saldos"))]


@router.get("/vencimentos")
def vencimentos(dias: int | None = Query(default=None, ge=0, le=365),
                ctx: Contexto = Depends(contexto_atual)) -> list[dict]:
    if not ctx.pode("estoque.saldos"):
        raise HTTPException(status_code=403, detail="Sem permissão para esta ação")
    with get_cursor() as cur:
        return motor.vencimentos(cur, _unidade(cur, ctx), dias)


@router.get("/abaixo-do-minimo")
def abaixo_do_minimo(ctx: Contexto = Depends(contexto_atual)) -> list[dict]:
    if not ctx.pode("estoque.saldos"):
        raise HTTPException(status_code=403, detail="Sem permissão para esta ação")
    with get_cursor() as cur:
        return motor.abaixo_do_minimo(cur, _unidade(cur, ctx))
