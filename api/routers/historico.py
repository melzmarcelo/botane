"""Consulta da auditoria."""

from fastapi import APIRouter, Depends, Query, Response

import auditoria
from seguranca import requer_permissao

router = APIRouter(
    prefix="/auditoria",
    tags=["auditoria"],
    dependencies=[Depends(requer_permissao("admin.auditoria"))],
)


@router.get("")
def listar(
    limite: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    entidade: str | None = None,
    resposta: Response = None,
) -> list[dict]:
    return auditoria.listar(limite=limite, offset=offset, entidade=entidade,
                            resposta=resposta)
