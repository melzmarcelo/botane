"""As traduções do cardápio do site (inglês e alemão) — ver, corrigir, gerar de novo.

🔑 Pedido do dono (decidido em 29/09/2026): Claude Haiku, categorias também, site nos três
idiomas. A regra mora em `services/traducao.py`.
"""

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import auditoria
from database import get_cursor
from seguranca import Contexto, requer_permissao
from services import segredos
from services import traducao as servico

router = APIRouter(prefix="/traducao", tags=["Tradução"])

Tipo = Literal["produto", "categoria", "subcategoria", "catalogo"]
# Quem vê o catálogo vê as traduções; quem edita catálogo ou produto corrige.
_VER = requer_permissao("catalogos.ver", "catalogos.editar", "cadastros.produtos")
_EDITAR = requer_permissao("catalogos.editar", "cadastros.produtos")
# 🔑 A chave da Anthropic é credencial da casa: quem configura integração (como SMTP e Omie).
_CONFIGURAR = requer_permissao("admin.integracoes")


class TextosDoIdioma(BaseModel):
    nome: str | None = Field(default=None, max_length=160)
    descricao: str | None = Field(default=None, max_length=700)


class TraducaoManual(BaseModel):
    en: TextosDoIdioma | None = None
    de: TextosDoIdioma | None = None


class ConfigTraducao(BaseModel):
    # Em branco mantém a chave guardada: a tela só a mostra mascarada.
    chave: str | None = Field(default=None, max_length=300)
    modelo: str | None = Field(default=None, max_length=80)
    ativa: bool = True


def _ver_config(cur) -> dict:
    cfg = servico._config(cur)
    cur.execute("""SELECT ultimo_status, ultima_mensagem FROM integracoes
                    WHERE servico = %s AND id_unidade IS NULL""", (servico.SERVICO,))
    l = cur.fetchone() or {}
    return {"ativa": cfg["ativa"], "ligada": bool(cfg["ativa"] and cfg["chave"]),
            "chave": segredos.mascarar(cfg["chave"]) if cfg["chave"] else None,
            "modelo": cfg["modelo"], "modelo_padrao": servico.MODELO_PADRAO,
            "credencial_ilegivel": cfg["ilegivel"],
            "ultimo_status": l.get("ultimo_status"), "ultima_mensagem": l.get("ultima_mensagem")}


@router.get("/config")
def ver_config(ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    """A chave da Anthropic da casa — ⚠️ só mascarada, nunca inteira."""
    with get_cursor() as cur:
        return _ver_config(cur)


@router.put("/config")
def salvar_config(body: ConfigTraducao, ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    chave = (body.chave or "").strip()
    if chave and not chave.startswith("sk-ant-"):
        raise HTTPException(status_code=422,
                            detail="Isso não parece uma chave da Anthropic (ela começa com sk-ant-).")
    with get_cursor() as cur:
        cur.execute("SELECT credenciais FROM integracoes WHERE servico = %s AND id_unidade IS NULL",
                    (servico.SERVICO,))
        atual = cur.fetchone()
        cred = segredos.decifrar(atual["credenciais"]) if atual else {}
        if chave:
            cred["chave"] = chave
        modelo = (body.modelo or "").strip() or servico.MODELO_PADRAO
        cur.execute(
            # ⚠️ O índice parcial da 012 (serviço da casa toda, id_unidade nulo) — o mesmo do SMTP.
            """INSERT INTO integracoes (id_unidade, servico, ativa, modo, credenciais, config)
               VALUES (NULL, %s, %s, 'real', %s, %s)
               ON CONFLICT (servico) WHERE id_unidade IS NULL DO UPDATE
                   SET ativa = EXCLUDED.ativa, credenciais = EXCLUDED.credenciais,
                       config = EXCLUDED.config, atualizado_em = now()""",
            (servico.SERVICO, body.ativa, segredos.cifrar(cred), json.dumps({"modelo": modelo})))
        # A auditoria diz QUE a chave mudou — nunca a chave, nem mascarada.
        auditoria.registrar(cur, ctx.id_usuario, "integracao", servico.SERVICO, "configurar",
                            depois={"ativa": body.ativa, "modelo": modelo, "chave_trocada": bool(chave)})
        return _ver_config(cur) | {"message": "Configuração salva."}


@router.delete("/config/chave")
def apagar_chave(ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    """Tira a chave (a casa trocou de conta, ou não quer mais pagar pela tradução)."""
    with get_cursor() as cur:
        cur.execute("""UPDATE integracoes SET credenciais = %s, ativa = false, atualizado_em = now()
                        WHERE servico = %s AND id_unidade IS NULL""",
                    (segredos.cifrar({}), servico.SERVICO))
        auditoria.registrar(cur, ctx.id_usuario, "integracao", servico.SERVICO, "remover_chave")
        return _ver_config(cur) | {"message": "Chave removida. A tradução automática está desligada."}


@router.post("/config/testar")
def testar_config(ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    """Uma chamada mínima com a chave guardada — a tela diz se funciona."""
    with get_cursor() as cur:
        cfg = servico._config(cur)
    if not cfg["chave"]:
        raise HTTPException(status_code=400, detail="Cadastre a chave antes de testar.")
    ok, frase = servico.testar(cfg["chave"], cfg["modelo"])
    with get_cursor() as cur:
        cur.execute("""UPDATE integracoes SET ultimo_status = %s, ultima_mensagem = %s
                        WHERE servico = %s AND id_unidade IS NULL""",
                    ("ok" if ok else "erro", frase, servico.SERVICO))
    if not ok:
        raise HTTPException(status_code=502, detail=frase)
    return {"ok": True, "message": frase}


@router.get("/estado")
def estado(ctx: Contexto = Depends(_VER)) -> dict:
    """Se a tradução automática está ligada (a chave da Anthropic está cadastrada)."""
    with get_cursor() as cur:
        return servico.estado(cur)


@router.get("/catalogo/{id_catalogo}/pendentes")
def pendentes(id_catalogo: int, ctx: Contexto = Depends(_VER)) -> dict:
    with get_cursor() as cur:
        return {"pendentes": servico.pendentes_do_catalogo(cur, id_catalogo), **servico.estado(cur)}


@router.post("/catalogo/{id_catalogo}/traduzir")
def traduzir_catalogo(id_catalogo: int, forcar: bool = False,
                      ctx: Contexto = Depends(_EDITAR)) -> dict:
    """Traduz tudo o que falta no catálogo (o nome, as seções e os produtos)."""
    with get_cursor() as cur:
        r = servico.do_catalogo(cur, id_catalogo, forcar)
        auditoria.registrar(cur, ctx.id_usuario, "catalogo", id_catalogo, "traduzir",
                            depois={"traduzidos": r["traduzidos"], "forcar": forcar})
        if r["erro"] and not r["traduzidos"]:
            raise HTTPException(status_code=503, detail=r["erro"])
        falta = servico.pendentes_do_catalogo(cur, id_catalogo)
        return r | {"pendentes": falta,
                    "message": (f"{r['traduzidos']} tradução(ões) feita(s)." if r["traduzidos"]
                                else "Nada a traduzir — está tudo em dia.")
                    + (f" {falta} ainda pendente(s)." if falta else "")}


@router.get("/{tipo}/{id_}")
def obter(tipo: Tipo, id_: int, ctx: Contexto = Depends(_VER)) -> dict:
    with get_cursor() as cur:
        return servico.obter(cur, tipo, id_) | servico.estado(cur)


@router.put("/{tipo}/{id_}")
def corrigir(tipo: Tipo, id_: int, body: TraducaoManual, ctx: Contexto = Depends(_EDITAR)) -> dict:
    """A tradução corrigida à mão — e a automática não a sobrescreve mais."""
    dados = {k: v.model_dump(exclude_unset=True) for k, v in
             (("en", body.en), ("de", body.de)) if v is not None}
    with get_cursor() as cur:
        r = servico.gravar_manual(cur, tipo, id_, dados)
        auditoria.registrar(cur, ctx.id_usuario, tipo, id_, "traducao_manual", depois=dados)
        return r | servico.estado(cur) | {"message": "Tradução salva."}


@router.post("/{tipo}/{id_}/gerar")
def gerar(tipo: Tipo, id_: int, ctx: Contexto = Depends(_EDITAR)) -> dict:
    """Gera de novo — inclusive o que foi corrigido à mão, que volta a ser automático."""
    with get_cursor() as cur:
        r = servico.traduzir(cur, tipo, [id_], forcar=True)
        if r["erro"]:
            raise HTTPException(status_code=503, detail=r["erro"])
        auditoria.registrar(cur, ctx.id_usuario, tipo, id_, "traducao_gerar")
        return servico.obter(cur, tipo, id_) | servico.estado(cur) | {"message": "Tradução gerada."}
