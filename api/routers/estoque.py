"""Estoque: saldos, razão e lançamentos.

Nenhum endpoint aqui escreve em `estoque_movimentos` na mão — todos passam por
`services.estoque.lancar`, que é onde ficam a trava e o cálculo do médio.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

import auditoria
from database import get_cursor
from models.estoque import (
    EntradaRequest,
    EstornoRequest,
    MovimentoResponse,
    ProducaoRequest,
    SaidaRequest,
    SaldoResponse,
    TransferenciaRequest,
)
from seguranca import Contexto, contexto_atual, requer_permissao
from services import estoque as motor

router = APIRouter(prefix="/estoque", tags=["estoque"])


def _unidade(cur, ctx: Contexto) -> int:
    """A loja do contexto. Com uma só, é ela; com várias, a primeira do usuário."""
    if ctx.unidades:
        return sorted(ctx.unidades)[0]
    cur.execute("SELECT id FROM unidades WHERE ativo ORDER BY matriz DESC, id LIMIT 1")
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=400, detail="Nenhuma loja cadastrada")
    return linha["id"]


@router.get("/saldos", response_model=list[SaldoResponse])
def saldos(
    busca: str | None = Query(default=None, max_length=80),
    id_local: int | None = None,
    apenas_com_saldo: bool = False,
    abaixo_do_minimo: bool = False,
    # Produto desativado com saldo continua existindo — mas só aparece quando
    # pedido, senão o inventário do dia a dia fica cheio de coisa fora de linha.
    incluir_inativos: bool = False,
    ctx: Contexto = Depends(requer_permissao("estoque.saldos")),
) -> list[dict]:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        cur.execute(
            """
            SELECT s.id_produto, p.codigo, p.nome AS produto, p.um_estoque, p.estoque_minimo,
                   s.id_local, l.nome AS local, s.quantidade, s.custo_medio,
                   round(s.quantidade * s.custo_medio, 2) AS valor, s.atualizado_em,
                   (p.estoque_minimo IS NOT NULL AND s.quantidade < p.estoque_minimo) AS abaixo_do_minimo
              FROM estoque_saldos s
              JOIN produtos p ON p.id = s.id_produto
              JOIN locais_estoque l ON l.id = s.id_local
             WHERE s.id_unidade = %s
               AND (%s OR p.ativo)
               AND (%s::int IS NULL OR s.id_local = %s)
               AND (NOT %s OR s.quantidade <> 0)
               AND (NOT %s OR (p.estoque_minimo IS NOT NULL AND s.quantidade < p.estoque_minimo))
               AND (%s::varchar IS NULL
                    OR lower(p.nome) LIKE lower('%%' || %s || '%%')
                    OR lower(p.codigo) LIKE lower('%%' || %s || '%%'))
             ORDER BY lower(p.nome), l.nome
            """,
            (id_unidade, incluir_inativos, id_local, id_local, apenas_com_saldo,
             abaixo_do_minimo, busca, busca, busca),
        )
        return [dict(r) for r in cur.fetchall()]


@router.get("/movimentos", response_model=list[MovimentoResponse])
def movimentos(
    id_produto: int | None = None,
    id_local: int | None = None,
    tipo: str | None = None,
    limite: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    ctx: Contexto = Depends(requer_permissao("estoque.saldos")),
) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT m.id, m.data_movimento, m.tipo, m.id_produto, p.nome AS produto, p.codigo,
                   l.nome AS local, m.quantidade, m.custo_unitario, m.custo_total,
                   m.saldo_apos, m.custo_medio_apos, m.custo_provisorio, m.documento,
                   pm.nome AS motivo, m.observacao, u.nome AS usuario, m.id_estorno_de,
                   EXISTS (SELECT 1 FROM estoque_movimentos e WHERE e.id_estorno_de = m.id) AS estornado
              FROM estoque_movimentos m
              JOIN produtos p ON p.id = m.id_produto
              JOIN locais_estoque l ON l.id = m.id_local
              LEFT JOIN perda_motivos pm ON pm.id = m.id_motivo_perda
              LEFT JOIN usuarios u ON u.id = m.id_usuario
             WHERE (%s::int IS NULL OR m.id_produto = %s)
               AND (%s::int IS NULL OR m.id_local = %s)
               AND (%s::varchar IS NULL OR m.tipo = %s)
             ORDER BY m.id DESC
             LIMIT %s OFFSET %s
            """,
            (id_produto, id_produto, id_local, id_local, tipo, tipo, limite, offset),
        )
        linhas = [dict(r) for r in cur.fetchall()]
    for l in linhas:
        l["rotulo"] = motor.ROTULOS.get(l["tipo"], l["tipo"])
    return linhas


@router.get("/motivos-perda")
def motivos_perda(ctx: Contexto = Depends(contexto_atual)) -> list[dict]:
    with get_cursor() as cur:
        cur.execute("SELECT id, nome FROM perda_motivos WHERE ativo ORDER BY nome")
        return [dict(r) for r in cur.fetchall()]


@router.get("/vencimentos")
def vencimentos(dias: int = Query(default=None, ge=0, le=365),
                ctx: Contexto = Depends(requer_permissao("estoque.saldos"))) -> list[dict]:
    """Lotes vencendo dentro da janela dos parâmetros (ou da informada)."""
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        if dias is None:
            cur.execute(
                "SELECT alerta_validade_dias FROM parametros WHERE id_unidade = %s", (id_unidade,)
            )
            p = cur.fetchone()
            dias = p["alerta_validade_dias"] if p else 15
        cur.execute(
            """SELECT el.id, el.lote, el.validade, el.quantidade, p.nome AS produto,
                      p.codigo, l.nome AS local,
                      (el.validade - current_date) AS dias_restantes
                 FROM estoque_lotes el
                 JOIN produtos p ON p.id = el.id_produto
                 JOIN locais_estoque l ON l.id = el.id_local
                WHERE el.quantidade > 0 AND el.validade IS NOT NULL
                  AND el.validade <= current_date + %s
                ORDER BY el.validade""",
            (dias,),
        )
        return [dict(r) for r in cur.fetchall()]


@router.post("/entradas", status_code=201)
def entrada(body: EntradaRequest,
            ctx: Contexto = Depends(requer_permissao("estoque.entradas"))) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        r = motor.lancar(
            cur, id_unidade=id_unidade, id_produto=body.id_produto, tipo="ENTRADA_MANUAL",
            quantidade=body.quantidade, id_local=body.id_local,
            custo_unitario=body.custo_unitario, data_movimento=body.data_movimento,
            origem_tipo="MANUAL", documento=body.documento, observacao=body.observacao,
            id_usuario=ctx.id_usuario, lote=body.lote, validade=body.validade,
            pode_retroativo=ctx.pode("estoque.retroativo"),
        )
        auditoria.registrar(cur, ctx.id_usuario, "estoque", r["id"], "entrada",
                            depois={"produto": body.id_produto, "qtd": body.quantidade,
                                    "custo": body.custo_unitario}, id_unidade=id_unidade)
    return {"id": r["id"], "saldo": float(r["saldo_apos"]),
            "custo_medio": float(r["custo_medio_apos"]), "message": "Entrada lançada"}


@router.post("/saidas", status_code=201)
def saida(body: SaidaRequest, ctx: Contexto = Depends(contexto_atual)) -> dict:
    # Perda e consumo têm chaves diferentes: quem aponta quebra não
    # necessariamente pode dar baixa de venda.
    chave = {"SAIDA_PERDA": "estoque.perdas"}.get(body.tipo, "estoque.saidas")
    if not ctx.pode(chave):
        raise HTTPException(status_code=403, detail=f"Sem permissão para esta ação ({chave})")
    if body.tipo not in motor.SAIDAS or body.tipo.startswith(("TRANSFERENCIA", "ESTORNO", "AJUSTE")):
        raise HTTPException(status_code=400, detail="Tipo de saída inválido para este endpoint.")

    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        r = motor.lancar(
            cur, id_unidade=id_unidade, id_produto=body.id_produto, tipo=body.tipo,
            quantidade=body.quantidade, id_local=body.id_local,
            data_movimento=body.data_movimento, origem_tipo="MANUAL",
            id_motivo_perda=body.id_motivo_perda, observacao=body.observacao,
            id_usuario=ctx.id_usuario, lote=body.lote, validade=body.validade,
            pode_retroativo=ctx.pode("estoque.retroativo"),
        )
        auditoria.registrar(cur, ctx.id_usuario, "estoque", r["id"], body.tipo.lower(),
                            depois={"produto": body.id_produto, "qtd": body.quantidade},
                            id_unidade=id_unidade)
    return {"id": r["id"], "saldo": float(r["saldo_apos"]),
            "custo_unitario": float(r["custo_unitario"]),
            "custo_provisorio": r["custo_provisorio"], "message": "Saída lançada"}


@router.post("/transferencias", status_code=201)
def transferencia(body: TransferenciaRequest,
                  ctx: Contexto = Depends(requer_permissao("estoque.transferencias"))) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        r = motor.transferir(
            cur, id_unidade=id_unidade, id_produto=body.id_produto, quantidade=body.quantidade,
            id_local_origem=body.id_local_origem, id_local_destino=body.id_local_destino,
            id_usuario=ctx.id_usuario, observacao=body.observacao,
        )
        auditoria.registrar(cur, ctx.id_usuario, "estoque", r["saida"]["id"], "transferencia",
                            depois={"produto": body.id_produto, "qtd": body.quantidade,
                                    "de": body.id_local_origem, "para": body.id_local_destino},
                            id_unidade=id_unidade)
    return {"saida": r["saida"]["id"], "entrada": r["entrada"]["id"],
            "message": "Transferência lançada"}


@router.post("/movimentos/{id_movimento}/estornar", status_code=201)
def estornar(id_movimento: int, body: EstornoRequest,
             ctx: Contexto = Depends(requer_permissao("estoque.ajuste"))) -> dict:
    with get_cursor() as cur:
        r = motor.estornar(cur, id_movimento, ctx.id_usuario, body.motivo)
        auditoria.registrar(cur, ctx.id_usuario, "estoque", id_movimento, "estornar",
                            depois={"movimento_estorno": r["id"], "motivo": body.motivo})
    return {"id": r["id"], "saldo": float(r["saldo_apos"]), "message": "Movimento estornado"}


@router.post("/producoes", status_code=201)
def produzir(body: ProducaoRequest,
             ctx: Contexto = Depends(requer_permissao("estoque.saidas"))) -> dict:
    """Consome a ficha homologada e devolve o produzido ao estoque."""
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        r = motor.produzir(
            cur, id_unidade=id_unidade, id_produto=body.id_produto, quantidade=body.quantidade,
            id_local=body.id_local, id_usuario=ctx.id_usuario, observacao=body.observacao,
        )
        auditoria.registrar(cur, ctx.id_usuario, "producao", r["id"], "produzir",
                            depois={"produto": body.id_produto, "qtd": body.quantidade,
                                    "custo": r["custo_total"]}, id_unidade=id_unidade)
    return r


@router.get("/producoes")
def listar_producoes(limite: int = Query(default=50, ge=1, le=200),
                     ctx: Contexto = Depends(requer_permissao("estoque.saldos"))) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """SELECT pr.id, pr.data, pr.quantidade, pr.custo_total, pr.custo_unitario,
                      pr.versao_ficha, p.nome AS produto, p.codigo, l.nome AS local,
                      u.nome AS usuario
                 FROM producoes pr
                 JOIN produtos p ON p.id = pr.id_produto
                 JOIN locais_estoque l ON l.id = pr.id_local
                 LEFT JOIN usuarios u ON u.id = pr.id_usuario
                ORDER BY pr.data DESC LIMIT %s""",
            (limite,),
        )
        return [dict(r) for r in cur.fetchall()]
