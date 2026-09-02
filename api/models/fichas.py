"""Modelos da ficha técnica."""

from datetime import date, datetime

from pydantic import BaseModel, Field

STATUS = ("RASCUNHO", "HOMOLOGADA", "ARQUIVADA")


class ItemFicha(BaseModel):
    id_insumo: int | None = None
    id_subficha: int | None = None
    qtd_bruta: float = Field(gt=0)
    qtd_liquida: float | None = Field(default=None, ge=0)
    um: str | None = Field(default=None, max_length=6)
    fator_correcao: float = Field(default=1, gt=0)
    fator_coccao: float = Field(default=1, gt=0)
    observacao: str | None = None
    ordem: int = 0


class FichaCreate(BaseModel):
    id_produto: int
    rendimento_qtd: float = Field(default=1, gt=0)
    rendimento_um: str | None = Field(default=None, max_length=6)
    porcoes: float = Field(default=1, gt=0)
    tempo_preparo_min: int | None = Field(default=None, ge=0, le=6000)
    modo_preparo: str | None = None
    alergenos: str | None = None
    observacao: str | None = None
    itens: list[ItemFicha] = []


class FichaUpdate(BaseModel):
    rendimento_qtd: float | None = Field(default=None, gt=0)
    rendimento_um: str | None = None
    porcoes: float | None = Field(default=None, gt=0)
    tempo_preparo_min: int | None = Field(default=None, ge=0, le=6000)
    modo_preparo: str | None = None
    alergenos: str | None = None
    observacao: str | None = None
    itens: list[ItemFicha] | None = None


class FichaResumo(BaseModel):
    id: int
    id_produto: int
    produto: str
    codigo: str
    versao: int
    status: str
    rendimento_qtd: float
    rendimento_um: str | None = None
    porcoes: float
    itens: int = 0
    atualizada_em: datetime | None = None
    # A foto do prato pronto. Na LISTA ela vale como miniatura: um cardápio de
    # 464 pratos se percorre pelo olho, não lendo 464 nomes.
    foto_url: str | None = None
    # Só vem para quem tem `fichas.custos`.
    custo_total: float | None = None
    custo_por_porcao: float | None = None
    custo_completo: bool | None = None


class FichaResponse(BaseModel):
    id: int
    id_produto: int
    produto: str
    codigo: str
    versao: int
    status: str
    rendimento_qtd: float
    rendimento_um: str | None = None
    porcoes: float
    tempo_preparo_min: int | None = None
    modo_preparo: str | None = None
    alergenos: str | None = None
    observacao: str | None = None
    vigente_de: date | None = None
    vigente_ate: date | None = None
    homologada_em: datetime | None = None
    homologada_por: str | None = None
    criado_em: datetime | None = None
    # 🔑 **A coluna existe desde a etapa 3 e nunca tinha sido usada.** A ficha é
    # seguida por quem está de pé na cozinha, e "está pronto?" é uma pergunta
    # visual — nenhuma descrição de montagem responde o que uma foto responde.
    foto_url: str | None = None
    itens: list[dict] = []
    # Bloco de dinheiro — ausente para quem não tem `fichas.custos`.
    custo_total: float | None = None
    custo_por_porcao: float | None = None
    custo_por_unidade_rendimento: float | None = None
    itens_sem_custo: int | None = None
    custo_completo: bool | None = None
    ve_custo: bool = False
