"""Login, refresh, logout e /me. Único router público do sistema."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

import auditoria
from config import BLOQUEIO_MINUTOS, MAX_TENTATIVAS_LOGIN, REFRESH_GRACA_SEGUNDOS
from database import get_cursor
from models.acesso import (
    EsqueciSenhaRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RedefinirSenhaRequest,
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
    unidade_atual,
    verificar_senha,
)
from services import senhas

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

        # ⚠️ A escolha de quem entrou vai para o BANCO, não só para o navegador.
        # O front guarda o token em sessionStorage quando não é persistente, e
        # ele morre com o navegador — mas o servidor não pode confiar nisso:
        # quem copiou o token não está preso ao navegador de ninguém. É a
        # validade curta que garante a promessa.
        valor, hashed, expira = gerar_refresh(body.manter_conectado)
        cur.execute(
            """INSERT INTO sessoes
                   (id_usuario, refresh_hash, expira_em, ip, agente, persistente)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (u["id"], hashed, expira, _ip(request), request.headers.get("user-agent"),
             body.manter_conectado),
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
    agora = datetime.now(timezone.utc)
    with get_cursor() as cur:
        cur.execute(
            """SELECT s.id, s.expira_em, s.revogada_em, s.persistente, s.substituida_em,
                      u.id AS id_usuario, u.nome, u.email, u.ativo, u.trocar_senha
                 FROM sessoes s JOIN usuarios u ON u.id = s.id_usuario
                WHERE s.refresh_hash = %s""",
            (h,),
        )
        s = cur.fetchone()
        if not s or s["expira_em"] <= agora:
            raise HTTPException(status_code=401, detail="Sessão expirada, entre de novo")
        # 🔑 **A GRAÇA existe por causa da rotação.** O token antigo morre no
        # instante em que o novo nasce; duas abas (ou duas chamadas que escapem
        # da trava do front) apresentam o MESMO token, a primeira rotaciona e a
        # segunda chegaria com um token revogado há milissegundos. Sem esta
        # janela, quem não fez nada errado era jogado para a tela de login no
        # meio do trabalho — que foi exatamente a queixa que originou isto.
        #
        # ⚠️ **A graça vale só para quem foi SUBSTITUÍDO por uma rotação.**
        # `revogada_em` também é preenchida pelo logout, e perdoar ali seria um
        # buraco: sair da conta deixaria o refresh valendo mais 30 segundos. A
        # suíte pegou exatamente isso. Sair vale na hora, sempre — assim como
        # sessão derrubada pelo admin e troca de senha.
        if s["revogada_em"]:
            na_graca = (
                s["substituida_em"] is not None
                and s["substituida_em"] >= agora - timedelta(seconds=REFRESH_GRACA_SEGUNDOS)
            )
            if not na_graca:
                raise HTTPException(status_code=401,
                                    detail="Sessão expirada, entre de novo")
        if not s["ativo"]:
            raise HTTPException(status_code=403, detail="Usuário inativo")

        # Marca a substituição junto com a revogação: é o par que abre a graça.
        cur.execute(
            """UPDATE sessoes SET revogada_em = now(), substituida_em = now()
                WHERE id = %s AND revogada_em IS NULL""",
            (s["id"],),
        )
        # ⚠️ A rotação PRESERVA o modo. Sem isso, renovar uma sessão de navegador
        # a promoveria para 30 dias: a escolha da pessoa duraria até a primeira
        # renovação e depois sumiria, sem nada avisando.
        valor, hashed, expira = gerar_refresh(s["persistente"])
        cur.execute(
            """INSERT INTO sessoes (id_usuario, refresh_hash, expira_em, persistente)
               VALUES (%s, %s, %s, %s)""",
            (s["id_usuario"], hashed, expira, s["persistente"]),
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

        # A loja ATUAL decide: o envio ao PDV é configurado por loja, e quem
        # troca de loja no seletor tem de ver a marca da loja em que está.
        cur.execute(
            """SELECT enviar_ao_pdv FROM integracoes
                WHERE servico = 'PDV_LEGAL' AND id_unidade = %s""",
            (unidade_atual(cur, ctx),),
        )
        linha_pdv = cur.fetchone()

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
        "enviar_ao_pdv": bool(linha_pdv["enviar_ao_pdv"]) if linha_pdv else False,
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


# ---------------------------------------------------------------- senha esquecida

# A mesma frase para e-mail cadastrado e para e-mail inventado. Responder
# "não encontramos esse e-mail" transformaria a tela pública num verificador de
# quem trabalha na casa — e a lista de quem trabalha aqui não é pública.
RESPOSTA_UNICA = (
    "Se este e-mail estiver cadastrado, o link para redefinir a senha chega em instantes. "
    "Confira também a caixa de spam."
)


@router.post("/esqueci-senha")
def esqueci_senha(body: EsqueciSenhaRequest, request: Request) -> dict:
    with get_cursor() as cur:
        r = senhas.pedir(cur, body.email, _ip(request))
        # A auditoria registra o que de fato aconteceu — é onde o dono descobre
        # que alguém tentou recuperar a senha de um endereço que não existe.
        auditoria.registrar(
            cur, r.get("id_usuario"), "senha", body.email.strip().lower(), "recuperacao_pedida",
            depois={"enviado": r["enviado"], "motivo": r.get("motivo"), "modo": r.get("modo")},
            ip=_ip(request),
        )
    return {"message": RESPOSTA_UNICA}


@router.get("/redefinir-senha/{token}")
def conferir_token(token: str) -> dict:
    """A tela pergunta antes de mostrar o formulário: o link ainda vale?

    Sem isto, a pessoa digita a senha nova duas vezes para só então descobrir
    que o link tinha vencido.
    """
    with get_cursor() as cur:
        t = senhas.usuario_do_token(cur, token)
    # Só o primeiro nome: o suficiente para a pessoa reconhecer a conta, sem
    # entregar o e-mail de ninguém a quem achou o link.
    return {"valido": True, "nome": (t["nome"] or "").split(" ")[0]}


@router.post("/redefinir-senha")
def redefinir_senha(body: RedefinirSenhaRequest, request: Request) -> dict:
    with get_cursor() as cur:
        r = senhas.redefinir(cur, body.token, body.senha)
        auditoria.registrar(cur, r["id_usuario"], "senha", r["id_usuario"], "redefinida",
                            ip=_ip(request))
    return {
        "message": "Senha alterada. Entre com a senha nova.",
        # Quem redefine a senha porque desconfia de invasão precisa saber que as
        # outras sessões caíram junto.
        "detalhe": "Por segurança, todas as sessões abertas foram encerradas.",
    }
