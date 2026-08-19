"""Senha, token e a dependência `requer_permissao`.

Regra da casa: **toda rota declara a permissão que exige**. A tela esconder o
botão é conforto, não segurança.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Iterable

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request

from config import JWT_EXPIRY_MIN, JWT_SECRET, REFRESH_EXPIRY_DIAS
from database import get_cursor

# ---------------------------------------------------------------- senha


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha: str, hash_salvo: str | None) -> bool:
    if not hash_salvo:
        return False
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), hash_salvo.encode("utf-8"))
    except ValueError:
        return False


# ---------------------------------------------------------------- token


def criar_access_token(id_usuario: int, email: str) -> tuple[str, int]:
    expira = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRY_MIN)
    payload = {"sub": str(id_usuario), "email": email, "exp": expira}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256"), JWT_EXPIRY_MIN * 60


def gerar_refresh() -> tuple[str, str, datetime]:
    """Devolve (valor em claro, hash guardado, validade).

    O banco guarda só o hash: vazamento da tabela não vira sessão de ninguém.
    """
    valor = secrets.token_urlsafe(48)
    return (
        valor,
        hashlib.sha256(valor.encode()).hexdigest(),
        datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRY_DIAS),
    )


def hash_refresh(valor: str) -> str:
    return hashlib.sha256(valor.encode()).hexdigest()


def decodificar_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sessão expirada, entre de novo")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")


# ---------------------------------------------------------------- contexto


class Contexto:
    """Quem está chamando, e o que essa pessoa pode fazer."""

    def __init__(self, id_usuario: int, email: str, nome: str, permissoes: set[str],
                 unidades: set[int], todas_unidades: bool, unidade_pedida: int | None = None):
        self.id_usuario = id_usuario
        self.email = email
        self.nome = nome
        self.permissoes = permissoes
        self.unidades = unidades
        self.todas_unidades = todas_unidades
        # A loja escolhida no seletor da tela, se houver. Vem do cabeçalho
        # `X-Unidade` — nunca do corpo: assim vale para GET também, e uma tela
        # não precisa lembrar de repassá-la em cada chamada.
        self.unidade_pedida = unidade_pedida

    def pode(self, chave: str) -> bool:
        return chave in self.permissoes

    def ve_unidade(self, id_unidade: int | None) -> bool:
        if id_unidade is None or self.todas_unidades:
            return True
        return id_unidade in self.unidades


def carregar_contexto(id_usuario: int) -> Contexto:
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, nome, email, ativo FROM usuarios WHERE id = %s", (id_usuario,)
        )
        u = cur.fetchone()
        if not u:
            raise HTTPException(status_code=401, detail="Usuário não encontrado")
        if not u["ativo"]:
            raise HTTPException(status_code=403, detail="Usuário inativo")

        cur.execute(
            """
            SELECT DISTINCT pp.chave
              FROM usuario_papeis up
              JOIN papel_permissoes pp ON pp.id_papel = up.id_papel
             WHERE up.id_usuario = %s
            """,
            (id_usuario,),
        )
        permissoes = {r["chave"] for r in cur.fetchall()}

        cur.execute(
            "SELECT id_unidade FROM usuario_papeis WHERE id_usuario = %s", (id_usuario,)
        )
        linhas = cur.fetchall()

    todas = any(r["id_unidade"] is None for r in linhas)
    unidades = {r["id_unidade"] for r in linhas if r["id_unidade"] is not None}
    return Contexto(u["id"], u["email"], u["nome"], permissoes, unidades, todas)


def contexto_atual(request: Request) -> Contexto:
    """Dependência base: exige autenticação, não exige permissão nenhuma."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado")
    dados = decodificar_token(auth[7:])
    ctx = carregar_contexto(int(dados["sub"]))

    pedida = request.headers.get("X-Unidade")
    if pedida and pedida.isdigit():
        # Quem não enxerga a loja não passa a enxergar por mandar o cabeçalho:
        # a validação é a mesma do resto do sistema.
        if ctx.ve_unidade(int(pedida)):
            ctx.unidade_pedida = int(pedida)
        else:
            raise HTTPException(status_code=403, detail="Sem acesso a esta loja")

    request.state.contexto = ctx
    return ctx


def requer_permissao(*chaves: str):
    """Exige QUALQUER uma das chaves. Use no router ou no endpoint.

        router = APIRouter(dependencies=[Depends(requer_permissao("admin.usuarios"))])
    """

    def _dep(ctx: Contexto = Depends(contexto_atual)) -> Contexto:
        if not any(ctx.pode(c) for c in chaves):
            raise HTTPException(
                status_code=403,
                detail=f"Sem permissão para esta ação ({' ou '.join(chaves)})",
            )
        return ctx

    return _dep


def exige(ctx: Contexto, *chaves: Iterable[str]) -> None:
    """Checagem no meio de um service, quando a regra depende do corpo."""
    if not any(ctx.pode(c) for c in chaves):
        raise HTTPException(status_code=403, detail="Sem permissão para esta ação")


def unidade_atual(cur, ctx: Contexto) -> int:
    """A loja em que a operação acontece.

    Em ordem: a escolhida no seletor da tela, a única do usuário, a matriz.
    Estava copiada em sete routers — e uma cópia sempre fica para trás quando a
    regra muda, que foi o que aconteceu ao existir o seletor.
    """
    if ctx.unidade_pedida:
        return ctx.unidade_pedida
    if ctx.unidades:
        return sorted(ctx.unidades)[0]
    cur.execute("SELECT id FROM unidades WHERE ativo ORDER BY matriz DESC, id LIMIT 1")
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=400, detail="Nenhuma loja cadastrada")
    return linha["id"]
