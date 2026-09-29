"""Pedidos pelo catálogo — o lado da CASA: lista, painel, confirmar, lançar no PDV, entregar.

🔑 **Pedido do dono (28/09/2026):** *"uma tela com pedidos, um painel para acompanhar e aviso na
tela inicial."* A regra mora em `services/pedidos.py`; o site fala com `routers/publico.py`.

⚠️ **As rotas exigem o Portal ligado na loja atual** — a mesma trava de Reservas.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response

import auditoria
from database import get_cursor
from models.pedidos import Confirmacao, ConfigPedidos, LancadoNoPdv, Motivo, PagamentoFeito
from routers.reservas import _unidade
from seguranca import Contexto, requer_permissao
from services import pedidos as servico

router = APIRouter(prefix="/pedidos", tags=["Pedidos"])

_VER = requer_permissao("pedidos.ver", "pedidos.operar")
_OPERAR = requer_permissao("pedidos.operar")
# A configuração é do CATÁLOGO: quem edita o catálogo decide se ele aceita pedido.
_CAT_VER = requer_permissao("catalogos.ver", "catalogos.editar")
_CAT_EDITAR = requer_permissao("catalogos.editar")


# ---------------------------------------------------------------- configuração (catálogo)

@router.get("/config/{id_catalogo}")
def obter_config(id_catalogo: int, ctx: Contexto = Depends(_CAT_VER)) -> dict:
    with get_cursor() as cur:
        _unidade(cur, ctx)
        return servico.config(cur, id_catalogo)


@router.put("/config/{id_catalogo}")
def salvar_config(id_catalogo: int, body: ConfigPedidos,
                  ctx: Contexto = Depends(_CAT_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        antes = servico.config(cur, id_catalogo)
        cfg = servico.salvar_config(cur, id_catalogo, body.model_dump())
        auditoria.registrar(cur, ctx.id_usuario, "catalogo_pedidos", id_catalogo, "salvar",
                            antes=antes, depois=body.model_dump(), id_unidade=id_unidade)
        return cfg | {"message": ("Pedidos pelo site ligados neste catálogo." if cfg["aceita"]
                                  else "Configuração de pedidos salva.")}


# ---------------------------------------------------------------- consulta

@router.get("/painel")
def painel(ctx: Contexto = Depends(_VER)) -> dict:
    with get_cursor() as cur:
        return servico.painel(cur, _unidade(cur, ctx))


@router.get("")
def listar(situacao: str = "abertos", dia: date | None = None, busca: str | None = None,
           limite: int = Query(default=50, ge=1, le=200),
           offset: int = Query(default=0, ge=0),
           resposta: Response = None,
           ctx: Contexto = Depends(_VER)) -> list[dict]:
    with get_cursor() as cur:
        return servico.listar(cur, _unidade(cur, ctx), situacao, dia, busca,
                              limite, offset, resposta)


@router.get("/{id_pedido}")
def obter(id_pedido: int, ctx: Contexto = Depends(_VER)) -> dict:
    with get_cursor() as cur:
        return servico.obter(cur, _unidade(cur, ctx), id_pedido)


@router.get("/{id_pedido}/catalogo")
def catalogo_para_troca(id_pedido: int, ctx: Contexto = Depends(_OPERAR)) -> list[dict]:
    """Os itens do mesmo catálogo que podem entrar no pedido, com o preço vigente."""
    with get_cursor() as cur:
        return servico.catalogo_para_troca(cur, _unidade(cur, ctx), id_pedido)


@router.get("/{id_pedido}/pdf")
def imprimir(id_pedido: int, ctx: Contexto = Depends(_VER)) -> Response:
    with get_cursor() as cur:
        conteudo = servico.pdf(cur, _unidade(cur, ctx), id_pedido)
    return Response(conteudo, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="pedido-{id_pedido}.pdf"'})


# ---------------------------------------------------------------- as ações

def _acao(ctx: Contexto, id_pedido: int, nome: str, fazer, depois: dict | None = None) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        p = fazer(cur, id_unidade)
        auditoria.registrar(cur, ctx.id_usuario, "pedido", id_pedido, nome,
                            depois={"numero": p["numero"], **(depois or {})},
                            id_unidade=id_unidade)
        return p


@router.post("/{id_pedido}/confirmar")
def confirmar(id_pedido: int, body: Confirmacao, ctx: Contexto = Depends(_OPERAR)) -> dict:
    dados = body.model_dump()
    p = _acao(ctx, id_pedido, "confirmar",
              lambda cur, u: servico.confirmar(cur, u, id_pedido, ctx.id_usuario, dados),
              {"trocado": bool(dados.get("itens"))})
    return p | {"message": (f"Pedido {p['numero']} confirmado"
                            + (" com os produtos trocados." if p["alterado"] else "."))}


@router.post("/{id_pedido}/recusar")
def recusar(id_pedido: int, body: Motivo, ctx: Contexto = Depends(_OPERAR)) -> dict:
    p = _acao(ctx, id_pedido, "recusar",
              lambda cur, u: servico.recusar(cur, u, id_pedido, ctx.id_usuario, body.motivo),
              {"motivo": body.motivo})
    return p | {"message": f"Pedido {p['numero']} recusado."}


@router.post("/{id_pedido}/cancelar")
def cancelar(id_pedido: int, body: Motivo, ctx: Contexto = Depends(_OPERAR)) -> dict:
    p = _acao(ctx, id_pedido, "cancelar",
              lambda cur, u: servico.cancelar(cur, u, id_pedido, ctx.id_usuario, body.motivo),
              {"motivo": body.motivo})
    return p | {"message": f"Pedido {p['numero']} cancelado."}


@router.post("/{id_pedido}/lancado-pdv")
def lancado_pdv(id_pedido: int, body: LancadoNoPdv, ctx: Contexto = Depends(_OPERAR)) -> dict:
    p = _acao(ctx, id_pedido, "lancado_pdv",
              lambda cur, u: servico.lancado_no_pdv(cur, u, id_pedido, ctx.id_usuario, body.cupom),
              {"cupom": body.cupom})
    return p | {"message": f"Pedido {p['numero']} marcado como lançado no PDV."}


@router.post("/{id_pedido}/pago")
def pago(id_pedido: int, body: PagamentoFeito, ctx: Contexto = Depends(_OPERAR)) -> dict:
    p = _acao(ctx, id_pedido, "pago",
              lambda cur, u: servico.pago(cur, u, id_pedido, ctx.id_usuario, body.como),
              {"como": body.como})
    return p | {"message": f"Pagamento do pedido {p['numero']} registrado."}


@router.post("/{id_pedido}/entregar")
def entregar(id_pedido: int, ctx: Contexto = Depends(_OPERAR)) -> dict:
    p = _acao(ctx, id_pedido, "entregar",
              lambda cur, u: servico.entregar(cur, u, id_pedido, ctx.id_usuario))
    if not p["lancado_pdv_em"]:
        return p | {"message": f"Pedido {p['numero']} entregue — falta marcar o lançamento no PDV."}
    return p | {"message": f"Pedido {p['numero']} entregue."}
