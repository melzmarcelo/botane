"""Modelos de entrada e saída do módulo de acesso. Nada de `body: dict`."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------- login


class LoginRequest(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str


class UsuarioResumo(BaseModel):
    id: int
    nome: str
    email: str
    trocar_senha: bool = False


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    expira_em: int
    usuario: UsuarioResumo


class MeResponse(BaseModel):
    id: int
    nome: str
    email: str
    telefone: str | None = None
    foto_url: str | None = None
    trocar_senha: bool
    permissoes: list[str]
    papeis: list[str]
    unidades: list[dict]
    todas_unidades: bool


class TrocarSenhaRequest(BaseModel):
    senha_atual: str
    senha_nova: str = Field(min_length=8)


# ---------------------------------------------------------------- usuários


class PapelVinculo(BaseModel):
    id_papel: int
    id_unidade: int | None = None


class UsuarioCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr
    senha: str = Field(min_length=8)
    telefone: str | None = None
    ativo: bool = True
    papeis: list[PapelVinculo] = []


class UsuarioUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    telefone: str | None = None
    ativo: bool | None = None
    senha: str | None = Field(default=None, min_length=8)
    papeis: list[PapelVinculo] | None = None


class UsuarioResponse(BaseModel):
    id: int
    nome: str
    email: str
    telefone: str | None = None
    ativo: bool
    ultimo_acesso: datetime | None = None
    bloqueado: bool = False
    papeis: list[dict] = []


# ---------------------------------------------------------------- papéis


class PapelCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=80)
    descricao: str | None = None
    permissoes: list[str] = []


class PapelUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=80)
    descricao: str | None = None
    permissoes: list[str] | None = None


class PapelResponse(BaseModel):
    id: int
    nome: str
    descricao: str | None = None
    sistema: bool
    permissoes: list[str] = []
    usuarios: int = 0


class PermissaoResponse(BaseModel):
    chave: str
    modulo: str
    descricao: str
    ordem: int
