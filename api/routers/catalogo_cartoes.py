"""Os cartões de conteúdo do Cardápio Vivo (120) e o vídeo da abertura de seção.

🔑 Pedido do dono (16/10/2026): introdução do cardápio, aberturas de seção e cartões entre os
pratos — vídeo, foto ou texto —, só no feed. Ver `services/catalogo_cartoes.py`.
⚠️ **Router próprio, registrado ANTES do `catalogos`**: aquele tem `/{id_catalogo}` de um
segmento, e a ordem de registro é a ordem em que o FastAPI tenta casar o caminho.
⚠️ A mesma porta dos catálogos (`_unidade`): sem o Portal ligado na loja, recusa com 409.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

import arquivos
import auditoria
from database import get_cursor
from models.cardapio_vivo import CartaoCreate
from routers.catalogos import _EDITAR, _VER, _unidade
from seguranca import Contexto
from services import catalogo_cartoes as servico

router = APIRouter(prefix="/catalogos", tags=["catálogos"])
_SECOES = ("categoria", "subcategoria")


@router.get("/{id_catalogo}/cartoes")
def listar(id_catalogo: int, dias: int = 30, ctx: Contexto = Depends(_VER)) -> dict:
    with get_cursor() as cur:
        return servico.listar(cur, _unidade(cur, ctx), id_catalogo, dias)


@router.post("/{id_catalogo}/cartoes", status_code=201)
def criar(id_catalogo: int, body: CartaoCreate, ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        novo = servico.criar(cur, id_unidade, id_catalogo, body.model_dump(), ctx.id_usuario)
        auditoria.registrar(cur, ctx.id_usuario, "catalogo_cartao", novo["id"], "criar",
                            depois={"titulo": novo["titulo"]}, id_unidade=id_unidade)
        return novo


@router.put("/cartoes/{id_cartao}")
def atualizar(id_cartao: int, body: CartaoCreate, ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        muda = servico.atualizar(cur, id_unidade, id_cartao, body.model_dump())
        auditoria.registrar(cur, ctx.id_usuario, "catalogo_cartao", id_cartao, "atualizar",
                            depois={"titulo": muda["titulo"], "ativo": muda["ativo"]},
                            id_unidade=id_unidade)
        return muda


@router.delete("/cartoes/{id_cartao}")
def remover(id_cartao: int, ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        fora = servico.remover(cur, id_unidade, id_cartao)
        auditoria.registrar(cur, ctx.id_usuario, "catalogo_cartao", id_cartao, "excluir",
                            id_unidade=id_unidade)
        return fora


@router.post("/cartoes/{id_cartao}/foto")
async def enviar_foto(id_cartao: int, arquivo: UploadFile = File(...),
                      ctx: Contexto = Depends(_EDITAR)) -> dict:
    # ⚠️ Os bytes chegam ANTES de pedir a conexão, como na foto da seção.
    dados, mime, extensao = await arquivos.ler_enviada(arquivo)
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        posto = servico.guardar_foto(cur, id_unidade, id_cartao, dados, mime, extensao)
        auditoria.registrar(cur, ctx.id_usuario, "catalogo_cartao", id_cartao, "enviar_foto",
                            depois={"nome": arquivo.filename}, id_unidade=id_unidade)
        return posto


@router.post("/cartoes/{id_cartao}/video")
async def enviar_video(id_cartao: int, arquivo: UploadFile = File(...),
                       ctx: Contexto = Depends(_EDITAR)) -> dict:
    """O mesmo tratamento do vídeo do prato: MP4 720p, mudo, até 15 s, e a capa.

    ⚠️ A conversão roda FORA do laço e sem transação aberta (segundos de CPU).
    """
    cru = await arquivos.ler_video(arquivo)
    mp4, capa, segundos = await run_in_threadpool(arquivos.converter_video, cru)
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        posto = servico.guardar_video(cur, id_unidade, id_cartao, mp4, capa, segundos)
        auditoria.registrar(cur, ctx.id_usuario, "catalogo_cartao", id_cartao, "enviar_video",
                            depois={"nome": arquivo.filename, "bytes": len(mp4), "segundos": segundos},
                            id_unidade=id_unidade)
        return posto | {"message": f"Vídeo convertido: {segundos:.0f} s, {len(mp4) / 1048576:.1f} MB."}


@router.delete("/cartoes/{id_cartao}/midia")
def remover_midia(id_cartao: int, ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        fora = servico.remover_midia(cur, id_unidade, id_cartao)
        auditoria.registrar(cur, ctx.id_usuario, "catalogo_cartao", id_cartao, "remover_midia",
                            id_unidade=id_unidade)
        return fora


# --------------------------------------------------- o vídeo da seção ------

def _tipo(tipo: str) -> str:
    if tipo not in _SECOES:
        raise HTTPException(status_code=404, detail="Seção desconhecida.")
    return tipo


@router.post("/secoes/{tipo}/{id_secao}/video")
async def enviar_video_secao(tipo: str, id_secao: int, arquivo: UploadFile = File(...),
                             ctx: Contexto = Depends(_EDITAR)) -> dict:
    """O vídeo da abertura de seção no Cardápio Vivo — ganha da foto quando existe."""
    _tipo(tipo)
    cru = await arquivos.ler_video(arquivo)
    mp4, capa, segundos = await run_in_threadpool(arquivos.converter_video, cru)
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        posto = servico.guardar_video_secao(cur, id_unidade, tipo, id_secao, mp4, capa)
        auditoria.registrar(cur, ctx.id_usuario, f"catalogo_{tipo}", id_secao, "enviar_video",
                            depois={"nome": arquivo.filename, "segundos": segundos},
                            id_unidade=id_unidade)
        return posto | {"message": f"Vídeo convertido: {segundos:.0f} s, {len(mp4) / 1048576:.1f} MB."}


@router.delete("/secoes/{tipo}/{id_secao}/video")
def remover_video_secao(tipo: str, id_secao: int, ctx: Contexto = Depends(_EDITAR)) -> dict:
    _tipo(tipo)
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        fora = servico.remover_video_secao(cur, id_unidade, tipo, id_secao)
        auditoria.registrar(cur, ctx.id_usuario, f"catalogo_{tipo}", id_secao, "remover_video",
                            id_unidade=id_unidade)
        return fora
