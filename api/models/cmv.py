"""Modelos de vendas e CMV."""

from datetime import date

from pydantic import BaseModel, Field


class ItemVenda(BaseModel):
    id_produto: int | None = None
    codigo: str | None = None          # alternativa ao id: o código do produto
    descricao: str | None = None
    quantidade: float = Field(gt=0)
    valor_unitario: float = Field(default=0, ge=0)


class VendaImportar(BaseModel):
    data: date
    documento: str | None = Field(default=None, max_length=40)
    canal: str | None = None
    origem: str = "PLANILHA"
    itens: list[ItemVenda]


class ImportarVendasRequest(BaseModel):
    vendas: list[VendaImportar]


class VendaResponse(BaseModel):
    id: int
    data: date
    origem: str
    canal: str | None = None
    documento: str | None = None
    valor_total: float
    cancelada: bool
    itens: int = 0
    sem_custo: int = 0


class ApuracaoResponse(BaseModel):
    inicio: date
    fim: date
    estoque_inicial: float
    compras: float
    estoque_final: float
    cmv_real: float
    cmv_teorico: float
    variancia: float
    variancia_pct: float | None = None
    perdas: float
    consumo_interno: float
    ajustes: float
    receita: float
    vendas: int
    itens_sem_custo: int
    cobertura_ficha_pct: float
    food_cost_pct: float | None = None
    fechado: bool = False
    # O ritmo em que esta loja fecha, e como o período se chama. Vão na
    # apuração porque é a tela que mostra os dois lado a lado — e uma tela que
    # diz "agosto" enquanto o fechamento congela a semana mente sobre si mesma.
    ciclo: str = "MENSAL"
    rotulo: str | None = None


class FechamentoRequest(BaseModel):
    # ⚠️ Qualquer dia DENTRO do período a fechar. O tamanho do período vem da
    # configuração da loja (`parametros.ciclo_fechamento`), não daqui: mandar o
    # ciclo no pedido deixaria a tela fechar num ritmo e o razão travar noutro.
    competencia: date


class FechamentoResponse(BaseModel):
    id: int
    competencia: date
    inicio: date
    fim: date
    estoque_inicial: float
    compras: float
    estoque_final: float
    cmv_real: float
    cmv_teorico: float
    variancia: float
    perdas: float
    consumo_interno: float
    ajustes: float
    receita: float
    food_cost_pct: float | None = None
    status: str
    ciclo: str = "MENSAL"
    rotulo: str | None = None
    fechado_por: str | None = None
    fechado_em: str | None = None
