"""Etiquetas de validade — emitir, imprimir, consultar pelo QR e dar baixa.

🔑 **Pedido do dono (28/09/2026):** *"um novo módulo, o de Etiquetas … para controlar
validade, quantidade e demais coisas úteis, em produtos produzidos e abertos para
consumo."* A regra mora em `services/etiquetas.py`; o estudo em `docs/etiquetas-estudo.md`.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response

import auditoria
from database import get_cursor
from models.etiquetas import (BaixaDeEtiqueta, DescarteDeEtiqueta, EmitirEtiquetas,
                              EtiquetaConfig, ValidadesDoProduto)
from seguranca import Contexto, requer_permissao, unidade_atual
from services import etiquetas as servico

router = APIRouter(prefix="/etiquetas", tags=["Etiquetas"])

_IMPRIMIR = requer_permissao("etiquetas.imprimir")
_DESCARTAR = requer_permissao("etiquetas.descartar")
_CONFIGURAR = requer_permissao("etiquetas.configurar")
# Ler a validade de um produto serve a quem imprime E a quem configura.
_VER_VALIDADE = requer_permissao("etiquetas.imprimir", "etiquetas.configurar")
# 🔑 **As validades do PRODUTO moram no cadastro dele** (06/10/2026, pedido do dono:
# *"deixamos tudo centralizado no produto"*). Quem cadastra produto passa a ver e
# gravar as regras — eram só de quem configurava etiquetas, e o cartão no cadastro
# apareceria travado para a pessoa que edita todo o resto daquela tela.
# ⚠️ O MODELO da etiqueta (rolo, o que imprime) continua só de `etiquetas.configurar`:
# é a impressora da loja, não um dado do produto.
_VER_VALIDADE_DO_PRODUTO = requer_permissao(
    "etiquetas.imprimir", "etiquetas.configurar", "cadastros.produtos")
_GRAVAR_VALIDADE_DO_PRODUTO = requer_permissao("etiquetas.configurar", "cadastros.produtos")


def _loja_da_etiqueta(cur, ctx: Contexto, id_etiqueta: int) -> int:
    """⚠️ A baixa vale na loja DA ETIQUETA, não na do seletor: quem lê o QR pelo celular
    pode estar com outra loja escolhida. Quem não enxerga aquela loja não passa."""
    cur.execute("SELECT id_unidade FROM etiquetas WHERE id = %s", (id_etiqueta,))
    linha = cur.fetchone()
    if not linha or not ctx.ve_unidade(linha["id_unidade"]):
        raise HTTPException(status_code=404, detail="Etiqueta não encontrada")
    return linha["id_unidade"]


# ---------------------------------------------------------------- configuração

@router.get("/configuracao")
def obter_config(ctx: Contexto = Depends(_VER_VALIDADE)) -> dict:
    with get_cursor() as cur:
        return servico.config(cur, unidade_atual(cur, ctx))


@router.put("/configuracao")
def salvar_config(body: EtiquetaConfig, ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        antes = servico.config(cur, id_unidade)
        cfg = servico.salvar_config(cur, id_unidade, body.model_dump())
        auditoria.registrar(cur, ctx.id_usuario, "etiqueta_config", id_unidade, "salvar",
                            antes=antes, depois=body.model_dump(), id_unidade=id_unidade)
        return cfg | {"message": "Modelo da etiqueta salvo."}


@router.get("/validades/{id_produto}")
def obter_validades(id_produto: int,
                    ctx: Contexto = Depends(_VER_VALIDADE_DO_PRODUTO)) -> list[dict]:
    with get_cursor() as cur:
        return servico.validades(cur, id_produto)


@router.put("/validades/{id_produto}")
def salvar_validades(id_produto: int, body: ValidadesDoProduto,
                     ctx: Contexto = Depends(_GRAVAR_VALIDADE_DO_PRODUTO)) -> dict:
    with get_cursor() as cur:
        antes = servico.validades(cur, id_produto)
        regras = servico.salvar_validades(cur, id_produto,
                                          [r.model_dump() for r in body.regras])
        auditoria.registrar(cur, ctx.id_usuario, "produto_validades", id_produto, "salvar",
                            antes={"regras": antes}, depois={"regras": regras})
        return {"regras": regras, "message": "Validades salvas."}


@router.get("/produtos-com-validade")
def produtos_com_validade(busca: str | None = None,
                          limite: int = Query(default=50, ge=1, le=200),
                          offset: int = Query(default=0, ge=0),
                          resposta: Response = None,
                          ctx: Contexto = Depends(_VER_VALIDADE)) -> list[dict]:
    with get_cursor() as cur:
        return servico.produtos_com_regra(cur, busca, limite, offset, resposta)


# ---------------------------------------------------------------- emissão

@router.get("/sugestao")
def sugestao(id_produto: int, evento: str = "PRODUCAO", conservacao: str | None = None,
             ctx: Contexto = Depends(_IMPRIMIR)) -> dict:
    """A validade calculada ANTES de imprimir — a tela mostra e a pessoa confere."""
    if evento not in servico.EVENTOS:
        raise HTTPException(status_code=400, detail="Evento inválido")
    if conservacao is not None and conservacao not in servico.CONSERVACOES:
        raise HTTPException(status_code=400, detail="Conservação inválida")
    with get_cursor() as cur:
        return servico.sugestao(cur, unidade_atual(cur, ctx), id_produto, evento, conservacao)


@router.get("/producao/{id_producao}")
def da_producao(id_producao: int, ctx: Contexto = Depends(_IMPRIMIR)) -> dict:
    with get_cursor() as cur:
        return servico.da_producao(cur, id_producao, unidade_atual(cur, ctx))


@router.post("", status_code=201)
def emitir(body: EmitirEtiquetas, ctx: Contexto = Depends(_IMPRIMIR)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        if body.id_origem:
            id_unidade = _loja_da_etiqueta(cur, ctx, body.id_origem)
        linhas = servico.emitir(cur, id_unidade=id_unidade, id_usuario=ctx.id_usuario,
                                nome_usuario=ctx.nome, dados=body.model_dump())
        auditoria.registrar(cur, ctx.id_usuario, "etiqueta", linhas[0]["id"], "emitir",
                            depois={"produto": linhas[0]["id_produto"], "evento": body.evento,
                                    "copias": len(linhas),
                                    "codigos": [l["codigo"] for l in linhas]},
                            id_unidade=id_unidade)
        n = len(linhas)
        return {"etiquetas": linhas, "ids": [l["id"] for l in linhas],
                "message": f"{n} etiqueta{'s' if n > 1 else ''} pronta{'s' if n > 1 else ''}."}


@router.get("/pdf")
def imprimir(ids: str = Query(min_length=1), reimpressao: bool = False,
             ctx: Contexto = Depends(_IMPRIMIR)) -> Response:
    try:
        lista = [int(i) for i in ids.split(",") if i.strip()][:200]
    except ValueError:
        raise HTTPException(status_code=400, detail="Lista de etiquetas inválida")
    with get_cursor() as cur:
        id_unidade = _loja_da_etiqueta(cur, ctx, lista[0]) if lista else unidade_atual(cur, ctx)
        conteudo = servico.pdf(cur, lista, id_unidade, reimpressao=reimpressao)
    return Response(conteudo, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="etiquetas.pdf"'})


# ---------------------------------------------------------------- consulta

@router.get("/painel")
def painel(ctx: Contexto = Depends(_IMPRIMIR)) -> dict:
    with get_cursor() as cur:
        return servico.painel(cur, unidade_atual(cur, ctx))


@router.get("")
def listar(situacao: str = "ativas", busca: str | None = None, id_local: int | None = None,
           evento: str | None = None,
           limite: int = Query(default=50, ge=1, le=200),
           offset: int = Query(default=0, ge=0),
           resposta: Response = None,
           ctx: Contexto = Depends(_IMPRIMIR)) -> list[dict]:
    with get_cursor() as cur:
        return servico.consulta(cur, unidade_atual(cur, ctx), situacao, busca, id_local,
                                evento or None, limite, offset, resposta)


@router.get("/codigo/{codigo}")
def por_codigo(codigo: str, ctx: Contexto = Depends(_IMPRIMIR)) -> dict:
    """O que o QR abre: tudo sobre o pote, e as ações que cabem a quem leu."""
    with get_cursor() as cur:
        etq = servico.por_codigo(cur, codigo)
        if not ctx.ve_unidade(etq["id_unidade"]):
            raise HTTPException(status_code=404, detail="Etiqueta não encontrada")
        return etq | {"pode_descartar": ctx.pode("etiquetas.descartar")}


@router.post("/{id_etiqueta}/usar")
def usar(id_etiqueta: int, body: BaixaDeEtiqueta, ctx: Contexto = Depends(_IMPRIMIR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _loja_da_etiqueta(cur, ctx, id_etiqueta)
        etq = servico.usar(cur, id_etiqueta, id_unidade, ctx.id_usuario, body.observacao)
        auditoria.registrar(cur, ctx.id_usuario, "etiqueta", id_etiqueta, "usar",
                            depois={"codigo": etq["codigo"]}, id_unidade=id_unidade)
        return etq | {"message": "Etiqueta baixada: usado."}


@router.post("/{id_etiqueta}/descartar")
def descartar(id_etiqueta: int, body: DescarteDeEtiqueta,
              ctx: Contexto = Depends(_DESCARTAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _loja_da_etiqueta(cur, ctx, id_etiqueta)
        etq = servico.descartar(cur, id_etiqueta, id_unidade, ctx.id_usuario, body.model_dump())
        auditoria.registrar(cur, ctx.id_usuario, "etiqueta", id_etiqueta, "descartar",
                            depois={"codigo": etq["codigo"], "motivo": etq["motivo"],
                                    "movimento": etq["id_movimento"]},
                            id_unidade=id_unidade)
        return etq | {"message": ("Descartado — perda lançada no estoque."
                                  if etq["id_movimento"] else "Descartado.")}
