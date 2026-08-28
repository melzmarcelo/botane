"""Modelos dos ajustes em lote."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class LinhaAjusteCusto(BaseModel):
    id_produto: int
    # ⚠️ O custo CERTO, não a diferença. Quem confere olha a etiqueta e digita o
    # valor que deveria estar lá; pedir a diferença obrigaria a fazer a conta de
    # cabeça, que é exatamente onde o erro entra.
    custo_novo: float = Field(ge=0)
    id_local: int | None = None
    observacao: str | None = None


class AjusteCustoRequest(BaseModel):
    linhas: list[LinhaAjusteCusto] = Field(min_length=1, max_length=200)
    observacao: str | None = None
    documento: str | None = Field(default=None, max_length=60)


class PreviaCustoRequest(BaseModel):
    linhas: list[LinhaAjusteCusto] = Field(min_length=1, max_length=200)
