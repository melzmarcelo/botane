"""A tela inicial — o que o dono precisa saber batendo o olho.

Uma chamada só, de propósito: o painel que faz seis requisições pisca seis
vezes e mostra número velho ao lado de número novo enquanto carrega.

Três regras que valem para tudo o que sai daqui:

* **Número verdadeiro ou nenhum.** Food cost sem venda importada não é 0%, é
  desconhecido — e vai como `null`, para a tela dizer "sem vendas no período"
  em vez de mostrar um zero que parece resultado.
* **A conta vem com o quanto dá para confiar nela.** O CMV teórico depende de
  quantos pratos têm ficha; por isso a cobertura viaja junto.
* **Dinheiro obedece a permissão.** Quem não tem `cmv.painel` recebe a parte
  operacional e mais nada — não um zero no lugar do valor.
"""

from datetime import date

from fastapi import APIRouter, Depends

from database import get_cursor
from seguranca import Contexto, contexto_atual, requer_permissao, unidade_atual
from services import alertas as alertas_motor
from services import cmv as cmv_motor
from services import periodos, relatorios

router = APIRouter(prefix="/inicio", tags=["Início"])


def _float(v):
    return None if v is None else float(v)


def _dia_de_vendas(cur, id_unidade: int, data: date | None = None) -> dict | None:
    """O movimento de UM dia, com os vizinhos que têm venda.

    🔑 **Abre no dia da ÚLTIMA venda, não em hoje** (pedido do dono, 03/09/2026).
    De manhã, ou num dia em que a busca no PDV ainda não rodou, "hoje" é um dia
    sem venda nenhuma — e um cartão zerado se lê como *"a casa não vendeu"*, que
    é diferente de *"ainda não importou"*. Abrindo no último dia com venda, o
    número na tela é sempre um número de verdade.

    🔑 **As setas andam entre dias que TÊM venda, não entre dias do calendário.**
    Numa casa que fecha na segunda, avançar um dia cairia num zero — e seria o
    mesmo engano por outra porta. Por isso quem diz para onde dá para ir é o
    servidor: `anterior` e `proximo` vêm nulos quando não há para onde, e é isso
    que desliga a seta.

    ⚠️ **A receita sai de `venda_itens`, como a do CMV** — e não do
    `vendas.valor_total` do cabeçalho. Hoje os dois concordam por construção (o
    cabeçalho é a soma dos itens), mas ler de fontes diferentes é como um painel
    passa a discordar de si mesmo no primeiro caso de borda. O painel já mostra
    a receita do período logo acima: as duas têm de vir do mesmo lugar.

    ⚠️ **Venda cancelada fica de fora**, aqui como em todo lugar.

    ⚠️ **Ticket médio é receita ÷ número de VENDAS**, não ÷ itens: é o quanto
    cada cliente gastou. E vem **nulo** sem venda no dia — zero ali seria um
    ticket de zero real, que é uma afirmação, não a ausência de uma.
    """
    if data is None:
        cur.execute(
            "SELECT max(data) AS d FROM vendas WHERE id_unidade = %s AND NOT cancelada",
            (id_unidade,),
        )
        data = (cur.fetchone() or {}).get("d")
        if data is None:
            return None  # a casa ainda não tem venda nenhuma

    cur.execute(
        # ⚠️ **A receita é LÍQUIDA: a soma dos itens menos o desconto do
        # cupom.** O PDV informa o valor cobrado, e era essa a diferença que
        # fazia a conferência não fechar. O desconto sai de uma subconsulta
        # porque o join com os itens repetiria o valor do cabeçalho uma vez por
        # linha do cupom — somá-lo ali multiplicaria o desconto pelo número de
        # itens.
        """SELECT count(DISTINCT v.id) AS vendas,
                  coalesce(sum(vi.valor_total), 0)
                    - coalesce((SELECT sum(d.desconto) FROM vendas d
                                 WHERE d.id_unidade = %s AND NOT d.cancelada
                                   AND d.data = %s), 0) AS receita,
                  coalesce(sum(vi.quantidade), 0) AS itens
             FROM vendas v
             LEFT JOIN venda_itens vi ON vi.id_venda = v.id
            WHERE v.id_unidade = %s AND NOT v.cancelada AND v.data = %s""",
        (id_unidade, data, id_unidade, data),
    )
    r = dict(cur.fetchone())

    # 🔑 **Os cupons CANCELADOS do dia, em número** (pedido do dono,
    # 03/09/2026). Eles passaram a ser importados marcados, e é este número que
    # faz a conferência com o PDV fechar sozinha: lá o dia tinha 164 cupons e
    # aqui 154, sem nada explicando a diferença. Com ele à vista, 154 + 10 = 164
    # e ninguém precisa desconfiar de perda de dado.
    # ⚠️ Consulta PRÓPRIA, e não um `FILTER` na de cima: aquela tem `NOT
    # cancelada` no WHERE e o join com os itens, então um filtro ali contaria
    # ITENS de venda cancelada, não vendas.
    # ⚠️ **O valor sai de `venda_itens`, como a receita** — e não do
    # `vendas.valor_total` do cabeçalho. Hoje os dois concordam por construção,
    # mas ler de fontes diferentes é como um painel passa a discordar de si
    # mesmo no primeiro caso de borda. O cancelado tem de ser comparável ao
    # vendido, e comparável quer dizer medido do mesmo jeito.
    cur.execute(
        """SELECT count(DISTINCT v.id) AS n,
                  coalesce(sum(vi.valor_total), 0) AS valor
             FROM vendas v
             LEFT JOIN venda_itens vi ON vi.id_venda = v.id
            WHERE v.id_unidade = %s AND v.cancelada AND v.data = %s""",
        (id_unidade, data),
    )
    canc = dict(cur.fetchone())
    canceladas, valor_cancelado = canc["n"], float(canc["valor"])

    cur.execute(
        """SELECT max(data) FILTER (WHERE data < %(d)s) AS anterior,
                  min(data) FILTER (WHERE data > %(d)s) AS proximo
             FROM vendas WHERE id_unidade = %(u)s AND NOT cancelada""",
        {"u": id_unidade, "d": data},
    )
    vizinhos = dict(cur.fetchone())

    receita = float(r["receita"])
    return {
        "data": data,
        "vendas": r["vendas"],
        "canceladas": canceladas,
        # Quanto o dia deixou de faturar por cancelamento. ⚠️ Vai como número,
        # não como texto: quem formata é a tela, que sabe se quem olha pode ver
        # dinheiro.
        "valor_cancelado": valor_cancelado,
        "itens": float(r["itens"]),
        "receita": receita,
        "ticket_medio": (receita / r["vendas"]) if r["vendas"] else None,
        "anterior": vizinhos["anterior"],
        "proximo": vizinhos["proximo"],
    }


def _producao_do_setor(cur, id_unidade: int, ctx: Contexto) -> dict:
    """O que a cozinha DESTA pessoa tem para fazer — o plano, não o dinheiro.

    🔑 **Pedido do dono (03/09/2026).** A agenda de produção existe desde a
    etapa de fichas, mas só na tela dela: quem entra de manhã via o painel do
    mês e tinha de navegar até Produção para descobrir o que assar hoje. E, com
    Bar, Confeitaria e Cafeteria na mesma lista, quem é da Confeitaria percorria
    a agenda inteira para achar as duas linhas dela.

    🔑 **O recorte é o SETOR do usuário** (`usuario_setores`, migração 052).
    ⚠️ **Sem setor marcado, vem a casa inteira** — a mesma convenção da loja. É
    o que faz esta tela nascer útil para quem já está cadastrado, em vez de
    nascer vazia esperando alguém reconfigurar todo mundo.

    ⚠️ **De ONTEM em diante, não de hoje.** A linha planejada que ninguém
    cumpriu é a que mais importa ver, e ela está no passado — é a mesma regra da
    tela de agenda, e ler diferente faria as duas discordarem sobre o que está
    pendente.

    ⚠️ **Só PLANEJADA.** Linha cumprida sai da lista de tarefas: misturar o que
    foi feito com o que falta é o que faz uma agenda crescer para sempre e
    esconder o pendente no meio do histórico.

    ⚠️ **Contagem e quantidade, nunca custo.** Este bloco vale para quem não vê
    dinheiro — é justamente a cozinha —, então nada aqui pode carregar valor.
    """
    cur.execute(
        """SELECT a.id, a.id_produto, p.nome AS produto, p.um_estoque,
                  a.data_prevista, a.quantidade, s.nome AS setor,
                  (a.data_prevista < current_date) AS atrasada
             FROM producao_agenda a
             JOIN produtos p ON p.id = a.id_produto
             LEFT JOIN setores s ON s.id = p.id_setor
            WHERE a.id_unidade = %(u)s
              AND a.status = 'PLANEJADA'
              AND a.data_prevista <= current_date + 7
              -- ⚠️ Produto SEM setor entra sempre: ele não é de ninguém, e
              -- escondê-lo faria a linha sumir do painel de toda a casa.
              AND (%(todos)s OR p.id_setor IS NULL OR p.id_setor = ANY(%(setores)s))
            ORDER BY a.data_prevista, lower(p.nome)""",
        {"u": id_unidade, "todos": ctx.todos_setores,
         "setores": list(ctx.setores) or [0]},
    )
    linhas = [dict(r) for r in cur.fetchall()]
    hoje = date.today()
    return {
        "linhas": [{**l, "quantidade": float(l["quantidade"])} for l in linhas[:8]],
        "total": len(linhas),
        "atrasadas": sum(1 for l in linhas if l["atrasada"]),
        "hoje": sum(1 for l in linhas if l["data_prevista"] == hoje),
        # A tela precisa saber se está mostrando um recorte ou a casa inteira —
        # senão "nada para produzir" se lê como "a casa não tem produção".
        "todos_setores": ctx.todos_setores,
        "setores": sorted({l["setor"] for l in linhas if l["setor"]}),
    }


@router.get("/dia")
def dia(data: date | None = None,
        ctx: Contexto = Depends(requer_permissao("cmv.painel"))) -> dict:
    """O movimento de um dia — é o que as setas do painel pedem.

    ⚠️ **Endpoint próprio, e não um parâmetro do painel inteiro.** Navegar entre
    dias não pode custar a apuração do período, a lista de alertas e o peso por
    setor: seria refazer a tela toda para trocar três números.

    ⚠️ Sem `data`, responde o dia da última venda — a mesma resposta com que o
    painel abre.
    """
    with get_cursor() as cur:
        return {"dia": _dia_de_vendas(cur, unidade_atual(cur, ctx), data)}


@router.get("")
def painel(ctx: Contexto = Depends(contexto_atual)) -> dict:
    hoje = date.today()

    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        # ⚠️ O painel do dono abre no PERÍODO DA CASA, não no mês. Numa casa que
        # fecha toda semana, um food cost "de agosto" na tela inicial é um
        # número que ela nunca usou para decidir nada — e que não bate com o
        # fechamento que ela assinou no domingo.
        ciclo = periodos.config(cur, id_unidade)
        inicio, fim_do_ciclo = periodos.periodo_do_dia(
            hoje, ciclo["ciclo"], dia_semana=ciclo["dia_semana"], dia_mes=ciclo["dia_mes"])
        fim = min(fim_do_ciclo, hoje)

        # ---- operação: contagem, não dinheiro. Vale para qualquer pessoa. ----
        cur.execute(
            """SELECT
                 (SELECT count(*) FROM produtos WHERE ativo AND controla_estoque) AS produtos,
                 (SELECT count(*) FROM fichas_tecnicas
                   WHERE status = 'HOMOLOGADA' AND vigente_ate IS NULL) AS fichas,
                 (SELECT count(*) FROM notas_entrada
                   WHERE id_unidade = %s AND status IN ('IMPORTADA', 'CONCILIADA')) AS notas_abertas,
                 (SELECT count(*) FROM nota_itens i JOIN notas_entrada n ON n.id = i.id_nota
                   WHERE n.id_unidade = %s AND i.id_produto IS NULL AND NOT i.ignorado
                     AND n.status <> 'CANCELADA') AS itens_a_vincular,
                 (SELECT count(*) FROM estoque_lotes l JOIN produtos p ON p.id = l.id_produto
                   WHERE l.id_unidade = %s AND p.ativo AND l.quantidade > 0
                     AND l.validade IS NOT NULL
                     AND l.validade <= current_date + 7) AS vencendo,
                 (SELECT count(*) FROM produtos p
                   WHERE p.ativo AND p.controla_estoque AND p.estoque_minimo IS NOT NULL
                     AND coalesce((SELECT sum(s.quantidade) FROM estoque_saldos s
                                    WHERE s.id_produto = p.id AND s.id_unidade = %s), 0)
                         < p.estoque_minimo) AS abaixo_minimo,
                 (SELECT count(*) FROM estoque_movimentos
                   WHERE id_unidade = %s AND data_movimento >= %s) AS movimentos_mes""",
            (id_unidade, id_unidade, id_unidade, id_unidade, id_unidade, inicio),
        )
        operacao = dict(cur.fetchone())

        resposta = {
            "periodo": {
                "inicio": inicio,
                "fim": fim,
                "rotulo": periodos.rotulo(inicio, fim_do_ciclo, ciclo["ciclo"]),
                "ciclo": ciclo["ciclo"],
            },
            "operacao": operacao,
            "alertas": alertas_motor.levantar(cur, id_unidade),
            # 🔑 **Vem ANTES do corte do dinheiro, de propósito**: é a parte
            # do painel que serve a quem NÃO vê valor — a cozinha. Deixá-lo
            # depois do `return` daria à cozinha um painel só de contagens, que
            # é justamente o que o pedido veio corrigir.
            "producao": (_producao_do_setor(cur, id_unidade, ctx)
                         if ctx.pode("producao.agenda") else None),
            "dinheiro": None,
            # ⚠️ Nulo para quem não vê dinheiro, como o resto: o cartão do dia
            # é valor e ticket médio, e um cartão só com a contagem seria uma
            # quarta coisa a explicar em troca de nada.
            "dia": None,
            "pesos": [],
        }

        if not ctx.pode("cmv.painel"):
            return resposta

        a = cmv_motor.apurar(cur, id_unidade, inicio, fim)
        estoque_agora = cmv_motor.valor_do_estoque(cur, id_unidade)
        receita = float(a["receita"])

        resposta["dinheiro"] = {
            "estoque_agora": float(estoque_agora),
            "compras_mes": float(a["compras"]),
            "cmv_mes": float(a["cmv_real"]),
            "perdas_mes": float(a["perdas"]),
            "receita_mes": receita,
            "vendas": a["vendas"],
            # Sem venda no período, food cost e variância não são zero: são
            # desconhecidos. Zero ali pareceria um resultado excelente.
            "food_cost_pct": _float(a["food_cost_pct"]) if receita else None,
            "variancia": float(a["variancia"]) if receita else None,
            "cobertura_ficha_pct": float(a["cobertura_ficha_pct"]),
            "cmv_teorico": float(a["cmv_teorico"]),
        }

        # ⚠️ **Vem no mesmo pacote**, não numa segunda chamada: o painel que faz
        # seis requisições pisca seis vezes. Só a NAVEGAÇÃO pelas setas custa
        # uma ida ao servidor, e aí é alguém pedindo.
        resposta["dia"] = _dia_de_vendas(cur, id_unidade)

        if ctx.pode("cmv.relatorios") or ctx.pode("cmv.painel"):
            grupos = relatorios.cmv_por_grupo(cur, id_unidade, inicio, fim, "setor")
            resposta["pesos"] = [
                {"grupo": g["grupo"], "cmv": float(g["cmv"]),
                 "participacao_pct": g["participacao_pct"]}
                for g in grupos[:4]
            ]

    return resposta


@router.get("/rede")
def rede(ctx: Contexto = Depends(requer_permissao("cmv.painel"))) -> dict:
    """As lojas lado a lado — o painel de quem responde pelas duas.

    🔑 **Toda tela do sistema responde por UMA loja**, e está certo: quem opera
    opera numa de cada vez. Mas o dono de duas não tem onde ver as duas — e
    somar de cabeça dois food costs de bases diferentes é a conta que ninguém
    faz certo. Esta é a tela que passa a existir quando existe a segunda loja.

    ⚠️ **Roda a MESMA apuração de cada loja, uma por vez** — nunca uma consulta
    nova que some tudo. Uma segunda implementação divergiria no primeiro caso de
    borda (ciclo de fechamento diferente, grupo fora do CMV configurado só numa
    delas), e o consolidado passaria a discordar do painel de cada uma. Assim,
    se a soma não bate, o erro está numa das partes — não entre elas.

    ⚠️ **Cada loja tem o SEU ciclo**: uma pode fechar por semana e a outra por
    mês. O período vai declarado em cada linha, porque um total que junta
    períodos diferentes precisa dizer que faz isso.

    ⚠️ **Só as lojas que a pessoa ENXERGA.** Gerente de uma loja que abrir esta
    tela vê a dele, e o total é o dela — não um consolidado que ele não pode ver.
    """
    hoje = date.today()
    linhas: list[dict] = []
    total_cmv = total_receita = total_estoque = total_perdas = 0.0

    with get_cursor() as cur:
        cur.execute(
            "SELECT id, nome, apelido, matriz FROM unidades WHERE ativo "
            "ORDER BY matriz DESC, id")
        lojas = [dict(r) for r in cur.fetchall() if ctx.ve_unidade(r["id"])]

        for loja in lojas:
            ciclo = periodos.config(cur, loja["id"])
            inicio, fim_do_ciclo = periodos.periodo_do_dia(
                hoje, ciclo["ciclo"], dia_semana=ciclo["dia_semana"],
                dia_mes=ciclo["dia_mes"])
            fim = min(fim_do_ciclo, hoje)
            a = cmv_motor.apurar(cur, loja["id"], inicio, fim)
            estoque = float(cmv_motor.valor_do_estoque(cur, loja["id"]))
            receita = float(a["receita"])
            linhas.append({
                "id_unidade": loja["id"],
                "loja": loja["apelido"] or loja["nome"],
                "matriz": loja["matriz"],
                "periodo": {
                    "inicio": inicio, "fim": fim,
                    "rotulo": periodos.rotulo(inicio, fim_do_ciclo, ciclo["ciclo"]),
                    "ciclo": ciclo["ciclo"],
                },
                "estoque_agora": estoque,
                "compras": float(a["compras"]),
                "cmv": float(a["cmv_real"]),
                "perdas": float(a["perdas"]),
                "receita": receita,
                "vendas": a["vendas"],
                # Número verdadeiro ou nenhum: sem venda, food cost zero
                # pareceria um resultado excelente.
                "food_cost_pct": _float(a["food_cost_pct"]) if receita else None,
                "cobertura_ficha_pct": float(a["cobertura_ficha_pct"]),
            })
            total_cmv += float(a["cmv_real"])
            total_receita += receita
            total_estoque += estoque
            total_perdas += float(a["perdas"])

    return {
        "lojas": linhas,
        "total": {
            "estoque_agora": total_estoque,
            "cmv": total_cmv,
            "perdas": total_perdas,
            "receita": total_receita,
            # 🔑 **O food cost da rede se RECALCULA, não se soma.** Média de
            # percentuais dá o mesmo peso à loja que vendeu R$ 100 mil e à que
            # vendeu R$ 5 mil — e erra justamente para quem tem uma grande e uma
            # pequena, que é o caso comum de quem abre a segunda.
            "food_cost_pct": (round(total_cmv / total_receita * 100, 2)
                              if total_receita else None),
        },
    }
