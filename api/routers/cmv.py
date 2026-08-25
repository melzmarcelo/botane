"""Painel de CMV, curva ABC, margem por prato e fechamento de período."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

import auditoria
from database import get_cursor
from models.cmv import ApuracaoResponse, FechamentoRequest, FechamentoResponse
from seguranca import Contexto, requer_permissao, unidade_atual
from services import cmv as motor
from services import relatorios

router = APIRouter(prefix="/cmv", tags=["CMV"])


def _periodo(inicio: date | None, fim: date | None) -> tuple[date, date]:
    """Sem datas, o padrão é o mês corrente — que é o que o gestor olha."""
    hoje = date.today()
    if not inicio:
        inicio = hoje.replace(day=1)
    if not fim:
        fim = hoje
    if fim < inicio:
        raise HTTPException(status_code=400, detail="A data final é anterior à inicial.")
    return inicio, fim


def _float(v):
    return None if v is None else float(v)


@router.get("/apuracao", response_model=ApuracaoResponse)
def apuracao(
    inicio: date | None = None,
    fim: date | None = None,
    ctx: Contexto = Depends(requer_permissao("cmv.painel")),
) -> dict:
    inicio, fim = _periodo(inicio, fim)
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = motor.apurar(cur, id_unidade, inicio, fim)
        cur.execute(
            """SELECT 1 FROM cmv_fechamentos
                WHERE id_unidade = %s AND status = 'FECHADO' AND fim >= %s AND inicio <= %s""",
            (id_unidade, inicio, fim),
        )
        fechado = cur.fetchone() is not None

    resposta = {k: (_float(v) if not isinstance(v, (date, int)) else v) for k, v in r.items()}
    resposta["variancia_pct"] = (
        float(r["variancia"] / r["cmv_teorico"] * 100) if r["cmv_teorico"] else None
    )
    resposta["fechado"] = fechado
    return resposta


@router.get("/abc")
def abc(
    inicio: date | None = None,
    fim: date | None = None,
    limite: int = Query(default=50, ge=5, le=200),
    ctx: Contexto = Depends(requer_permissao("cmv.relatorios", "cmv.painel")),
) -> list[dict]:
    inicio, fim = _periodo(inicio, fim)
    with get_cursor() as cur:
        return motor.curva_abc(cur, unidade_atual(cur, ctx), inicio, fim, limite)


@router.get("/margem")
def margem(
    inicio: date | None = None,
    fim: date | None = None,
    limite: int = Query(default=50, ge=5, le=200),
    ctx: Contexto = Depends(requer_permissao("cmv.relatorios", "cmv.painel")),
) -> list[dict]:
    inicio, fim = _periodo(inicio, fim)
    with get_cursor() as cur:
        return motor.margem_por_prato(cur, unidade_atual(cur, ctx), inicio, fim, limite)


@router.get("/por-grupo")
def por_grupo(
    agrupar: str = Query(default="setor", pattern="^(setor|categoria)$"),
    inicio: date | None = None,
    fim: date | None = None,
    ctx: Contexto = Depends(requer_permissao("cmv.relatorios", "cmv.painel")),
) -> list[dict]:
    """O CMV do período quebrado por setor ou por categoria."""
    inicio, fim = _periodo(inicio, fim)
    with get_cursor() as cur:
        return relatorios.cmv_por_grupo(cur, unidade_atual(cur, ctx), inicio, fim, agrupar)


@router.get("/precos")
def precos(
    inicio: date | None = None,
    fim: date | None = None,
    limite: int = Query(default=40, ge=5, le=200),
    ctx: Contexto = Depends(requer_permissao("cmv.relatorios", "cmv.painel")),
) -> list[dict]:
    """O que subiu e o que caiu entre as notas — ordenado pelo impacto em reais."""
    inicio, fim = _periodo(inicio, fim)
    with get_cursor() as cur:
        return relatorios.evolucao_de_preco(cur, unidade_atual(cur, ctx), inicio, fim, limite)


@router.get("/precos/{id_produto}")
def preco_do_produto(
    id_produto: int,
    ctx: Contexto = Depends(requer_permissao("cmv.relatorios", "cmv.painel")),
) -> list[dict]:
    """Cada compra do insumo, da mais recente para a mais antiga."""
    with get_cursor() as cur:
        return relatorios.historico_de_preco(cur, unidade_atual(cur, ctx), id_produto)


@router.get("/movimentacao")
def movimentacao(inicio: date | None = None, fim: date | None = None,
                 ctx: Contexto = Depends(requer_permissao("cmv.painel"))) -> dict:
    """O que cada produto tinha, o que entrou, o que saiu e o que sobrou.

    Mês FECHADO devolve o que foi congelado no fechamento; mês aberto calcula
    do razão na hora. A resposta diz qual dos dois é (`congelado`), porque a
    diferença importa: um número que ainda pode mudar não se manda ao contador.
    """
    hoje = date.today()
    inicio = inicio or hoje.replace(day=1)
    fim = fim or hoje
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        # Só vale o fechamento que cobre EXATAMENTE o período pedido: um recorte
        # de dez dias dentro de um mês fechado não é o mês fechado.
        cur.execute(
            """SELECT id, competencia, status FROM cmv_fechamentos
                WHERE id_unidade = %s AND inicio = %s AND fim = %s AND status = 'FECHADO'""",
            (id_unidade, inicio, fim),
        )
        fechamento = cur.fetchone()
        if fechamento:
            linhas = motor.movimentacao_congelada(cur, fechamento["id"])
            congelado = True
        else:
            linhas = motor.movimentacao_por_produto(cur, id_unidade, inicio, fim)
            congelado = False

        # Um recorte DENTRO de um mês fechado não é o mês fechado — mas quem
        # pediu precisa saber que existe uma versão definitiva do mês inteiro,
        # senão manda adiante o recorte achando que é ela.
        cur.execute(
            """SELECT competencia, inicio, fim FROM cmv_fechamentos
                WHERE id_unidade = %s AND status = 'FECHADO'
                  AND %s BETWEEN inicio AND fim
                ORDER BY competencia DESC LIMIT 1""",
            (id_unidade, inicio),
        )
        mes = cur.fetchone()
        mes_fechado = (
            {"competencia": str(mes["competencia"]), "inicio": str(mes["inicio"]),
             "fim": str(mes["fim"])}
            if mes and not congelado
            else None
        )

    # A soma das linhas COMO ELAS APARECEM: o rodapé tem de fechar com a coluna
    # que a pessoa consegue conferir a mão. Isso quer dizer que a identidade
    # "inicial + entradas − saídas = final" pode diferir por centavos num
    # relatório de centenas de produtos — é o arredondamento de cada linha, não
    # erro de conta. Arredondar o rodapé também evita o 26865.370000000003 que
    # a soma de floats devolve.
    total = {
        campo: round(sum(float(l[campo]) for l in linhas), 2)
        for campo in ("valor_inicial", "valor_entradas", "valor_saidas", "valor_final")
    }
    return {
        "inicio": str(inicio), "fim": str(fim), "congelado": congelado,
        # Preenchido só quando o recorte cai dentro de um mês fechado sem ser
        # ele: a tela oferece o mês inteiro, que é o número definitivo.
        "mes_fechado": mes_fechado,
        "competencia": str(fechamento["competencia"]) if fechamento else None,
        "produtos": len(linhas), "total": total, "linhas": linhas,
    }


@router.get("/fechamentos", response_model=list[FechamentoResponse])
def listar_fechamentos(ctx: Contexto = Depends(requer_permissao("cmv.painel"))) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """SELECT f.*, u.nome AS fechado_por_nome FROM cmv_fechamentos f
                 LEFT JOIN usuarios u ON u.id = f.fechado_por
                 JOIN unidades un ON un.id = f.id_unidade
                ORDER BY f.competencia DESC LIMIT 36"""
        )
        linhas = []
        for r in cur.fetchall():
            d = dict(r)
            d["fechado_por"] = d.pop("fechado_por_nome", None)
            d["fechado_em"] = d["fechado_em"].isoformat() if d["fechado_em"] else None
            linhas.append(d)
    return linhas


@router.post("/fechamentos", status_code=201)
def fechar(body: FechamentoRequest,
           ctx: Contexto = Depends(requer_permissao("cmv.fechamento"))) -> dict:
    """Congela o mês. Depois disso, movimento com data anterior é recusado."""
    competencia = body.competencia.replace(day=1)
    proximo = (competencia + timedelta(days=32)).replace(day=1)
    fim = proximo - timedelta(days=1)

    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT status FROM cmv_fechamentos
                WHERE id_unidade = %s AND competencia = %s""",
            (id_unidade, competencia),
        )
        atual = cur.fetchone()
        if atual and atual["status"] == "FECHADO":
            raise HTTPException(status_code=409, detail="Este mês já está fechado.")
        if competencia > date.today().replace(day=1):
            raise HTTPException(status_code=400, detail="Não dá para fechar mês futuro.")

        r = motor.apurar(cur, id_unidade, competencia, fim)
        cur.execute(
            """INSERT INTO cmv_fechamentos
                   (id_unidade, competencia, inicio, fim, estoque_inicial, compras,
                    estoque_final, cmv_real, cmv_teorico, variancia, perdas, consumo_interno,
                    ajustes, receita, food_cost_pct, status, fechado_por, fechado_em)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       'FECHADO', %s, now())
               ON CONFLICT (id_unidade, competencia) DO UPDATE SET
                   estoque_inicial = EXCLUDED.estoque_inicial, compras = EXCLUDED.compras,
                   estoque_final = EXCLUDED.estoque_final, cmv_real = EXCLUDED.cmv_real,
                   cmv_teorico = EXCLUDED.cmv_teorico, variancia = EXCLUDED.variancia,
                   perdas = EXCLUDED.perdas, consumo_interno = EXCLUDED.consumo_interno,
                   ajustes = EXCLUDED.ajustes, receita = EXCLUDED.receita,
                   food_cost_pct = EXCLUDED.food_cost_pct, status = 'FECHADO',
                   fechado_por = EXCLUDED.fechado_por, fechado_em = now()
               RETURNING id""",
            (id_unidade, competencia, competencia, fim, r["estoque_inicial"], r["compras"],
             r["estoque_final"], r["cmv_real"], r["cmv_teorico"], r["variancia"], r["perdas"],
             r["consumo_interno"], r["ajustes"], r["receita"], r["food_cost_pct"],
             ctx.id_usuario),
        )
        novo = cur.fetchone()["id"]
        # A movimentação por produto é congelada junto: fechar o mês tem de
        # travar também o relatório que EXPLICA o número, não só o número.
        produtos_congelados = motor.congelar_movimentacao(cur, novo, id_unidade,
                                                          competencia, fim)
        auditoria.registrar(cur, ctx.id_usuario, "cmv", novo, "fechar",
                            depois={"competencia": str(competencia),
                                    "cmv_real": float(r["cmv_real"]),
                                    "variancia": float(r["variancia"])},
                            id_unidade=id_unidade)
    return {"id": novo, "competencia": str(competencia), "cmv_real": float(r["cmv_real"]),
            "variancia": float(r["variancia"]), "produtos": produtos_congelados,
            "message": f"Período fechado — {produtos_congelados} produto(s) na movimentação"}


@router.post("/fechamentos/{id_fechamento}/reabrir")
def reabrir(id_fechamento: int,
            ctx: Contexto = Depends(requer_permissao("cmv.reabrir"))) -> dict:
    """Reabrir é exceção e fica registrado — é o que dá sentido ao fechamento."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT competencia, status FROM cmv_fechamentos WHERE id = %s", (id_fechamento,)
        )
        f = cur.fetchone()
        if not f:
            raise HTTPException(status_code=404, detail="Fechamento não encontrado")
        if f["status"] != "FECHADO":
            raise HTTPException(status_code=400, detail="Este período já está reaberto.")
        cur.execute(
            """UPDATE cmv_fechamentos SET status = 'REABERTO', reaberto_por = %s,
                                          reaberto_em = now()
                WHERE id = %s""",
            (ctx.id_usuario, id_fechamento),
        )
        auditoria.registrar(cur, ctx.id_usuario, "cmv", id_fechamento, "reabrir",
                            antes={"competencia": str(f["competencia"])})
    return {"message": "Período reaberto — lançamentos retroativos voltam a ser aceitos"}
