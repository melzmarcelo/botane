"""Os anúncios do Cardápio Vivo (121, fase 1) — cadastro, regras de exibição e relatório.

🔑 Pedido do dono (16/10/2026). Ver `services/cardapio_anuncios.py`.
⚠️ A mesma porta do Cardápio Vivo: sem o Portal ligado na loja, recusa com 409.
⚠️ `/regras` é declarada ANTES de `/{id_anuncio}`: com o id tipado como inteiro, o FastAPI
recusaria "regras" com 422 em vez de seguir para a rota certa.
"""

from datetime import date

from fastapi import APIRouter, Depends, File, Query, UploadFile
from starlette.concurrency import run_in_threadpool

import arquivos
import auditoria
from database import get_cursor
from models.cardapio_vivo import AnuncioCreate, RegrasAnuncio
from routers.reservas import _unidade
from seguranca import Contexto, requer_permissao
from services import cardapio_anuncios as servico

router = APIRouter(prefix="/cardapio-vivo/anuncios", tags=["Cardápio Vivo"])
_VER = requer_permissao("catalogos.ver")
_EDITAR = requer_permissao("catalogos.editar")


@router.get("")
def listar(ctx: Contexto = Depends(_VER)) -> dict:
    with get_cursor() as cur:
        return servico.listar(cur, _unidade(cur, ctx))


@router.post("", status_code=201)
def criar(body: AnuncioCreate, ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        novo = servico.criar(cur, id_unidade, body.model_dump(), ctx.id_usuario)
        auditoria.registrar(cur, ctx.id_usuario, "cardapio_anuncio", novo["id"], "criar",
                            depois={"nome": novo["nome"], "origem": novo["origem"]}, id_unidade=id_unidade)
        return novo


@router.put("/regras")
def gravar_regras(body: RegrasAnuncio, ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        antes = servico.regras(cur, id_unidade)
        depois = servico.salvar_regras(cur, id_unidade, body.model_dump())
        auditoria.registrar(cur, ctx.id_usuario, "cardapio_config", id_unidade, "regras_anuncio",
                            antes=antes, depois=depois, id_unidade=id_unidade)
        return depois | {"message": "Regras dos anúncios gravadas."}


@router.put("/{id_anuncio}")
def atualizar(id_anuncio: int, body: AnuncioCreate, ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        muda = servico.atualizar(cur, id_unidade, id_anuncio, body.model_dump())
        auditoria.registrar(cur, ctx.id_usuario, "cardapio_anuncio", id_anuncio, "atualizar",
                            depois={"nome": muda["nome"], "ativo": muda["ativo"]}, id_unidade=id_unidade)
        return muda


@router.delete("/{id_anuncio}")
def remover(id_anuncio: int, ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        fora = servico.remover(cur, id_unidade, id_anuncio)
        auditoria.registrar(cur, ctx.id_usuario, "cardapio_anuncio", id_anuncio, "excluir",
                            id_unidade=id_unidade)
        return fora


@router.post("/{id_anuncio}/foto")
async def enviar_foto(id_anuncio: int, arquivo: UploadFile = File(...),
                      ctx: Contexto = Depends(_EDITAR)) -> dict:
    dados, mime, extensao = await arquivos.ler_enviada(arquivo)
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        posto = servico.guardar_foto(cur, id_unidade, id_anuncio, dados, mime, extensao)
        auditoria.registrar(cur, ctx.id_usuario, "cardapio_anuncio", id_anuncio, "enviar_foto",
                            depois={"nome": arquivo.filename}, id_unidade=id_unidade)
        return posto


@router.post("/{id_anuncio}/video")
async def enviar_video(id_anuncio: int, arquivo: UploadFile = File(...),
                       ctx: Contexto = Depends(_EDITAR)) -> dict:
    """O mesmo tratamento do vídeo do prato. ⚠️ A conversão roda fora do laço e sem conexão."""
    cru = await arquivos.ler_video(arquivo)
    mp4, capa, segundos = await run_in_threadpool(arquivos.converter_video, cru)
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        posto = servico.guardar_video(cur, id_unidade, id_anuncio, mp4, capa, segundos)
        auditoria.registrar(cur, ctx.id_usuario, "cardapio_anuncio", id_anuncio, "enviar_video",
                            depois={"nome": arquivo.filename, "segundos": segundos}, id_unidade=id_unidade)
        return posto | {"message": f"Vídeo convertido: {segundos:.0f} s, {len(mp4) / 1048576:.1f} MB."}


@router.delete("/{id_anuncio}/midia")
def remover_midia(id_anuncio: int, ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        return servico.remover_midia(cur, id_unidade, id_anuncio)


@router.get("/{id_anuncio}/relatorio")
def relatorio(id_anuncio: int, de: date | None = Query(None), ate: date | None = Query(None),
              ctx: Contexto = Depends(_VER)) -> dict:
    """Os números de um anúncio num período (padrão: os últimos 30 dias)."""
    padrao_de, padrao_ate = servico.periodo_padrao()
    with get_cursor() as cur:
        return servico.relatorio(cur, _unidade(cur, ctx), id_anuncio, de or padrao_de, ate or padrao_ate)
