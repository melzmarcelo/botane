"""Contas a pagar — o que entra pelas rotas de `routers/contas_pagar.py` (migração 163)."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# ⚠️ Decimal: é dinheiro (regra 2 do CLAUDE.md).
Valor = Field(gt=0, max_digits=14, decimal_places=2)
Forma = Literal["PIX", "TRANSFERENCIA", "BOLETO", "DINHEIRO", "CARTAO", "OUTRO"]


class ContaCreate(BaseModel):
    id_pessoa: int
    id_categoria: int | None = None
    descricao: str = Field(min_length=1, max_length=200)
    funcao: str | None = Field(default=None, max_length=60)
    competencia: date
    vencimento: date
    valor: Decimal = Valor
    observacao: str | None = Field(default=None, max_length=300)


class ContaUpdate(ContaCreate):
    pass


class ItemEquipe(BaseModel):
    id_pessoa: int
    valor: Decimal = Valor
    funcao: str | None = Field(default=None, max_length=60)
    observacao: str | None = Field(default=None, max_length=300)


class EquipeRequest(BaseModel):
    """A equipe do dia: uma conta por pessoa, de uma vez."""

    data: date
    vencimento: date
    id_categoria: int | None = None
    descricao: str = Field(default="Diária", min_length=1, max_length=200)
    itens: list[ItemEquipe] = Field(min_length=1, max_length=60)


class AgendarRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)
    data: date
    forma: Forma
    baixa_automatica: bool = True


class PagarRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)
    pago_em: date
    forma: Forma
    # Só com UMA conta: juros, desconto. Com várias, cada uma é paga pelo valor dela.
    valor_pago: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)


class IdsRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


class CategoriaRequest(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    ativo: bool = True
