"""Modelos dos pedidos pelo catálogo do site (migração 101)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Modo = Literal["RETIRADA", "ENTREGA"]
Pagamento = Literal["RETIRADA", "ENTREGA", "WHATSAPP"]


class ConfigPedidos(BaseModel):
    """O cartão "Pedidos pelo site" de um catálogo do tipo Produtos."""
    aceita: bool = False
    retirada: bool = True
    entrega: bool = False
    taxa_entrega: float = Field(default=0, ge=0, le=9999)
    pedido_minimo: float = Field(default=0, ge=0, le=99999)
    antecedencia_min: int = Field(default=30, ge=0, le=10080)
    antecedencia_max_dias: int = Field(default=7, ge=0, le=60)
    pagamentos: list[Pagamento] = Field(default_factory=lambda: ["RETIRADA"])
    texto_pagamento: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _coerente(self):
        if self.aceita and not (self.retirada or self.entrega):
            raise ValueError("Marque retirada, entrega ou os dois.")
        if self.aceita and not self.pagamentos:
            raise ValueError("Marque ao menos uma forma de pagamento.")
        self.pagamentos = sorted(set(self.pagamentos))
        return self


class ItemDoCarrinho(BaseModel):
    # O ITEM do catálogo (catalogo_itens.id) — o produto e o preço o servidor descobre.
    id_item: int
    quantidade: float = Field(gt=0, le=999)
    observacao: str | None = Field(default=None, max_length=200)


class PedidoDoSite(BaseModel):
    """O carrinho enviado. ⚠️ Nenhum preço vem daqui: quem calcula é o servidor."""
    telefone: str = Field(max_length=30)
    nome: str | None = Field(default=None, max_length=120)
    chave: str = Field(min_length=8, max_length=60)
    modo: Modo
    endereco: str | None = Field(default=None, max_length=300)
    # Nulo = "o quanto antes" (agora + antecedência mínima).
    para_quando: datetime | None = None
    forma_pagamento: Pagamento
    observacao: str | None = Field(default=None, max_length=500)
    itens: list[ItemDoCarrinho] = Field(min_length=1, max_length=60)

    @field_validator("endereco", "observacao", "nome")
    @classmethod
    def _limpo(cls, v):
        return (v or "").strip() or None


class PedidoDoCliente(BaseModel):
    """ "Meus pedidos" e o cancelar pelo site: telefone (e nome, se vier) no corpo."""
    telefone: str = Field(max_length=30)
    nome: str | None = Field(default=None, max_length=120)


class ItemTrocado(BaseModel):
    """Na confirmação, a casa manda a lista como ficou: o id do item do CATÁLOGO para item
    novo, ou o do produto que já estava no pedido."""
    id_produto: int | None = None
    id_item_catalogo: int | None = None
    quantidade: float = Field(gt=0, le=999)
    observacao: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _um_dos_dois(self):
        if not (self.id_produto or self.id_item_catalogo):
            raise ValueError("Diga o produto do item.")
        return self


class Confirmacao(BaseModel):
    # Vazio = confirma como o cliente pediu.
    itens: list[ItemTrocado] | None = Field(default=None, max_length=60)
    observacao: str | None = Field(default=None, max_length=300)


class Motivo(BaseModel):
    motivo: str = Field(min_length=3, max_length=300)


class LancadoNoPdv(BaseModel):
    cupom: str | None = Field(default=None, max_length=40)


class PagamentoFeito(BaseModel):
    como: Literal["DINHEIRO", "CARTAO", "PIX", "OUTRO"]
