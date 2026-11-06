"""O assistente pelo WhatsApp (etapa 1, migração 151): o número da casa e o vínculo do PRÓPRIO
telefone.

🔑 **Pedido do dono (06/11/2026):** *"no meu usuário vou vincular o meu número de telefone…"*, e
*"este número poderia ser compartilhado entre lojas"* — por isso o número é UM, da casa, e se
configura em Integrações (`admin.integracoes`), não na loja. A regra está em
`services/assistente.py`; o estudo em `docs/assistente-whatsapp-estudo.md`.

⚠️ **Cada um mexe só no próprio vínculo**: o `id_usuario` vem do login, nunca da requisição.
Quem perde a permissão ou é desativado deixa de ser atendido na hora — o webhook confere as
duas coisas a cada mensagem.
"""

from fastapi import APIRouter, Depends

import auditoria
from config import API_URL_PUBLICA
from database import get_cursor
from models.assistente import ConfigAssistente
from seguranca import Contexto, requer_permissao
from services import assistente as servico

router = APIRouter(prefix="/assistente", tags=["assistente"])
_PODE = requer_permissao(servico.PERMISSAO)
_CONFIGURAR = requer_permissao("admin.integracoes")


# ---------------------------------------------------------------- o número (Integrações)
@router.get("/config")
def ver_config(ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    with get_cursor() as cur:
        return servico.configuracao(cur, API_URL_PUBLICA)


@router.put("/config")
def salvar_config(body: ConfigAssistente, ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    with get_cursor() as cur:
        servico.salvar(cur, body)
        # ⚠️ Nada de segredo na auditoria: só se foi trocado.
        auditoria.registrar(cur, ctx.id_usuario, "integracao", servico.SERVICO, "configurar",
                            depois={"ativa": body.ativa, "modo": body.modo, "numero": body.numero,
                                    "phone_number_id": body.phone_number_id,
                                    "token_trocado": bool((body.token or "").strip()),
                                    "segredo_trocado": bool((body.app_secret or "").strip())})
        return servico.configuracao(cur, API_URL_PUBLICA) | {"message": "Assistente gravado."}


# ---------------------------------------------------------------- o vínculo (Perfil)
@router.get("/vinculo")
def obter(ctx: Contexto = Depends(_PODE)) -> dict:
    with get_cursor() as cur:
        return servico.estado(cur, ctx)


@router.post("/vinculo/codigo")
def gerar_codigo(ctx: Contexto = Depends(_PODE)) -> dict:
    """Um código para mandar do próprio WhatsApp ao número do assistente (15 minutos)."""
    with get_cursor() as cur:
        return servico.gerar_codigo(cur, ctx) | {
            "message": "Código gerado: mande-o pelo seu WhatsApp em até 15 minutos."}


@router.delete("/vinculo")
def desvincular(ctx: Contexto = Depends(_PODE)) -> dict:
    with get_cursor() as cur:
        servico.desvincular(cur, ctx)
        return servico.estado(cur, ctx) | {"message": "WhatsApp desligado do seu usuário."}
