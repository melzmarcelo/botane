"""Modelos do produto — o cadastro central do sistema."""

from datetime import date, datetime

from pydantic import BaseModel, Field

TIPOS = ("INSUMO", "REVENDA", "PRODUZIDO", "KIT", "EMBALAGEM")
STATUS = ("RASCUNHO", "ATIVO", "ARQUIVADO")


class FornecedorDoProduto(BaseModel):
    id_fornecedor: int
    codigo_no_fornecedor: str | None = None
    embalagem: str | None = None
    fator: float = Field(default=1, gt=0)
    ultimo_preco: float | None = None
    preferencial: bool = False


class ProdutoBase(BaseModel):
    nome: str = Field(min_length=2, max_length=160)
    nome_curto: str | None = Field(default=None, max_length=60)
    tipo: str = "INSUMO"
    id_categoria: int | None = None
    id_setor: int | None = None
    producao_propria: bool = False
    controla_estoque: bool = True
    um_estoque: str | None = Field(default=None, max_length=6)
    um_compra: str | None = Field(default=None, max_length=6)
    fator_compra: float = Field(default=1, gt=0)
    perecivel: bool = False
    validade_dias: int | None = Field(default=None, ge=0, le=3650)
    controla_lote: bool = False
    controla_validade: bool = False
    estoque_minimo: float | None = Field(default=None, ge=0)
    estoque_maximo: float | None = Field(default=None, ge=0)
    ncm: str | None = Field(default=None, max_length=10)
    codigo_barras: str | None = Field(default=None, max_length=20)
    codigo_omie: str | None = Field(default=None, max_length=40)
    observacao: str | None = None


class ProdutoCreate(ProdutoBase):
    # Em branco, o sistema gera um sequencial — ninguém precisa inventar código.
    codigo: str | None = Field(default=None, max_length=40)
    status: str = "ATIVO"
    preco_venda: float | None = Field(default=None, ge=0)
    fornecedores: list[FornecedorDoProduto] = []


class ProdutoUpdate(ProdutoBase):
    nome: str | None = Field(default=None, min_length=2, max_length=160)
    codigo: str | None = Field(default=None, max_length=40)
    tipo: str | None = None
    fator_compra: float | None = Field(default=None, gt=0)
    producao_propria: bool | None = None
    controla_estoque: bool | None = None
    perecivel: bool | None = None
    controla_lote: bool | None = None
    controla_validade: bool | None = None
    status: str | None = None
    ativo: bool | None = None
    preco_venda: float | None = Field(default=None, ge=0)
    fornecedores: list[FornecedorDoProduto] | None = None


class ProdutoResponse(BaseModel):
    id: int
    codigo: str
    nome: str
    nome_curto: str | None = None
    tipo: str
    id_categoria: int | None = None
    categoria: str | None = None
    id_setor: int | None = None
    setor: str | None = None
    producao_propria: bool
    controla_estoque: bool
    um_estoque: str | None = None
    um_compra: str | None = None
    fator_compra: float
    perecivel: bool
    validade_dias: int | None = None
    controla_lote: bool
    controla_validade: bool
    estoque_minimo: float | None = None
    estoque_maximo: float | None = None
    ncm: str | None = None
    codigo_barras: str | None = None
    codigo_omie: str | None = None
    origem: str
    status: str
    observacao: str | None = None
    ativo: bool
    criado_em: datetime | None = None
    preco_venda: float | None = None
    preco_desde: date | None = None
    fornecedores: list[dict] = []


class ProdutoResumo(BaseModel):
    """O que a lista precisa — sem carregar fornecedor e histórico de preço."""

    id: int
    codigo: str
    nome: str
    tipo: str
    categoria: str | None = None
    setor: str | None = None
    um_estoque: str | None = None
    producao_propria: bool
    controla_estoque: bool
    status: str
    ativo: bool
    preco_venda: float | None = None


class ContagemProdutos(BaseModel):
    total: int
    por_tipo: dict[str, int]
    rascunhos: int
    inativos: int
