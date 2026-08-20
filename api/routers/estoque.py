"""Estoque: saldos, razão e lançamentos.

Nenhum endpoint aqui escreve em `estoque_movimentos` na mão — todos passam por
`services.estoque.lancar`, que é onde ficam a trava e o cálculo do médio.
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response

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
from seguranca import Contexto, contexto_atual, requer_permissao, unidade_atual
from services import estoque as motor

router = APIRouter(prefix="/estoque", tags=["estoque"])


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
        id_unidade = unidade_atual(cur, ctx)
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
    # `inicio`/`fim` com os mesmos nomes do CSV do razão: o período é a
    # pergunta mais comum aqui ("o que entrou de café em agosto?") e ter dois
    # nomes para a mesma coisa em duas portas só confunde.
    inicio: date | None = None,
    fim: date | None = None,
    busca: str | None = None,
    limite: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    resposta: Response = None,
    ctx: Contexto = Depends(requer_permissao("estoque.saldos")),
) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT m.id, m.data_movimento, m.tipo, m.id_produto, p.nome AS produto, p.codigo,
                   l.nome AS local, m.quantidade, m.custo_unitario, m.custo_total,
                   m.saldo_apos, m.custo_medio_apos, m.custo_provisorio, m.documento,
                   pm.nome AS motivo, m.observacao, u.nome AS usuario, m.id_estorno_de,
                   EXISTS (SELECT 1 FROM estoque_movimentos e WHERE e.id_estorno_de = m.id) AS estornado,
                   count(*) OVER () AS _total
              FROM estoque_movimentos m
              JOIN produtos p ON p.id = m.id_produto
              JOIN locais_estoque l ON l.id = m.id_local
              LEFT JOIN perda_motivos pm ON pm.id = m.id_motivo_perda
              LEFT JOIN usuarios u ON u.id = m.id_usuario
             WHERE (%s::int IS NULL OR m.id_produto = %s)
               AND (%s::int IS NULL OR m.id_local = %s)
               AND (%s::varchar IS NULL OR m.tipo = %s)
               AND (%s::date IS NULL OR m.data_movimento >= %s)
               -- `fim` é dia CHEIO: `<= fim` cortaria o que foi lançado às 14h
               -- do próprio dia, porque a coluna guarda data e hora.
               AND (%s::date IS NULL OR m.data_movimento < %s::date + 1)
               AND (%s::varchar IS NULL
                    OR lower(p.nome) LIKE lower('%%' || %s || '%%')
                    OR lower(p.codigo) LIKE lower('%%' || %s || '%%'))
             ORDER BY m.id DESC
             LIMIT %s OFFSET %s
            """,
            (id_produto, id_produto, id_local, id_local, tipo, tipo,
             inicio, inicio, fim, fim, busca, busca, busca, limite, offset),
        )
        linhas = [dict(r) for r in cur.fetchall()]
    total = linhas[0].pop("_total", len(linhas)) if linhas else offset
    for l in linhas:
        l.pop("_total", None)
        l["rotulo"] = motor.ROTULOS.get(l["tipo"], l["tipo"])
    if resposta is not None:
        resposta.headers["X-Total"] = str(total)
    return linhas


@router.get("/tipos-movimento")
def tipos_movimento(ctx: Contexto = Depends(contexto_atual)) -> list[dict]:
    """Os tipos de movimento e como se chamam na tela.

    Vem do servidor para o filtro do razão não repetir a lista à mão: um tipo
    novo apareceria nos lançamentos e não no filtro, e ninguém notaria.
    """
    return [{"tipo": t, "rotulo": r} for t, r in motor.ROTULOS.items()]


@router.get("/motivos-perda")
def motivos_perda(ctx: Contexto = Depends(contexto_atual)) -> list[dict]:
    with get_cursor() as cur:
        cur.execute("SELECT id, nome FROM perda_motivos WHERE ativo ORDER BY nome")
        return [dict(r) for r in cur.fetchall()]


@router.get("/lotes")
def lotes(id_produto: int | None = None,
          incluir_zerados: bool = False,
          incluir_inativos: bool = False,
          ctx: Contexto = Depends(requer_permissao("estoque.saldos"))) -> list[dict]:
    """Os lotes em estoque, na ordem em que o FEFO vai consumi-los.

    Diferente de `/vencimentos`, que só olha a janela de alerta: aqui entra
    também o lote sem validade — que existe, ocupa prateleira, e é o último da
    fila justamente por não ter data.
    """
    with get_cursor() as cur:
        cur.execute(
            """SELECT el.id, el.id_produto, el.lote, el.validade, el.quantidade,
                      p.nome AS produto, p.codigo, p.um_estoque, l.nome AS local,
                      (el.validade - current_date) AS dias_restantes
                 FROM estoque_lotes el
                 JOIN produtos p ON p.id = el.id_produto
                 JOIN locais_estoque l ON l.id = el.id_local
                WHERE (%s::int IS NULL OR el.id_produto = %s)
                  AND (%s OR el.quantidade > 0)
                  -- Produto desativado guarda saldo e razão, mas não tem o que
                  -- fazer na fila de separação: ninguém vai buscar aquele pote.
                  AND (%s OR p.ativo)
                ORDER BY p.nome, el.validade NULLS LAST, el.id""",
            (id_produto, id_produto, incluir_zerados, incluir_inativos),
        )
        return [dict(r) for r in cur.fetchall()]


@router.get("/vencimentos")
def vencimentos(dias: int = Query(default=None, ge=0, le=365),
                ctx: Contexto = Depends(requer_permissao("estoque.saldos"))) -> list[dict]:
    """Lotes vencendo dentro da janela dos parâmetros (ou da informada)."""
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
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


def _frase_dos_lotes(r: dict) -> str | None:
    """Diz de qual lote a mercadoria saiu — a conferência que se faz na prateleira."""
    lotes = r.get("lotes") or []
    if not lotes:
        return None
    partes = []
    for l in lotes:
        nome = l.get("lote") or "sem identificação"
        venc = f" (vence {l['validade'].strftime('%d/%m')})" if l.get("validade") else ""
        partes.append(f"{_qtd(l['quantidade'])} do lote {nome}{venc}")
    return "Saída lançada: " + ", ".join(partes)


def _qtd(valor) -> str:
    """6.0000 vira "6"; 2.5 vira "2,5".

    `:g` não serve: em `Decimal` ele preserva as casas do coeficiente, e a tela
    mostrava "6.0000 do lote" — número de sistema no meio de uma frase que a
    cozinha lê.
    """
    d = Decimal(str(valor)).normalize()
    if d == d.to_integral_value():
        d = d.quantize(Decimal(1))
    return f"{d:f}".replace(".", ",")


@router.post("/entradas", status_code=201)
def entrada(body: EntradaRequest,
            ctx: Contexto = Depends(requer_permissao("estoque.entradas"))) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
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
            "custo_medio": float(r["custo_medio_apos"]),
            "lotes": r.get("lotes") or [], "message": "Entrada lançada"}


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
        id_unidade = unidade_atual(cur, ctx)
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
            "custo_provisorio": r["custo_provisorio"],
            # De quais lotes saiu: quem deu baixa precisa poder conferir na
            # prateleira que pegou o pote certo.
            "lotes": r.get("lotes") or [],
            "message": _frase_dos_lotes(r) or "Saída lançada"}


@router.post("/transferencias", status_code=201)
def transferencia(body: TransferenciaRequest,
                  ctx: Contexto = Depends(requer_permissao("estoque.transferencias"))) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
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
    return {"id": r["id"], "saldo": float(r["saldo_apos"]),
            "lotes": r.get("lotes") or [], "message": "Movimento estornado"}


@router.post("/producoes", status_code=201)
def produzir(body: ProducaoRequest,
             ctx: Contexto = Depends(requer_permissao("estoque.saidas"))) -> dict:
    """Consome a ficha homologada e devolve o produzido ao estoque."""
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
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
