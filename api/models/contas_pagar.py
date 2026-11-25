"""Contas a pagar — o que entra pelas rotas de `routers/contas_pagar.py` (migração 163)."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# ⚠️ Decimal: é dinheiro (regra 2 do CLAUDE.md).
Valor = Field(gt=0, max_digits=14, decimal_places=2)
Forma = Literal["PIX", "TRANSFERENCIA", "BOLETO", "DINHEIRO", "CARTAO", "OUTRO"]


class _ContaBase(BaseModel):
    id_pessoa: int
    id_categoria: int | None = None
    descricao: str = Field(min_length=1, max_length=200)
    funcao: str | None = Field(default=None, max_length=60)
    competencia: date
    vencimento: date
    valor: Decimal = Valor
    observacao: str | None = Field(default=None, max_length=300)


class ContaCreate(_ContaBase):
    # 🔑 Parcelar (etapa 3, migração 167): com 2 ou mais, `valor` é o TOTAL da compra, rateado em
    # centavos, e o `vencimento` é o da primeira parcela; as outras, um mês depois cada.
    parcelas: int = Field(default=1, ge=1, le=60)


class ContaUpdate(_ContaBase):
    pass


class ContaFixaRequest(BaseModel):
    """A conta fixa (migração 167): o molde que gera a conta de cada mês."""

    id_pessoa: int
    id_categoria: int | None = None
    descricao: str = Field(min_length=1, max_length=180)
    valor: Decimal = Valor
    valor_variavel: bool = False
    dia_vencimento: int = Field(ge=1, le=31)
    # Qualquer dia do mês serve: vale o mês (a API guarda o dia 1º).
    inicio: date
    fim: date | None = None
    antecedencia_dias: int = Field(default=10, ge=0, le=60)
    agendar: bool = False
    forma: Forma | None = None
    observacao: str | None = Field(default=None, max_length=300)


class EncerrarFixaRequest(BaseModel):
    # Cancela também as já geradas que vencem de hoje em diante e estão em aberto.
    cancelar_abertas: bool = False


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
