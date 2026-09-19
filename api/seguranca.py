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

from config import (
    BLOQUEIO_MINUTOS,
    JWT_EXPIRY_MIN,
    JWT_SECRET,
    MAX_TENTATIVAS_LOGIN,
    REFRESH_EXPIRY_DIAS,
    REFRESH_SESSAO_HORAS,
)
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


def conferir_credenciais(email: str, senha: str) -> dict:
    """O usuário dono de e-mail e senha, ou `HTTPException` — com a trava de tentativas.

    Usado pelo login da tela e pela autorização do conector do Claude: as duas
    portas pedem senha, e uma porta sem a trava seria o caminho para adivinhá-la.

    🔑 **A tentativa errada é gravada em UM bloco, e o erro sai DEPOIS dele.**
    `get_conn` desfaz tudo quando uma exceção atravessa o `with` — e era assim
    que o login fazia: `UPDATE tentativas_login` e `raise` no mesmo bloco. O
    rollback levava o contador junto, e **o bloqueio nunca chegou a acontecer**
    (achado em 19/09/2026: duas senhas erradas, contador em zero). Qualquer um
    podia tentar senhas sem limite.
    """
    email = email.strip().lower()
    erro: HTTPException | None = None
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

        if not verificar_senha(senha, u["senha_hash"]):
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
            erro = generico   # ⚠️ levantado FORA do bloco, depois do commit
        else:
            cur.execute(
                """UPDATE usuarios
                      SET tentativas_login = 0, bloqueado_ate = NULL, ultimo_acesso = now()
                    WHERE id = %s""",
                (u["id"],),
            )
    if erro:
        raise erro
    return dict(u)


# ---------------------------------------------------------------- token


def criar_access_token(id_usuario: int, email: str) -> tuple[str, int]:
    expira = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRY_MIN)
    payload = {"sub": str(id_usuario), "email": email, "exp": expira}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256"), JWT_EXPIRY_MIN * 60


def gerar_refresh(persistente: bool = True) -> tuple[str, str, datetime]:
    """Devolve (valor em claro, hash guardado, validade).

    O banco guarda só o hash: vazamento da tabela não vira sessão de ninguém.

    ⚠️ `persistente` é a escolha de quem entrou. Sem "manter conectado" a
    validade é de horas, não de dias: o front guarda o token em sessionStorage
    e ele morre com o navegador, mas **o servidor não pode confiar nisso** —
    quem copiou o token não está preso ao navegador de ninguém.
    """
    valor = secrets.token_urlsafe(48)
    prazo = (timedelta(days=REFRESH_EXPIRY_DIAS) if persistente
             else timedelta(hours=REFRESH_SESSAO_HORAS))
    return (
        valor,
        hashlib.sha256(valor.encode()).hexdigest(),
        datetime.now(timezone.utc) + prazo,
    )


def hash_refresh(valor: str) -> str:
    return hashlib.sha256(valor.encode()).hexdigest()


# ---------------------------------------------------------------- chave de API

# 🔑 **O prefixo separa as duas portas antes de qualquer conta.** JWT começa com
# `eyJ` (o cabeçalho em base64); a chave de máquina começa com isto. Sem ele,
# cada requisição com chave pagaria uma tentativa de decodificar JWT antes, e o
# erro devolvido seria "token inválido" — que não diz qual das duas portas falhou.
PREFIXO_TOKEN_API = "btn_"

# ⚠️ Gravar o último uso a CADA requisição transformaria toda leitura do Claude
# numa escrita no banco. Um minuto de resolução basta para a tela dizer "usada
# agora há pouco" — que é a pergunta de quem vai revogar.
_USO_RESOLUCAO = timedelta(minutes=1)


def gerar_token_api() -> tuple[str, str, str]:
    """Devolve (valor em claro, prefixo mostrável, hash guardado)."""
    valor = PREFIXO_TOKEN_API + secrets.token_urlsafe(32)
    return valor, valor[: len(PREFIXO_TOKEN_API) + 6], hash_refresh(valor)


def resolver_token_api(valor: str) -> dict:
    """A linha viva da chave, ou 401. Atualiza o último uso quando vale a pena.

    ⚠️ Revogada, vencida e inexistente dão a MESMA frase: quem testa chaves
    roubadas não aprende qual delas um dia existiu.
    """
    agora = datetime.now(timezone.utc)
    with get_cursor() as cur:
        cur.execute(
            """SELECT id, id_usuario, somente_leitura, expira_em, revogado_em, ultimo_uso_em
                 FROM tokens_api WHERE token_hash = %s""",
            (hash_refresh(valor),),
        )
        t = cur.fetchone()
        if not t or t["revogado_em"] or t["expira_em"] <= agora:
            raise HTTPException(status_code=401, detail="Chave de acesso inválida ou revogada")
        if not t["ultimo_uso_em"] or t["ultimo_uso_em"] < agora - _USO_RESOLUCAO:
            cur.execute("UPDATE tokens_api SET ultimo_uso_em = now() WHERE id = %s", (t["id"],))
    return t


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
                 unidades: set[int], todas_unidades: bool, unidade_pedida: int | None = None,
                 setores: set[int] | None = None, todos_setores: bool = True):
        self.id_usuario = id_usuario
        self.email = email
        self.nome = nome
        self.permissoes = permissoes
        self.unidades = unidades
        self.todas_unidades = todas_unidades
        # De que parte da casa esta pessoa cuida. ⚠️ **Vazio quer dizer TODOS**,
        # e é por isso que `todos_setores` nasce verdadeiro: a mesma convenção da
        # loja (`id_unidade` nulo = todas). Sem isso, o deploy tiraria a agenda
        # de produção do painel de todo mundo até alguém reconfigurar pessoa por
        # pessoa.
        self.setores = setores or set()
        self.todos_setores = todos_setores
        # A loja escolhida no seletor da tela, se houver. Vem do cabeçalho
        # `X-Unidade` — nunca do corpo: assim vale para GET também, e uma tela
        # não precisa lembrar de repassá-la em cada chamada.
        self.unidade_pedida = unidade_pedida
        # Qual chave de máquina fez a chamada — nulo quando é gente, pelo login.
        # É o que permite às rotas de chave recusarem ser geridas por uma chave.
        self.id_token: int | None = None

    def pode(self, chave: str) -> bool:
        return chave in self.permissoes

    def ve_unidade(self, id_unidade: int | None) -> bool:
        if id_unidade is None or self.todas_unidades:
            return True
        return id_unidade in self.unidades

    def ve_setor(self, id_setor: int | None) -> bool:
        """O setor é desta pessoa?

        ⚠️ **Produto SEM setor responde que sim**, como a loja nula. Ele não é
        de ninguém, e escondê-lo faria a linha da agenda sumir do painel de toda
        a casa — sem nada dizendo por quê. Setor em branco é falta de cadastro,
        não uma decisão de acesso.
        """
        if id_setor is None or self.todos_setores:
            return True
        return id_setor in self.setores


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

        # ⚠️ **Só os setores ATIVOS contam.** Um setor desativado que continuasse
        # na lista deixaria a pessoa restrita a um lugar que não existe mais — e
        # o sintoma seria um painel vazio sem explicação. Desativar o último
        # setor de alguém a devolve a "todos", que é o padrão.
        cur.execute(
            """SELECT us.id_setor FROM usuario_setores us
                 JOIN setores s ON s.id = us.id_setor AND s.ativo
                WHERE us.id_usuario = %s""",
            (id_usuario,),
        )
        setores = {r["id_setor"] for r in cur.fetchall()}

    todas = any(r["id_unidade"] is None for r in linhas)
    unidades = {r["id_unidade"] for r in linhas if r["id_unidade"] is not None}
    return Contexto(u["id"], u["email"], u["nome"], permissoes, unidades, todas,
                    setores=setores, todos_setores=not setores)


def contexto_da_credencial(credencial: str, escreve: bool) -> Contexto:
    """O `Contexto` de quem apresentou esta credencial (JWT da tela ou chave `btn_`).

    `escreve` diz se o pedido ALTERA alguma coisa. Quem decide é o chamador:
    `contexto_atual` olha o método HTTP; o `/mcp` é POST por protocolo e passa
    `False`, porque as ferramentas dele só leem — e cada uma, lá dentro, vira um
    GET que passa por esta mesma conferência.
    """
    if credencial.startswith(PREFIXO_TOKEN_API):
        chave = resolver_token_api(credencial)
        # 🔑 **Somente leitura se decide aqui, uma vez.** Vale para toda rota que
        # existe e para as que ainda vão nascer — deixar a cada router a tarefa
        # de lembrar é o jeito de a primeira rota nova esquecer.
        # ⚠️ Nem as "escritas inofensivas" passam (trocar a própria senha, o
        # próprio nome): chave vazada que troca a senha do dono toma a conta.
        if chave["somente_leitura"] and escreve:
            raise HTTPException(
                status_code=403,
                detail="Esta chave de acesso é só de leitura — não pode alterar nada.")
        ctx = carregar_contexto(chave["id_usuario"])
        ctx.id_token = chave["id"]
        return ctx
    dados = decodificar_token(credencial)
    return carregar_contexto(int(dados["sub"]))


def contexto_atual(request: Request) -> Contexto:
    """Dependência base: exige autenticação, não exige permissão nenhuma."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado")
    ctx = contexto_da_credencial(
        auth[7:], escreve=request.method not in ("GET", "HEAD", "OPTIONS"))

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
