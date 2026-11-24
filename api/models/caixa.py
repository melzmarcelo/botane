"""Conferência do caixa e taxa por forma de pagamento (migração 161)."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class ContadoRequest(BaseModel):
    """O dinheiro contado na gaveta num dia."""

    # ⚠️ Decimal: é dinheiro (regra 2 do CLAUDE.md).
    contado: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    observacao: str | None = Field(default=None, max_length=300)


class TaxaForma(BaseModel):
    grupo: Literal["DINHEIRO", "CREDITO", "DEBITO", "PIX", "VALE", "OUTRO"]
    # Nula apaga: "não sei a taxa" é diferente de "a taxa é zero".
    taxa_pct: Decimal | None = Field(default=None, ge=0, lt=100, max_digits=6, decimal_places=3)


class TaxasRequest(BaseModel):
    itens: list[TaxaForma] = Field(min_length=1, max_length=10)
