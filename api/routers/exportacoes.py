"""Exportações em CSV.

Cada relatório usa a **mesma permissão da tela** que o mostra — exportar não é
uma porta lateral para ver o que a pessoa não poderia ver.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

import auditoria
from database import get_cursor
from seguranca import Contexto, contexto_atual, unidade_atual
from services import alertas as alertas_motor
from services import cmv as cmv_motor
from services import relatorios
from services import exportacao
from services import estoque as estoque_motor

router = APIRouter(prefix="/exportar", tags=["exportações"])


def _exige(ctx: Contexto, chave: str) -> None:
    if not ctx.pode(chave):
        raise HTTPException(status_code=403, detail=f"Sem permissão para esta ação ({chave})")


def _resposta(conteudo: str, nome: str) -> Response:
    return Response(
        content=conteudo.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


def _periodo(inicio: date | None, fim: date | None) -> tuple[date, date]:
    hoje = date.today()
    return (inicio or hoje.replace(day=1)), (fim or hoje)


@router.get("/saldos.csv")
def saldos(ctx: Contexto = Depends(contexto_atual)) -> Response:
    _exige(ctx, "estoque.saldos")
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT p.codigo, p.nome AS produto, c.nome AS categoria, l.nome AS local,
                      p.um_estoque, s.quantidade, s.custo_medio,
                      round(s.quantidade * s.custo_medio, 2) AS valor, p.estoque_minimo
                 FROM estoque_saldos s
                 JOIN produtos p ON p.id = s.id_produto
                 JOIN locais_estoque l ON l.id = s.id_local
                 LEFT JOIN categorias c ON c.id = p.id_categoria
                WHERE s.id_unidade = %s AND p.ativo AND s.quantidade <> 0
                ORDER BY lower(p.nome), l.nome""",
            (id_unidade,),
        )
        linhas = [dict(r) for r in cur.fetchall()]
        total = sum(float(l["valor"] or 0) for l in linhas)
        auditoria.registrar(cur, ctx.id_usuario, "exportacao", "saldos", "exportar",
                            depois={"linhas": len(linhas)}, id_unidade=id_unidade)

    conteudo = exportacao.csv_de(
        linhas,
        [("codigo", "Código"), ("produto", "Produto"), ("categoria", "Categoria"),
         ("local", "Local"), ("um_estoque", "Unidade"), ("quantidade", "Saldo"),
         ("custo_medio", "Custo médio"), ("valor", "Valor em estoque"),
         ("estoque_minimo", "Estoque mínimo")],
        titulo="Posição de estoque",
        resumo=[("Linhas", len(linhas)), ("Valor total em estoque", round(total, 2))],
    )
    return _resposta(conteudo, exportacao.nome_arquivo("estoque"))


@router.get("/movimentos.csv")
def movimentos(inicio: date | None = None, fim: date | None = None,
               tipo: str | None = None, id_local: int | None = None,
               busca: str | None = None,
               ctx: Contexto = Depends(contexto_atual)) -> Response:
    """O razão em CSV, com os MESMOS filtros da tela.

    Sem eles, filtrar na tela e clicar em baixar dava outro arquivo — e quem
    conferisse os dois acharia que um dos dois está errado.
    """
    _exige(ctx, "estoque.saldos")
    inicio, fim = _periodo(inicio, fim)
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT m.data_movimento, m.tipo, p.codigo, p.nome AS produto, l.nome AS local,
                      m.quantidade, m.custo_unitario, m.custo_total, m.saldo_apos,
                      m.custo_medio_apos, m.documento, pm.nome AS motivo, m.observacao,
                      u.nome AS usuario
                 FROM estoque_movimentos m
                 JOIN produtos p ON p.id = m.id_produto
                 JOIN locais_estoque l ON l.id = m.id_local
                 LEFT JOIN perda_motivos pm ON pm.id = m.id_motivo_perda
                 LEFT JOIN usuarios u ON u.id = m.id_usuario
                WHERE m.id_unidade = %s AND m.data_movimento >= %s AND m.data_movimento < %s
                  AND (%s::varchar IS NULL OR m.tipo = %s)
                  AND (%s::int IS NULL OR m.id_local = %s)
                  AND (%s::varchar IS NULL
                       OR lower(p.nome) LIKE lower('%%' || %s || '%%')
                       OR lower(p.codigo) LIKE lower('%%' || %s || '%%'))
                ORDER BY m.id""",
            (id_unidade, inicio, fim + timedelta(days=1), tipo, tipo,
             id_local, id_local, busca, busca, busca),
        )
        linhas = [dict(r) for r in cur.fetchall()]
    for l in linhas:
        l["tipo"] = estoque_motor.ROTULOS.get(l["tipo"], l["tipo"])

    conteudo = exportacao.csv_de(
        linhas,
        [("data_movimento", "Data"), ("tipo", "Movimento"), ("codigo", "Código"),
         ("produto", "Produto"), ("local", "Local"), ("quantidade", "Quantidade"),
         ("custo_unitario", "Custo unitário"), ("custo_total", "Custo total"),
         ("saldo_apos", "Saldo depois"), ("custo_medio_apos", "Custo médio depois"),
         ("documento", "Documento"), ("motivo", "Motivo"), ("observacao", "Observação"),
         ("usuario", "Quem lançou")],
        titulo=f"Razão de estoque — {inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}",
        resumo=[("Movimentos", len(linhas))],
    )
    return _resposta(conteudo, exportacao.nome_arquivo("movimentos", inicio, fim))


@router.get("/cmv.csv")
def cmv(inicio: date | None = None, fim: date | None = None,
        ctx: Contexto = Depends(contexto_atual)) -> Response:
    """A apuração aberta linha a linha — é o arquivo que vai para o contador."""
    _exige(ctx, "cmv.relatorios")
    inicio, fim = _periodo(inicio, fim)
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        a = cmv_motor.apurar(cur, id_unidade, inicio, fim)
        margem = cmv_motor.margem_por_prato(cur, id_unidade, inicio, fim, 500)
        auditoria.registrar(cur, ctx.id_usuario, "exportacao", "cmv", "exportar",
                            depois={"inicio": str(inicio), "fim": str(fim)},
                            id_unidade=id_unidade)

    composicao = [
        {"linha": "Estoque inicial", "valor": a["estoque_inicial"]},
        {"linha": "(+) Compras", "valor": a["compras"]},
        {"linha": "(−) Estoque final", "valor": -a["estoque_final"]},
        {"linha": "(=) CMV real", "valor": a["cmv_real"]},
        {"linha": "CMV teórico (fichas × vendas)", "valor": a["cmv_teorico"]},
        {"linha": "Variância (real − teórico)", "valor": a["variancia"]},
        {"linha": "  dos quais: perdas", "valor": a["perdas"]},
        {"linha": "  dos quais: consumo interno", "valor": a["consumo_interno"]},
        {"linha": "  dos quais: ajustes de inventário", "valor": a["ajustes"]},
        {"linha": "Receita do período", "valor": a["receita"]},
    ]

    primeira = exportacao.csv_de(
        composicao, [("linha", "Composição do CMV"), ("valor", "Valor (R$)")],
        titulo=f"CMV — {inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}",
        resumo=[("Food cost", f"{a['food_cost_pct']:.2f}%" if a["food_cost_pct"] else "—"),
                ("Cobertura de ficha", f"{a['cobertura_ficha_pct']:.1f}%"),
                ("Vendas no período", a["vendas"])],
    )
    segunda = exportacao.csv_de(
        margem,
        [("produto", "Prato"), ("quantidade", "Vendidos"), ("receita", "Receita"),
         ("custo", "Custo pela ficha"), ("margem", "Margem"),
         ("food_cost_pct", "Food cost %"), ("sem_custo", "Tem item sem custo")],
        titulo="Margem por prato",
    ).lstrip(exportacao.BOM)

    return _resposta(primeira + "\r\n" + segunda, exportacao.nome_arquivo("cmv", inicio, fim))


@router.get("/movimentacao.csv")
def movimentacao(inicio: date | None = None, fim: date | None = None,
                 ctx: Contexto = Depends(contexto_atual)) -> Response:
    """A movimentação do mês, produto a produto — a planilha que se confere.

    Mês fechado sai do que foi CONGELADO no fechamento; mês aberto sai do razão
    na hora. O cabeçalho diz qual dos dois, porque mandar ao contador um número
    que ainda pode mudar é o erro que este relatório existe para evitar.
    """
    _exige(ctx, "cmv.relatorios")
    inicio, fim = _periodo(inicio, fim)
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT id, competencia FROM cmv_fechamentos
                WHERE id_unidade = %s AND inicio = %s AND fim = %s AND status = 'FECHADO'""",
            (id_unidade, inicio, fim),
        )
        fechamento = cur.fetchone()
        if fechamento:
            linhas = cmv_motor.movimentacao_congelada(cur, fechamento["id"])
        else:
            linhas = cmv_motor.movimentacao_por_produto(cur, id_unidade, inicio, fim)
        auditoria.registrar(cur, ctx.id_usuario, "exportacao", "movimentacao", "exportar",
                            depois={"inicio": str(inicio), "fim": str(fim),
                                    "congelado": bool(fechamento)},
                            id_unidade=id_unidade)

    soma = lambda campo: sum(float(l[campo] or 0) for l in linhas)  # noqa: E731
    conteudo = exportacao.csv_de(
        linhas,
        [("codigo", "Código"), ("produto", "Produto"), ("um_estoque", "Un."),
         ("categoria", "Categoria"), ("setor", "Setor"),
         ("qtd_inicial", "Estoque inicial (qtd)"), ("valor_inicial", "Estoque inicial (R$)"),
         ("qtd_entradas", "Entradas (qtd)"), ("valor_entradas", "Entradas (R$)"),
         ("qtd_saidas", "Saídas (qtd)"), ("valor_saidas", "Saídas (R$)"),
         ("qtd_final", "Estoque final (qtd)"), ("valor_final", "Estoque final (R$)"),
         ("custo_medio_final", "Custo médio final")],
        titulo=(f"Movimentação de estoque — {inicio.strftime('%d/%m/%Y')} a "
                f"{fim.strftime('%d/%m/%Y')}"),
        resumo=[
            ("Situação", "mês fechado (congelado)" if fechamento else "mês aberto (parcial)"),
            ("Produtos", len(linhas)),
            ("Estoque inicial (R$)", round(soma("valor_inicial"), 2)),
            ("Entradas (R$)", round(soma("valor_entradas"), 2)),
            ("Saídas (R$)", round(soma("valor_saidas"), 2)),
            ("Estoque final (R$)", round(soma("valor_final"), 2)),
        ],
    )
    return _resposta(conteudo, exportacao.nome_arquivo("movimentacao", inicio, fim))


@router.get("/abc.csv")
def abc(inicio: date | None = None, fim: date | None = None,
        ctx: Contexto = Depends(contexto_atual)) -> Response:
    _exige(ctx, "cmv.relatorios")
    inicio, fim = _periodo(inicio, fim)
    with get_cursor() as cur:
        linhas = cmv_motor.curva_abc(cur, unidade_atual(cur, ctx), inicio, fim, 500)

    conteudo = exportacao.csv_de(
        linhas,
        [("codigo", "Código"), ("produto", "Insumo"), ("quantidade", "Consumo"),
         ("um_estoque", "Unidade"), ("valor", "Valor consumido"),
         ("participacao_pct", "Participação %"), ("acumulada_pct", "Acumulado %"),
         ("classe", "Classe")],
        titulo=f"Curva ABC — {inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}",
        resumo=[("Insumos", len(linhas)),
                ("Valor consumido", round(sum(l["valor"] for l in linhas), 2))],
    )
    return _resposta(conteudo, exportacao.nome_arquivo("curva-abc", inicio, fim))


@router.get("/precos.csv")
def precos(inicio: date | None = None, fim: date | None = None,
           ctx: Contexto = Depends(contexto_atual)) -> Response:
    """A planilha que vai para a reunião com o fornecedor."""
    _exige(ctx, "cmv.relatorios")
    inicio, fim = _periodo(inicio, fim)
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        linhas = relatorios.evolucao_de_preco(cur, id_unidade, inicio, fim, 500)
        grupos = relatorios.cmv_por_grupo(cur, id_unidade, inicio, fim, "setor")

    conteudo = exportacao.csv_de(
        linhas,
        [("codigo", "Código"), ("produto", "Insumo"), ("um_estoque", "Unidade"),
         ("compras", "Compras"), ("quantidade", "Quantidade comprada"),
         ("primeiro", "Primeiro preço"), ("ultimo", "Último preço"),
         ("variacao_pct", "Variação %"), ("impacto", "Impacto R$"),
         ("menor", "Menor preço"), ("fornecedor_mais_barato", "Mais barato com"),
         ("economia_possivel", "Economia possível"),
         ("fornecedor_ultimo", "Última compra com"), ("data_ultimo", "Data da última")],
        titulo=f"Evolução de preço — {inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}",
        resumo=[("Insumos com variação", len(linhas)),
                ("Impacto somado", round(sum(l["impacto"] for l in linhas), 2)),
                ("Economia possível", round(sum(l["economia_possivel"] for l in linhas), 2))],
    )
    conteudo += exportacao.csv_de(
        grupos,
        [("grupo", "Setor"), ("estoque_inicial", "Estoque inicial"), ("compras", "Compras"),
         ("estoque_final", "Estoque final"), ("cmv", "CMV"), ("perdas", "Perdas"),
         ("participacao_pct", "Participação %")],
        titulo="Onde o custo pesa (por setor)",
    )
    return _resposta(conteudo, exportacao.nome_arquivo("precos-e-setores", inicio, fim))


@router.get("/produtos.csv")
def produtos(ctx: Contexto = Depends(contexto_atual)) -> Response:
    _exige(ctx, "cadastros.produtos")
    with get_cursor() as cur:
        cur.execute(
            """SELECT p.codigo, p.nome AS produto, p.tipo, c.nome AS categoria,
                      s.nome AS setor, p.um_estoque, p.um_compra, p.fator_compra,
                      p.estoque_minimo, p.perecivel, p.validade_dias, p.controla_lote,
                      p.ncm, p.codigo_barras, p.status, p.ativo,
                      (SELECT pp.preco_venda FROM produto_precos pp
                        WHERE pp.id_produto = p.id AND pp.vigente_ate IS NULL
                        ORDER BY pp.vigente_de DESC LIMIT 1) AS preco_venda
                 FROM produtos p
                 LEFT JOIN categorias c ON c.id = p.id_categoria
                 LEFT JOIN setores s ON s.id = p.id_setor
                ORDER BY lower(p.nome)"""
        )
        linhas = [dict(r) for r in cur.fetchall()]

    conteudo = exportacao.csv_de(
        linhas,
        [("codigo", "Código"), ("produto", "Produto"), ("tipo", "Tipo"),
         ("categoria", "Categoria"), ("setor", "Setor"), ("um_estoque", "Un. estoque"),
         ("um_compra", "Un. compra"), ("fator_compra", "Fator"),
         ("preco_venda", "Preço de venda"), ("estoque_minimo", "Estoque mínimo"),
         ("perecivel", "Perecível"), ("validade_dias", "Validade (dias)"),
         ("controla_lote", "Controla lote"), ("ncm", "NCM"),
         ("codigo_barras", "Código de barras"), ("status", "Situação"), ("ativo", "Ativo")],
        titulo="Cadastro de produtos",
        resumo=[("Produtos", len(linhas))],
    )
    return _resposta(conteudo, exportacao.nome_arquivo("produtos"))


@router.get("/vencimentos.csv")
def vencimentos(dias: int | None = Query(default=None, ge=0, le=365),
                ctx: Contexto = Depends(contexto_atual)) -> Response:
    _exige(ctx, "estoque.saldos")
    with get_cursor() as cur:
        linhas = alertas_motor.vencimentos(cur, unidade_atual(cur, ctx), dias)

    conteudo = exportacao.csv_de(
        linhas,
        [("validade", "Validade"), ("dias_restantes", "Dias restantes"),
         ("codigo", "Código"), ("produto", "Produto"), ("lote", "Lote"),
         ("local", "Local"), ("quantidade", "Quantidade"), ("um_estoque", "Unidade"),
         ("valor", "Valor")],
        titulo="Lotes a vencer",
        resumo=[("Lotes", len(linhas)),
                ("Valor exposto", round(sum(float(l["valor"] or 0) for l in linhas), 2))],
    )
    return _resposta(conteudo, exportacao.nome_arquivo("vencimentos"))


@router.get("/inventario/{id_inventario}.csv")
def inventario(id_inventario: int, ctx: Contexto = Depends(contexto_atual)) -> Response:
    """A folha de contagem — imprimir, contar no papel e digitar depois."""
    _exige(ctx, "estoque.inventario")
    with get_cursor() as cur:
        cur.execute(
            """SELECT i.data, i.status, i.cega, l.nome AS local FROM inventarios i
                 JOIN locais_estoque l ON l.id = i.id_local WHERE i.id = %s""",
            (id_inventario,),
        )
        inv = cur.fetchone()
        if not inv:
            raise HTTPException(status_code=404, detail="Inventário não encontrado")
        cur.execute(
            """SELECT p.codigo, p.nome AS produto, p.um_estoque, ii.qtd_sistema,
                      ii.qtd_contada, ii.custo_medio,
                      (coalesce(ii.qtd_contada, ii.qtd_sistema) - ii.qtd_sistema) AS diferenca,
                      round((coalesce(ii.qtd_contada, ii.qtd_sistema) - ii.qtd_sistema)
                            * ii.custo_medio, 2) AS impacto
                 FROM inventario_itens ii
                 JOIN produtos p ON p.id = ii.id_produto
                WHERE ii.id_inventario = %s ORDER BY lower(p.nome)""",
            (id_inventario,),
        )
        linhas = [dict(r) for r in cur.fetchall()]

    # Contagem CEGA aberta: a folha impressa é o caminho mais fácil de furar o
    # sigilo — quem conta leria o esperado no papel. As colunas do sistema saem.
    cega_aberta = inv["cega"] and inv["status"] == "ABERTO"
    colunas = [("codigo", "Código"), ("produto", "Produto"), ("um_estoque", "Unidade")]
    if not cega_aberta:
        colunas.append(("qtd_sistema", "Saldo no sistema"))
    colunas.append(("qtd_contada", "Contado"))
    if not cega_aberta:
        colunas += [("diferenca", "Diferença"), ("custo_medio", "Custo médio"),
                    ("impacto", "Impacto (R$)")]

    conteudo = exportacao.csv_de(
        linhas,
        colunas,
        titulo=f"Inventário #{id_inventario} — {inv['local']}",
        resumo=[("Data", inv["data"]), ("Situação", inv["status"]),
                ("Contagem", "cega — o saldo do sistema não sai daqui"
                             if cega_aberta else "aberta"),
                ("Itens", len(linhas))],
    )
    return _resposta(conteudo, exportacao.nome_arquivo(f"inventario-{id_inventario}"))
