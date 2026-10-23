"""Modelos das contas a receber do consumo (lotes de cobrança)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

FormaPagamento = Literal["PIX", "DINHEIRO", "CARTAO", "TRANSFERENCIA", "FOLHA", "PERMUTA",
                         "OUTRO"]


class LotesGerar(BaseModel):
    """Gerar lotes: um por pessoa, com o que está em aberto até `ate`.

    ⚠️ Sem `ids_pessoa`, são todas as pessoas com algo em aberto no recorte.
    `ids_venda` escolhe documentos a dedo e só vale com UMA pessoa.
    """

    ate: date
    de: date | None = None
    ids_pessoa: list[int] | None = Field(default=None, max_length=500)
    ids_venda: list[int] | None = Field(default=None, max_length=2000)
    observacao: str | None = Field(default=None, max_length=500)


class LoteReceber(BaseModel):
    """A baixa do lote inteiro (decisão do dono: não há baixa parcial)."""

    recebido_em: date
    forma_pagamento: FormaPagamento
    observacao: str | None = Field(default=None, max_length=500)
