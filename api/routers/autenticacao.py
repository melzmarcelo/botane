"""Login, refresh, logout e /me. Único router público do sistema."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

import auditoria
from config import BLOQUEIO_MINUTOS, MAX_TENTATIVAS_LOGIN
from database import get_cursor
from models.acesso import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    RefreshRequest,
    TrocarSenhaRequest,
)
from seguranca import (
    Contexto,
    contexto_atual,
    criar_access_token,
    gerar_refresh,
    hash_refresh,
    hash_senha,
    verificar_senha,
)

router = APIRouter(prefix="/auth", tags=["autenticação"])


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request):
    email = body.email.strip().lower()
    with get_cursor() as cur:
        cur.execute(
            """SELECT id, nome, email, senha_hash, ativo, tentativas_login,
                      bloqueado_ate, trocar_senha
                 FROM usuarios WHERE lower(email) = %s""",
            (email,),
        )
        u = cur.fetchone()

        # Mensagem única para e-mail errado e senha errada: não confirma quem existe.
        generico = HTTPException(status_code=401, detail="E-mail ou senha inválidos")
        if not u:
            raise generico
        if not u["ativo"]:
            raise HTTPException(status_code=403, detail="Usuário inativo")
        if u["bloqueado_ate"] and u["bloqueado_ate"] > datetime.now(timezone.utc):
            raise HTTPException(
                status_code=429,
                detail="Muitas tentativas. Tente de novo em alguns minutos.",
            )

        if not verificar_senha(body.senha, u["senha_hash"]):
            tentativas = (u["tentativas_login"] or 0) + 1
            bloqueio = (
                datetime.now(timezone.utc) + timedelta(minutes=BLOQUEIO_MINUTOS)
                if tentativas >= MAX_TENTATIVAS_LOGIN
                else None
            )
            cur.execute(
                "UPDATE usuarios SET tentativas_login = %s, bloqueado_ate = %s WHERE id = %s",
                (tentativas, bloqueio, u["id"]),
            )
            raise generico

        cur.execute(
            """UPDATE usuarios
                  SET tentativas_login = 0, bloqueado_ate = NULL, ultimo_acesso = now()
                WHERE id = %s""",
            (u["id"],),
        )

        valor, hashed, expira = gerar_refresh()
        cur.execute(
            """INSERT INTO sessoes (id_usuario, refresh_hash, expira_em, ip, agente)
               VALUES (%s, %s, %s, %s, %s)""",
            (u["id"], hashed, expira, _ip(request), request.headers.get("user-agent")),
        )
        auditoria.registrar(cur, u["id"], "sessao", u["id"], "login", ip=_ip(request))

    token, ttl = criar_access_token(u["id"], u["email"])
    return {
        "access_token": token,
        "refresh_token": valor,
        "expira_em": ttl,
        "usuario": {
            "id": u["id"],
            "nome": u["nome"],
            "email": u["email"],
            "trocar_senha": u["trocar_senha"],
        },
    }


@router.post("/refresh", response_model=LoginResponse)
def refresh(body: RefreshRequest):
    """Rotaciona o refresh: o antigo morre no mesmo instante em que o novo nasce."""
    h = hash_refresh(body.refresh_token)
    with get_cursor() as cur:
        cur.execute(
            """SELECT s.id, s.expira_em, s.revogada_em,
                      u.id AS id_usuario, u.nome, u.email, u.ativo, u.trocar_senha
                 FROM sessoes s JOIN usuarios u ON u.id = s.id_usuario
                WHERE s.refresh_hash = %s""",
            (h,),
        )
        s = cur.fetchone()
        if not s or s["revogada_em"] or s["expira_em"] <= datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Sessão expirada, entre de novo")
        if not s["ativo"]:
            raise HTTPException(status_code=403, detail="Usuário inativo")

        cur.execute("UPDATE sessoes SET revogada_em = now() WHERE id = %s", (s["id"],))
        valor, hashed, expira = gerar_refresh()
        cur.execute(
            "INSERT INTO sessoes (id_usuario, refresh_hash, expira_em) VALUES (%s, %s, %s)",
            (s["id_usuario"], hashed, expira),
        )

    token, ttl = criar_access_token(s["id_usuario"], s["email"])
    return {
        "access_token": token,
        "refresh_token": valor,
        "expira_em": ttl,
        "usuario": {
            "id": s["id_usuario"],
            "nome": s["nome"],
            "email": s["email"],
            "trocar_senha": s["trocar_senha"],
        },
    }


@router.post("/logout")
def logout(body: RefreshRequest, ctx: Contexto = Depends(contexto_atual)):
    with get_cursor() as cur:
        cur.execute(
            """UPDATE sessoes SET revogada_em = now()
                WHERE refresh_hash = %s AND id_usuario = %s AND revogada_em IS NULL""",
            (hash_refresh(body.refresh_token), ctx.id_usuario),
        )
    return {"message": "Sessão encerrada"}


@router.get("/me", response_model=MeResponse)
def me(ctx: Contexto = Depends(contexto_atual)):
    with get_cursor() as cur:
        cur.execute(
            "SELECT nome, email, telefone, foto_url, trocar_senha FROM usuarios WHERE id = %s",
            (ctx.id_usuario,),
        )
        u = cur.fetchone()
        cur.execute(
            """SELECT DISTINCT p.nome FROM usuario_papeis up
                 JOIN papeis p ON p.id = up.id_papel
                WHERE up.id_usuario = %s ORDER BY p.nome""",
            (ctx.id_usuario,),
        )
        papeis = [r["nome"] for r in cur.fetchall()]

        # Com uma loja só, a interface esconde o seletor — mas o dado já vem pronto.
        if ctx.todas_unidades:
            cur.execute(
                "SELECT id, nome, apelido, matriz FROM unidades WHERE ativo ORDER BY id"
            )
        else:
            cur.execute(
                """SELECT id, nome, apelido, matriz FROM unidades
                    WHERE ativo AND id = ANY(%s) ORDER BY id""",
                (list(ctx.unidades) or [0],),
            )
        unidades = [dict(r) for r in cur.fetchall()]

    return {
        "id": ctx.id_usuario,
        "nome": u["nome"],
        "email": u["email"],
        "telefone": u["telefone"],
        "foto_url": u["foto_url"],
        "trocar_senha": u["trocar_senha"],
        "permissoes": sorted(ctx.permissoes),
        "papeis": papeis,
        "unidades": unidades,
        "todas_unidades": ctx.todas_unidades,
    }


@router.post("/trocar-senha")
def trocar_senha(
    body: TrocarSenhaRequest, request: Request, ctx: Contexto = Depends(contexto_atual)
):
    with get_cursor() as cur:
        cur.execute("SELECT senha_hash FROM usuarios WHERE id = %s", (ctx.id_usuario,))
        atual = cur.fetchone()
        if not verificar_senha(body.senha_atual, atual["senha_hash"]):
            raise HTTPException(status_code=400, detail="Senha atual não confere")
        cur.execute(
            "UPDATE usuarios SET senha_hash = %s, trocar_senha = false WHERE id = %s",
            (hash_senha(body.senha_nova), ctx.id_usuario),
        )
        # Trocar a senha derruba as outras sessões — é o ponto de trocar a senha.
        cur.execute(
            "UPDATE sessoes SET revogada_em = now() WHERE id_usuario = %s AND revogada_em IS NULL",
            (ctx.id_usuario,),
        )
        auditoria.registrar(
            cur, ctx.id_usuario, "usuario", ctx.id_usuario, "trocar_senha", ip=_ip(request)
        )
    return {"message": "Senha alterada. Entre de novo."}
