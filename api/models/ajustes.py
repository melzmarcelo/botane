"""Modelos dos ajustes em lote."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class LinhaAjusteEstoque(BaseModel):
    id_produto: int
    # Os mesmos tipos que a tela de Ajustes já oferece. A validação de verdade
    # é do razão (`estoque.TIPOS`); aqui só se recusa o que nem faz sentido
    # pedir por esta porta.
    tipo: str = Field(pattern="^(ENTRADA_MANUAL|SAIDA_CONSUMO_INTERNO|SAIDA_PERDA"
                              "|ENTRADA_DEVOLUCAO)$")
    quantidade: float = Field(gt=0)
    id_local: int | None = None
    custo_unitario: float | None = None
    id_motivo_perda: int | None = None
    lote: str | None = None
    validade: date | None = None
    observacao: str | None = None


class AjusteEstoqueRequest(BaseModel):
    linhas: list[LinhaAjusteEstoque] = Field(min_length=1, max_length=200)
    observacao: str | None = None
    documento: str | None = Field(default=None, max_length=60)
    data_movimento: datetime | None = None


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
