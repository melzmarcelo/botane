"""OAuth 2.1 do conector do Claude: registro, código, troca, renovação e revogação.

🔑 **Existe por causa do claude.ai.** Lá o conector é uma URL, e o único jeito
de um conector ter login é OAuth com registro dinâmico (RFC 7591) e PKCE. O
fluxo inteiro:

    1. o Claude lê `/.well-known/oauth-protected-resource` e descobre o emissor
    2. lê `/.well-known/oauth-authorization-server` e se registra (`/oauth/registrar`)
    3. abre `/oauth/autorizar` no navegador: a pessoa entra com a senha do Botané
       e autoriza — e ele recebe um CÓDIGO de uso único, preso ao PKCE
    4. troca o código por chave em `/oauth/token`, e renova ali mesmo

🔑 **A chave que nasce é uma linha de `tokens_api`** (`origem = 'oauth'`), só de
leitura: aparece na tela de chaves do usuário e se revoga no mesmo clique. Tudo o
que vale para a chave manual — escopo de loja, usuário inativo, trava de método —
vale aqui sem uma linha a mais.

⚠️ Só o HASH de código, chave e renovação vai para o banco.
"""

import base64
import hashlib
import secrets
from urllib.parse import urlencode, urlsplit

import auditoria
from config import API_URL_PUBLICA
from database import get_cursor
from seguranca import PREFIXO_TOKEN_API, gerar_token_api, hash_refresh

ESCOPO = "botane.leitura"
ESCOPO_ESCRITA = "botane.escrita"
PERMISSAO = "integracao.claude"

# ⚠️ A chave de acesso vive UMA hora; quem mantém a conexão é a renovação. Chave
# curta é o que limita o estrago de uma que vaze no log de alguém.
CHAVE_MINUTOS = 60
# Renovação deslizante: cada uso empurra o prazo. Conexão parada por 30 dias
# morre sozinha, e reconectar é refazer o login.
RENOVACAO_DIAS = 30
CODIGO_MINUTOS = 10
PREFIXO_RENOVACAO = "btr_"


class ErroOAuth(Exception):
    """Erro no formato da RFC 6749: `error` + `error_description`."""

    def __init__(self, erro: str, descricao: str, status: int = 400):
        super().__init__(descricao)
        self.erro, self.descricao, self.status = erro, descricao, status

    def corpo(self) -> dict:
        return {"error": self.erro, "error_description": self.descricao}


# ------------------------------------------------------------------ endereços

def emissor() -> str:
    """A ORIGEM da API pública (sem o `/api`).

    ⚠️ Emissor sem caminho, de propósito: os metadados moram então em
    `https://dominio/.well-known/…`, o endereço que todo cliente tenta primeiro.
    No ar, o `app.yaml` manda esse caminho para a API (e não para o Next).
    """
    p = urlsplit(API_URL_PUBLICA)
    return f"{p.scheme}://{p.netloc}"


def url_mcp() -> str:
    return f"{API_URL_PUBLICA}/mcp"


def url_metadados_recurso() -> str:
    """RFC 9728: o caminho do recurso vai DEPOIS do `.well-known/…`."""
    return f"{emissor()}/.well-known/oauth-protected-resource{urlsplit(url_mcp()).path}"


def metadados_servidor() -> dict:
    base = API_URL_PUBLICA
    return {
        "issuer": emissor(),
        "authorization_endpoint": f"{base}/oauth/autorizar",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/registrar",
        "revocation_endpoint": f"{base}/oauth/revogar",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post",
                                                  "client_secret_basic"],
        "revocation_endpoint_auth_methods_supported": ["none", "client_secret_post",
                                                       "client_secret_basic"],
        "scopes_supported": [ESCOPO, ESCOPO_ESCRITA],
        "authorization_response_iss_parameter_supported": True,
    }


def metadados_recurso() -> dict:
    return {
        "resource": url_mcp(),
        "resource_name": "Botané",
        "authorization_servers": [emissor()],
        "scopes_supported": [ESCOPO, ESCOPO_ESCRITA],
        "bearer_methods_supported": ["header"],
    }


# ------------------------------------------------------------------ registro

def _redirect_aceito(uri: str) -> bool:
    """HTTPS em qualquer lugar; HTTP só na própria máquina (o Claude Code usa isso).

    ⚠️ Fragmento é proibido pela RFC — e seria um jeito de o código vazar no
    histórico do navegador.
    """
    try:
        p = urlsplit(uri)
    except ValueError:
        return False
    if p.fragment or not p.netloc:
        return False
    if p.scheme == "https":
        return True
    return p.scheme == "http" and p.hostname in ("localhost", "127.0.0.1", "::1")


def registrar_cliente(nome: str | None, redirect_uris: list[str], metodo: str | None) -> dict:
    metodo = metodo or "none"
    if metodo not in ("none", "client_secret_post", "client_secret_basic"):
        raise ErroOAuth("invalid_client_metadata",
                        f"token_endpoint_auth_method não suportado: {metodo}")
    if not redirect_uris:
        raise ErroOAuth("invalid_redirect_uri", "Informe ao menos um redirect_uri.")
    for uri in redirect_uris:
        if not _redirect_aceito(uri):
            raise ErroOAuth("invalid_redirect_uri",
                            f"redirect_uri recusado (use https, ou http só em localhost): {uri}")

    client_id = "btc_" + secrets.token_urlsafe(18)
    segredo = None if metodo == "none" else secrets.token_urlsafe(32)
    nome = (nome or "Cliente MCP").strip()[:120] or "Cliente MCP"
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO oauth_clientes (client_id, segredo_hash, metodo_auth, nome,
                                           redirect_uris)
               VALUES (%s, %s, %s, %s, %s) RETURNING criado_em""",
            (client_id, hash_refresh(segredo) if segredo else None, metodo, nome,
             redirect_uris),
        )
        criado = cur.fetchone()["criado_em"]
    resposta = {
        "client_id": client_id,
        "client_id_issued_at": int(criado.timestamp()),
        "client_name": nome,
        "redirect_uris": redirect_uris,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": metodo,
        "scope": ESCOPO,
    }
    if segredo:
        resposta["client_secret"] = segredo
        resposta["client_secret_expires_at"] = 0
    return resposta


def cliente(client_id: str | None) -> dict | None:
    if not client_id:
        return None
    with get_cursor() as cur:
        cur.execute("SELECT * FROM oauth_clientes WHERE client_id = %s", (client_id,))
        return cur.fetchone()


def autenticar_cliente(client_id: str | None, segredo: str | None) -> dict:
    """O cliente do pedido de token, conferido pelo método com que se registrou."""
    c = cliente(client_id)
    if not c:
        raise ErroOAuth("invalid_client", "Cliente desconhecido.", 401)
    if c["metodo_auth"] != "none":
        if not segredo or not secrets.compare_digest(hash_refresh(segredo), c["segredo_hash"]):
            raise ErroOAuth("invalid_client", "Segredo do cliente inválido.", 401)
    return c


# ------------------------------------------------------------------ autorização

def recurso_aceito(recurso: str | None) -> bool:
    """RFC 8707: se o cliente disse PARA ONDE quer a chave, tem de ser este MCP."""
    return not recurso or recurso.rstrip("/") == url_mcp().rstrip("/")


def emitir_codigo(c: dict, id_usuario: int, redirect_uri: str, code_challenge: str,
                  recurso: str | None, escrita: bool = False) -> str:
    codigo = secrets.token_urlsafe(32)
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO oauth_codigos (codigo_hash, id_cliente, id_usuario, redirect_uri,
                                          code_challenge, recurso, expira_em, escrita)
               VALUES (%s, %s, %s, %s, %s, %s, now() + make_interval(mins => %s), %s)""",
            (hash_refresh(codigo), c["id"], id_usuario, redirect_uri, code_challenge,
             recurso, CODIGO_MINUTOS, escrita),
        )
    return codigo


def url_de_volta(redirect_uri: str, **params: str | None) -> str:
    extra = urlencode({k: v for k, v in params.items() if v is not None})
    return redirect_uri + ("&" if urlsplit(redirect_uri).query else "?") + extra


def _pkce_confere(verificador: str | None, desafio: str) -> bool:
    if not verificador or not 43 <= len(verificador) <= 128:
        return False
    calculado = base64.urlsafe_b64encode(
        hashlib.sha256(verificador.encode("ascii", "ignore")).digest()).rstrip(b"=").decode()
    return secrets.compare_digest(calculado, desafio)


# ------------------------------------------------------------------ chave

def _resposta_de_chave(chave: str, renovacao: str, escrita: bool = False) -> dict:
    escopo = f"{ESCOPO} {ESCOPO_ESCRITA}" if escrita else ESCOPO
    return {"access_token": chave, "token_type": "Bearer",
            "expires_in": CHAVE_MINUTOS * 60, "refresh_token": renovacao, "scope": escopo}


def trocar_codigo(c: dict, codigo: str | None, redirect_uri: str | None,
                  verificador: str | None, recurso: str | None) -> dict:
    """Código → chave. Uso ÚNICO: o `UPDATE … WHERE usado_em IS NULL` é a trava.

    ⚠️ Dois pedidos com o mesmo código ao mesmo tempo: só um vê a linha livre,
    porque a marcação e a leitura são a mesma instrução.
    """
    if not codigo:
        raise ErroOAuth("invalid_request", "Falta o code.")
    with get_cursor() as cur:
        cur.execute(
            """UPDATE oauth_codigos SET usado_em = now()
                WHERE codigo_hash = %s AND usado_em IS NULL AND expira_em > now()
            RETURNING id_cliente, id_usuario, redirect_uri, code_challenge, recurso,
                      escrita""",
            (hash_refresh(codigo),),
        )
        k = cur.fetchone()
    # ⚠️ As conferências vêm DEPOIS de queimar o código: errar o verificador não
    # devolve uma segunda chance a quem está adivinhando.
    if not k or k["id_cliente"] != c["id"]:
        raise ErroOAuth("invalid_grant", "Código inválido, vencido ou já usado.")
    if redirect_uri != k["redirect_uri"]:
        raise ErroOAuth("invalid_grant", "redirect_uri diferente do da autorização.")
    if not _pkce_confere(verificador, k["code_challenge"]):
        raise ErroOAuth("invalid_grant", "code_verifier não confere (PKCE).")
    if recurso and not recurso_aceito(recurso):
        raise ErroOAuth("invalid_target", "Este servidor só emite chave para o próprio MCP.")

    chave, prefixo, chave_hash = gerar_token_api()
    renovacao = PREFIXO_RENOVACAO + secrets.token_urlsafe(40)
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO tokens_api (id_usuario, nome, prefixo, token_hash, somente_leitura,
                                       expira_em, criado_por, origem, id_cliente_oauth,
                                       refresh_hash, refresh_expira_em)
               VALUES (%s, %s, %s, %s, %s, now() + make_interval(mins => %s), %s, 'oauth',
                       %s, %s, now() + make_interval(days => %s))
               RETURNING id""",
            (k["id_usuario"], c["nome"][:80], prefixo, chave_hash, not k["escrita"],
             CHAVE_MINUTOS, k["id_usuario"], c["id"], hash_refresh(renovacao),
             RENOVACAO_DIAS),
        )
        id_token = cur.fetchone()["id"]
        auditoria.registrar(cur, k["id_usuario"], "token_api", id_token, "conectar_claude",
                            depois={"cliente": c["nome"], "prefixo": prefixo,
                                    "pode_alterar": k["escrita"]})
    return _resposta_de_chave(chave, renovacao, k["escrita"])


def renovar(c: dict, renovacao: str | None) -> dict:
    """Renovação → chave nova, na MESMA linha (rotaciona chave e renovação juntas)."""
    if not renovacao:
        raise ErroOAuth("invalid_request", "Falta o refresh_token.")
    chave, prefixo, chave_hash = gerar_token_api()
    nova = PREFIXO_RENOVACAO + secrets.token_urlsafe(40)
    with get_cursor() as cur:
        cur.execute(
            """UPDATE tokens_api
                  SET token_hash = %s, prefixo = %s,
                      expira_em = now() + make_interval(mins => %s),
                      refresh_hash = %s,
                      refresh_expira_em = now() + make_interval(days => %s)
                WHERE refresh_hash = %s AND id_cliente_oauth = %s
                  AND revogado_em IS NULL AND refresh_expira_em > now()
            RETURNING id, somente_leitura""",
            (chave_hash, prefixo, CHAVE_MINUTOS, hash_refresh(nova), RENOVACAO_DIAS,
             hash_refresh(renovacao), c["id"]),
        )
        linha = cur.fetchone()
        if not linha:
            raise ErroOAuth("invalid_grant", "Renovação inválida, vencida ou revogada.")
    # ⚠️ A renovação PRESERVA o que a pessoa autorizou: a linha é a mesma, e
    # `somente_leitura` não é tocado. Renovar não amplia nem encolhe o acesso.
    return _resposta_de_chave(chave, nova, not linha["somente_leitura"])


def revogar(c: dict, valor: str | None) -> None:
    """RFC 7009: revoga a conexão dona da chave OU da renovação. Silencioso sempre.

    ⚠️ Só as do PRÓPRIO cliente: um cliente não derruba a conexão de outro.
    """
    if not valor:
        return
    coluna = "refresh_hash" if valor.startswith(PREFIXO_RENOVACAO) else "token_hash"
    if coluna == "token_hash" and not valor.startswith(PREFIXO_TOKEN_API):
        return
    with get_cursor() as cur:
        cur.execute(
            f"""UPDATE tokens_api SET revogado_em = now()
                 WHERE {coluna} = %s AND id_cliente_oauth = %s AND revogado_em IS NULL""",
            (hash_refresh(valor), c["id"]),
        )
