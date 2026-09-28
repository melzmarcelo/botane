"""WhatsApp — a aba da loja (configuração, avisos, teste, histórico) e o webhook da Meta.

🔑 **Pedido do dono (28/09/2026):** *"tudo configurável, numa aba nova dentro da loja: a loja
faz toda a validação com a Meta e só informa como vamos usar."* A regra está em
`services/whatsapp.py`; o estudo em `docs/whatsapp-estudo.md`.

⚠️ **`admin.unidades`**, a chave da tela de Lojas: é configuração da loja, e guarda o token
dela. O token e o segredo nunca voltam na resposta.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

import auditoria
from config import API_URL_PUBLICA
from database import get_cursor
from models.whatsapp import ConfigWhatsapp, TesteWhatsapp
from paginacao import pagina
from seguranca import Contexto, requer_permissao
from services import whatsapp as servico

router = APIRouter(prefix="/unidades/{id_unidade}/whatsapp", tags=["WhatsApp"])
publico = APIRouter(prefix="/publico/whatsapp", tags=["WhatsApp"])
_ADMIN = requer_permissao("admin.unidades")


def _loja(cur, ctx: Contexto, id_unidade: int) -> None:
    cur.execute("SELECT 1 FROM unidades WHERE id = %s", (id_unidade,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Loja não encontrada.")
    if not ctx.ve_unidade(id_unidade):
        raise HTTPException(status_code=403, detail="Sem acesso a esta loja.")


@router.get("")
def obter(id_unidade: int, ctx: Contexto = Depends(_ADMIN)) -> dict:
    with get_cursor() as cur:
        _loja(cur, ctx, id_unidade)
        return servico.configuracao(cur, id_unidade, API_URL_PUBLICA)


@router.put("")
def salvar(id_unidade: int, body: ConfigWhatsapp, ctx: Contexto = Depends(_ADMIN)) -> dict:
    with get_cursor() as cur:
        _loja(cur, ctx, id_unidade)
        servico.salvar(cur, id_unidade, body)
        # ⚠️ Nada de segredo na auditoria: só se foi trocado.
        auditoria.registrar(cur, ctx.id_usuario, "whatsapp", id_unidade, "configurar",
                            depois={"ativa": body.ativa, "modo": body.modo,
                                    "phone_number_id": body.phone_number_id,
                                    "token_trocado": bool((body.token or "").strip()),
                                    "segredo_trocado": bool((body.app_secret or "").strip()),
                                    "avisos": {a.evento: a.ativo for a in body.avisos}},
                            id_unidade=id_unidade)
        return servico.configuracao(cur, id_unidade, API_URL_PUBLICA) | {
            "message": "WhatsApp da loja gravado."}


@router.post("/teste")
def testar(id_unidade: int, body: TesteWhatsapp, ctx: Contexto = Depends(_ADMIN)) -> dict:
    """Uma mensagem de exemplo do aviso escolhido, para o número informado.

    ⚠️ Sai pela FILA como qualquer outra — é o que prova o caminho inteiro. Precisa do
    WhatsApp ligado na loja; o aviso em si não precisa estar ligado.
    """
    if body.evento not in servico.EVENTOS:
        raise HTTPException(status_code=400, detail="Aviso desconhecido.")
    exemplo = {"nome": "Cliente", "casa": "", "data": "31/12", "hora": "12:00", "pessoas": 2,
               "premio": "Um almoço grátis", "vence": "31/12/2026", "codigo": "TESTE1"}
    with get_cursor() as cur:
        _loja(cur, ctx, id_unidade)
        exemplo["casa"] = servico._casa(cur, id_unidade)
        variaveis = [exemplo[v] for v in servico.EVENTOS[body.evento]["variaveis"]]
        ok = servico.enfileirar(cur, id_unidade, body.evento, f"teste:{secrets.token_hex(4)}",
                                body.telefone, variaveis, nome="Teste", ignorar_aviso=True)
        if not ok:
            raise HTTPException(
                status_code=400,
                detail="Não entrou na fila: ligue o WhatsApp na loja e confira o telefone (com DDD).")
    enviados = servico.processar_fila()
    return {"message": "Mensagem de teste enviada para a fila"
                       + (" e processada — veja o histórico." if enviados else ".")}


@router.get("/mensagens")
def mensagens(id_unidade: int, resposta: Response,
              status: str | None = Query(None, max_length=12),
              limite: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
              ctx: Contexto = Depends(_ADMIN)) -> list[dict]:
    """O histórico: para quem, qual aviso, quando e o que aconteceu com cada mensagem."""
    with get_cursor() as cur:
        _loja(cur, ctx, id_unidade)
        linhas = pagina(
            cur,
            """SELECT id, evento, telefone, nome, texto, status, agendada_para, enviada_em,
                      erro, tentativas, resposta, respondida_em, criada_em, id_reserva
                 FROM whatsapp_mensagens
                WHERE id_unidade = %s AND (%s::text IS NULL OR status = %s)
                ORDER BY criada_em DESC, id DESC""",
            (id_unidade, status, status), limite=limite, offset=offset, resposta=resposta)
    for x in linhas:
        for campo in ("agendada_para", "enviada_em", "respondida_em", "criada_em"):
            x[campo] = x[campo].isoformat() if x[campo] else None
        x["aviso"] = servico.EVENTOS.get(x["evento"], {}).get("nome", "Resposta ao cliente")
    return linhas


# ---------------------------------------------------------------- o webhook da Meta
@publico.get("/webhook")
def verificar(request: Request) -> Response:
    """A Meta confere o endereço: devolve o `hub.challenge` se o token for de alguma loja."""
    q = request.query_params
    with get_cursor() as cur:
        ok = q.get("hub.mode") == "subscribe" and servico.verificar_webhook(
            cur, q.get("hub.verify_token"))
    if not ok:
        raise HTTPException(status_code=403, detail="Token de verificação não confere.")
    return Response(q.get("hub.challenge") or "", media_type="text/plain")


@publico.post("/webhook")
async def receber(request: Request) -> dict:
    """Estados das mensagens e respostas dos clientes. ⚠️ Assinatura conferida no serviço."""
    corpo = await request.body()
    with get_cursor() as cur:
        return servico.receber(cur, corpo, request.headers.get("X-Hub-Signature-256"))
