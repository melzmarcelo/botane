"""Modelos de entrada e saída do módulo de acesso. Nada de `body: dict`."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from config import SENHA_MINIMA


# ---------------------------------------------------------------- login


class LoginRequest(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1)
    # ⚠️ O padrão é **não** manter conectado: a escolha segura é a que vale para
    # quem não escolheu nada, e um cliente antigo que não mande o campo recebe
    # a sessão curta em vez da de 30 dias.
    manter_conectado: bool = False


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
    # ⚠️ Dica de INTERFACE, não permissão. A marca "integrado com PDV" no
    # cadastro de produto, setor e categoria só faz sentido com o envio ligado —
    # e quem cadastra produto não tem `integracao.pdv` para perguntar ao
    # `/pdv/config`. Vem por aqui porque `/auth/me` é o que toda tela já
    # carrega uma vez, e assim o campo não custa uma requisição por tela.
    enviar_ao_pdv: bool = False


class TrocarSenhaRequest(BaseModel):
    senha_atual: str
    senha_nova: str = Field(min_length=SENHA_MINIMA)


class EsqueciSenhaRequest(BaseModel):
    email: str = Field(min_length=3, max_length=160)


class RedefinirSenhaRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    senha: str = Field(min_length=SENHA_MINIMA)


# ---------------------------------------------------------------- usuários


class PapelVinculo(BaseModel):
    id_papel: int
    id_unidade: int | None = None


class UsuarioCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr
    senha: str = Field(min_length=SENHA_MINIMA)
    telefone: str | None = None
    ativo: bool = True
    papeis: list[PapelVinculo] = []


class UsuarioUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    telefone: str | None = None
    ativo: bool | None = None
    senha: str | None = Field(default=None, min_length=SENHA_MINIMA)
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
