"""Ordem de compra — o que entra pelas rotas de `routers/ordens_compra.py`."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# ⚠️ Decimal e não float: quantidade é `numeric` (regra 2 do CLAUDE.md).
Quantidade = Field(gt=0, max_digits=18, decimal_places=4)

# Para quando o item precisa chegar (migração 159).
Urgencia = Literal["PODE_ESPERAR", "SEMANA", "HOJE"]


class OrdemItemCreate(BaseModel):
    """Um item pedido: do cadastro OU em texto livre, nunca os dois."""

    id_produto: int | None = None
    descricao_livre: str | None = Field(default=None, max_length=160)
    quantidade: Decimal = Quantidade
    um: str = Field(min_length=1, max_length=6)
    observacao: str | None = Field(default=None, max_length=300)
    urgencia: Urgencia = "SEMANA"
    # Já havia um pedido aberto do mesmo item e a pessoa escolheu somar nele.
    somar_em: int | None = None

    @model_validator(mode="after")
    def _um_ou_outro(self) -> "OrdemItemCreate":
        livre = (self.descricao_livre or "").strip()
        if bool(self.id_produto) == bool(livre):
            raise ValueError("Escolha um produto do cadastro ou escreva o item, um dos dois.")
        return self


class OrdemLoteRequest(BaseModel):
    """As sugestões marcadas, de uma vez."""

    itens: list[OrdemItemCreate] = Field(min_length=1, max_length=200)


class OrdemItemUpdate(BaseModel):
    quantidade: Decimal = Quantidade
    um: str = Field(min_length=1, max_length=6)
    observacao: str | None = Field(default=None, max_length=300)
    # Nula = não mexi: quem chamava antes da migração 159 não perde a urgência ao corrigir.
    urgencia: Urgencia | None = None


class OrdemCompraLinha(BaseModel):
    id: int
    # Vazia = comprou tudo o que foi pedido.
    quantidade: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)


class OrdemComprarRequest(BaseModel):
    itens: list[OrdemCompraLinha] = Field(min_length=1, max_length=200)
    id_fornecedor: int | None = None


class OrdemVoltarRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


class OrdemAprovarRequest(BaseModel):
    """Os pedidos aguardando que quem aprova marcou (migração 165)."""

    ids: list[int] = Field(min_length=1, max_length=200)


class OrdemRecusarRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)
    # Opcional, mas é o que quem pediu lê na aba Recusados.
    motivo: str | None = Field(default=None, max_length=300)
