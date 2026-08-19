"""Modelos dos cadastros de apoio: setores, locais, categorias, UM e fornecedores."""

from datetime import date

from pydantic import BaseModel, Field

TIPOS_LOCAL = ("SECO", "RESFRIADO", "CONGELADO", "BAR")
TIPOS_CATEGORIA = ("INSUMO", "REVENDA", "PRODUZIDO", "EMBALAGEM")
GRANDEZAS = ("MASSA", "VOLUME", "UNIDADE")


# ---------------------------------------------------------------- setores


class SetorCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=80)
    cor: str | None = Field(default=None, max_length=9)
    ordem: int = 0
    id_unidade: int | None = None
    ativo: bool = True


class SetorUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=80)
    cor: str | None = None
    ordem: int | None = None
    ativo: bool | None = None


class SetorResponse(BaseModel):
    id: int
    nome: str
    cor: str | None = None
    ordem: int
    id_unidade: int | None = None
    ativo: bool


# ---------------------------------------------------------------- locais


class LocalCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=80)
    tipo: str = "SECO"
    id_unidade: int | None = None
    principal: bool = False
    ativo: bool = True


class LocalUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=80)
    tipo: str | None = None
    principal: bool | None = None
    ativo: bool | None = None


class LocalResponse(BaseModel):
    id: int
    id_unidade: int
    nome: str
    tipo: str
    principal: bool
    ativo: bool


# ---------------------------------------------------------------- categorias


class CategoriaCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=80)
    id_pai: int | None = None
    tipo: str = "INSUMO"
    ordem: int = 0
    ativo: bool = True


class CategoriaUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=80)
    id_pai: int | None = None
    tipo: str | None = None
    ordem: int | None = None
    ativo: bool | None = None


class CategoriaResponse(BaseModel):
    id: int
    id_pai: int | None = None
    nome: str
    caminho: str = ""          # "Insumos › Hortifrúti"
    nivel: int = 0
    tipo: str
    ordem: int
    ativo: bool
    produtos: int = 0


# ---------------------------------------------------------------- unidades de medida


class UnidadeMedidaCreate(BaseModel):
    sigla: str = Field(min_length=1, max_length=6)
    nome: str = Field(min_length=2, max_length=40)
    grandeza: str = "UNIDADE"
    fator_base: float = 1
    ativo: bool = True


class UnidadeMedidaUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=40)
    grandeza: str | None = None
    fator_base: float | None = Field(default=None, gt=0)
    ativo: bool | None = None


class UnidadeMedidaResponse(BaseModel):
    sigla: str
    nome: str
    grandeza: str
    fator_base: float
    ativo: bool


# ---------------------------------------------------------------- fornecedores


class FornecedorCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=160)
    nome_fantasia: str | None = None
    cnpj: str | None = Field(default=None, max_length=18)
    email: str | None = None
    telefone: str | None = None
    whatsapp: str | None = None
    contato: str | None = None
    cidade: str | None = None
    uf: str | None = Field(default=None, max_length=2)
    prazo_entrega_dias: int | None = Field(default=None, ge=0, le=365)
    dias_entrega: str | None = None
    pedido_minimo: float | None = Field(default=None, ge=0)
    observacao: str | None = None
    codigo_omie: str | None = None
    ativo: bool = True


class FornecedorUpdate(FornecedorCreate):
    nome: str | None = Field(default=None, min_length=2, max_length=160)


class FornecedorResponse(FornecedorCreate):
    id: int
    produtos: int = 0
    ultima_compra: date | None = None
