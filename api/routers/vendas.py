"""Vendas — a outra metade do CMV.

Enquanto a API do PDV Legal não abre, a venda entra por planilha ou na mão. O
destino é o mesmo que a integração vai preencher, e o **custo da ficha é
congelado na importação**: o CMV teórico de março não muda quando alguém corrige
uma receita em abril.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

import auditoria
from database import get_cursor
from models.cmv import ImportarVendasRequest, VendaResponse
from seguranca import Contexto, requer_permissao
from services import cmv as motor

router = APIRouter(prefix="/vendas", tags=["vendas"])

_ver = requer_permissao("cmv.painel", "cmv.relatorios")
_editar = requer_permissao("cmv.fechamento", "cmv.painel")


def _unidade(cur, ctx: Contexto) -> int:
    if ctx.unidades:
        return sorted(ctx.unidades)[0]
    cur.execute("SELECT id FROM unidades WHERE ativo ORDER BY matriz DESC, id LIMIT 1")
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=400, detail="Nenhuma loja cadastrada")
    return linha["id"]


@router.get("", response_model=list[VendaResponse])
def listar(
    inicio: date | None = None,
    fim: date | None = None,
    limite: int = Query(default=100, ge=1, le=500),
    ctx: Contexto = Depends(_ver),
) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """SELECT v.id, v.data, v.origem, v.canal, v.documento, v.valor_total, v.cancelada,
                      count(vi.id) AS itens,
                      count(*) FILTER (WHERE vi.custo_ficha_unitario IS NULL) AS sem_custo
                 FROM vendas v
                 LEFT JOIN venda_itens vi ON vi.id_venda = v.id
                WHERE (%s::date IS NULL OR v.data >= %s)
                  AND (%s::date IS NULL OR v.data <= %s)
                GROUP BY v.id
                ORDER BY v.data DESC, v.id DESC
                LIMIT %s""",
            (inicio, inicio, fim, fim, limite),
        )
        return [dict(r) for r in cur.fetchall()]


@router.post("/importar", status_code=201)
def importar(body: ImportarVendasRequest, ctx: Contexto = Depends(_editar)) -> dict:
    """Importa um lote. Documento repetido é ignorado — reimportar não duplica."""
    if not body.vendas:
        raise HTTPException(status_code=400, detail="Nenhuma venda na importação.")

    importadas, repetidas, itens_total, sem_vinculo, sem_custo = 0, 0, 0, 0, 0
    custos_cache: dict[int, tuple] = {}

    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)

        for venda in body.vendas:
            if venda.documento:
                cur.execute(
                    """SELECT 1 FROM vendas
                        WHERE id_unidade = %s AND origem = %s AND documento = %s""",
                    (id_unidade, venda.origem, venda.documento),
                )
                if cur.fetchone():
                    repetidas += 1
                    continue

            total = sum(i.quantidade * i.valor_unitario for i in venda.itens)
            cur.execute(
                """INSERT INTO vendas (id_unidade, data, origem, canal, documento,
                                       valor_total, id_usuario)
                   VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (id_unidade, venda.data, venda.origem, venda.canal, venda.documento,
                 total, ctx.id_usuario),
            )
            id_venda = cur.fetchone()["id"]
            importadas += 1

            for item in venda.itens:
                id_produto = item.id_produto
                if not id_produto and item.codigo:
                    cur.execute(
                        "SELECT id FROM produtos WHERE lower(codigo) = lower(%s)", (item.codigo,)
                    )
                    achado = cur.fetchone()
                    id_produto = achado["id"] if achado else None
                if not id_produto and item.descricao:
                    # Último recurso: nome exato. Semelhança só sugere, nunca vincula.
                    cur.execute(
                        "SELECT id FROM produtos WHERE lower(nome) = lower(%s) AND ativo",
                        (item.descricao,),
                    )
                    achado = cur.fetchone()
                    id_produto = achado["id"] if achado else None

                custo, origem = (None, "sem_produto")
                if id_produto:
                    if id_produto not in custos_cache:
                        custos_cache[id_produto] = motor.custo_teorico_do_produto(cur, id_produto)
                    custo, origem = custos_cache[id_produto]
                else:
                    sem_vinculo += 1
                if custo is None:
                    sem_custo += 1

                cur.execute(
                    """INSERT INTO venda_itens (id_venda, codigo_pdv, descricao_pdv, id_produto,
                                                quantidade, valor_unitario, valor_total,
                                                custo_ficha_unitario, origem_custo)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (id_venda, item.codigo, item.descricao, id_produto, item.quantidade,
                     item.valor_unitario, item.quantidade * item.valor_unitario, custo, origem),
                )
                itens_total += 1

        auditoria.registrar(cur, ctx.id_usuario, "vendas", None, "importar",
                            depois={"vendas": importadas, "itens": itens_total,
                                    "repetidas": repetidas, "sem_vinculo": sem_vinculo},
                            id_unidade=id_unidade)

    return {
        "importadas": importadas,
        "repetidas": repetidas,
        "itens": itens_total,
        "itens_sem_vinculo": sem_vinculo,
        "itens_sem_custo": sem_custo,
        "message": f"{importadas} venda(s) importada(s)"
        + (f", {repetidas} já existiam" if repetidas else ""),
    }


@router.delete("/{id_venda}")
def cancelar(id_venda: int, ctx: Contexto = Depends(_editar)) -> dict:
    """Cancela a venda para o CMV — não apaga, para o histórico continuar fiel."""
    with get_cursor() as cur:
        cur.execute("UPDATE vendas SET cancelada = true WHERE id = %s", (id_venda,))
        auditoria.registrar(cur, ctx.id_usuario, "vendas", id_venda, "cancelar")
    return {"message": "Venda cancelada"}


@router.get("/sem-vinculo")
def sem_vinculo(ctx: Contexto = Depends(_ver)) -> list[dict]:
    """Itens vendidos que não achamos no cadastro — a fila de de-para do PDV."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT vi.codigo_pdv, vi.descricao_pdv, count(*) AS ocorrencias,
                      sum(vi.quantidade) AS quantidade, sum(vi.valor_total) AS receita
                 FROM venda_itens vi
                 JOIN vendas v ON v.id = vi.id_venda
                WHERE vi.id_produto IS NULL AND NOT v.cancelada
                GROUP BY vi.codigo_pdv, vi.descricao_pdv
                ORDER BY receita DESC LIMIT 100"""
        )
        return [dict(r) for r in cur.fetchall()]
