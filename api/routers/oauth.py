"""OAuth do conector do Claude — metadados, registro, login/autorização, token.

⚠️ **Rotas PÚBLICAS, e têm de ser**: é por elas que alguém que ainda não tem
chave consegue uma. O que protege cada uma:

- metadados: não contam nada que não esteja no protocolo
- registro: registrar-se não dá acesso a nada, só a mandar alguém ao login
- autorizar: a SENHA do Botané, com a mesma trava de tentativas do login da tela,
  e a permissão `integracao.claude`
- token: código de uso único + PKCE, ou renovação

Regras e fluxo em `services/oauth.py`.
"""

import base64
import html
from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from models.oauth import RegistroCliente
from seguranca import carregar_contexto, conferir_credenciais
from services import oauth

router = APIRouter(tags=["conector do Claude"])

_SEM_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _erro(e: oauth.ErroOAuth) -> JSONResponse:
    return JSONResponse(e.corpo(), status_code=e.status, headers=_SEM_CACHE)


# ------------------------------------------------------------------ metadados

@router.get("/.well-known/oauth-authorization-server")
def metadados_servidor() -> dict:
    return oauth.metadados_servidor()


# ⚠️ Com e sem o caminho do recurso: a RFC 9728 manda o cliente pedir
# `/.well-known/oauth-protected-resource/api/mcp`, mas há cliente que pede a raiz.
@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/{resto:path}")
def metadados_recurso(resto: str = "") -> dict:
    return oauth.metadados_recurso()


# ------------------------------------------------------------------ registro

@router.post("/oauth/registrar", status_code=201)
def registrar(body: RegistroCliente):
    try:
        return JSONResponse(
            oauth.registrar_cliente(body.client_name, body.redirect_uris,
                                    body.token_endpoint_auth_method),
            status_code=201, headers=_SEM_CACHE)
    except oauth.ErroOAuth as e:
        return _erro(e)


# ------------------------------------------------------------------ autorizar

_CSS = """
:root{color-scheme:light}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#dee6d3;
 font:15px/1.5 Inter,"Segoe UI",system-ui,sans-serif;color:#14201a;padding:24px 16px;
 box-sizing:border-box}
main{width:100%;max-width:420px;box-sizing:border-box;background:#fcfdfa;border:1px solid #d8ded0;
 border-radius:18px;padding:28px 26px;box-shadow:0 10px 30px rgba(20,32,26,.08)}
h1{font:700 22px/1.2 "Bricolage Grotesque","Segoe UI",system-ui,sans-serif;margin:0 0 4px}
.marca{font:600 12px/1 "IBM Plex Mono",ui-monospace,monospace;letter-spacing:.08em;
 text-transform:uppercase;color:#2c6a4a;margin:0 0 14px}
p{margin:0 0 12px}.suave{color:#5d6c61;font-size:13.5px}
.quem{background:#e3efe7;border:1px solid #cfe1d5;border-radius:12px;padding:12px 14px;
 margin:14px 0 18px;font-size:14px}
.quem b{display:block;font-size:15px}
.quem code{font:12.5px "IBM Plex Mono",ui-monospace,monospace;word-break:break-all}
ul{margin:6px 0 0;padding-left:18px}
label{display:block;font-weight:600;font-size:14px;margin:12px 0 4px}
input[type=email],input[type=password]{width:100%;box-sizing:border-box;padding:10px 12px;
 border:1px solid #c7cfbe;border-radius:10px;font:inherit;background:#fff}
input:focus{outline:2px solid #2c6a4a;outline-offset:1px}
.acoes{display:flex;gap:10px;margin-top:20px;flex-wrap:wrap}
button{font:600 15px/1 inherit;font-family:inherit;border-radius:999px;padding:12px 18px;
 cursor:pointer;border:1px solid #2c6a4a}
.sim{background:#2c6a4a;color:#fff;flex:1}.nao{background:transparent;color:#2c6a4a}
.escolha{display:flex;gap:10px;align-items:flex-start;margin-top:16px;padding:12px 14px;
 border:1px solid #d8ded0;border-radius:12px;background:#fcfdfa}
.escolha input{margin-top:3px;width:18px;height:18px;accent-color:#2c6a4a;flex:none}
.escolha span{font-size:13.5px;color:#5d6c61}
.escolha b{display:block;font-size:14.5px;color:#14201a;font-weight:600}
.erro{background:#f7e7e4;border:1px solid #e8c9c3;color:#95332a;border-radius:12px;
 padding:10px 14px;margin:0 0 14px;font-size:14px}
"""


def _pagina(titulo: str, corpo: str, status: int = 200) -> HTMLResponse:
    doc = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>{html.escape(titulo)} · Botané</title>
<style>{_CSS}</style></head><body><main><p class="marca">Botané Deli &amp; Café</p>
{corpo}</main></body></html>"""
    # 🔑 Página que pede senha não pode abrir dentro de moldura alheia: é o
    # clickjacking clássico — o botão "Permitir" por baixo de outra coisa.
    return HTMLResponse(doc, status_code=status, headers={
        **_SEM_CACHE,
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": "frame-ancestors 'none'; default-src 'none'; "
                                   "style-src 'unsafe-inline'",
        "Referrer-Policy": "no-referrer",
    })


def _pagina_de_erro(msg: str) -> HTMLResponse:
    return _pagina("Não foi possível conectar",
                   f"<h1>Não foi possível conectar</h1><p>{html.escape(msg)}</p>"
                   "<p class='suave'>Volte ao Claude e tente conectar de novo.</p>", 400)


def _conferir_pedido(response_type: str | None, client_id: str | None,
                     redirect_uri: str | None, code_challenge: str | None,
                     code_challenge_method: str | None, resource: str | None,
                     state: str | None) -> tuple[dict | None, HTMLResponse | RedirectResponse | None]:
    """O cliente e o endereço de volta, ou a resposta de erro certa.

    🔑 **Cliente ou `redirect_uri` inválidos NUNCA redirecionam** (RFC 6749 §4.1.2.1):
    mandar o navegador para um endereço que não conferimos é o redirecionador
    aberto que entrega o código a quem o forjou. Os outros erros voltam ao
    cliente, porque ali o endereço já é de confiança.
    """
    c = oauth.cliente(client_id)
    if not c:
        return None, _pagina_de_erro("Este aplicativo não está registrado no Botané.")
    if not redirect_uri or redirect_uri not in c["redirect_uris"]:
        return None, _pagina_de_erro("O endereço de retorno não confere com o registrado.")

    def volta(erro: str, descricao: str) -> RedirectResponse:
        return RedirectResponse(oauth.url_de_volta(
            redirect_uri, error=erro, error_description=descricao, state=state,
            iss=oauth.emissor()), status_code=302)

    if response_type != "code":
        return None, volta("unsupported_response_type", "Só response_type=code.")
    # ⚠️ PKCE OBRIGATÓRIO e só S256: é o que o OAuth 2.1 pede para cliente
    # público, e o Claude é cliente público.
    if not code_challenge or code_challenge_method != "S256":
        return None, volta("invalid_request", "PKCE com S256 é obrigatório.")
    if not oauth.recurso_aceito(resource):
        return None, volta("invalid_target", "Este servidor só autoriza o próprio MCP.")
    return c, None


def _formulario(c: dict, campos: dict[str, str | None], erro: str = "",
                email: str = "", escrita: bool = False) -> HTMLResponse:
    # ⚠️ **Nasce DESMARCADA.** Quem quer que o Claude altere diz que quer; o
    # contrário — vir marcada e a pessoa desmarcar — transforma um clique
    # distraído em permissão de escrita.
    marcado = "checked" if escrita else ""
    escondidos = "".join(
        f'<input type="hidden" name="{k}" value="{html.escape(v)}">'
        for k, v in campos.items() if v is not None)
    volta = urlsplit(campos["redirect_uri"] or "")
    aviso = f'<div class="erro" role="alert">{html.escape(erro)}</div>' if erro else ""
    corpo = f"""
<h1>Conectar ao Botané</h1>
<div class="quem"><b>{html.escape(c['nome'])}</b>
quer consultar o Botané em seu nome.<br>
<span class="suave">Vai voltar para <code>{html.escape(volta.netloc)}</code></span></div>
<p>O aplicativo vai poder <b>ler</b>, com as suas permissões e lojas:</p>
<ul class="suave"><li>produtos, fichas técnicas e custos</li>
<li>estoque, notas de compra e vendas</li><li>CMV e relatórios</li></ul>
<p class="suave" style="margin-top:10px">Alterar, só se você marcar a caixa abaixo. Dá para
desconectar a qualquer momento no Botané, em Perfil ▸ Claude.</p>
<form method="post" action="autorizar">{aviso}{escondidos}
<label for="email">E-mail</label>
<input id="email" name="email" type="email" autocomplete="username" required
 value="{html.escape(email)}" {'' if email else 'autofocus'}>
<label for="senha">Senha</label>
<input id="senha" name="senha" type="password" autocomplete="current-password" required
 {'autofocus' if email else ''}>
<label class="escolha" for="escrita">
<input type="checkbox" id="escrita" name="escrita" value="1" {marcado}>
<span><b>Deixar o Claude alterar cadastros</b>
Conciliar notas, criar e corrigir produtos, juntar cadastros repetidos e lançar notas no
estoque — sempre com as suas permissões, e cada alteração fica registrada na Auditoria.
Sem marcar, ele só consulta.</span></label>
<div class="acoes">
<button class="sim" name="decisao" value="permitir">Entrar e permitir</button>
<button class="nao" name="decisao" value="negar" formnovalidate>Cancelar</button>
</div></form>"""
    return _pagina("Conectar ao Botané", corpo)


@router.get("/oauth/autorizar", response_class=HTMLResponse)
def autorizar_pagina(response_type: str | None = None, client_id: str | None = None,
                     redirect_uri: str | None = None, code_challenge: str | None = None,
                     code_challenge_method: str | None = None, state: str | None = None,
                     scope: str | None = None, resource: str | None = None):
    c, erro = _conferir_pedido(response_type, client_id, redirect_uri, code_challenge,
                               code_challenge_method, resource, state)
    if erro:
        return erro
    return _formulario(c, {
        "response_type": response_type, "client_id": client_id, "redirect_uri": redirect_uri,
        "code_challenge": code_challenge, "code_challenge_method": code_challenge_method,
        "state": state, "scope": scope, "resource": resource})


@router.post("/oauth/autorizar", response_class=HTMLResponse)
def autorizar(response_type: str | None = Form(None), client_id: str | None = Form(None),
              redirect_uri: str | None = Form(None), code_challenge: str | None = Form(None),
              code_challenge_method: str | None = Form(None), state: str | None = Form(None),
              scope: str | None = Form(None), resource: str | None = Form(None),
              email: str = Form(""), senha: str = Form(""), decisao: str = Form(""),
              escrita: str = Form("")):
    # ⚠️ Confere TUDO de novo: os campos escondidos vieram do navegador, e o
    # navegador não é de confiança.
    c, erro = _conferir_pedido(response_type, client_id, redirect_uri, code_challenge,
                               code_challenge_method, resource, state)
    if erro:
        return erro
    campos = {"response_type": response_type, "client_id": client_id,
              "redirect_uri": redirect_uri, "code_challenge": code_challenge,
              "code_challenge_method": code_challenge_method, "state": state,
              "scope": scope, "resource": resource}

    if decisao != "permitir":
        return RedirectResponse(oauth.url_de_volta(
            redirect_uri, error="access_denied", error_description="A pessoa não autorizou.",
            state=state, iss=oauth.emissor()), status_code=302)

    quer_escrever = escrita == "1"
    try:
        u = conferir_credenciais(email, senha)
    except HTTPException as e:
        return _formulario(c, campos, str(e.detail), email, quer_escrever)
    try:
        ctx = carregar_contexto(u["id"])
    except HTTPException as e:
        return _formulario(c, campos, str(e.detail), email, quer_escrever)
    if not ctx.pode(oauth.PERMISSAO):
        return _formulario(c, campos, "Seu usuário não tem permissão para conectar o Claude. "
                                      "Peça ao administrador: Papéis ▸ “Conectar o Claude”.",
                           email, quer_escrever)
    # ⚠️ A permissão vem ANTES da troca de senha: é o "não" definitivo. Na ordem
    # inversa, quem não pode conectar trocaria a senha para só então descobrir.
    if u["trocar_senha"]:
        return _formulario(c, campos, "Você precisa trocar a senha antes. Entre no "
                                      "Botané pelo navegador, troque, e volte aqui.", email,
                           quer_escrever)

    codigo = oauth.emitir_codigo(c, u["id"], redirect_uri, code_challenge, resource,
                                 escrita=quer_escrever)
    # ⚠️ 303, não 302: depois de um POST, só o 303 garante que o navegador siga
    # com GET — e o cliente espera o código num GET.
    return RedirectResponse(oauth.url_de_volta(redirect_uri, code=codigo, state=state,
                                               iss=oauth.emissor()), status_code=303)


# ------------------------------------------------------------------ token

def _credencial_do_cliente(request: Request, client_id: str | None,
                           client_secret: str | None) -> tuple[str | None, str | None]:
    """`client_secret_basic` (cabeçalho) ou `_post`/`none` (formulário)."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        try:
            par = base64.b64decode(auth[6:]).decode()
            cid, _, seg = par.partition(":")
            return unquote(cid), unquote(seg)
        except (ValueError, UnicodeDecodeError):
            return None, None
    return client_id, client_secret


@router.post("/oauth/token")
def token(request: Request, grant_type: str = Form(""), code: str | None = Form(None),
          redirect_uri: str | None = Form(None), code_verifier: str | None = Form(None),
          refresh_token: str | None = Form(None), client_id: str | None = Form(None),
          client_secret: str | None = Form(None), resource: str | None = Form(None)):
    try:
        c = oauth.autenticar_cliente(*_credencial_do_cliente(request, client_id, client_secret))
        if grant_type == "authorization_code":
            corpo = oauth.trocar_codigo(c, code, redirect_uri, code_verifier, resource)
        elif grant_type == "refresh_token":
            corpo = oauth.renovar(c, refresh_token)
        else:
            raise oauth.ErroOAuth("unsupported_grant_type", f"grant_type: {grant_type or '—'}")
    except oauth.ErroOAuth as e:
        return _erro(e)
    return JSONResponse(corpo, headers=_SEM_CACHE)


@router.post("/oauth/revogar")
def revogar(request: Request, token: str | None = Form(None),
            client_id: str | None = Form(None), client_secret: str | None = Form(None)):
    """RFC 7009: responde 200 mesmo para chave desconhecida — não confirma o que existe."""
    try:
        c = oauth.autenticar_cliente(*_credencial_do_cliente(request, client_id, client_secret))
    except oauth.ErroOAuth as e:
        return _erro(e)
    oauth.revogar(c, token)
    return JSONResponse({}, headers=_SEM_CACHE)
