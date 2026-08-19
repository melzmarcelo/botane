"""Modelos do estoque."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class SaldoResponse(BaseModel):
    id_produto: int
    codigo: str
    produto: str
    um_estoque: str | None = None
    id_local: int
    local: str
    quantidade: float
    custo_medio: float
    valor: float
    estoque_minimo: float | None = None
    abaixo_do_minimo: bool = False
    atualizado_em: datetime | None = None


class MovimentoResponse(BaseModel):
    id: int
    data_movimento: datetime
    tipo: str
    rotulo: str
    id_produto: int
    produto: str
    codigo: str
    local: str
    quantidade: float
    custo_unitario: float
    custo_total: float
    saldo_apos: float
    custo_medio_apos: float
    custo_provisorio: bool
    documento: str | None = None
    motivo: str | None = None
    observacao: str | None = None
    usuario: str | None = None
    estornado: bool = False
    id_estorno_de: int | None = None


class EntradaRequest(BaseModel):
    id_produto: int
    quantidade: float = Field(gt=0)
    custo_unitario: float = Field(ge=0)
    id_local: int | None = None
    data_movimento: datetime | None = None
    documento: str | None = Field(default=None, max_length=60)
    observacao: str | None = None
    lote: str | None = Field(default=None, max_length=40)
    validade: date | None = None


class SaidaRequest(BaseModel):
    id_produto: int
    quantidade: float = Field(gt=0)
    tipo: str = "SAIDA_CONSUMO_INTERNO"   # ou SAIDA_PERDA, SAIDA_VENDA
    id_local: int | None = None
    id_motivo_perda: int | None = None
    data_movimento: datetime | None = None
    observacao: str | None = None
    lote: str | None = None
    validade: date | None = None


class TransferenciaRequest(BaseModel):
    id_produto: int
    quantidade: float = Field(gt=0)
    id_local_origem: int
    id_local_destino: int
    observacao: str | None = None


class EstornoRequest(BaseModel):
    motivo: str | None = None


class ProducaoRequest(BaseModel):
    id_produto: int
    quantidade: float = Field(gt=0)
    id_local: int | None = None
    observacao: str | None = None


class InventarioCreate(BaseModel):
    id_local: int
    data: date | None = None
    observacao: str | None = None
    # Vazio = puxa tudo o que tem saldo ou movimento no local.
    produtos: list[int] = []


class ContagemItem(BaseModel):
    id_produto: int
    qtd_contada: float | None = Field(default=None, ge=0)
    observacao: str | None = None


class ContagemRequest(BaseModel):
    itens: list[ContagemItem]


class InventarioResponse(BaseModel):
    id: int
    id_local: int
    local: str
    data: date
    status: str
    observacao: str | None = None
    criado_em: datetime | None = None
    fechado_em: datetime | None = None
    itens: list[dict] = []
    contados: int = 0
    total_itens: int = 0
    diferenca_valor: float | None = None
