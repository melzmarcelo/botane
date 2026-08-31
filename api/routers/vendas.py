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
from paginacao import pagina
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
    # A busca vai ao SERVIDOR: com 1.375 vendas num mês, filtrar a página
    # carregada acharia o documento só quando ele já estivesse na tela.
    busca: str | None = None,
    origem: str | None = None,
    limite: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    resposta: Response = None,
    ctx: Contexto = Depends(_ver),
) -> list[dict]:
    """As vendas da loja atual, da mais recente para a mais antiga.

    ⚠️ **Filtra por `id_unidade`, e isso não estava aqui.** Toda tabela de
    movimento carrega a loja desde o começo, mas a listagem somava as de todas —
    numa casa com duas lojas, a tela de uma mostraria as vendas da outra e o
    total não bateria com o CMV daquela loja.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        alvo = f"%{busca.strip()}%" if busca and busca.strip() else None
        return pagina(
            cur,
            """SELECT v.id, v.data, v.hora, v.origem, v.canal, v.documento, v.valor_total,
                      v.cancelada,
                      count(vi.id) AS itens,
                      count(*) FILTER (WHERE vi.custo_ficha_unitario IS NULL) AS sem_custo
                 FROM vendas v
                 LEFT JOIN venda_itens vi ON vi.id_venda = v.id
                WHERE v.id_unidade = %s
                  AND (%s::date IS NULL OR v.data >= %s)
                  AND (%s::date IS NULL OR v.data <= %s)
                  AND (%s::text IS NULL OR v.origem = %s)
                  AND (%s::text IS NULL OR v.documento ILIKE %s)
                GROUP BY v.id
                -- Com a hora gravada, a ordem do DIA passa a ser a do relógio:
                -- quem procura "a venda das 14h" não a acha pela ordem de
                -- importação. NULLS LAST porque a planilha não tem hora.
                ORDER BY v.data DESC, v.hora DESC NULLS LAST, v.id DESC""",
            (id_unidade, inicio, inicio, fim, fim, origem, origem, alvo, alvo),
            limite=limite, offset=offset, resposta=resposta,
        )


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
                """INSERT INTO vendas (id_unidade, data, hora, origem, canal, documento,
                                       valor_total, id_usuario)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (id_unidade, venda.data, venda.hora, venda.origem, venda.canal,
                 venda.documento, total, ctx.id_usuario),
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
                        # 🔑 A loja vai junto: este custo é CONGELADO no item de
                        # venda. Calculado com o estoque das duas lojas, o erro
                        # fica gravado no CMV daquele mês, sem conserto.
                        custos_cache[id_produto] = motor.custo_teorico_do_produto(
                            cur, id_produto, id_unidade=id_unidade)
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
        # ⚠️ A loja entra na busca: sem ela, um id de outra loja seria cancelado
        # por quem nem enxerga aquela venda na tela.
        id_unidade = unidade_atual(cur, ctx)
        cur.execute("SELECT cancelada FROM vendas WHERE id = %s AND id_unidade = %s",
                    (id_venda, id_unidade))
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
def sem_vinculo(busca: str | None = None, ctx: Contexto = Depends(_ver)) -> list[dict]:
    """Itens vendidos que não achamos no cadastro — a fila de de-para do PDV.

    ⚠️ **A lista é cortada no topo por RECEITA, e por isso tem busca.** São os
    100 que mais pesam; num cardápio grande, o item que alguém quer resolver
    raramente está entre eles — e não achá-lo lê como "já foi resolvido", que é
    outra coisa. É a mesma lição do ranking de margem, que ganhou `id_produto`
    pelo mesmo motivo.
    """
    alvo = f"%{busca.strip()}%" if busca and busca.strip() else None
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT vi.codigo_pdv, vi.descricao_pdv, count(*) AS ocorrencias,
                      sum(vi.quantidade) AS quantidade, sum(vi.valor_total) AS receita
                 FROM venda_itens vi
                 JOIN vendas v ON v.id = vi.id_venda
                WHERE vi.id_produto IS NULL AND NOT v.cancelada AND v.id_unidade = %(u)s
                  AND (%(alvo)s::text IS NULL
                       OR vi.codigo_pdv ILIKE %(alvo)s
                       OR vi.descricao_pdv ILIKE %(alvo)s)
                GROUP BY vi.codigo_pdv, vi.descricao_pdv
                ORDER BY receita DESC LIMIT 100""",
            {"u": id_unidade, "alvo": alvo},
        )
        return [dict(r) for r in cur.fetchall()]


# ⚠️ **`/{id_venda}` vem DEPOIS de `/sem-vinculo`, e a ordem é o que faz as duas
# funcionarem.** O FastAPI casa as rotas na ordem em que foram declaradas: com o
# parâmetro na frente, "sem-vinculo" viraria um id e o pedido morreria em 422
# antes de chegar à fila de de-para.
@router.get("/{id_venda}")
def detalhe(id_venda: int, ctx: Contexto = Depends(_ver)) -> dict:
    """Uma venda inteira: cabeçalho, itens e o que cada item deixou.

    ⚠️ **O custo aqui é o CONGELADO no item**, não o custo de hoje. É ele que
    entrou no CMV teórico daquele dia, e recalcular na hora de mostrar faria a
    tela discordar do relatório — a diferença apareceria como variância sem
    causa. Item sem custo é item cujo prato não tem ficha; ele aparece dito
    assim, porque é o que explica um CMV teórico menor que o real.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT v.id, v.data, v.hora, v.origem, v.canal, v.documento, v.id_externo,
                      v.mesa, v.valor_total, v.desconto, v.cancelada, v.importada_em,
                      u.nome AS usuario
                 FROM vendas v
                 LEFT JOIN usuarios u ON u.id = v.id_usuario
                WHERE v.id = %s AND v.id_unidade = %s""",
            (id_venda, id_unidade),
        )
        venda = cur.fetchone()
        if not venda:
            raise HTTPException(status_code=404, detail="Venda não encontrada")

        cur.execute(
            """SELECT vi.id, vi.codigo_pdv, vi.descricao_pdv, vi.id_produto,
                      vi.quantidade, vi.valor_unitario, vi.valor_total,
                      vi.custo_ficha_unitario, vi.origem_custo,
                      p.nome AS produto, p.codigo AS produto_codigo, p.tipo,
                      c.nome AS categoria, s.nome AS setor
                 FROM venda_itens vi
                 LEFT JOIN produtos p ON p.id = vi.id_produto
                 LEFT JOIN categorias c ON c.id = p.id_categoria
                 LEFT JOIN setores s ON s.id = p.id_setor
                WHERE vi.id_venda = %s
                ORDER BY vi.id""",
            (id_venda,),
        )
        itens = [dict(r) for r in cur.fetchall()]

        # Os movimentos de estoque que esta venda causou — a prova de que ela
        # saiu da prateleira, e o que o estorno devolveu quando foi cancelada.
        #
        # ⚠️ **O estorno NÃO se acha pela origem da venda.** Ele nasce com
        # `origem_tipo = 'ESTORNO'` e `origem_id` apontando para o movimento que
        # desfaz, não para a venda — procurar só por `origem_tipo = 'VENDA'`
        # mostrava a saída e escondia a devolução, e a tela de uma venda
        # cancelada dizia que o produto tinha saído e nunca voltado. A segunda
        # perna do OR é o que fecha o par.
        cur.execute(
            """WITH da_venda AS (
                   SELECT id FROM estoque_movimentos
                    WHERE origem_tipo = 'VENDA' AND origem_id = %s
               )
               SELECT m.id, m.tipo, m.quantidade, m.custo_total, m.data_movimento,
                      m.id_estorno_de, p.nome AS produto, l.nome AS local
                 FROM estoque_movimentos m
                 JOIN produtos p ON p.id = m.id_produto
                 LEFT JOIN locais_estoque l ON l.id = m.id_local
                WHERE m.id IN (SELECT id FROM da_venda)
                   OR m.id_estorno_de IN (SELECT id FROM da_venda)
                ORDER BY m.id""",
            (id_venda,),
        )
        movimentos = [dict(r) for r in cur.fetchall()]

    custo = sum(float(i["quantidade"]) * float(i["custo_ficha_unitario"] or 0) for i in itens)
    receita = sum(float(i["valor_total"] or 0) for i in itens)
    return {
        **dict(venda),
        "itens": itens,
        "movimentos": movimentos,
        "receita": receita,
        # ⚠️ O custo teórico só vale a soma quando TODO item tem ficha. Com um
        # item sem custo, a margem sairia alta demais e pareceria um resultado
        # excelente — por isso a tela recebe a contagem e diz "parcial".
        "custo_teorico": custo,
        "itens_sem_custo": sum(1 for i in itens if i["custo_ficha_unitario"] is None),
        "itens_sem_vinculo": sum(1 for i in itens if i["id_produto"] is None),
    }
