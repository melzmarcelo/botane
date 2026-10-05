"""Os QR codes do Portal de Clientes — todos num lugar só.

🔑 **Pedido do dono (27/09/2026):** *"implementar também a opção de mais QR codes: o da
pontuação, o do cardápio que pode ir na mesa, o da própria reserva. Criar uma tela em
reservas específica para organizar estes QR codes."*

Cada QR é só um ENDEREÇO do site do cliente, com a loja dentro:
* **site** — a página inicial;
* **reserva** — abre direto a reserva;
* **cardapio** — um por catálogo, abre direto aquele cardápio;
* **fidelidade** — o check-in (mesa) ou o pedido de código (caixa), com o segredo.

⚠️ O endereço do site mora em `fidelidade_config.site_url` desde a 091 — é da REDE, e a
casa o ajusta sem deploy. Esta tela passa a ser o lugar dele.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

import auditoria
from database import get_cursor
from routers.reservas import _unidade
from seguranca import Contexto, requer_permissao
from services import fidelidade
from services import fidelidade_qr

router = APIRouter(prefix="/reservas/qrcodes", tags=["Reservas"])
_CONFIGURAR = requer_permissao("reservas.configurar")


class EnderecoDoSite(BaseModel):
    site_url: str = Field(min_length=8, max_length=200, pattern=r"^https?://")


def _catalogos(cur, id_unidade: int) -> list[dict]:
    """Os catálogos ATIVOS que aparecem nesta loja — os que valem um QR de mesa.

    ⚠️ Sem olhar o período de publicação: o QR se imprime ANTES de o cardápio de verão
    entrar no ar, e fica na mesa depois. Fora do período, o site simplesmente não o abre.
    """
    cur.execute(
        """SELECT c.id, c.nome, c.origem FROM catalogos c
            WHERE EXISTS (SELECT 1 FROM catalogo_lojas l
                           WHERE l.id_catalogo = c.id AND l.id_unidade = %s)
              AND c.situacao = 'ATIVO'
            ORDER BY lower(c.nome)""",
        (id_unidade,),
    )
    return [dict(r) for r in cur.fetchall()]


def _tipos(cur, id_unidade: int) -> dict:
    cfg = fidelidade.config(cur)
    base = f"{cfg['site_url']}/?loja={id_unidade}"
    caixa = cfg["metodo"] == "CODIGO_CAIXA"
    tipos = [
        {"tipo": "site", "nome": "Site da casa", "link": base,
         "titulo": "Conheça a casa", "chamada": "Cardápio, reservas e contato no celular",
         "onde": "vitrine, balcão, material impresso"},
        {"tipo": "reserva", "nome": "Reserva", "link": base + "#reserva",
         "titulo": "Reserve sua mesa", "chamada": "Escolha o dia e o horário pelo celular",
         "onde": "porta, balcão, sacola"},
        {"tipo": "fidelidade", "nome": "Pontuação da fidelidade",
         "link": fidelidade.link_do_qr(cfg, id_unidade),
         "disponivel": fidelidade.ligada(cur, id_unidade),
         "motivo": None if fidelidade.ligada(cur, id_unidade)
         else "A fidelidade não está ligada nesta loja (Portal de Clientes → Configuração).",
         "titulo": "Some selos na fidelidade" if caixa else "Faça seu check-in",
         "chamada": f"A cada {cfg['visitas']} visitas: {cfg['premio']}",
         "onde": "no CAIXA — o atendente passa o código" if caixa else "nas MESAS",
         "metodo": cfg["metodo"]},
    ]
    for c in _catalogos(cur, id_unidade):
        tipos.append({
            "tipo": "cardapio", "id_catalogo": c["id"], "nome": f"Cardápio — {c['nome']}",
            "link": f"{base}&catalogo={c['id']}#cardapio",
            "titulo": c["nome"], "chamada": "Veja o cardápio no celular", "onde": "nas mesas"})
    return {"site_url": cfg["site_url"], "tipos": tipos}


@router.get("")
def listar(ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    """Os QR codes que esta loja pode imprimir, com o endereço de cada um."""
    with get_cursor() as cur:
        return _tipos(cur, _unidade(cur, ctx))


@router.put("/site")
def endereco_do_site(body: EnderecoDoSite, ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    """O endereço que TODOS os QR abrem. ⚠️ Mudar depois de imprimir invalida os impressos."""
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        url = body.site_url.strip().rstrip("/")
        cur.execute("UPDATE fidelidade_config SET site_url = %s, atualizado_em = now() "
                    "WHERE id = 1", (url,))
        auditoria.registrar(cur, ctx.id_usuario, "qrcodes", 1, "site_url", depois={"url": url})
        return _tipos(cur, id_unidade) | {"message": "Endereço do site gravado."}


@router.get("/pdf")
def pdf(tipo: str = Query(pattern="^(site|reserva|cardapio|fidelidade)$"),
        id_catalogo: int | None = None,
        quantidade: int = Query(1, ge=1, le=200),
        tamanho: str = Query("M", pattern="^(P|M|G)$"),
        titulo: str | None = Query(None, max_length=60),
        chamada: str | None = Query(None, max_length=120),
        extra: str | None = Query(None, max_length=200),
        numerar: bool = False,
        primeira_mesa: int = Query(1, ge=1, le=999),
        ctx: Contexto = Depends(_CONFIGURAR)) -> Response:
    """O PDF de um tipo de QR, em A4, para recortar (grande 1, médio 4, pequeno 12)."""
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        lista = _tipos(cur, id_unidade)["tipos"]
        alvo = next((t for t in lista if t["tipo"] == tipo
                     and (tipo != "cardapio" or t.get("id_catalogo") == id_catalogo)), None)
        if not alvo:
            raise HTTPException(status_code=404, detail="Este QR code não existe nesta loja.")
        if alvo.get("disponivel") is False:
            raise HTTPException(status_code=409, detail=alvo["motivo"])
        cur.execute("SELECT nome_fantasia, razao_social FROM empresa WHERE id = 1")
        e = cur.fetchone() or {}
        cur.execute("SELECT coalesce(apelido, nome) AS nome FROM unidades WHERE id = %s",
                    (id_unidade,))
        loja = (cur.fetchone() or {}).get("nome")
    casa = e.get("nome_fantasia") or e.get("razao_social") or "Nossa casa"
    if loja:
        casa = f"{casa} · {loja}"
    conteudo = fidelidade_qr.gerar(
        link=alvo["link"], quantidade=quantidade, tamanho=tamanho,
        titulo=(titulo if titulo is not None else alvo["titulo"]).strip() or alvo["titulo"],
        chamada=(chamada if chamada is not None else alvo["chamada"]).strip(),
        extra=(extra or "").strip(), casa=casa, numerar=numerar, primeira_mesa=primeira_mesa,
    )
    return Response(conteudo, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="qrcodes-{tipo}-{date.today():%Y%m%d}.pdf"'})
