"""Fidelidade — o cartão de visitas do Portal de Clientes (configuração e balcão).

🔑 **Pedido do dono (24/09/2026):** *"no menu podemos ter Fidelidade — Configuração,
onde vamos configurar a quantidade, o prêmio, os dias de validade, os dias de
consumo … e a impressão do QR code."* A regra mora em `services/fidelidade.py`; o
site do cliente fala com `routers/publico.py`.

⚠️ **As rotas exigem o Portal ligado na loja atual** (a mesma trava de Reservas):
a configuração é da rede, mas quem mexe nela está dentro do módulo.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query, Response

import auditoria
from database import get_cursor
from models.fidelidade import EntregaPremio, FidelidadeConfig, LocalDaLoja
from paginacao import pagina
from relogio import agora_da_casa
from routers.reservas import _unidade
from seguranca import Contexto, requer_permissao
from services import fidelidade as servico
from services import fidelidade_qr

router = APIRouter(prefix="/fidelidade", tags=["Fidelidade"])

_CONFIGURAR = requer_permissao("fidelidade.configurar")
_OPERAR = requer_permissao("fidelidade.operar")


def _com_link(cur, id_unidade: int, cfg: dict) -> dict:
    local = servico.local_da_loja(cur, id_unidade)
    return cfg | {
        # As coordenadas da LOJA ATUAL (092) — a regra é da rede, o ponto é de cada casa.
        "local": {"latitude": local[0], "longitude": local[1]} if local else None,
        "ligada": servico.ligada(cur, id_unidade),
        "link": servico.link_do_qr(cfg, id_unidade),
        "regras": servico.regras(cfg),
    }


@router.get("/configuracao")
def obter(ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    """A configuração da rede, e o link do QR para a loja ATUAL."""
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        return _com_link(cur, id_unidade, servico.config(cur))


@router.put("/configuracao")
def salvar(body: FidelidadeConfig, ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    """⚠️ Não mexe no que já foi ganho: prêmio emitido guarda as regras dele."""
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        antes = servico.config(cur)
        cfg = servico.salvar(cur, body)
        auditoria.registrar(cur, ctx.id_usuario, "fidelidade_config", 1, "salvar",
                            antes={k: v for k, v in antes.items() if k != "token"},
                            depois=body.model_dump())
        return _com_link(cur, id_unidade, cfg) | {"message": "Fidelidade salva."}


@router.put("/localizacao")
def definir_localizacao(body: LocalDaLoja, ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    """As coordenadas da loja atual, de onde se mede o raio do check-in (092).

    🔑 A tela oferece "usar minha localização atual": quem configura estando na casa
    grava o ponto certo sem procurar coordenada em mapa.
    """
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        antes = servico.local_da_loja(cur, id_unidade)
        servico.definir_local(cur, id_unidade, body.latitude, body.longitude)
        auditoria.registrar(cur, ctx.id_usuario, "unidade", id_unidade, "localizacao",
                            antes={"latitude": antes[0], "longitude": antes[1]} if antes else None,
                            depois=body.model_dump())
        return _com_link(cur, id_unidade, servico.config(cur)) | {
            "message": "Localização da loja gravada."}


@router.post("/token")
def trocar_token(ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    """Gera outro segredo para o QR. ⚠️ Os QR já impressos deixam de valer."""
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        servico.novo_token(cur)
        auditoria.registrar(cur, ctx.id_usuario, "fidelidade_config", 1, "trocar_token")
        return _com_link(cur, id_unidade, servico.config(cur)) | {
            "message": "QR code trocado. Imprima os novos — os antigos não valem mais."}


@router.get("/qrcodes.pdf")
def qrcodes(quantidade: int = Query(1, ge=1, le=200),
            tamanho: str = Query("M", pattern="^(P|M|G)$"),
            titulo: str = Query("Faça seu check-in", max_length=60),
            chamada: str | None = Query(None, max_length=120),
            extra: str | None = Query(None, max_length=200),
            numerar: bool = False,
            primeira_mesa: int = Query(1, ge=1, le=999),
            ctx: Contexto = Depends(_CONFIGURAR)) -> Response:
    """Os QR codes de check-in desta loja, em A4, para recortar."""
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        cfg = servico.config(cur)
        cur.execute("SELECT nome_fantasia, razao_social FROM empresa WHERE id = 1")
        e = cur.fetchone() or {}
        cur.execute("SELECT coalesce(apelido, nome) AS nome FROM unidades WHERE id = %s",
                    (id_unidade,))
        loja = (cur.fetchone() or {}).get("nome")
    casa = e.get("nome_fantasia") or e.get("razao_social") or "Botané"
    if loja:
        casa = f"{casa} · {loja}"
    pdf = fidelidade_qr.gerar(
        link=servico.link_do_qr(cfg, id_unidade),
        quantidade=quantidade, tamanho=tamanho, titulo=titulo.strip() or "Faça seu check-in",
        chamada=(chamada if chamada is not None
                 else f"A cada {cfg['visitas']} visitas: {cfg['premio']}").strip(),
        extra=(extra or "").strip(), casa=casa, numerar=numerar, primeira_mesa=primeira_mesa,
    )
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="qrcodes-fidelidade-{date.today():%Y%m%d}.pdf"'})


@router.get("/premios")
def listar_premios(resposta: Response,
                   status: str | None = Query(None, pattern="^(DISPONIVEL|USADO|VENCIDO)$"),
                   busca: str | None = Query(None, max_length=120),
                   limite: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                   ctx: Contexto = Depends(_OPERAR)) -> list[dict]:
    """Os prêmios ganhos, da rede — o cliente pode buscar o almoço em qualquer loja."""
    with get_cursor() as cur:
        _unidade(cur, ctx)
        sql, params = servico.consulta_premios(status, busca)
        linhas = pagina(cur, sql, params, limite=limite, offset=offset, resposta=resposta)
    hoje = agora_da_casa().date()
    return [servico.linha_do_premio(x, hoje) for x in linhas]


@router.post("/premios/entregar")
def entregar(body: EntregaPremio, ctx: Contexto = Depends(_OPERAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        r = servico.entregar(cur, id_unidade, body.codigo, ctx.id_usuario)
        auditoria.registrar(cur, ctx.id_usuario, "fidelidade_premio", r["id"], "entregar",
                            depois={"codigo": body.codigo.upper(), "loja": id_unidade})
    return r | {"message": f"Prêmio entregue a {r['cliente']}: {r['premio']}."
                           + (" O check-in de hoje foi retirado — a visita do prêmio não conta "
                              "carimbo." if r["carimbo_retirado"] else "")}
