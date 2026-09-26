"""O conector do Claude pela URL: OAuth 2.1 + MCP em `/mcp`.

É o caminho que o claude.ai percorre, passo a passo, sem biblioteca MCP — cada
passo é conferido pelo que a especificação exige, não pelo que o cliente tolera.

1. sem chave, `/mcp` responde 401 apontando os metadados (é assim que o
   claude.ai descobre onde fazer login)
2. metadados do recurso e do servidor de autorização
3. registro dinâmico: https e localhost passam; http de fora e fragmento, não
4. página de autorização: cliente ou retorno inválidos NUNCA redirecionam;
   sem PKCE volta com erro; a página não abre em moldura
5. login errado fica na página; quem não tem `integracao.claude` não conecta;
   "Cancelar" volta com `access_denied`
6. código: uso único, preso ao PKCE e ao `redirect_uri`
7. MCP: initialize, tools/list, tools/call (ok, 403 vira `isError`, argumento
   ruim vira `isError`), método desconhecido, notificação → 202
7b. TODA ferramenta do catálogo responde — caminho errado aparece como 404,
   e quem exige argumento diz qual falta
7c. gravar é outra chave: a de leitura nem vê as ferramentas de escrita, a
   gerada com "permite alterar" grava, e a auditoria marca que veio do Claude
7d. conciliar e lançar uma nota inteira pelo conector (e estornar para limpar)
7e. achar cadastros repetidos, ver a prévia e fundi-los
7f. conectar pelo claude.ai marcando "deixar o Claude alterar": a chave nasce
   podendo gravar, a renovação preserva, e sem marcar continua só leitura
8. a conexão aparece na tela de chaves do usuário e em "minhas", com origem
9. renovação rotaciona chave e renovação na MESMA linha; a antiga morre
10. revogar (RFC 7009 e pela tela) derruba a conexão

    python tests/smoke_conector_claude.py            (API de pé na 9200)
"""

import base64
import hashlib
import html
import json
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, ".")
sys.path.insert(0, "tests")
from comum import garantir_cozinha  # noqa: E402
from database import get_cursor  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
VOLTA = "http://localhost:33418/callback"

ok = 0
falhas: list[str] = []


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


class _SemSeguir(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_abridor = urllib.request.build_opener(_SemSeguir)


def pedir(metodo, caminho, corpo=None, token=None, form=None, cabecalhos=None):
    """Devolve (status, cabeçalhos, corpo decodificado ou texto)."""
    url = caminho if caminho.startswith("http") else BASE + caminho
    req = urllib.request.Request(url, method=metodo)
    dados = None
    if form is not None:
        dados = urllib.parse.urlencode(form).encode()
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    elif corpo is not None:
        dados = json.dumps(corpo).encode()
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for k, v in (cabecalhos or {}).items():
        req.add_header(k, v)
    try:
        r = _abridor.open(req, dados, timeout=60)
        st, cab, bruto = r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        st, cab, bruto = e.code, e.headers, e.read()
    texto = bruto.decode(errors="replace")
    try:
        return st, cab, json.loads(texto) if texto else None
    except json.JSONDecodeError:
        return st, cab, texto


def rpc(token, metodo, params=None, id_=1):
    corpo = {"jsonrpc": "2.0", "method": metodo}
    if id_ is not None:
        corpo["id"] = id_
    if params is not None:
        corpo["params"] = params
    return pedir("POST", "/mcp", corpo, token=token,
                 cabecalhos={"Accept": "application/json, text/event-stream"})


def pkce():
    verificador = secrets.token_urlsafe(48)
    desafio = base64.urlsafe_b64encode(
        hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    return verificador, desafio


def url_autorizar(client_id, desafio, **extra):
    q = {"response_type": "code", "client_id": client_id, "redirect_uri": VOLTA,
         "code_challenge": desafio, "code_challenge_method": "S256", "state": "xyz",
         "scope": "botane.leitura", **extra}
    return "/oauth/autorizar?" + urllib.parse.urlencode(q)


def enviar_formulario(url, email, senha, decisao="permitir", escrita=False):
    """O que o navegador faria: ler os campos escondidos e mandar o formulário."""
    st, _, pagina = pedir("GET", url)
    campos = {n: html.unescape(v) for n, v in
              re.findall(r'type="hidden" name="(\w+)" value="([^"]*)"', pagina)}
    campos.update(email=email, senha=senha, decisao=decisao)
    if escrita:
        campos["escrita"] = "1"
    return pedir("POST", "/oauth/autorizar", form=campos)


def parametros_da_volta(cab):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(cab["Location"]).query))


print("1. sem chave, 401 apontando os metadados")
st, cab, _ = pedir("POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "ping"})
checar("POST /mcp sem chave dá 401", st == 401, st)
www = cab.get("WWW-Authenticate", "")
checar("com WWW-Authenticate e resource_metadata", "resource_metadata=" in www, www)
meta_url = re.search(r'resource_metadata="([^"]+)"', www).group(1)
st, _, _ = pedir("GET", "/mcp")
checar("GET /mcp é 405 (sem fluxo SSE)", st == 405, st)

print("\n2. metadados")
st, _, rec = pedir("GET", meta_url)
checar("o endereço do cabeçalho responde os metadados do recurso", st == 200, (st, meta_url))
checar("e aponta o MCP como recurso", rec.get("resource", "").endswith("/mcp"), rec)
emissor = rec["authorization_servers"][0]
st, _, srv = pedir("GET", emissor + "/.well-known/oauth-authorization-server")
checar("o emissor publica os metadados do servidor", st == 200, st)
checar("com PKCE S256", srv.get("code_challenge_methods_supported") == ["S256"], srv)
checar("e com registro dinâmico", bool(srv.get("registration_endpoint")), srv)
checar("o issuer é o próprio emissor", srv.get("issuer") == emissor, srv)

print("\n3. registro dinâmico")
st, _, cli = pedir("POST", "/oauth/registrar", {
    "client_name": "Claude (suíte)", "redirect_uris": [VOLTA, "https://claude.ai/api/mcp/auth_callback"],
    "token_endpoint_auth_method": "none", "grant_types": ["authorization_code", "refresh_token"],
    "response_types": ["code"], "logo_uri": "https://exemplo/x.png"})
checar("registro devolve 201 com client_id", st == 201 and cli.get("client_id"), (st, cli))
checar("cliente público não recebe segredo", "client_secret" not in cli, cli)
client_id = cli["client_id"]
for ruim, porque in [("http://evil.example/cb", "http fora de localhost"),
                     ("https://claude.ai/cb#frag", "fragmento")]:
    st, _, r = pedir("POST", "/oauth/registrar", {"redirect_uris": [ruim]})
    checar(f"recusa redirect_uri com {porque}", st == 400 and r.get("error") == "invalid_redirect_uri",
           (st, r))

print("\n4. a página de autorização")
verificador, desafio = pkce()
st, cab, pagina = pedir("GET", url_autorizar(client_id, desafio))
checar("abre a página de login", st == 200 and "Conectar ao Botané" in pagina, st)
checar("mostra o nome do cliente", "Claude (suíte)" in pagina)
checar("e não abre em moldura", cab.get("X-Frame-Options") == "DENY", dict(cab))
st, cab, _ = pedir("GET", url_autorizar("btc_nao_existe", desafio))
checar("cliente desconhecido: erro NA PÁGINA, sem redirecionar",
       st == 400 and "Location" not in cab, st)
st, cab, _ = pedir("GET", url_autorizar(client_id, desafio).replace(
    urllib.parse.quote(VOLTA, safe=""), urllib.parse.quote("https://evil.example/cb", safe="")))
checar("retorno não registrado: erro NA PÁGINA, sem redirecionar",
       st == 400 and "Location" not in cab, (st, cab.get("Location")))
st, cab, _ = pedir("GET", url_autorizar(client_id, desafio, code_challenge_method="plain"))
checar("sem PKCE S256: volta ao cliente com invalid_request",
       st == 302 and parametros_da_volta(cab).get("error") == "invalid_request", st)

print("\n5. login, permissão e cancelar")
st, cab, pagina = enviar_formulario(url_autorizar(client_id, desafio), ADMIN[0], "errada")
checar("senha errada fica na página, com a frase", st == 200 and "inválidos" in pagina, st)
st, _, s_admin = pedir("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
admin = s_admin["access_token"]


def _chamar(metodo, caminho, corpo=None, token=None):
    st, _, d = pedir(metodo, caminho, corpo, token=token)
    return st, d


garantir_cozinha(_chamar, admin)
_, _, usuarios = pedir("GET", "/usuarios?incluir_inativos=true&limite=500", token=admin)
id_cozinha_conector = next(u["id"] for u in usuarios
                           if u["email"] == "smoke.cozinha@botane.com.br")
criadas: list[int] = []
st, cab, pagina = enviar_formulario(url_autorizar(client_id, desafio),
                                    "smoke.cozinha@botane.com.br", "smoke12345")
checar("quem não tem integracao.claude não conecta",
       st == 200 and "não tem permissão" in pagina, st)
st, cab, _ = enviar_formulario(url_autorizar(client_id, desafio), ADMIN[0], ADMIN[1], "negar")
checar("cancelar volta com access_denied",
       st == 302 and parametros_da_volta(cab).get("error") == "access_denied", st)

print("\n6. o código")
st, cab, _ = enviar_formulario(url_autorizar(client_id, desafio), ADMIN[0], ADMIN[1])
volta = parametros_da_volta(cab) if "Location" in cab else {}
checar("permitir redireciona (303) ao retorno com code", st == 303 and volta.get("code"), st)
checar("devolvendo o state e o iss", volta.get("state") == "xyz" and volta.get("iss") == emissor,
       volta)
codigo = volta["code"]
st, _, r = pedir("POST", "/oauth/token", form={
    "grant_type": "authorization_code", "code": codigo, "redirect_uri": VOLTA,
    "client_id": client_id, "code_verifier": "x" * 50})
checar("verificador PKCE errado é recusado", st == 400 and r.get("error") == "invalid_grant", r)
st, _, r = pedir("POST", "/oauth/token", form={
    "grant_type": "authorization_code", "code": codigo, "redirect_uri": VOLTA,
    "client_id": client_id, "code_verifier": verificador})
checar("e o código foi queimado pela tentativa errada", st == 400, (st, r))

verificador, desafio = pkce()
st, cab, _ = enviar_formulario(url_autorizar(client_id, desafio), ADMIN[0], ADMIN[1])
codigo = parametros_da_volta(cab)["code"]
st, _, r = pedir("POST", "/oauth/token", form={
    "grant_type": "authorization_code", "code": codigo, "redirect_uri": "https://outro/cb",
    "client_id": client_id, "code_verifier": verificador})
checar("redirect_uri diferente do da autorização é recusado", st == 400, r)
verificador, desafio = pkce()
st, cab, _ = enviar_formulario(url_autorizar(client_id, desafio), ADMIN[0], ADMIN[1])
codigo = parametros_da_volta(cab)["code"]
troca = {"grant_type": "authorization_code", "code": codigo, "redirect_uri": VOLTA,
         "client_id": client_id, "code_verifier": verificador}
st, cab, tk = pedir("POST", "/oauth/token", form=troca)
checar("código certo vira chave", st == 200 and tk.get("access_token", "").startswith("btn_"),
       (st, tk))
checar("com renovação e validade", tk.get("refresh_token") and tk.get("expires_in"), tk)
checar("e sem cache", "no-store" in (cab.get("Cache-Control") or ""), dict(cab))
st, _, r = pedir("POST", "/oauth/token", form=troca)
checar("o mesmo código de novo é recusado (uso único)", st == 400, (st, r))
chave = tk["access_token"]

print("\n7. o protocolo MCP")
st, _, r = rpc(chave, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "suite", "version": "1"}})
checar("initialize responde", st == 200 and r.get("result", {}).get("serverInfo"), r)
checar("negociando a versão pedida", r["result"]["protocolVersion"] == "2025-06-18", r)
checar("e declarando ferramentas", "tools" in r["result"]["capabilities"], r)
st, _, _ = rpc(chave, "notifications/initialized", id_=None)
checar("notificação responde 202", st == 202, st)
st, _, r = rpc(chave, "tools/list")
ferramentas = {t["name"]: t for t in r["result"]["tools"]}
checar("tools/list traz as ferramentas", len(ferramentas) >= 15, len(ferramentas))
checar("todas marcadas só leitura",
       all(t["annotations"]["readOnlyHint"] for t in ferramentas.values()))
checar("com esquema de entrada", all(t["inputSchema"]["type"] == "object"
                                     for t in ferramentas.values()))
st, _, r = rpc(chave, "tools/call", {"name": "quem_sou", "arguments": {}})
eu = json.loads(r["result"]["content"][0]["text"])
checar("tools/call quem_sou devolve o administrador",
       not r["result"]["isError"] and eu.get("email") == ADMIN[0], r)
st, _, r = rpc(chave, "tools/call", {"name": "buscar_produtos", "arguments": {"limite": 2}})
checar("buscar_produtos devolve o total e a página",
       '"total"' in r["result"]["content"][0]["text"], r)
st, _, r = rpc(chave, "tools/call", {"name": "detalhe_produto",
                                     "arguments": {"id_produto": "../usuarios"}})
checar("id no caminho que não é inteiro vira isError (sem sair da rota)",
       r["result"]["isError"] is True, r)
st, _, r = rpc(chave, "tools/call", {"name": "vendas", "arguments": {"inicio": "ontem"}})
checar("argumento que a rota recusa vira isError com o motivo",
       r["result"]["isError"] and "inicio" in r["result"]["content"][0]["text"], r)
st, _, r = rpc(chave, "tools/call", {"name": "quem_sou", "arguments": {"xis": 1}})
checar("argumento desconhecido vira isError", r["result"]["isError"] is True, r)
st, _, r = rpc(chave, "tools/call", {"name": "apagar_tudo", "arguments": {}})
checar("ferramenta inexistente é erro de protocolo", r.get("error", {}).get("code") == -32602, r)
st, _, r = rpc(chave, "resources/list")
checar("método não suportado dá -32601", r.get("error", {}).get("code") == -32601, r)
st, _, r = pedir("PUT", "/auth/me", {"nome": "Invadido"}, token=chave)
checar("a chave do Claude continua só de leitura na API", st == 403, st)

print("\n7b. TODA ferramenta responde")
# 🔑 Cada ferramenta aponta para uma rota escrita à mão na tabela. Um caminho
# errado, um parâmetro que a rota não conhece ou uma permissão que o dono da
# chave não tem só aparecem quando alguém chama — e ninguém chama as 60 à mão.
# Aqui: quem não exige argumento é CHAMADO; quem exige é conferido pela recusa,
# que prova que a ferramenta existe e sabe o que pede.
st, _, r = rpc(chave, "tools/list")
mudas, exigentes = [], []
for t in r["result"]["tools"]:
    obrigatorios = t["inputSchema"].get("required") or []
    st, _, resp = rpc(chave, "tools/call", {"name": t["name"], "arguments": {}})
    res = resp.get("result") or {}
    texto = (res.get("content") or [{}])[0].get("text", "")
    if "error" in resp or not res:
        mudas.append((t["name"], resp))
    elif obrigatorios:
        if "obrigatório" not in texto:
            exigentes.append((t["name"], texto[:80]))
    # 403 (sem permissão) e 409 (módulo desligado nesta loja) são RESPOSTA, não
    # defeito. 404 não: ali a ferramenta aponta para uma rota que não existe.
    elif res.get("isError") and not texto.startswith(("403", "409")):
        mudas.append((t["name"], texto[:90]))
checar(f"as {len(r['result']['tools'])} ferramentas respondem sem erro de protocolo",
       not mudas, mudas[:3])
checar("e as que pedem argumento dizem qual falta", not exigentes, exigentes[:3])
# As de caminho, com id de verdade — é o que prova a substituição no caminho.
_, _, lista = rpc(chave, "tools/call", {"name": "lojas", "arguments": {}})
id_loja = json.loads(lista["result"]["content"][0]["text"])[0]["id"]
st, _, r = rpc(chave, "tools/call", {"name": "parametros_da_loja",
                                     "arguments": {"id_unidade": id_loja}})
checar("ferramenta com id no caminho responde com id de verdade",
       not r["result"]["isError"], r["result"]["content"][0]["text"][:100])


print("\n7c. gravar é outra chave")
# 🔑 A chave do claude.ai é SEMPRE só de leitura. Alterar exige chave gerada à
# mão, marcada como "permite alterar" — e é isso que este bloco cobra, dos dois
# lados: a de leitura nem VÊ as ferramentas que gravam, e a de escrita grava.
st, _, r = rpc(chave, "tools/list")
nomes_leitura = {t["name"] for t in r["result"]["tools"]}
checar("chave de leitura não enxerga as ferramentas que gravam",
       "vincular_item_de_nota" not in nomes_leitura and "lancar_nota" not in nomes_leitura,
       sorted(n for n in nomes_leitura if "criar" in n or "lancar" in n))
st, _, r = rpc(chave, "tools/call", {"name": "criar_produto",
                                     "arguments": {"nome": "Não deveria existir"}})
checar("e chamá-las assim mesmo vira isError, não gravação",
       r["result"]["isError"] and "leitura" in r["result"]["content"][0]["text"], r)

st, _, ke = pedir("POST", "/usuarios/1/tokens",
                  {"nome": "Claude que altera", "dias": 1, "somente_leitura": False},
                  token=admin)
checar("o admin gera chave que altera", st == 201 and ke.get("somente_leitura") is False, st)
criadas.append(ke.get("id"))
escrita = ke["token"]
st, _, r = pedir("POST", f"/usuarios/{id_cozinha_conector}/tokens",
                 {"nome": "sem permissão", "somente_leitura": False}, token=admin)
checar("mas não para quem não pode conectar o Claude (400)", st == 400, (st, r))

st, _, r = rpc(escrita, "tools/list")
gravam = [t for t in r["result"]["tools"] if not t["annotations"]["readOnlyHint"]]
# ⚠️ Pelos NOMES, não pela contagem: ferramenta nova de gravação quebraria um
# número fixo aqui, e a suíte acusaria a tela em vez de celebrar a novidade.
nomes_gravam = {t["name"] for t in gravam}
checar("a chave que altera enxerga as ferramentas de gravação",
       {"vincular_item_de_nota", "criar_produto", "atualizar_produto", "lancar_nota",
        "fundir_produtos"} <= nomes_gravam, sorted(nomes_gravam))
checar("e todas vêm marcadas como destrutivas, para o Claude perguntar antes",
       all(t["annotations"]["destructiveHint"] for t in gravam))

marca_p = str(int(time.time()))[-6:]
st, _, r = rpc(escrita, "tools/call", {"name": "criar_produto", "arguments": {
    "nome": f"Insumo do Claude {marca_p}", "tipo": "INSUMO", "um_estoque": "KG",
    "estoque_minimo": 2}})
criado = json.loads(r["result"]["content"][0]["text"])
checar("criar_produto cria de verdade", not r["result"]["isError"] and criado.get("id"), r)
id_novo = criado["id"]
st, _, r = rpc(escrita, "tools/call", {"name": "atualizar_produto", "arguments": {
    "id_produto": id_novo, "marca": "Marca do Claude", "estoque_maximo": 9}})
checar("atualizar_produto corrige o cadastro", not r["result"]["isError"], r)
st, _, r = rpc(escrita, "tools/call", {"name": "detalhe_produto",
                                       "arguments": {"id_produto": id_novo}})
depois = json.loads(r["result"]["content"][0]["text"])
checar("e grava SÓ o que foi mandado",
       depois["marca"] == "Marca do Claude" and float(depois["estoque_minimo"]) == 2
       and float(depois["estoque_maximo"]) == 9,
       {k: depois.get(k) for k in ("marca", "estoque_minimo", "estoque_maximo")})
# 🔑 **Todos os campos que a tela edita** (pedido do dono, 23/09/2026). Até ali a
# unidade e o fator ficavam fora; entram porque a ROTA segura a conversão com 409.
campos_update = next(t for t in gravam
                     if t["name"] == "atualizar_produto")["inputSchema"]["properties"]
from models.produtos import ProdutoUpdate  # noqa: E402
checar("o conector aceita TODO campo que o PUT de produto aceita",
       set(ProdutoUpdate.model_fields) <= set(campos_update),
       sorted(set(ProdutoUpdate.model_fields) - set(campos_update)))
st, _, r = rpc(escrita, "tools/call", {"name": "atualizar_produto", "arguments": {
    "id_produto": id_novo, "controla_estoque": False,
    "nome_catalogo": "Insumo do Claude", "observacao": "marcado pelo conector"}})
checar("controla_estoque é desmarcado pelo conector", not r["result"]["isError"], r)
st, _, r = rpc(escrita, "tools/call", {"name": "detalhe_produto",
                                       "arguments": {"id_produto": id_novo}})
d2 = json.loads(r["result"]["content"][0]["text"])
checar("e grava, junto com os campos que antes não chegavam",
       d2.get("controla_estoque") is False and d2.get("nome_catalogo") == "Insumo do Claude"
       and d2.get("observacao") == "marcado pelo conector",
       {k: d2.get(k) for k in ("controla_estoque", "nome_catalogo", "observacao")})
# ⚠️ A troca de unidade passa pela MESMA conversão da tela: KG → G multiplica o
# mínimo por mil. Se o conector gravasse a sigla crua, o mínimo ficaria em 2 g.
st, _, r = rpc(escrita, "tools/call", {"name": "atualizar_produto", "arguments": {
    "id_produto": id_novo, "um_estoque": "G"}})
st, _, r2 = rpc(escrita, "tools/call", {"name": "detalhe_produto",
                                        "arguments": {"id_produto": id_novo}})
d3 = json.loads(r2["result"]["content"][0]["text"])
checar("trocar a unidade pelo conector CONVERTE, como na tela",
       not r["result"]["isError"] and d3.get("um_estoque") == "G"
       and float(d3.get("estoque_minimo") or 0) == 2000,
       (r["result"], {k: d3.get(k) for k in ("um_estoque", "estoque_minimo")}))
# ⚠️ **Devolve o produto como estava**: o 7d dá entrada de nota NELE, e com o
# estoque desligado a nota entraria sem mexer no razão — o 7d falharia medindo
# outra coisa.
st, _, r = rpc(escrita, "tools/call", {"name": "atualizar_produto", "arguments": {
    "id_produto": id_novo, "um_estoque": "KG", "controla_estoque": True}})
checar("e o conector religa o controle e volta a unidade",
       not r["result"]["isError"], r["result"])
with get_cursor() as cur:
    cur.execute("""SELECT origem FROM auditoria WHERE entidade = 'produto'
                    AND id_entidade = %s ORDER BY em DESC LIMIT 1""", (str(id_novo),))
    linha = cur.fetchone()
checar("a auditoria marca que veio do Claude", (linha or {}).get("origem") == "claude", linha)
st, _, r = pedir("PUT", f"/produtos/{id_novo}", {"marca": "pela tela"}, token=admin)
with get_cursor() as cur:
    cur.execute("""SELECT origem FROM auditoria WHERE entidade = 'produto'
                    AND id_entidade = %s ORDER BY em DESC LIMIT 1""", (str(id_novo),))
    pela_tela = cur.fetchone()
checar("e a alteração pela tela NÃO sai marcada",
       (pela_tela or {}).get("origem") is None, pela_tela)

print("\n7d. conciliar e lançar uma nota, de ponta a ponta pelo conector")
# 🔑 A fila de conciliação é o trabalho que o dono quis passar ao Claude. Aqui a
# nota é criada pela API (como o Omie faria), e daí em diante TUDO é ferramenta:
# achar o item sem produto, ligá-lo e lançar no estoque.
st, _, nota = pedir("POST", "/notas", {
    "numero": f"CLA{marca_p}", "data_emissao": "2026-09-20", "data_entrada": "2026-09-20",
    "itens": [{"descricao": f"INSUMO CLAUDE {marca_p}", "codigo_fornecedor": f"CL{marca_p}",
               "quantidade": 3, "um": "KG", "valor_unitario": 10}]}, token=admin)
id_nota = (nota or {}).get("id")
checar("a nota de teste é criada", st in (200, 201) and id_nota, (st, nota))

st, _, r = rpc(escrita, "tools/call", {"name": "itens_sem_produto", "arguments": {}})
fila = json.loads(r["result"]["content"][0]["text"])
item = next((i for i in fila if i["id_nota"] == id_nota), None)
checar("o item aparece na fila de conciliação", item is not None, len(fila))

st, _, r = rpc(escrita, "tools/call", {"name": "vincular_item_de_nota", "arguments": {
    "id_item": item["id"], "id_produto": id_novo, "aprender": True}})
checar("vincular_item_de_nota liga o item ao produto", not r["result"]["isError"], r)
st, _, r = rpc(escrita, "tools/call", {"name": "nota_entrada",
                                       "arguments": {"id_nota": id_nota}})
conferida = json.loads(r["result"]["content"][0]["text"])
checar("e a nota deixa de ter pendência",
       all(i.get("id_produto") for i in conferida["itens"]), conferida.get("itens"))

st, _, r = rpc(escrita, "tools/call", {"name": "lancar_nota", "arguments": {"id_nota": id_nota}})
checar("lancar_nota dá entrada no estoque", not r["result"]["isError"],
       r["result"]["content"][0]["text"][:120])
st, _, r = rpc(escrita, "tools/call", {"name": "movimentos_estoque",
                                       "arguments": {"id_produto": id_novo, "limite": 5}})
movimentos = json.loads(r["result"]["content"][0]["text"])["itens"]
checar("e o razão passa a ter a entrada", any(float(m["quantidade"]) == 3 for m in movimentos),
       [(m["tipo"], m["quantidade"]) for m in movimentos])
with get_cursor() as cur:
    cur.execute("""SELECT origem FROM auditoria WHERE entidade = 'nota'
                    AND id_entidade = %s ORDER BY em DESC LIMIT 1""", (str(id_nota),))
    linha = cur.fetchone()
checar("o lançamento fica marcado como do Claude na auditoria",
       (linha or {}).get("origem") == "claude", linha)

# ⚠️ Limpeza: o razão é append-only, então desfazer é ESTORNAR — nunca apagar.
# É a mesma correção que uma pessoa faria pela tela.
st, _, r = pedir("POST", f"/notas/{id_nota}/estornar", {}, token=admin)
checar("o estorno desfaz o lançamento (e é assim que se corrige)", st == 200, (st, r))
pedir("DELETE", f"/produtos/{id_novo}", token=admin)


print("\n7e. achar os repetidos e fundi-los pelo conector")
# 🔑 Pedido do dono (21/09/2026): "buscar pelo Claude os produtos iguais e
# vincular eles por lá". Fusão NÃO tem desfazer, então o caminho é: achar,
# ver a prévia, e só então fundir — e é assim que a suíte anda.
nome_igual = f"REPETIDO DO CLAUDE {marca_p}"
ids_iguais = []
for _ in range(2):
    st, _, p = pedir("POST", "/produtos", {"nome": nome_igual, "tipo": "INSUMO",
                                           "um_estoque": "KG"}, token=admin)
    ids_iguais.append(p["id"])
checar("preparo: dois cadastros com o mesmo nome", len(ids_iguais) == 2, ids_iguais)

st, _, r = rpc(escrita, "tools/call", {"name": "produtos_duplicados",
                                       "arguments": {"limite": 1000}})
duplicados = json.loads(r["result"]["content"][0]["text"])
grupo = next((g for g in duplicados if g.get("nome") == nome_igual), None)
checar("produtos_duplicados acha o par", grupo is not None,
       [g.get("nome") for g in duplicados[:3]])

fica, sai = ids_iguais
st, _, r = rpc(escrita, "tools/call", {"name": "previa_de_fusao",
                                       "arguments": {"id_produto": fica, "id_sai": sai}})
previa = json.loads(r["result"]["content"][0]["text"])
checar("a prévia diz o que a fusão faria, sem fazer",
       not r["result"]["isError"] and "pode" in previa, previa)
st, _, r = rpc(escrita, "tools/call", {"name": "detalhe_produto",
                                       "arguments": {"id_produto": sai}})
checar("e o que sairia continua lá depois da prévia",
       not r["result"]["isError"], r["result"]["content"][0]["text"][:80])

st, _, r = rpc(escrita, "tools/call", {"name": "fundir_produtos",
                                       "arguments": {"id_produto": fica, "id_sai": sai}})
checar("fundir_produtos junta os dois", not r["result"]["isError"],
       r["result"]["content"][0]["text"][:120])
with get_cursor() as cur:
    cur.execute("SELECT status, fundido_em FROM produtos WHERE id = %s", (sai,))
    absorvido = cur.fetchone()
    cur.execute("SELECT status FROM produtos WHERE id = %s", (fica,))
    sobrevivente = cur.fetchone()
checar("o que saiu fica marcado como absorvido",
       absorvido["fundido_em"] is not None, dict(absorvido))
checar("e o que ficou continua ativo", sobrevivente["status"] == "ATIVO", sobrevivente)
st, _, r = rpc(chave, "tools/call", {"name": "fundir_produtos",
                                     "arguments": {"id_produto": fica, "id_sai": sai}})
checar("chave só de leitura não funde nada",
       r["result"]["isError"] and "leitura" in r["result"]["content"][0]["text"], r)
pedir("DELETE", f"/produtos/{fica}", token=admin)


print("\n7g. fichas técnicas pelo conector")
# 🔑 Pedido do dono (24/09/2026): "disponibilizar a criação de Fichas Técnicas
# pelo Claude — ela tem muitas fichas em outros arquivos." O Claude lê o arquivo;
# aqui chega a receita já em ids, pela MESMA rota da tela.


def ferramenta(nome, args, token=None):
    _st, _, r = rpc(token or escrita, "tools/call", {"name": nome, "arguments": args})
    texto = r["result"]["content"][0]["text"]
    try:
        return r["result"]["isError"], json.loads(texto)
    except json.JSONDecodeError:
        return r["result"]["isError"], texto


ids_insumos = []
for nome, um in ((f"FARINHA DO CLAUDE {marca_p}", "KG"), (f"OVO DO CLAUDE {marca_p}", "UN")):
    st, _, p = pedir("POST", "/produtos", {"nome": nome, "tipo": "INSUMO", "um_estoque": um},
                     token=admin)
    ids_insumos.append(p["id"])
farinha, ovo = ids_insumos
erro, prato = ferramenta("criar_produto", {"nome": f"Bolo do Claude {marca_p}",
                                           "tipo": "PRODUZIDO", "um_estoque": "UN"})
checar("preparo: o prato nasce pelo conector, tipo PRODUZIDO", not erro and prato.get("id"),
       prato)
id_prato = prato["id"]

nomes_leitura_7g = {t["name"] for t in rpc(chave, "tools/list")[2]["result"]["tools"]}
checar("chave só de leitura não enxerga as ferramentas de ficha",
       not {"criar_ficha_tecnica", "atualizar_ficha_tecnica",
            "nova_versao_da_ficha"} & nomes_leitura_7g)

receita = {"id_produto": id_prato, "rendimento_qtd": 1, "rendimento_um": "KG",
           "porcoes": 10, "tempo_preparo_min": 50,
           "modo_preparo": "Misture tudo e asse por 40 minutos.",
           "itens": [{"id_insumo": farinha, "qtd_bruta": 500, "um": "G"},
                     {"id_insumo": ovo, "qtd_bruta": 3, "um": "UN"}]}
erro, criada = ferramenta("criar_ficha_tecnica", receita)
checar("criar_ficha_tecnica cria a ficha", not erro and criada.get("id"), criada)
id_ficha = criada.get("id")
erro, lida = ferramenta("ficha_tecnica", {"id_ficha": id_ficha})
checar("ela nasce RASCUNHO, com os dois itens e o modo de preparo",
       lida.get("status") == "RASCUNHO" and len(lida.get("itens") or []) == 2
       and lida.get("modo_preparo") == receita["modo_preparo"],
       {k: lida.get(k) for k in ("status", "modo_preparo")})
checar("e com os ingredientes na ORDEM do arquivo",
       [i.get("id_insumo") for i in lida.get("itens") or []] == [farinha, ovo],
       [i.get("id_insumo") for i in lida.get("itens") or []])
with get_cursor() as cur:
    cur.execute("""SELECT origem FROM auditoria WHERE entidade = 'ficha'
                    AND id_entidade = %s ORDER BY em DESC LIMIT 1""", (str(id_ficha),))
    linha = cur.fetchone()
checar("a auditoria marca que a ficha veio do Claude",
       (linha or {}).get("origem") == "claude", linha)

# ⚠️ As recusas são as da tela, e chegam ao Claude como erro com a frase.
erro, r = ferramenta("criar_ficha_tecnica", {**receita, "id_produto": farinha})
checar("ficha em INSUMO é recusada, dizendo para ajustar o tipo",
       erro and "produzido" in str(r).lower(), r)
erro, r = ferramenta("criar_ficha_tecnica", {**receita, "itens": [
    {"id_insumo": farinha, "id_subficha": id_ficha, "qtd_bruta": 1}]})
checar("linha com insumo E sub-ficha é recusada", erro and "OU" in str(r), r)
erro, r = ferramenta("criar_ficha_tecnica", {**receita, "itens": [
    {"id_insumo": farinha, "qtd_bruta": 0}]})
checar("quantidade zero é recusada dizendo QUAL campo", erro and "qtd_bruta" in str(r), r)

erro, r = ferramenta("atualizar_ficha_tecnica", {"id_ficha": id_ficha, "porcoes": 12,
    "itens": [{"id_insumo": farinha, "qtd_bruta": 600, "um": "G"},
              {"id_insumo": ovo, "qtd_bruta": 4, "um": "UN"}]})
checar("atualizar_ficha_tecnica corrige o rascunho", not erro, r)
erro, lida = ferramenta("ficha_tecnica", {"id_ficha": id_ficha})
checar("e grava as quantidades novas e as porções",
       float(lida.get("porcoes") or 0) == 12
       and sorted(float(i["qtd_bruta"]) for i in lida.get("itens") or []) == [4.0, 600.0],
       lida.get("itens"))

# 🔑 A homologação fica na TELA — o conector nem oferece.
checar("não existe ferramenta de homologar", "homologar_ficha" not in nomes_gravam)
st, _, _r = pedir("POST", f"/fichas/{id_ficha}/homologar", token=admin)
checar("preparo: a casa homologa pela tela", st == 200, (st, _r))
erro, r = ferramenta("atualizar_ficha_tecnica", {"id_ficha": id_ficha, "porcoes": 8})
checar("ficha homologada não se edita pelo conector",
       erro and "nova versão" in str(r), r)
erro, nova = ferramenta("nova_versao_da_ficha", {"id_ficha": id_ficha})
checar("nova_versao_da_ficha abre a versão 2 em rascunho",
       not erro and nova.get("versao") == 2, nova)
erro, lida = ferramenta("ficha_tecnica", {"id_ficha": nova.get("id")})
checar("com os itens copiados da homologada",
       lida.get("status") == "RASCUNHO" and len(lida.get("itens") or []) == 2, lida)

with get_cursor() as cur:
    cur.execute("SELECT id FROM fichas_tecnicas WHERE id_produto = %s", (id_prato,))
    fichas_do_prato = [x["id"] for x in cur.fetchall()]
    cur.execute("DELETE FROM ficha_itens WHERE id_ficha = ANY(%s)", (fichas_do_prato,))
    cur.execute("DELETE FROM ficha_modos WHERE id_ficha = ANY(%s)", (fichas_do_prato,))
    cur.execute("DELETE FROM fichas_tecnicas WHERE id = ANY(%s)", (fichas_do_prato,))
for i in (id_prato, farinha, ovo):
    pedir("DELETE", f"/produtos/{i}", token=admin)


print("\n7h. as tabelas em volta do produto e a foto da ficha, pelo conector")
# 🔑 Pedido do dono (26/09/2026): *"liberar as opções do produto em tabelas
# periféricas — onde o produto está, mais de uma prateleira, unidades de conversão
# quando há produtos vinculados, desativar — e gravar a foto da ficha do PDF."*
marca_h = str(time.time_ns() // 100)[-7:]
erro, prod = ferramenta("criar_produto", {"nome": f"Periferico do Claude {marca_h}",
                                          "tipo": "INSUMO", "um_estoque": "KG"})
checar("preparo: um produto novo", not erro and prod.get("id"), prod)
id_h = prod.get("id")
erro, locais_casa = ferramenta("locais", {})
ativos = [x["id"] for x in (locais_casa if isinstance(locais_casa, list) else [])
          if x.get("ativo", True)][:2]
checar("preparo: a loja tem ao menos duas prateleiras", len(ativos) == 2, locais_casa)
for id_local in ativos:
    erro, r = ferramenta("incluir_local_do_produto", {"id_produto": id_h, "id_local": id_local})
    checar(f"incluir_local_do_produto põe na prateleira {id_local}", not erro, r)
erro, onde = ferramenta("locais_do_produto", {"id_produto": id_h})
checar("locais_do_produto mostra as DUAS prateleiras",
       not erro and {x.get("id_local") for x in onde} >= set(ativos), onde)
erro, r = ferramenta("incluir_local_do_produto", {"id_produto": id_h, "id_local": ativos[0]})
checar("repetir não duplica", not erro and "já era" in str(r), r)
erro, r = ferramenta("tirar_local_do_produto", {"id_produto": id_h, "id_local": ativos[1]})
checar("tirar_local_do_produto tira a prateleira vazia", not erro, r)
erro, onde = ferramenta("locais_do_produto", {"id_produto": id_h})
checar("e ela sai da lista", ativos[1] not in {x.get("id_local") for x in onde}, onde)

erro, r = ferramenta("gravar_unidades_de_compra", {"id_produto": id_h, "itens": [
    {"um": "CX", "fator": 12, "padrao": True}, {"um": "UN", "fator": 0.5}]})
checar("gravar_unidades_de_compra grava a tabela de conversão", not erro, r)
erro, uns = ferramenta("unidades_de_compra", {"id_produto": id_h})
checar("unidades_de_compra devolve as duas, a padrão primeiro",
       not erro and [u["um"] for u in uns] == ["CX", "UN"] and uns[0]["padrao"], uns)
erro, r = ferramenta("gravar_unidades_de_compra", {"id_produto": id_h, "itens": [
    {"um": "KG", "fator": 3}]})
checar("a unidade de estoque com fator diferente de 1 é recusada", erro and "400" in str(r), r)

with get_cursor() as cur:
    cur.execute("""INSERT INTO codigos_externos (sistema, codigo, id_produto, origem_vinculo)
                   VALUES ('FORNECEDOR', %s, %s, 'FUSAO')""", (f"MEIO-{marca_h}", id_h))
erro, r = ferramenta("converter_codigo_vinculado", {"id_produto": id_h, "sistema": "FORNECEDOR",
                                                    "codigo": f"MEIO-{marca_h}", "fator": 0.5})
checar("converter_codigo_vinculado diz quanto vale o código do vinculado", not erro, r)
with get_cursor() as cur:
    cur.execute("SELECT fator, fator_confirmado FROM codigos_externos WHERE codigo = %s",
                (f"MEIO-{marca_h}",))
    cod = cur.fetchone()
checar("e grava o fator, confirmado", cod and float(cod["fator"]) == 0.5
       and cod["fator_confirmado"], cod)
erro, r = ferramenta("converter_codigo_vinculado", {"id_produto": id_h, "sistema": "FORNECEDOR",
                                                    "codigo": "NAO-EXISTE", "fator": 2})
checar("código que não é deste produto: 404", erro and "404" in str(r), r)

# A foto da ficha em base64: um PNG de verdade, pequeno.
from io import BytesIO  # noqa: E402

from PIL import Image  # noqa: E402

buf = BytesIO()
Image.new("RGB", (40, 30), (200, 120, 40)).save(buf, format="JPEG", quality=75)
foto64 = base64.b64encode(buf.getvalue()).decode()
erro, prato_h = ferramenta("criar_produto", {"nome": f"Prato com foto {marca_h}",
                                             "tipo": "PRODUZIDO", "um_estoque": "UN"})
erro, ficha_h = ferramenta("criar_ficha_tecnica", {"id_produto": prato_h.get("id"),
                                                   "rendimento_um": "UN", "itens": [
    {"id_insumo": id_h, "qtd_bruta": 0.2, "um": "KG"}]})
checar("preparo: uma ficha nova", not erro and ficha_h.get("id"), ficha_h)
erro, r = ferramenta("enviar_foto_da_ficha", {"id_ficha": ficha_h.get("id"),
                                              "imagem_base64": "data:image/jpeg;base64," + foto64})
checar("enviar_foto_da_ficha grava a foto (aceita o prefixo data:)",
       not erro and str(r.get("foto_url", "")).startswith("/arquivos/"), r)
erro, lida = ferramenta("ficha_tecnica", {"id_ficha": ficha_h.get("id")})
checar("e a ficha passa a apontar para ela", lida.get("foto_url") == r.get("foto_url"), lida)
erro, r = ferramenta("enviar_foto_da_ficha", {"id_ficha": ficha_h.get("id"),
                                              "imagem_base64": base64.b64encode(
                                                  b"isto nao e imagem nenhuma").decode()})
checar("texto que não é imagem é recusado (400)", erro and "400" in str(r), r)
erro, r = ferramenta("enviar_foto_da_ficha", {"id_ficha": ficha_h.get("id"),
                                              "imagem_base64": "@@@ nao e base64 @@@@"})
checar("base64 inválido é recusado", erro and "400" in str(r), r)
erro, r = ferramenta("enviar_foto_da_ficha", {"id_ficha": ficha_h.get("id"),
                                              "imagem_base64": foto64}, token=chave)
checar("a chave de leitura não grava foto", erro, r)

erro, r = ferramenta("desativar_produto", {"id_produto": id_h})
checar("desativar_produto desativa", not erro, r)
erro, d = ferramenta("detalhe_produto", {"id_produto": id_h})
checar("e o produto fica inativo", d.get("ativo") is False, d.get("ativo"))
erro, r = ferramenta("atualizar_produto", {"id_produto": id_h, "ativo": True})
erro, d = ferramenta("detalhe_produto", {"id_produto": id_h})
checar("reativar é pelo atualizar_produto", d.get("ativo") is True, d.get("ativo"))

with get_cursor() as cur:
    cur.execute("DELETE FROM ficha_itens WHERE id_ficha = %s", (ficha_h.get("id"),))
    cur.execute("SELECT foto_url FROM fichas_tecnicas WHERE id = %s", (ficha_h.get("id"),))
    cur.execute("DELETE FROM arquivos WHERE dono = %s", (f"ficha-{ficha_h.get('id')}",))
    cur.execute("DELETE FROM fichas_tecnicas WHERE id = %s", (ficha_h.get("id"),))
    cur.execute("DELETE FROM codigos_externos WHERE codigo = %s", (f"MEIO-{marca_h}",))
    cur.execute("DELETE FROM produto_unidades WHERE id_produto = %s", (id_h,))
    cur.execute("DELETE FROM estoque_saldos WHERE id_produto = %s AND quantidade = 0", (id_h,))
for i in (id_h, prato_h.get("id")):
    pedir("DELETE", f"/produtos/{i}", token=admin)


print("\n7f. conectar pelo claude.ai autorizando a ALTERAR")
# 🔑 Pedido do dono (21/09/2026), depois de topar na prática: as ferramentas de
# gravação não apareciam para a conexão do claude.ai, que nascia só de leitura.
# Agora a própria pessoa decide na página de entrada, numa caixa que nasce
# DESMARCADA — vir marcada transformaria um clique distraído em permissão.
st, _, pagina = pedir("GET", url_autorizar(client_id, pkce()[1]))
checar("a página oferece a caixa de alterar", 'name="escrita"' in pagina, st)
depois_da_caixa = pagina.split('name="escrita"')[1][:60]
checar("e ela nasce desmarcada", "checked" not in depois_da_caixa, depois_da_caixa)

verificador, desafio = pkce()
st, cab, _ = enviar_formulario(url_autorizar(client_id, desafio), ADMIN[0], ADMIN[1],
                               escrita=True)
st, _, com_escrita = pedir("POST", "/oauth/token", form={
    "grant_type": "authorization_code", "code": parametros_da_volta(cab)["code"],
    "redirect_uri": VOLTA, "client_id": client_id, "code_verifier": verificador})
checar("a chave sai com o escopo de escrita",
       "botane.escrita" in (com_escrita.get("scope") or ""), com_escrita.get("scope"))
st, _, r = rpc(com_escrita["access_token"], "tools/list")
checar("e enxerga as ferramentas de gravação",
       "fundir_produtos" in {t["name"] for t in r["result"]["tools"]})
st, _, r = rpc(com_escrita["access_token"], "tools/call", {"name": "criar_produto",
               "arguments": {"nome": f"Pelo claude.ai {marca_p}", "tipo": "INSUMO",
                             "um_estoque": "KG"}})
criado_oauth = json.loads(r["result"]["content"][0]["text"])
checar("e grava de verdade", not r["result"]["isError"] and criado_oauth.get("id"), r)
pedir("DELETE", f"/produtos/{criado_oauth['id']}", token=admin)

st, _, renovada = pedir("POST", "/oauth/token", form={
    "grant_type": "refresh_token", "refresh_token": com_escrita["refresh_token"],
    "client_id": client_id})
checar("a renovação PRESERVA o que foi autorizado",
       "botane.escrita" in (renovada.get("scope") or ""), renovada.get("scope"))
st, _, r = rpc(renovada["access_token"], "tools/list")
checar("e a chave renovada continua gravando",
       "fundir_produtos" in {t["name"] for t in r["result"]["tools"]})
# ⚠️ Acha a linha pelo PREFIXO da chave, não "a primeira de escrita": a suíte
# tem outras conexões vivas (o bloco 6 usa uma), e revogar a do vizinho faria os
# blocos seguintes falharem por um defeito que não existe. Foi o que aconteceu.
def _linha_da_chave(valor):
    _, _, linhas = pedir("GET", "/auth/me/tokens", token=admin)
    return next((t for t in linhas if valor.startswith(t["prefixo"])
                 and not t["revogado_em"]), None)


viva_escrita = _linha_da_chave(renovada["access_token"])
checar("a conexão aparece em 'minhas' como quem altera",
       viva_escrita is not None and not viva_escrita["somente_leitura"], viva_escrita)
if viva_escrita:
    pedir("DELETE", f"/auth/me/tokens/{viva_escrita['id']}", token=admin)

# ⚠️ Sem marcar, continua só de leitura — é o padrão, e é o que vale para quem
# só aperta "Entrar e permitir".
verificador, desafio = pkce()
st, cab, _ = enviar_formulario(url_autorizar(client_id, desafio), ADMIN[0], ADMIN[1])
st, _, sem_escrita = pedir("POST", "/oauth/token", form={
    "grant_type": "authorization_code", "code": parametros_da_volta(cab)["code"],
    "redirect_uri": VOLTA, "client_id": client_id, "code_verifier": verificador})
checar("sem marcar, a conexão nasce só de leitura",
       "botane.escrita" not in (sem_escrita.get("scope") or ""), sem_escrita.get("scope"))
st, _, r = rpc(sem_escrita["access_token"], "tools/list")
checar("e ela não vê as ferramentas de gravação",
       "fundir_produtos" not in {t["name"] for t in r["result"]["tools"]})
so_leitura = _linha_da_chave(sem_escrita["access_token"])
if so_leitura:
    pedir("DELETE", f"/auth/me/tokens/{so_leitura['id']}", token=admin)


print("\n8. a conexão aparece na tela")
st, _, lista = pedir("GET", "/usuarios/1/tokens", token=admin)
conexao = next((t for t in lista if t["nome"] == "Claude (suíte)" and not t["revogado_em"]), {})
checar("na lista do usuário, com origem oauth", conexao.get("origem") == "oauth", conexao)
checar("vencendo pela renovação (dias), não pela chave (1 h)",
       conexao.get("vence_em", "") > conexao.get("expira_em", ""), conexao)
st, _, minhas = pedir("GET", "/auth/me/tokens", token=admin)
checar("e em 'minhas'", any(t["id"] == conexao.get("id") for t in minhas), st)
st, _, _ = pedir("GET", "/auth/me/tokens", token=chave)
checar("a chave não lista as próprias chaves", st == 403, st)

print("\n9. renovação")
st, _, nova = pedir("POST", "/oauth/token", form={
    "grant_type": "refresh_token", "refresh_token": tk["refresh_token"], "client_id": client_id})
checar("renovar devolve chave e renovação novas",
       st == 200 and nova.get("access_token") != chave
       and nova.get("refresh_token") != tk["refresh_token"], (st, nova))
st, _, _ = rpc(chave, "ping")
checar("a chave antiga morre na renovação", st == 401, st)
st, _, r = rpc(nova["access_token"], "ping")
checar("a nova responde", st == 200 and "result" in r, (st, r))
st, _, r = pedir("POST", "/oauth/token", form={
    "grant_type": "refresh_token", "refresh_token": tk["refresh_token"], "client_id": client_id})
checar("a renovação antiga não serve mais", st == 400, (st, r))
st, _, lista = pedir("GET", "/usuarios/1/tokens", token=admin)
checar("e continua sendo UMA linha", sum(1 for t in lista if t["id"] == conexao.get("id")) == 1
       and sum(1 for t in lista if t["nome"] == "Claude (suíte)" and not t["revogado_em"]) == 1)

print("\n10. revogar")
st, _, _ = pedir("POST", "/oauth/revogar", form={"token": nova["refresh_token"],
                                                   "client_id": client_id})
checar("revogar (RFC 7009) responde 200", st == 200, st)
st, _, _ = rpc(nova["access_token"], "ping")
checar("e derruba a conexão inteira", st == 401, st)
st, _, _ = pedir("POST", "/oauth/revogar", form={"token": "btn_qualquer", "client_id": client_id})
checar("chave desconhecida também responde 200", st == 200, st)

verificador, desafio = pkce()
st, cab, _ = enviar_formulario(url_autorizar(client_id, desafio), ADMIN[0], ADMIN[1])
st, _, tk2 = pedir("POST", "/oauth/token", form={
    "grant_type": "authorization_code", "code": parametros_da_volta(cab)["code"],
    "redirect_uri": VOLTA, "client_id": client_id, "code_verifier": verificador})
_, _, minhas = pedir("GET", "/auth/me/tokens", token=admin)
viva = next(t for t in minhas if t["nome"] == "Claude (suíte)" and not t["revogado_em"])
st, _, _ = pedir("DELETE", f"/auth/me/tokens/{viva['id']}", token=admin)
checar("desconectar pelo Perfil responde 200", st == 200, st)
st, _, _ = rpc(tk2["access_token"], "ping")
checar("e a conexão para na hora", st == 401, st)

print(f"\n{ok} passaram, {len(falhas)} falharam")
if falhas:
    for f in falhas:
        print("  -", f)
    sys.exit(1)
