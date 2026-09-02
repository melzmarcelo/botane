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
    SaldoAgrupadoResponse,
    SaldoRedeForaResponse,
    SaldoRedeResponse,
    SaldoResponse,
    TransferenciaRequest,
)
from paginacao import com_total, pagina
from seguranca import Contexto, contexto_atual, requer_permissao, unidade_atual
from services import estoque as motor
from services import transferencias as transito_servico

router = APIRouter(prefix="/estoque", tags=["estoque"])


@router.get("/saldos", response_model=list[SaldoResponse])
def saldos(
    busca: str | None = Query(default=None, max_length=80),
    # Fixar UM produto é diferente de buscar por texto: "café" traz cinco
    # cafés, e quem quer o saldo de um deles não quer conferir os outros.
    id_produto: int | None = None,
    id_local: int | None = None,
    apenas_com_saldo: bool = False,
    abaixo_do_minimo: bool = False,
    # Produto desativado com saldo continua existindo — mas só aparece quando
    # pedido, senão o inventário do dia a dia fica cheio de coisa fora de linha.
    incluir_inativos: bool = False,
    limite: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    resposta: Response = None,
    ctx: Contexto = Depends(requer_permissao("estoque.saldos")),
) -> list[dict]:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        linhas = pagina(
            cur,
            """
            SELECT s.id_produto, p.codigo, p.nome AS produto, p.um_estoque, p.estoque_minimo,
                   s.id_local, l.nome AS local, s.quantidade, s.custo_medio,
                   round(s.quantidade * s.custo_medio, 2) AS valor, s.atualizado_em,
                   (p.estoque_minimo IS NOT NULL AND s.quantidade < p.estoque_minimo)
                       AS abaixo_do_minimo
              FROM estoque_saldos s
              JOIN produtos p ON p.id = s.id_produto
              JOIN locais_estoque l ON l.id = s.id_local
             WHERE s.id_unidade = %s
               AND (%s OR p.ativo)
               AND (%s::int IS NULL OR s.id_produto = %s)
               AND (%s::int IS NULL OR s.id_local = %s)
               AND (NOT %s OR s.quantidade <> 0)
               AND (NOT %s OR (p.estoque_minimo IS NOT NULL AND s.quantidade < p.estoque_minimo))
               AND (%s::varchar IS NULL
                    OR lower(p.nome) LIKE lower('%%' || %s || '%%')
                    OR lower(p.codigo) LIKE lower('%%' || %s || '%%'))
             ORDER BY lower(p.nome), l.nome
            """,
            (id_unidade, incluir_inativos, id_produto, id_produto, id_local, id_local,
             apenas_com_saldo, abaixo_do_minimo, busca, busca, busca),
            limite=limite, offset=offset, resposta=resposta,
        )
        # ⚠️ **Uma consulta só, casada em memória** — e não uma subconsulta por
        # linha. São 200 linhas por página contra um punhado de remessas
        # abertas; correlacionar cobraria o preço em toda listagem de saldo por
        # causa de um caso que quase sempre vem vazio.
        transito = transito_servico.em_transito_por_local(cur, id_unidade)
        if transito:
            for linha in linhas:
                linha["em_transito"] = transito.get(
                    (linha["id_produto"], linha["id_local"]), 0)
    return linhas


@router.get("/saldos-agrupados", response_model=list[SaldoAgrupadoResponse])
def saldos_agrupados(
    busca: str | None = Query(default=None, max_length=80),
    id_produto: int | None = None,
    id_setor: int | None = None,
    apenas_com_saldo: bool = False,
    abaixo_do_minimo: bool = False,
    incluir_inativos: bool = False,
    limite: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    resposta: Response = None,
    ctx: Contexto = Depends(requer_permissao("estoque.saldos")),
) -> list[dict]:
    """Uma linha por PRODUTO, somando os locais desta loja.

    🔑 **O processo da casa põe o mesmo produto em vários locais.** O açúcar
    entra no Estoque Central e de manhã cada setor leva um pacote para o seu
    canto — Bar, Confeitaria, Cozinha. A lista por prateleira responde "onde
    está"; esta responde "quanto a loja tem", que é a pergunta de quem vai
    comprar. As duas são necessárias, e é por isso que a tela escolhe.

    ⚠️ **`id_setor` corta pelo setor do LOCAL**, não pelo do produto: a pergunta
    aqui é "o que a Confeitaria tem na mão", e quem responde isso é onde a
    mercadoria está — não como o produto foi classificado no cadastro.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        sql = """
            SELECT s.id_produto, p.codigo, p.nome AS produto, p.um_estoque,
                   p.estoque_minimo,
                   sum(s.quantidade) AS quantidade,
                   round(sum(s.quantidade * s.custo_medio), 2) AS valor,
                   -- Ponderado, nunca a media dos medios: o mesmo cafe pode
                   -- estar na camara e no bar com custos diferentes.
                   CASE WHEN sum(s.quantidade) <> 0
                        THEN round(sum(s.quantidade * s.custo_medio)
                                   / sum(s.quantidade), 6) END AS custo_medio,
                   (p.estoque_minimo IS NOT NULL
                    AND sum(s.quantidade) < p.estoque_minimo) AS abaixo_do_minimo
              FROM estoque_saldos s
              JOIN produtos p ON p.id = s.id_produto
              JOIN locais_estoque l ON l.id = s.id_local
             WHERE s.id_unidade = %s
               AND (%s OR p.ativo)
               AND (%s::int IS NULL OR s.id_produto = %s)
               AND (%s::int IS NULL OR l.id_setor = %s)
               AND (%s::varchar IS NULL
                    OR lower(p.nome) LIKE lower('%%' || %s || '%%')
                    OR lower(p.codigo) LIKE lower('%%' || %s || '%%'))
             GROUP BY s.id_produto, p.codigo, p.nome, p.um_estoque, p.estoque_minimo
            HAVING (NOT %s OR sum(s.quantidade) <> 0)
               AND (NOT %s OR (p.estoque_minimo IS NOT NULL
                               AND sum(s.quantidade) < p.estoque_minimo))
             ORDER BY lower(p.nome)
        """
        params = (id_unidade, incluir_inativos, id_produto, id_produto,
                  id_setor, id_setor, busca, busca, busca,
                  apenas_com_saldo, abaixo_do_minimo)
        linhas = pagina(cur, sql, params, limite=limite, offset=offset, resposta=resposta)

        # Uma consulta a mais para a PAGINA, nao uma por linha — a mesma
        # escolha do `em_transito` e da visao de empresa.
        if linhas:
            cur.execute(
                """SELECT s.id_produto, s.id_local, l.nome AS local, se.nome AS setor,
                          sum(s.quantidade) AS quantidade,
                          round(sum(s.quantidade * s.custo_medio), 2) AS valor
                     FROM estoque_saldos s
                     JOIN locais_estoque l ON l.id = s.id_local
                     LEFT JOIN setores se ON se.id = l.id_setor
                    WHERE s.id_unidade = %s AND s.id_produto = ANY(%s)
                    GROUP BY 1, 2, 3, 4, l.principal, l.nome
                    ORDER BY l.principal DESC, lower(l.nome)""",
                (id_unidade, [l["id_produto"] for l in linhas]))
            por_produto: dict[int, list[dict]] = {}
            for r in cur.fetchall():
                por_produto.setdefault(r["id_produto"], []).append({
                    "id_local": r["id_local"], "local": r["local"], "setor": r["setor"],
                    "quantidade": float(r["quantidade"]), "valor": float(r["valor"] or 0),
                })
            for linha in linhas:
                linha["por_local"] = por_produto.get(linha["id_produto"], [])
    return linhas


def _lojas_que_ve(cur, ctx: Contexto) -> list[dict]:
    """As lojas ATIVAS que esta pessoa enxerga, na ordem de sempre.

    ⚠️ Mesma regra da tela da rede: gerente de uma loja que abrir a visão
    consolidada vê a dele, e o total é o dela — nunca um consolidado que ele não
    pode ver. Somar o que a pessoa não pode consultar seria vazar pelo total.
    """
    cur.execute("SELECT id, nome, apelido FROM unidades WHERE ativo "
                "ORDER BY matriz DESC, id")
    return [dict(r) for r in cur.fetchall() if ctx.ve_unidade(r["id"])]


@router.get("/saldos-rede", response_model=list[SaldoRedeResponse])
def saldos_rede(
    busca: str | None = Query(default=None, max_length=80),
    id_produto: int | None = None,
    apenas_com_saldo: bool = False,
    abaixo_do_minimo: bool = False,
    incluir_inativos: bool = False,
    limite: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    resposta: Response = None,
    ctx: Contexto = Depends(requer_permissao("estoque.saldos")),
) -> list[dict]:
    """O estoque da EMPRESA: uma linha por produto, somando as lojas.

    🔑 **A tela da rede dizia quanto VALE o estoque da empresa e não dizia de
    quê.** Para conferir um item era preciso trocar de loja no seletor e somar
    de cabeça — a mesma conta que a visão consolidada existe para evitar.

    ⚠️ **A prateleira sai da linha.** Aqui a pergunta é "quanto a rede tem de
    café", não "em que estante ele está": agrupar por local devolveria a mesma
    lista de sempre, só que mais longa. Onde ele está vem em `por_loja`.

    ⚠️ **Transferência em trânsito não aparece.** Entre lojas ela é movimento
    INTERNO da rede: a mercadoria continua contando na origem e o total não
    muda. Mostrá-la aqui sugeriria que parte do estoque da empresa está fora
    dela, o que não é verdade.
    """
    with get_cursor() as cur:
        lojas = _lojas_que_ve(cur, ctx)
        if not lojas:
            return []
        ids = [l["id"] for l in lojas]

        # ⚠️ **O corte é do SERVIDOR**, como em todo grid da casa — e aqui ele
        # é por PRODUTO, então o `LIMIT` só pode entrar depois do `GROUP BY`.
        sql = """
            SELECT s.id_produto, p.codigo, p.nome AS produto, p.um_estoque,
                   p.estoque_minimo,
                   sum(s.quantidade) AS quantidade,
                   round(sum(s.quantidade * s.custo_medio), 2) AS valor,
                   -- 🔑 **Ponderado, nunca a média dos médios**: a matriz com
                   -- 10 kg a 40 e a filial com 1 kg a 52 dão 41,09 na rede.
                   CASE WHEN sum(s.quantidade) <> 0
                        THEN round(sum(s.quantidade * s.custo_medio)
                                   / sum(s.quantidade), 6) END AS custo_medio,
                   (p.estoque_minimo IS NOT NULL
                    AND sum(s.quantidade) < p.estoque_minimo) AS abaixo_do_minimo
              FROM estoque_saldos s
              JOIN produtos p ON p.id = s.id_produto
             WHERE s.id_unidade = ANY(%s)
               AND (%s OR p.ativo)
               AND (%s::int IS NULL OR s.id_produto = %s)
               AND (%s::varchar IS NULL
                    OR lower(p.nome) LIKE lower('%%' || %s || '%%')
                    OR lower(p.codigo) LIKE lower('%%' || %s || '%%'))
             GROUP BY s.id_produto, p.codigo, p.nome, p.um_estoque, p.estoque_minimo
            HAVING (NOT %s OR sum(s.quantidade) <> 0)
               AND (NOT %s OR (p.estoque_minimo IS NOT NULL
                               AND sum(s.quantidade) < p.estoque_minimo))
             ORDER BY lower(p.nome)
        """
        params = (ids, incluir_inativos, id_produto, id_produto,
                  busca, busca, busca, apenas_com_saldo, abaixo_do_minimo)
        linhas = pagina(cur, sql, params, limite=limite, offset=offset, resposta=resposta)

        # ⚠️ **Uma consulta a mais para a PÁGINA, não uma por linha.** Só os
        # produtos que a página traz, e o de-para é feito em memória — mesma
        # escolha do `em_transito` dos saldos.
        if linhas:
            cur.execute(
                """SELECT s.id_produto, s.id_unidade, sum(s.quantidade) AS quantidade,
                          round(sum(s.quantidade * s.custo_medio), 2) AS valor
                     FROM estoque_saldos s
                    WHERE s.id_unidade = ANY(%s) AND s.id_produto = ANY(%s)
                    GROUP BY 1, 2""",
                (ids, [l["id_produto"] for l in linhas]))
            nomes = {l["id"]: (l["apelido"] or l["nome"]) for l in lojas}
            por_produto: dict[int, list[dict]] = {}
            for r in cur.fetchall():
                por_produto.setdefault(r["id_produto"], []).append({
                    "id_unidade": r["id_unidade"], "loja": nomes.get(r["id_unidade"], "—"),
                    "quantidade": float(r["quantidade"]), "valor": float(r["valor"] or 0),
                })
            for linha in linhas:
                # Na ordem das lojas, não na que o banco devolveu: coluna que
                # troca de lugar entre uma página e outra é coluna que ninguém lê.
                dele = {x["id_unidade"]: x for x in por_produto.get(linha["id_produto"], [])}
                linha["por_loja"] = [dele[i] for i in ids if i in dele]
    return linhas


@router.get("/saldos-rede/inativos", response_model=SaldoRedeForaResponse)
def saldos_rede_inativos(
    busca: str | None = Query(default=None, max_length=80),
    id_produto: int | None = None,
    apenas_com_saldo: bool = False,
    ctx: Contexto = Depends(requer_permissao("estoque.saldos")),
) -> dict:
    """O que a lista consolidada deixou de fora por o produto estar inativo.

    🔑 **É a linha que faz os dois números da empresa fecharem.** O painel da
    rede soma `estoque_saldos` inteiro — e está certo: tirar o inativo do
    estoque final inflaria o CMV. A lista filtra por ativo — e está certa
    também: ela mostra o que se opera. Sem dizer quanto ficou de fora, quem
    confere um contra o outro conclui que um dos dois mente.

    ⚠️ **Os MESMOS filtros da lista, sempre.** Um aviso que responde por outro
    recorte é pior que aviso nenhum: diria "e mais R$ 24 mil" com um produto só
    na tela. Por isso ele mora aqui e não numa consulta escrita na tela.

    ⚠️ **Só as lojas que a pessoa enxerga**, como a lista: o aviso é um TOTAL, e
    total é o pior lugar para vazar — nada nele denuncia um número maior do que
    devia.
    """
    with get_cursor() as cur:
        lojas = _lojas_que_ve(cur, ctx)
        if not lojas:
            return {"produtos": 0, "valor": 0.0}
        cur.execute(
            """SELECT count(*) AS produtos, coalesce(sum(valor), 0) AS valor
                 FROM (SELECT round(sum(s.quantidade * s.custo_medio), 2) AS valor
                         FROM estoque_saldos s
                         JOIN produtos p ON p.id = s.id_produto
                        WHERE s.id_unidade = ANY(%s)
                          AND NOT p.ativo
                          AND (%s::int IS NULL OR s.id_produto = %s)
                          AND (%s::varchar IS NULL
                               OR lower(p.nome) LIKE lower('%%' || %s || '%%')
                               OR lower(p.codigo) LIKE lower('%%' || %s || '%%'))
                        GROUP BY s.id_produto
                       HAVING (NOT %s OR sum(s.quantidade) <> 0)) AS _fora""",
            ([l["id"] for l in lojas], id_produto, id_produto,
             busca, busca, busca, apenas_com_saldo))
        r = cur.fetchone()
    return {"produtos": int(r["produtos"]), "valor": float(r["valor"] or 0)}


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
    # 🔑 **A saída que não achou saldo sai por um custo PROVISÓRIO** — o último
    # que o sistema conhece, ou zero. A linha nasce marcada no razão, mas com
    # centenas de movimentos a etiqueta só ajuda quem já está olhando para ela:
    # não havia como perguntar "quais são?". A resposta é uma entrada que
    # ninguém lançou, e cada uma delas está deixando o CMV torto até ser
    # lançada.
    apenas_provisorios: bool = False,
    limite: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    resposta: Response = None,
    ctx: Contexto = Depends(requer_permissao("estoque.saldos")),
) -> list[dict]:
    with get_cursor() as cur:
        # 🔑 **O razão não filtrava por LOJA** — e o CSV do razão sempre filtrou.
        # Com duas lojas a tela mostrava os movimentos das duas misturados
        # enquanto o arquivo baixado trazia só os desta, que é a divergência
        # exata que este endpoint documenta querer evitar. Mesma dívida que
        # vendas, inventários e locais já pagaram: toda lista de coisa que tem
        # `id_unidade` nasce com ela.
        id_unidade = unidade_atual(cur, ctx)
        linhas = pagina(
            cur,
            """
            SELECT m.id, m.data_movimento, m.tipo, m.id_produto, p.nome AS produto, p.codigo,
                   l.nome AS local, m.quantidade, m.custo_unitario, m.custo_total,
                   m.saldo_apos, m.custo_medio_apos, m.custo_provisorio, m.documento,
                   pm.nome AS motivo, m.observacao, u.nome AS usuario, m.id_estorno_de,
                   -- De onde o movimento veio. Sem isto, um ajuste feito em lote é
                   -- indistinguível de um avulso, e a pergunta "de onde veio?" só
                   -- se responde no banco.
                   m.origem_tipo, m.origem_id,
                   EXISTS (SELECT 1 FROM estoque_movimentos e
                            WHERE e.id_estorno_de = m.id) AS estornado
              FROM estoque_movimentos m
              JOIN produtos p ON p.id = m.id_produto
              JOIN locais_estoque l ON l.id = m.id_local
              LEFT JOIN perda_motivos pm ON pm.id = m.id_motivo_perda
              LEFT JOIN usuarios u ON u.id = m.id_usuario
             WHERE m.id_unidade = %s
               AND (%s::int IS NULL OR m.id_produto = %s)
               AND (%s::int IS NULL OR m.id_local = %s)
               AND (%s::varchar IS NULL OR m.tipo = %s)
               AND (%s::date IS NULL OR m.data_movimento >= %s)
               -- `fim` é dia CHEIO: `<= fim` cortaria o que foi lançado às 14h
               -- do próprio dia, porque a coluna guarda data e hora.
               AND (%s::date IS NULL OR m.data_movimento < %s::date + 1)
               AND (%s::varchar IS NULL
                    OR lower(p.nome) LIKE lower('%%' || %s || '%%')
                    OR lower(p.codigo) LIKE lower('%%' || %s || '%%'))
               AND (NOT %s OR m.custo_provisorio)
             ORDER BY m.id DESC
            """,
            (id_unidade, id_produto, id_produto, id_local, id_local, tipo, tipo,
             inicio, inicio, fim, fim, busca, busca, busca, apenas_provisorios),
            limite=limite, offset=offset, resposta=resposta,
        )
    for l in linhas:
        l["rotulo"] = motor.ROTULOS.get(l["tipo"], l["tipo"])
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
        # ⚠️ **Quem não enxerga a loja não empurra mercadoria para dentro
        # dela.** A transferência entre lojas toca DUAS: mandar para uma loja
        # que a pessoa não vê seria mexer num estoque que ela não pode nem
        # consultar. A mesma validação do resto do sistema — `ve_unidade`.
        for id_local in (body.id_local_origem, body.id_local_destino):
            cur.execute("SELECT id_unidade FROM locais_estoque WHERE id = %s", (id_local,))
            linha = cur.fetchone()
            if linha and not ctx.ve_unidade(linha["id_unidade"]):
                raise HTTPException(
                    status_code=403,
                    detail="Sem acesso à loja de um dos locais desta transferência.")
        # 🔑 **Entre LOJAS a transferência vira remessa; dentro da mesma, não.**
        # Prateleira para prateleira da mesma casa alguém carrega a caixa — e
        # exigir recebimento ali seria burocracia inventada. Entre lojas a
        # mercadoria leva tempo no caminho, e dizer que ela já chegou é mentir
        # para as duas: a origem some com o que ainda é dela e o destino
        # aparece com o que ainda não tem.
        unidades = []
        for id_local in (body.id_local_origem, body.id_local_destino):
            cur.execute("SELECT id_unidade FROM locais_estoque WHERE id = %s", (id_local,))
            linha = cur.fetchone()
            unidades.append(linha and linha["id_unidade"])
        if unidades[0] != unidades[1]:
            remessa = transito_servico.enviar(
                cur, id_local_origem=body.id_local_origem,
                id_local_destino=body.id_local_destino,
                itens=[{"id_produto": body.id_produto, "quantidade": body.quantidade}],
                id_usuario=ctx.id_usuario, observacao=body.observacao)
            auditoria.registrar(
                cur, ctx.id_usuario, "transferencia", remessa["id"], "enviar",
                depois={"produto": body.id_produto, "qtd": body.quantidade,
                        "de": remessa["origem"], "para": remessa["destino"]},
                id_unidade=remessa["id_unidade_origem"])
            return {"remessa": remessa["id"], "entre_lojas": True, "em_transito": True,
                    "message": (f"Remessa {remessa['id']} em trânsito para "
                                f"{remessa['destino']}. A quantidade continua no estoque "
                                "daqui até alguém conferir e receber lá.")}

        r = motor.transferir(
            cur, id_unidade=id_unidade, id_produto=body.id_produto, quantidade=body.quantidade,
            id_local_origem=body.id_local_origem, id_local_destino=body.id_local_destino,
            id_usuario=ctx.id_usuario, observacao=body.observacao,
        )
        auditoria.registrar(cur, ctx.id_usuario, "estoque", r["saida"]["id"], "transferencia",
                            depois={"produto": body.id_produto, "qtd": body.quantidade,
                                    "de": body.id_local_origem, "para": body.id_local_destino,
                                    "entre_lojas": r["entre_lojas"]},
                            id_unidade=id_unidade)
    return {"saida": r["saida"]["id"], "entrada": r["entrada"]["id"],
            "entre_lojas": False, "em_transito": False,
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
                     offset: int = Query(default=0, ge=0),
                     resposta: Response = None,
                     ctx: Contexto = Depends(requer_permissao("estoque.saldos"))) -> list[dict]:
    with get_cursor() as cur:
        return pagina(
            cur,
            """SELECT pr.id, pr.data, pr.quantidade, pr.custo_total, pr.custo_unitario,
                      pr.versao_ficha, p.nome AS produto, p.codigo, l.nome AS local,
                      u.nome AS usuario
                 FROM producoes pr
                 JOIN produtos p ON p.id = pr.id_produto
                 JOIN locais_estoque l ON l.id = pr.id_local
                 LEFT JOIN usuarios u ON u.id = pr.id_usuario
                ORDER BY pr.data DESC""",
            (),
            limite=limite, offset=offset, resposta=resposta,
        )
