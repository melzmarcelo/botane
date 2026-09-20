"""O conector MCP do Claude — `POST /mcp`, transporte Streamable HTTP, sem sessão.

🔑 **Sem biblioteca, de propósito.** O SDK `mcp` puxa `uvicorn`, `starlette` e
`pydantic` mais novos que os presos em `requirements.txt` — instalá-lo aqui
trocaria o servidor que passou na bateria. O que um servidor só de ferramentas
precisa do protocolo cabe neste arquivo: JSON-RPC 2.0 em POST, resposta JSON,
e quatro métodos (`initialize`, `ping`, `tools/list`, `tools/call`).

🔑 **Sem sessão (`Mcp-Session-Id`)**: cada pedido traz a chave e se basta. Não
há estado para perder quando o App Platform reinicia o contêiner.

⚠️ **Quem entra**: chave `btn_` (do OAuth do claude.ai ou gerada à mão na tela)
com a permissão `integracao.claude`. Sem chave, 401 com `WWW-Authenticate`
apontando os metadados — é assim que o claude.ai descobre onde fazer login.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from seguranca import contexto_da_credencial
from services import mcp_ferramentas as catalogo
from services import oauth

router = APIRouter(tags=["conector do Claude"])

# Da mais nova para a mais velha. Cliente que pede uma destas recebe ela mesma;
# o que pedir outra recebe a primeira, e decide se continua (é o que a
# especificação manda).
VERSOES = ["2025-11-25", "2025-06-18", "2025-03-26"]


def _erro_rpc(id_, codigo: int, msg: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": codigo, "message": msg}}


def _nao_autorizado(descricao: str, status: int = 401) -> Response:
    erro = "invalid_token" if status == 401 else "insufficient_scope"
    # ⚠️ A frase fica só no CORPO: cabeçalho HTTP é latin-1, e "▸" ali
    # derrubaria a resposta inteira com erro de codificação.
    return JSONResponse(
        {"error": erro, "error_description": descricao}, status_code=status,
        headers={"WWW-Authenticate":
                 f'Bearer resource_metadata="{oauth.url_metadados_recurso()}", '
                 f'error="{erro}"'})


@router.get("/mcp")
@router.delete("/mcp")
def sem_fluxo() -> Response:
    """Sem sessão e sem notificação do servidor: não há fluxo SSE para abrir."""
    return Response(status_code=405, headers={"Allow": "POST"})


@router.post("/mcp")
async def mcp(request: Request) -> Response:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return _nao_autorizado("Conecte-se ao Botané para usar este conector.")
    credencial = auth[7:]
    try:
        # ⚠️ `escreve=False`: o POST é do protocolo, não uma alteração. Cada
        # ferramenta vira um GET por dentro, que passa pela conferência de novo.
        # Vai ao banco: no threadpool, para não travar o laço assíncrono.
        ctx = await run_in_threadpool(contexto_da_credencial, credencial, escreve=False)
    except HTTPException as e:
        if e.status_code == 401:
            return _nao_autorizado(str(e.detail))
        return JSONResponse({"detail": e.detail}, status_code=e.status_code)
    if not ctx.pode(oauth.PERMISSAO):
        return _nao_autorizado(
            "Seu usuário não tem a permissão de conectar o Claude (Papéis ▸ Conectar o Claude).",
            403)

    try:
        msg = await request.json()
    except ValueError:
        return JSONResponse(_erro_rpc(None, -32700, "JSON inválido"), status_code=400)
    if isinstance(msg, list):
        # O lote saiu do protocolo em 2025-06-18; quem ainda manda recebe o motivo.
        return JSONResponse(_erro_rpc(None, -32600, "Lote não suportado: um pedido por POST."),
                            status_code=400)
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return JSONResponse(_erro_rpc(None, -32600, "Pedido JSON-RPC inválido"), status_code=400)

    metodo = msg.get("method")
    # Notificação (sem `id`) e resposta a pedido nosso: nada a devolver.
    if "id" not in msg or metodo is None:
        return Response(status_code=202)
    id_ = msg["id"]
    params = msg.get("params") or {}

    if metodo == "initialize":
        pedida = params.get("protocolVersion")
        resultado = {
            "protocolVersion": pedida if pedida in VERSOES else VERSOES[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "botane", "title": "Botané", "version": request.app.version},
            "instructions": catalogo.INSTRUCOES,
        }
    elif metodo == "ping":
        resultado = {}
    elif metodo == "tools/list":
        # 🔑 **Chave só de leitura não VÊ as ferramentas que gravam.** Escondê-las
        # é conforto — quem barra de verdade é `contexto_da_credencial`, que dá
        # 403 no POST lá dentro —, mas evita o modelo propor ao usuário uma ação
        # que vai falhar, e evita a conversa inteira andar para esse lado.
        pode_gravar = ctx.token_so_leitura is False
        resultado = {"tools": [f.descritor() for f in catalogo.FERRAMENTAS
                               if pode_gravar or not f.grava]}
    elif metodo == "tools/call":
        nome = params.get("name")
        if nome not in catalogo.POR_NOME:
            return JSONResponse(_erro_rpc(id_, -32602, f"Ferramenta desconhecida: {nome}"))
        if catalogo.POR_NOME[nome].grava and ctx.token_so_leitura is not False:
            return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": {
                "content": [{"type": "text", "text":
                             "Esta chave de acesso é só de leitura. Para alterar, peça ao "
                             "administrador uma chave marcada como \"permite alterar\" em "
                             "Usuários ▸ Chaves de acesso."}],
                "isError": True}})
        try:
            texto = await catalogo.chamar(request.app, credencial, nome,
                                          params.get("arguments") or {})
            resultado = {"content": [{"type": "text", "text": texto}], "isError": False}
        except catalogo.ErroFerramenta as e:
            # 🔑 Erro de FERRAMENTA não é erro de protocolo: volta como resultado
            # com `isError`, para o modelo ler a frase e corrigir o pedido.
            resultado = {"content": [{"type": "text", "text": str(e)}], "isError": True}
    else:
        return JSONResponse(_erro_rpc(id_, -32601, f"Método não suportado: {metodo}"))

    return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": resultado})
