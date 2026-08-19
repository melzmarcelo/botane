"""Configuração do envio de e-mail (SMTP).

Fica separado do Omie porque não é integração de dado: é o canal por onde o
sistema fala com as pessoas — hoje só a recuperação de senha, amanhã o aviso de
vencimento. Enquanto ninguém configurar, o sistema segue funcionando em modo
simulado, gravando as mensagens em arquivo.

A senha do servidor é cifrada e **nunca volta pela API** — só mascarada, do
mesmo jeito que a chave do Omie.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import auditoria
from database import get_cursor
from seguranca import Contexto, requer_permissao
from services import email as correio
from services import segredos

router = APIRouter(prefix="/email", tags=["E-mail"])

SERVICO = "SMTP"


class ConfigEmail(BaseModel):
    servidor: str | None = Field(default=None, max_length=120)
    porta: int | None = Field(default=None, ge=1, le=65535)
    seguranca: str = "starttls"                  # starttls | ssl | nenhuma
    usuario: str | None = Field(default=None, max_length=160)
    senha: str | None = Field(default=None, max_length=200)
    remetente_nome: str | None = Field(default=None, max_length=120)
    remetente_email: str | None = Field(default=None, max_length=160)
    modo: str = "simulado"                       # simulado | real
    ativa: bool = False


class TesteEmail(BaseModel):
    para: str = Field(min_length=3, max_length=160)


@router.get("/config")
def obter(ctx: Contexto = Depends(requer_permissao("admin.integracoes"))) -> dict:
    with get_cursor() as cur:
        cur.execute(
            """SELECT config, credenciais, ativa, modo, ultimo_status, ultima_mensagem
                 FROM integracoes WHERE servico = %s AND id_unidade IS NULL""",
            (SERVICO,),
        )
        linha = cur.fetchone()
    cfg = dict(linha["config"] or {}) if linha else {}
    cred = segredos.decifrar(linha["credenciais"]) if linha else {}
    return {
        "configurada": bool(cfg.get("servidor")),
        "modo": linha["modo"] if linha else "simulado",
        "ativa": linha["ativa"] if linha else False,
        "servidor": cfg.get("servidor"),
        "porta": cfg.get("porta"),
        "seguranca": cfg.get("seguranca") or "starttls",
        "usuario": cfg.get("usuario"),
        "remetente_nome": cfg.get("remetente_nome"),
        "remetente_email": cfg.get("remetente_email"),
        "senha": segredos.mascarar(cred.get("senha")),
        "ultimo_status": linha["ultimo_status"] if linha else None,
        "ultima_mensagem": linha["ultima_mensagem"] if linha else None,
        "pasta_simulado": correio.PASTA,
    }


@router.put("/config")
def salvar(body: ConfigEmail,
           ctx: Contexto = Depends(requer_permissao("admin.integracoes"))) -> dict:
    if body.modo not in ("simulado", "real"):
        raise HTTPException(status_code=400, detail="Modo deve ser 'simulado' ou 'real'.")
    if body.seguranca not in ("starttls", "ssl", "nenhuma"):
        raise HTTPException(status_code=400, detail="Segurança deve ser starttls, ssl ou nenhuma.")
    if body.modo == "real" and not body.servidor:
        raise HTTPException(status_code=400, detail="Para o modo real informe o servidor SMTP.")

    with get_cursor() as cur:
        cur.execute(
            "SELECT credenciais FROM integracoes WHERE servico = %s AND id_unidade IS NULL",
            (SERVICO,),
        )
        atual = cur.fetchone()
        cred = segredos.decifrar(atual["credenciais"]) if atual else {}
        # Campo em branco mantém a senha guardada: a tela mostra mascarada, e
        # salvar outra coisa não pode apagá-la sem querer.
        if body.senha:
            cred["senha"] = body.senha

        config = {
            "servidor": (body.servidor or "").strip() or None,
            "porta": body.porta or (465 if body.seguranca == "ssl" else 587),
            "seguranca": body.seguranca,
            "usuario": (body.usuario or "").strip() or None,
            "remetente_nome": (body.remetente_nome or "").strip() or None,
            "remetente_email": (body.remetente_email or "").strip() or None,
        }
        cur.execute(
            # `ON CONFLICT (id_unidade, servico)` NÃO serve aqui: id_unidade é
            # NULL (o SMTP é da casa toda) e nulos são distintos entre si no
            # Postgres, então o conflito nunca aconteceria e cada gravação criaria
            # outra linha. Quem garante a unicidade é o índice parcial da migração
            # 012, e é ele que o ON CONFLICT precisa nomear.
            """INSERT INTO integracoes (id_unidade, servico, ativa, modo, credenciais, config)
               VALUES (NULL, %s, %s, %s, %s, %s)
               ON CONFLICT (servico) WHERE id_unidade IS NULL DO UPDATE
                   SET ativa = EXCLUDED.ativa, modo = EXCLUDED.modo,
                       credenciais = EXCLUDED.credenciais, config = EXCLUDED.config,
                       atualizado_em = now()""",
            (SERVICO, body.ativa, body.modo, segredos.cifrar(cred),
             __import__("json").dumps(config)),
        )
        # A auditoria registra QUE a credencial mudou, não a credencial — nem
        # mascarada. Pedaço de senha em histórico não ajuda ninguém a investigar
        # nada, e vira vazamento no dia em que o mascaramento regredir.
        auditoria.registrar(cur, ctx.id_usuario, "integracao", SERVICO, "configurar",
                            depois={"modo": body.modo, "servidor": config["servidor"],
                                    "credencial_alterada": bool(body.senha)})
    return {"message": "Configuração de e-mail salva"}


@router.post("/testar")
def testar(body: TesteEmail,
           ctx: Contexto = Depends(requer_permissao("admin.integracoes"))) -> dict:
    with get_cursor() as cur:
        try:
            r = correio.testar(cur, body.para.strip())
            status, mensagem = "OK", r["detalhe"]
        except correio.ErroEmail as e:
            status, mensagem = "ERRO", e.mensagem
        cur.execute(
            """UPDATE integracoes SET ultimo_status = %s, ultima_mensagem = %s
                WHERE servico = %s AND id_unidade IS NULL""",
            (status, mensagem, SERVICO),
        )
        if status == "ERRO":
            raise HTTPException(status_code=502, detail=mensagem)
    return r
