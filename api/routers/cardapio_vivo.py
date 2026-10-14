"""Cardápio Vivo (113) — a configuração da loja, o acesso das mesas e o feed público.

🔑 **Pedido do dono (14/10/2026)**, estudo em `docs/cardapio-vivo-estudo.md`.

⚠️ **Dois routers neste arquivo, e a diferença é de quem entra.** `router` é de dentro
(cada rota declara a permissão); `publico` é a mesa — sem login, e por isso estreito:
só sai o que a casa publicou, e só grava evento anônimo com freio.
"""

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import ValidationError

import arquivos
import auditoria
import relogio
from config import WEB_URL
from database import get_cursor
from models.cardapio_vivo import ConfigCardapio, ExcecaoCardapio, LoteEventos
from routers.reservas import _unidade
from seguranca import Contexto, ip_do_cliente, requer_permissao
from services import cardapio_vivo as servico
from services import fidelidade_qr

router = APIRouter(prefix="/cardapio-vivo", tags=["Cardápio Vivo"])
publico = APIRouter(prefix="/publico/cardapio", tags=["site do cliente"])

_VER = requer_permissao("catalogos.ver")
_EDITAR = requer_permissao("catalogos.editar")
# ⚠️ O acesso das mesas (token, QR) é de quem configura o SALÃO, como os outros QR.
_SALAO = requer_permissao("reservas.configurar")


def _catalogos_produtos(cur, id_unidade: int) -> list[dict]:
    cur.execute(
        """SELECT c.id, c.nome, c.situacao FROM catalogos c
            WHERE c.origem = 'PRODUTOS' AND c.situacao <> 'INATIVO'
              AND EXISTS (SELECT 1 FROM catalogo_lojas l
                           WHERE l.id_catalogo = c.id AND l.id_unidade = %s)
            ORDER BY lower(c.nome)""",
        (id_unidade,))
    return [dict(r) for r in cur.fetchall()]


def _resposta_config(cur, id_unidade: int) -> dict:
    cfg = servico.config(cur, id_unidade)
    cfg.pop("atualizado_por", None)
    return {
        "config": cfg,
        "catalogos": _catalogos_produtos(cur, id_unidade),
        "opcoes": {"modos": list(servico.MODOS), "modos_liberados": list(servico.MODOS_LIBERADOS),
                   "fontes": list(servico.FONTES)},
        "link_loja": servico.link_da_loja(WEB_URL, id_unidade),
        "sem_midia": servico.sem_midia(cur, id_unidade, cfg["id_catalogo"]) if cfg["id_catalogo"] else [],
    }


@router.get("/config")
def obter_config(ctx: Contexto = Depends(_VER)) -> dict:
    with get_cursor() as cur:
        return _resposta_config(cur, _unidade(cur, ctx))


@router.put("/config")
def salvar_config(body: ConfigCardapio, ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        antes = servico.config(cur, id_unidade)
        servico.salvar_config(cur, id_unidade, body.model_dump(), ctx.id_usuario)
        auditoria.registrar(cur, ctx.id_usuario, "cardapio_config", id_unidade, "alterar",
                            antes={k: str(antes.get(k)) for k in body.model_dump()},
                            depois={k: str(v) for k, v in body.model_dump().items()})
        return _resposta_config(cur, id_unidade) | {"message": "Configuração gravada."}


@router.post("/config/logo")
async def enviar_logo(arquivo: UploadFile = File(...), ctx: Contexto = Depends(_EDITAR)) -> dict:
    """A logo da LOJA no feed. Sem ela, vale a da empresa."""
    conteudo, tipo, extensao = await arquivos.ler_enviada(arquivo)
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        antiga = servico.config(cur, id_unidade)["logo_url"]
        url = arquivos.gravar(cur, conteudo, tipo, extensao, f"cardapio-logo-{id_unidade}")
        cur.execute("""INSERT INTO cardapio_config (id_unidade, logo_url) VALUES (%s, %s)
                       ON CONFLICT (id_unidade) DO UPDATE SET logo_url = EXCLUDED.logo_url,
                                                              atualizado_em = now()""",
                    (id_unidade, url))
        if antiga and antiga != url:
            arquivos.remover(antiga, cur)
        return _resposta_config(cur, id_unidade) | {"message": "Logo gravada."}


@router.delete("/config/logo")
def remover_logo(ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        antiga = servico.config(cur, id_unidade)["logo_url"]
        cur.execute("UPDATE cardapio_config SET logo_url = NULL WHERE id_unidade = %s",
                    (id_unidade,))
        if antiga:
            arquivos.remover(antiga, cur)
        return _resposta_config(cur, id_unidade) | {"message": "Logo removida — vale a da empresa."}


@router.get("/excecoes")
def excecoes(ctx: Contexto = Depends(_VER)) -> list[dict]:
    with get_cursor() as cur:
        return servico.listar_excecoes(cur, _unidade(cur, ctx))


@router.put("/excecoes")
def salvar_excecao(body: ExcecaoCardapio, ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        r = servico.salvar_excecao(cur, id_unidade, body.model_dump())
        auditoria.registrar(cur, ctx.id_usuario, "cardapio_excecao", r["id"], "gravar",
                            depois={k: str(v) for k, v in body.model_dump().items()})
        return r


@router.delete("/excecoes/{id_excecao}")
def excluir_excecao(id_excecao: int, ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        r = servico.excluir_excecao(cur, id_unidade, id_excecao)
        auditoria.registrar(cur, ctx.id_usuario, "cardapio_excecao", id_excecao, "excluir")
        return r


@router.get("/sem-midia")
def sem_midia(id_catalogo: int, ctx: Contexto = Depends(_VER)) -> list[dict]:
    """Os itens publicados sem foto e sem vídeo próprios — o aviso da tela do catálogo."""
    with get_cursor() as cur:
        return servico.sem_midia(cur, _unidade(cur, ctx), id_catalogo)


# ------------------------------------------------------------------ acesso das mesas

@router.get("/mesas")
def mesas(ctx: Contexto = Depends(_SALAO)) -> dict:
    """Cada mesa com o link do cardápio dela — o QR e a etiqueta NFC gravam este link."""
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        return {"mesas": servico.mesas_com_acesso(cur, id_unidade, WEB_URL),
                "link_loja": servico.link_da_loja(WEB_URL, id_unidade)}


@router.post("/mesas/{id_mesa}/token")
def novo_token(id_mesa: int, ctx: Contexto = Depends(_SALAO)) -> dict:
    """Gera outro segredo para a mesa. ⚠️ O QR e a etiqueta NFC antigos param de abrir."""
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        token = servico.novo_token(cur, id_unidade, id_mesa)
        auditoria.registrar(cur, ctx.id_usuario, "mesa", id_mesa, "novo_token_cardapio")
        return {"link": servico.link_da_mesa(WEB_URL, id_unidade, token),
                "message": "Novo acesso gerado. Imprima o QR de novo e regrave a etiqueta NFC."}


def _casa(cur, id_unidade: int) -> str:
    cur.execute("SELECT nome_fantasia, razao_social FROM empresa WHERE id = 1")
    e = cur.fetchone() or {}
    cur.execute("SELECT coalesce(nullif(apelido, ''), nome) AS nome FROM unidades WHERE id = %s",
                (id_unidade,))
    loja = (cur.fetchone() or {}).get("nome")
    casa = e.get("nome_fantasia") or e.get("razao_social") or "Nossa casa"
    return f"{casa} · {loja}" if loja else casa


@router.get("/mesas/{id_mesa}/qr.png")
def qr_png(id_mesa: int, ctx: Contexto = Depends(_SALAO)) -> Response:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        mesa = next((m for m in servico.mesas_com_acesso(cur, id_unidade, WEB_URL)
                     if m["id"] == id_mesa), None)
    if not mesa:
        raise HTTPException(status_code=404, detail="Mesa não encontrada.")
    return Response(fidelidade_qr.png(mesa["link"], 900), media_type="image/png",
                    headers={"Content-Disposition":
                             f'attachment; filename="qr-mesa-{mesa["nome"]}.png"'})


@router.get("/mesas/qr.pdf")
def qr_pdf(ids: str | None = Query(None, max_length=2000, description="ids separados por vírgula"),
           tamanho: str = Query("M", pattern="^(P|M|G)$"),
           titulo: str = Query("Nosso cardápio", max_length=60),
           chamada: str = Query("Aponte a câmera e veja os pratos", max_length=120),
           ctx: Contexto = Depends(_SALAO)) -> Response:
    """Um cartão por mesa, cada um com o link DELA. Sem `ids`: todas as mesas ativas."""
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        lista = [m for m in servico.mesas_com_acesso(cur, id_unidade, WEB_URL) if m["ativo"]]
        casa = _casa(cur, id_unidade)
    if ids:
        try:
            quero = {int(x) for x in ids.split(",") if x.strip()}
        except ValueError:
            raise HTTPException(status_code=422, detail="Lista de mesas inválida.")
        lista = [m for m in lista if m["id"] in quero]
    if not lista:
        raise HTTPException(status_code=404, detail="Nenhuma mesa para imprimir.")
    pdf = fidelidade_qr.gerar_cartoes(
        [(m["link"], f"{m['salao']} · Mesa {m['nome']}") for m in lista],
        tamanho, titulo, chamada, "", casa)
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition":
            f'attachment; filename="qr-cardapio-mesas-{relogio.hoje_da_casa():%Y%m%d}.pdf"'})


# ------------------------------------------------------------------ público (a mesa)

_IDIOMA = Query(None, pattern="^(pt|en|de)$")


@publico.get("/mesa/{token}")
def cardapio_da_mesa(token: str, idioma: str | None = _IDIOMA) -> dict:
    """O cardápio da mesa: a loja e a mesa saem do TOKEN, nunca de um número na URL."""
    with get_cursor() as cur:
        mesa = servico.mesa_por_token(cur, token)
        if not mesa:
            # ⚠️ Token trocado (QR antigo) ou inventado: o mesmo 404, sem dizer qual.
            raise HTTPException(status_code=404, detail="Este QR code não vale mais. "
                                                        "Peça o cardápio ao garçom.")
        return servico.cardapio_publico(cur, mesa["id_unidade"], mesa, idioma)


@publico.get("/loja/{id_unidade}")
def cardapio_da_loja(id_unidade: int, idioma: str | None = _IDIOMA) -> dict:
    """O cardápio sem mesa (vitrine, balcão): o modo da LOJA, sem exceção de salão."""
    with get_cursor() as cur:
        return servico.cardapio_publico(cur, id_unidade, None, idioma)


@router.get("/previa")
def previa(id_catalogo: int, idioma: str | None = _IDIOMA,
           ctx: Contexto = Depends(_VER)) -> dict:
    """O feed de um catálogo ANTES de publicar — a pré-visualização do cadastro.

    ⚠️ Com login, e não pública: rascunho não é para o público, e a prévia mostra
    também as seções fora do dia e do horário.
    """
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        cur.execute("""SELECT 1 FROM catalogos c WHERE c.id = %s AND c.origem = 'PRODUTOS'
                         AND EXISTS (SELECT 1 FROM catalogo_lojas l
                                      WHERE l.id_catalogo = c.id AND l.id_unidade = %s)""",
                    (id_catalogo, id_unidade))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Catálogo não encontrado.")
        return servico.cardapio_publico(cur, id_unidade, None, idioma, previa_catalogo=id_catalogo)


@publico.post("/eventos", status_code=204)
async def eventos(request: Request) -> Response:
    """O lote de eventos do `sendBeacon`.

    ⚠️ **O corpo chega como `text/plain`, de propósito**: é o único tipo que o
    `sendBeacon` manda entre origens sem preflight (em casa, web e API estão em portas
    diferentes). Por isso o JSON é lido à mão e validado pelo mesmo modelo Pydantic.
    """
    corpo = await request.body()
    if len(corpo) > 64 * 1024:
        raise HTTPException(status_code=413, detail="Lote grande demais.")
    try:
        lote = LoteEventos.model_validate_json(corpo)
    except ValidationError:
        raise HTTPException(status_code=422, detail="Lote inválido.")
    dados = lote.model_dump()
    dados["sessao"] = str(lote.sessao)
    with get_cursor() as cur:
        servico.registrar_eventos(cur, dados, ip_do_cliente(request))
    return Response(status_code=204)
