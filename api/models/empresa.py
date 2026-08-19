"""Modelos da empresa, das lojas e dos parâmetros de operação."""

from datetime import date

from pydantic import BaseModel, Field


class EmpresaUpdate(BaseModel):
    razao_social: str | None = Field(default=None, max_length=160)
    nome_fantasia: str | None = Field(default=None, max_length=160)
    cnpj: str | None = Field(default=None, max_length=18)
    inscricao_estadual: str | None = None
    inscricao_municipal: str | None = None
    cnae_principal: str | None = None
    regime_tributario: str | None = None      # SIMPLES | PRESUMIDO | REAL | MEI
    data_abertura: date | None = None
    telefone: str | None = None
    whatsapp: str | None = None
    email: str | None = None
    site: str | None = None
    instagram: str | None = None
    cep: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = Field(default=None, max_length=2)
    codigo_ibge: str | None = None
    responsavel_nome: str | None = None
    responsavel_cpf: str | None = None
    responsavel_email: str | None = None
    contador_nome: str | None = None
    contador_crc: str | None = None
    contador_email: str | None = None
    contador_telefone: str | None = None
    logo_url: str | None = None
    cor_primaria: str | None = Field(default=None, max_length=9)


class EmpresaResponse(EmpresaUpdate):
    id: int


class UnidadeCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    apelido: str | None = Field(default=None, max_length=40)
    cnpj: str | None = None
    inscricao_estadual: str | None = None
    matriz: bool = False
    cep: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = Field(default=None, max_length=2)
    codigo_ibge: str | None = None
    telefone: str | None = None
    email: str | None = None
    timezone: str = "America/Sao_Paulo"
    horario_funcionamento: dict | None = None
    mesas: int | None = None
    ativo: bool = True


class UnidadeUpdate(UnidadeCreate):
    nome: str | None = Field(default=None, min_length=2, max_length=120)


class UnidadeResponse(UnidadeCreate):
    id: int


class ParametrosUpdate(BaseModel):
    dia_fechamento_cmv: int | None = Field(default=None, ge=1, le=28)
    bloquear_retroativo: bool | None = None
    permitir_saldo_negativo: bool | None = None
    exigir_motivo_perda: bool | None = None
    exigir_local_movimento: bool | None = None
    casas_decimais_qtd: int | None = Field(default=None, ge=0, le=6)
    alerta_validade_dias: int | None = Field(default=None, ge=0, le=365)
    bloquear_saida_vencido: bool | None = None
    alerta_variacao_preco_pct: float | None = Field(default=None, ge=0, le=999)
    criar_produto_da_nota: bool | None = None


class ParametrosResponse(ParametrosUpdate):
    id_unidade: int
