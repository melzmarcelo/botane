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
from seguranca import Contexto, contexto_atual, unidade_atual
from services import alertas as alertas_motor
from services import cmv as cmv_motor
from services import periodos, relatorios

router = APIRouter(prefix="/inicio", tags=["Início"])


def _float(v):
    return None if v is None else float(v)


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
            "dinheiro": None,
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

        if ctx.pode("cmv.relatorios") or ctx.pode("cmv.painel"):
            grupos = relatorios.cmv_por_grupo(cur, id_unidade, inicio, fim, "setor")
            resposta["pesos"] = [
                {"grupo": g["grupo"], "cmv": float(g["cmv"]),
                 "participacao_pct": g["participacao_pct"]}
                for g in grupos[:4]
            ]

    return resposta
