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
    # De que parte da casa a pessoa cuida. ⚠️ **Lista vazia = TODOS**, e
    # `todos_setores` diz isso sem a tela ter de deduzir do tamanho da lista —
    # que é onde front e servidor passariam a discordar.
    setores: list[dict] = []
    todos_setores: bool = True
    # ⚠️ Dica de INTERFACE, não permissão. A marca "integrado com PDV" no
    # cadastro de produto, setor e categoria só faz sentido com o envio ligado —
    # e quem cadastra produto não tem `integracao.pdv` para perguntar ao
    # `/pdv/config`. Vem por aqui porque `/auth/me` é o que toda tela já
    # carrega uma vez, e assim o campo não custa uma requisição por tela.
    enviar_ao_pdv: bool = False


class PerfilUpdate(BaseModel):
    """O que a pessoa muda no PRÓPRIO cadastro.

    ⚠️ **O e-mail fica de fora, e não é esquecimento.** Ele é a identidade de
    quem entra: trocá-lo aqui derrubaria o login da própria pessoa no instante
    seguinte, e ainda esbarraria na unicidade sem que ela entendesse por quê.
    Quem muda e-mail de alguém é o administrador, na tela de Usuários.
    ⚠️ Papel e loja também ficam de fora — quem se dá permissão não tem
    permissão nenhuma.
    """

    nome: str = Field(min_length=2, max_length=120)
    telefone: str | None = Field(default=None, max_length=30)


class TrocarSenhaRequest(BaseModel):
    senha_atual: str
    senha_nova: str = Field(min_length=SENHA_MINIMA)


class EsqueciSenhaRequest(BaseModel):
    email: str = Field(min_length=3, max_length=160)


class RedefinirSenhaRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    senha: str = Field(min_length=SENHA_MINIMA)


# ---------------------------------------------------------------- usuários


class PessoaMinima(BaseModel):
    """O mínimo para a pessoa existir, criada de dentro do cadastro do usuário.

    ⚠️ **Nome e e-mail, e mais nada.** Quem está cadastrando um usuário não está
    cadastrando um fornecedor: pedir CNPJ, prazo de entrega e pedido mínimo ali
    seria um formulário inteiro no meio de outro. O resto se completa depois, na
    tela de Pessoas.
    """

    nome: str = Field(min_length=2, max_length=160)
    email: str | None = Field(default=None, max_length=160)


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
    # ⚠️ **Vazio quer dizer TODOS os setores** — a mesma convenção do
    # `id_unidade` nulo. Quem não responde não fica sem nada; fica com tudo.
    setores: list[int] = []
    # 🔑 **Quem esta pessoa É** (04/09/2026, pedido do dono). O usuário é a
    # credencial; a pessoa é o cadastro. Sem o vínculo, o funcionário que compra
    # com desconto e o usuário que abre o sistema são dois registros que ninguém
    # liga — e a política de cupom não teria como achar a pessoa a partir de
    # quem está logado.
    id_pessoa: int | None = None
    # ⚠️ Alternativa a `id_pessoa`, não companheira: criar a pessoa a partir do
    # usuário, com nome e e-mail. Mandar os dois é ambíguo, e o servidor recusa.
    pessoa_nova: "PessoaMinima | None" = None


class UsuarioUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    telefone: str | None = None
    ativo: bool | None = None
    senha: str | None = Field(default=None, min_length=SENHA_MINIMA)
    papeis: list[PapelVinculo] | None = None
    # ⚠️ **Nulo NÃO é lista vazia aqui.** Nulo é "não mexi nos setores" — é o
    # que uma tela que ainda não conhece o campo manda —, e lista vazia é a
    # escolha explícita de "todos". Tratá-los igual faria qualquer PUT antigo
    # apagar em silêncio a restrição que alguém acabou de configurar.
    setores: list[int] | None = None
    # ⚠️ Nulo é "não mexi"; zero não existe aqui. Para DESVINCULAR, a tela manda
    # `id_pessoa: 0` — ver o router.
    id_pessoa: int | None = None
    pessoa_nova: PessoaMinima | None = None


class UsuarioResponse(BaseModel):
    id: int
    nome: str
    email: str
    telefone: str | None = None
    ativo: bool
    ultimo_acesso: datetime | None = None
    bloqueado: bool = False
    papeis: list[dict] = []
    setores: list[dict] = []
    id_pessoa: int | None = None
    pessoa: str | None = None


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
