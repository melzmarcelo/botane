"""Os erros que o sistema guardou (migração 112) — para ler sem o log da nuvem."""

from fastapi import APIRouter, Depends, Query

from database import get_cursor
from seguranca import requer_permissao
from services import erros

# ⚠️ A mesma chave do histórico de alterações, e não uma nova: quem investiga o
# que mudou é quem investiga o que quebrou, e uma chave a mais seria um papel a
# mais para alguém lembrar de marcar no dia em que precisar.
router = APIRouter(
    prefix="/erros",
    tags=["auditoria"],
    dependencies=[Depends(requer_permissao("admin.auditoria"))],
)


@router.get("")
def listar(limite: int = Query(50, ge=1, le=500), origem: str | None = None) -> list[dict]:
    with get_cursor() as cur:
        return erros.listar(cur, limite=limite, origem=origem)
