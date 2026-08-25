"""Vendas — a outra metade do CMV.

Enquanto a API do PDV Legal não abre, a venda entra por planilha ou na mão. O
destino é o mesmo que a integração vai preencher, e o **custo da ficha é
congelado na importação**: o CMV teórico de março não muda quando alguém corrige
uma receita em abril.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response

import auditoria
from database import get_cursor
from paginacao import com_total
from models.cmv import ImportarVendasRequest, VendaResponse
from seguranca import Contexto, requer_permissao, unidade_atual
from services import cmv as motor
from services import estoque as motor_estoque
from services import producao_agenda as agenda

router = APIRouter(prefix="/vendas", tags=["vendas"])

_ver = requer_permissao("cmv.painel", "cmv.relatorios")
_editar = requer_permissao("cmv.fechamento", "cmv.painel")


@router.get("", response_model=list[VendaResponse])
def listar(
    inicio: date | None = None,
    fim: date | None = None,
    limite: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    resposta: Response = None,
    ctx: Contexto = Depends(_ver),
) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """SELECT v.id, v.data, v.origem, v.canal, v.documento, v.valor_total, v.cancelada,
                      count(vi.id) AS itens,
                      count(*) FILTER (WHERE vi.custo_ficha_unitario IS NULL) AS sem_custo,
                      count(*) OVER () AS _total
                 FROM vendas v
                 LEFT JOIN venda_itens vi ON vi.id_venda = v.id
                WHERE (%s::date IS NULL OR v.data >= %s)
                  AND (%s::date IS NULL OR v.data <= %s)
                GROUP BY v.id
                ORDER BY v.data DESC, v.id DESC
                LIMIT %s OFFSET %s""",
            (inicio, inicio, fim, fim, limite, offset),
        )
        linhas = [dict(r) for r in cur.fetchall()]
    return com_total(linhas, resposta, offset)


@router.post("/importar", status_code=201)
def importar(body: ImportarVendasRequest, ctx: Contexto = Depends(_editar)) -> dict:
    """Importa um lote. Documento repetido é ignorado — reimportar não duplica."""
    if not body.vendas:
        raise HTTPException(status_code=400, detail="Nenhuma venda na importação.")

    importadas, repetidas, itens_total, sem_vinculo, sem_custo = 0, 0, 0, 0, 0
    produzidos_na_hora, baixados = 0, 0
    custos_cache: dict[int, tuple] = {}

    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)

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

                # VENDER É SAIR DO ESTOQUE. Sem esta baixa, o que foi vendido
                # continuava na prateleira do sistema: o CMV real ficava
                # subestimado e a primeira contagem cobria o buraco inteiro
                # como "ajuste de inventário", que é onde a diferença some.
                #
                # O que é feito NA HORA nasce e morre aqui: produz e baixa no
                # mesmo lançamento, e o saldo volta a zero. O que é PARA
                # ESTOQUE só baixa — foi produzido antes.
                if id_produto:
                    cur.execute(
                        """SELECT controla_estoque, id_local_padrao FROM produtos
                            WHERE id = %s""",
                        (id_produto,),
                    )
                    p_venda = cur.fetchone() or {}
                    if p_venda.get("controla_estoque"):
                        feito = agenda.producao_da_venda(
                            cur, id_unidade, id_produto, item.quantidade, ctx.id_usuario,
                            documento=venda.documento)
                        if feito:
                            produzidos_na_hora += 1
                        motor_estoque.lancar(
                            cur, id_unidade=id_unidade,
                            id_local=(feito or {}).get("id_local")
                                     or p_venda.get("id_local_padrao"),
                            id_produto=id_produto,
                            tipo="SAIDA_VENDA", quantidade=item.quantidade,
                            data_movimento=venda.data,
                            origem_tipo="VENDA", origem_id=id_venda,
                            documento=venda.documento, id_usuario=ctx.id_usuario,
                            observacao=("Produzido e vendido na hora" if feito
                                        else "Baixa da venda"),
                        )
                        baixados += 1

        auditoria.registrar(cur, ctx.id_usuario, "vendas", None, "importar",
                            depois={"vendas": importadas, "itens": itens_total,
                                    "repetidas": repetidas, "sem_vinculo": sem_vinculo,
                                    "produzidos_na_hora": produzidos_na_hora,
                                    "baixados": baixados},
                            id_unidade=id_unidade)

    return {
        "importadas": importadas,
        "repetidas": repetidas,
        "itens": itens_total,
        "itens_sem_vinculo": sem_vinculo,
        "itens_sem_custo": sem_custo,
        "produzidos_na_hora": produzidos_na_hora,
        "itens_baixados": baixados,
        "message": f"{importadas} venda(s) importada(s)"
        + (f", {repetidas} já existiam" if repetidas else "")
        + (f", {baixados} item(ns) baixado(s) do estoque" if baixados else "")
        + (f" ({produzidos_na_hora} produzido[s] na hora)" if produzidos_na_hora else ""),
    }


@router.delete("/{id_venda}")
def cancelar(id_venda: int, ctx: Contexto = Depends(_editar)) -> dict:
    """Cancela a venda para o CMV — não apaga, para o histórico continuar fiel.

    A baixa de estoque que a venda causou volta como ESTORNO. Cancelar sem
    devolver deixaria o produto vendido fora da prateleira e fora do caixa ao
    mesmo tempo — a diferença apareceria na contagem, sem nome.
    """
    with get_cursor() as cur:
        cur.execute("SELECT cancelada FROM vendas WHERE id = %s", (id_venda,))
        venda = cur.fetchone()
        if not venda:
            raise HTTPException(status_code=404, detail="Venda não encontrada")
        if venda["cancelada"]:
            raise HTTPException(status_code=400, detail="Esta venda já está cancelada.")

        cur.execute(
            """SELECT m.id FROM estoque_movimentos m
                WHERE m.origem_tipo = 'VENDA' AND m.origem_id = %s
                  AND NOT EXISTS (SELECT 1 FROM estoque_movimentos e
                                   WHERE e.id_estorno_de = m.id)
                ORDER BY m.id DESC""",
            (id_venda,),
        )
        movimentos = [r["id"] for r in cur.fetchall()]
        for id_movimento in movimentos:
            motor_estoque.estornar(cur, id_movimento, ctx.id_usuario,
                                   f"Cancelamento da venda #{id_venda}")

        cur.execute("UPDATE vendas SET cancelada = true WHERE id = %s", (id_venda,))
        auditoria.registrar(cur, ctx.id_usuario, "vendas", id_venda, "cancelar",
                            depois={"movimentos_estornados": len(movimentos)})
    return {"estornados": len(movimentos),
            "message": "Venda cancelada"
                       + (f" — {len(movimentos)} movimento(s) devolvido(s) ao estoque"
                          if movimentos else "")}


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
