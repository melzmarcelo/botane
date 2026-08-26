"""Painel de CMV, curva ABC, margem por prato e fechamento de período."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

import auditoria
from database import get_cursor
from models.cmv import ApuracaoResponse, FechamentoRequest, FechamentoResponse
from seguranca import Contexto, requer_permissao, unidade_atual
from services import cmv as motor
from services import periodos, relatorios

router = APIRouter(prefix="/cmv", tags=["CMV"])


def _periodo(cur, id_unidade: int, inicio: date | None,
             fim: date | None) -> tuple[date, date]:
    """Sem datas, o padrão é o período CORRENTE da loja — dia, semana ou mês.

    ⚠️ Antes era sempre "do dia 1 até hoje". Numa casa que fecha toda semana,
    abrir o painel no mês inteiro mostra um número que ela não usa para decidir
    nada — e, pior, um número que não bate com o fechamento que ela acabou de
    assinar.

    O fim é `min(fim do período, hoje)`: o período corrente ainda não terminou,
    e pedir estoque de uma data futura devolveria o saldo de agora com cara de
    projeção.
    """
    if not inicio or not fim:
        c = periodos.config(cur, id_unidade)
        p_inicio, p_fim = periodos.periodo_do_dia(
            date.today(), c["ciclo"], dia_semana=c["dia_semana"], dia_mes=c["dia_mes"])
        inicio = inicio or p_inicio
        fim = fim or min(p_fim, date.today())
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
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        inicio, fim = _periodo(cur, id_unidade, inicio, fim)
        c = periodos.config(cur, id_unidade)
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
    resposta["ciclo"] = c["ciclo"]
    resposta["rotulo"] = periodos.rotulo(inicio, fim, c["ciclo"])
    return resposta


@router.get("/abc")
def abc(
    inicio: date | None = None,
    fim: date | None = None,
    limite: int = Query(default=50, ge=5, le=200),
    ctx: Contexto = Depends(requer_permissao("cmv.relatorios", "cmv.painel")),
) -> list[dict]:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        inicio, fim = _periodo(cur, id_unidade, inicio, fim)
        return motor.curva_abc(cur, id_unidade, inicio, fim, limite)


@router.get("/margem")
def margem(
    inicio: date | None = None,
    fim: date | None = None,
    limite: int = Query(default=50, ge=5, le=200),
    ctx: Contexto = Depends(requer_permissao("cmv.relatorios", "cmv.painel")),
) -> list[dict]:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        inicio, fim = _periodo(cur, id_unidade, inicio, fim)
        return motor.margem_por_prato(cur, id_unidade, inicio, fim, limite)


@router.get("/por-grupo")
def por_grupo(
    agrupar: str = Query(default="setor", pattern="^(setor|categoria)$"),
    inicio: date | None = None,
    fim: date | None = None,
    ctx: Contexto = Depends(requer_permissao("cmv.relatorios", "cmv.painel")),
) -> list[dict]:
    """O CMV do período quebrado por setor ou por categoria."""
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        inicio, fim = _periodo(cur, id_unidade, inicio, fim)
        return relatorios.cmv_por_grupo(cur, id_unidade, inicio, fim, agrupar)


@router.get("/precos")
def precos(
    inicio: date | None = None,
    fim: date | None = None,
    limite: int = Query(default=40, ge=5, le=200),
    ctx: Contexto = Depends(requer_permissao("cmv.relatorios", "cmv.painel")),
) -> list[dict]:
    """O que subiu e o que caiu entre as notas — ordenado pelo impacto em reais."""
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        inicio, fim = _periodo(cur, id_unidade, inicio, fim)
        return relatorios.evolucao_de_preco(cur, id_unidade, inicio, fim, limite)


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

    Período FECHADO devolve o que foi congelado no fechamento; período aberto
    calcula do razão na hora. A resposta diz qual dos dois é (`congelado`), porque a
    diferença importa: um número que ainda pode mudar não se manda ao contador.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        inicio, fim = _periodo(cur, id_unidade, inicio, fim)
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

        # Um recorte DENTRO de um período fechado não é o período fechado — mas
        # quem pediu precisa saber que existe uma versão definitiva do período
        # inteiro, senão manda adiante o recorte achando que é ela.
        cur.execute(
            """SELECT competencia, inicio, fim, ciclo FROM cmv_fechamentos
                WHERE id_unidade = %s AND status = 'FECHADO'
                  AND inicio <= %s AND fim >= %s
                ORDER BY inicio DESC LIMIT 1""",
            (id_unidade, inicio, fim),
        )
        mes = cur.fetchone()
        mes_fechado = (
            {"competencia": str(mes["competencia"]), "inicio": str(mes["inicio"]),
             "fim": str(mes["fim"]),
             "rotulo": periodos.rotulo(mes["inicio"], mes["fim"], mes["ciclo"] or "MENSAL")}
            if mes and not congelado
            else None
        )

        # ⚠️ **A relação inversa também engana, e só apareceu com os ciclos.**
        # Numa casa que fecha toda semana, pedir "o mês" devolve um número que
        # mistura semanas congeladas com dias que ainda vão mudar — e nada na
        # tela dizia isso, porque a conferência de cima só olhava o recorte
        # CONTIDO num fechamento. Aqui a pergunta é a outra: quantos períodos
        # fechados este recorte atravessa?
        cur.execute(
            """SELECT count(*) AS n FROM cmv_fechamentos
                WHERE id_unidade = %s AND status = 'FECHADO'
                  AND inicio >= %s AND fim <= %s
                  AND NOT (inicio = %s AND fim = %s)""",
            (id_unidade, inicio, fim, inicio, fim),
        )
        atravessa = cur.fetchone()["n"] if not congelado else 0

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
        # Preenchido só quando o recorte cai dentro de um período fechado sem
        # ser ele: a tela oferece o período inteiro, que é o definitivo.
        "mes_fechado": mes_fechado,
        # E o contrário: quantos períodos já fechados este recorte engloba.
        "periodos_fechados_dentro": atravessa,
        "competencia": str(fechamento["competencia"]) if fechamento else None,
        "produtos": len(linhas), "total": total, "linhas": linhas,
    }


@router.get("/periodos")
def listar_periodos(
    quantos: int = Query(default=12, ge=1, le=60),
    ctx: Contexto = Depends(requer_permissao("cmv.painel")),
) -> dict:
    """Os últimos períodos da loja, no ritmo dela, e quais já estão fechados.

    É o que a tela oferece para escolher. Existe porque **o front não pode
    calcular isso**: a semana que fecha na quarta, o mês que começa no dia 26 e
    o dia corrido são três aritméticas diferentes, e uma segunda implementação
    em TypeScript divergiria da do servidor no primeiro caso de borda — com o
    agravante de que o desacordo apareceria como um fechamento no período
    errado, que é irreversível sem reabrir.

    ⚠️ O período corrente vem na lista com `fechavel: false`: ele é o que a
    pessoa está olhando, mas ainda não terminou.
    """
    hoje = date.today()
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        c = periodos.config(cur, id_unidade)
        lista = periodos.periodos_ate_hoje(
            c["ciclo"], quantos, dia_semana=c["dia_semana"], dia_mes=c["dia_mes"], hoje=hoje)
        cur.execute(
            """SELECT competencia, status FROM cmv_fechamentos
                WHERE id_unidade = %s AND ciclo = %s AND competencia = ANY(%s)""",
            (id_unidade, c["ciclo"], [i for i, _ in lista]),
        )
        estado = {r["competencia"]: r["status"] for r in cur.fetchall()}

    return {
        "ciclo": c["ciclo"],
        "dia_semana": c["dia_semana"],
        "dia_mes": c["dia_mes"],
        "descricao": periodos.descricao_do_ciclo(
            c["ciclo"], dia_semana=c["dia_semana"], dia_mes=c["dia_mes"]),
        "periodos": [
            {
                "inicio": str(i), "fim": str(f),
                "rotulo": periodos.rotulo(i, f, c["ciclo"]),
                "corrente": i <= hoje <= f,
                "status": estado.get(i),
                "fechavel": f < hoje and estado.get(i) != "FECHADO",
            }
            for i, f in lista
        ],
    }


@router.get("/fechamentos", response_model=list[FechamentoResponse])
def listar_fechamentos(ctx: Contexto = Depends(requer_permissao("cmv.painel"))) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """SELECT f.*, u.nome AS fechado_por_nome FROM cmv_fechamentos f
                 LEFT JOIN usuarios u ON u.id = f.fechado_por
                 JOIN unidades un ON un.id = f.id_unidade
                ORDER BY f.fim DESC, f.competencia DESC LIMIT 60"""
        )
        linhas = []
        for r in cur.fetchall():
            d = dict(r)
            d["fechado_por"] = d.pop("fechado_por_nome", None)
            d["fechado_em"] = d["fechado_em"].isoformat() if d["fechado_em"] else None
            # ⚠️ O rótulo vem do SERVIDOR, não da tela: quem sabe se "01/08" é o
            # mês de agosto ou a semana que começou nele é a coluna `ciclo`, e
            # remontar essa frase no front daria duas versões da mesma verdade.
            d["rotulo"] = periodos.rotulo(d["inicio"], d["fim"], d.get("ciclo") or "MENSAL")
            linhas.append(d)
    return linhas


@router.post("/fechamentos", status_code=201)
def fechar(body: FechamentoRequest,
           ctx: Contexto = Depends(requer_permissao("cmv.fechamento"))) -> dict:
    """Congela o período. Depois disso, movimento com data dentro dele é recusado.

    ⚠️ **O tamanho do período vem da loja, não do pedido.** `body.competencia` é
    qualquer dia dentro dele; quem diz se isso é um dia, uma semana ou um mês é
    `parametros.ciclo_fechamento`. Deixar o pedido escolher permitiria fechar a
    semana numa tela e o mês noutra, e aí "o período está fechado" passaria a
    depender de quem perguntou.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        c = periodos.config(cur, id_unidade)
        ciclo = c["ciclo"]
        competencia, fim = periodos.periodo_do_dia(
            body.competencia, ciclo, dia_semana=c["dia_semana"], dia_mes=c["dia_mes"])
        nome = periodos.rotulo(competencia, fim, ciclo)

        cur.execute(
            """SELECT status FROM cmv_fechamentos
                WHERE id_unidade = %s AND ciclo = %s AND competencia = %s""",
            (id_unidade, ciclo, competencia),
        )
        atual = cur.fetchone()
        if atual and atual["status"] == "FECHADO":
            raise HTTPException(status_code=409, detail=f"O período de {nome} já está fechado.")

        # ⚠️ **Período que ainda não chegou ao fim não fecha.** A conferência
        # antiga era "não dá para fechar mês futuro", e deixava fechar o mês
        # CORRENTE: no dia 25, congelar agosto travava os seis dias que ainda
        # iam acontecer, e a casa parava de conseguir lançar. Passava
        # despercebido porque ninguém fecha o mês no meio; com ciclo diário o
        # mesmo erro fica a um clique de distância.
        #
        # ⚠️ O corte é `fim > hoje`, não `fim >= hoje`: o dia de fechamento
        # pertence ao período que ele encerra, e é justamente à noite do
        # domingo — ou do próprio dia, no ciclo diário — que se fecha. Recusar
        # o último dia deixaria a casa sempre um período atrasada.
        if fim > date.today():
            raise HTTPException(
                status_code=400,
                detail=(f"O período de {nome} só termina em "
                        f"{fim.strftime('%d/%m/%Y')} e ainda está em curso. "
                        "Fechar agora travaria os dias que faltam."),
            )

        # ⚠️ **Períodos fechados não se sobrepõem.** Uma casa que fechava por mês
        # e passa a fechar por semana teria a semana de 24 a 30/08 caindo dentro
        # de agosto já fechado: dois congelados diriam coisas diferentes sobre os
        # mesmos dias, e a movimentação congelada — que é o que vai ao contador —
        # passaria a depender de qual dos dois se abrisse.
        cur.execute(
            """SELECT inicio, fim, ciclo FROM cmv_fechamentos
                WHERE id_unidade = %s AND status = 'FECHADO'
                  AND inicio <= %s AND fim >= %s
                  AND NOT (ciclo = %s AND competencia = %s)
                ORDER BY inicio LIMIT 1""",
            (id_unidade, fim, competencia, ciclo, competencia),
        )
        choque = cur.fetchone()
        if choque:
            outro = periodos.rotulo(choque["inicio"], choque["fim"], choque["ciclo"])
            raise HTTPException(
                status_code=409,
                detail=(f"O período de {nome} se sobrepõe a {outro}, que já está "
                        "fechado. Reabra o outro antes, ou escolha um período que "
                        "não o atravesse."),
            )

        r = motor.apurar(cur, id_unidade, competencia, fim)
        cur.execute(
            """INSERT INTO cmv_fechamentos
                   (id_unidade, ciclo, competencia, inicio, fim, estoque_inicial, compras,
                    estoque_final, cmv_real, cmv_teorico, variancia, perdas, consumo_interno,
                    ajustes, receita, food_cost_pct, status, fechado_por, fechado_em)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       'FECHADO', %s, now())
               ON CONFLICT (id_unidade, ciclo, competencia) DO UPDATE SET
                   estoque_inicial = EXCLUDED.estoque_inicial, compras = EXCLUDED.compras,
                   estoque_final = EXCLUDED.estoque_final, cmv_real = EXCLUDED.cmv_real,
                   cmv_teorico = EXCLUDED.cmv_teorico, variancia = EXCLUDED.variancia,
                   perdas = EXCLUDED.perdas, consumo_interno = EXCLUDED.consumo_interno,
                   ajustes = EXCLUDED.ajustes, receita = EXCLUDED.receita,
                   food_cost_pct = EXCLUDED.food_cost_pct, status = 'FECHADO',
                   fechado_por = EXCLUDED.fechado_por, fechado_em = now()
               RETURNING id""",
            (id_unidade, ciclo, competencia, competencia, fim, r["estoque_inicial"], r["compras"],
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
                            depois={"ciclo": ciclo, "competencia": str(competencia),
                                    "inicio": str(competencia), "fim": str(fim),
                                    "cmv_real": float(r["cmv_real"]),
                                    "variancia": float(r["variancia"])},
                            id_unidade=id_unidade)
    return {"id": novo, "ciclo": ciclo, "competencia": str(competencia),
            "inicio": str(competencia), "fim": str(fim), "rotulo": nome,
            "cmv_real": float(r["cmv_real"]), "variancia": float(r["variancia"]),
            "produtos": produtos_congelados,
            # ⚠️ "Período fechado: <nome>" e não "<Nome> fechado": o rótulo tanto
            # é feminino ("semana de 17 a 23") quanto masculino ("agosto de
            # 2026"), e concordar com os dois exigiria o sistema saber o gênero
            # de cada frase que ele mesmo monta.
            "message": f"Período fechado: {nome} — "
                       f"{produtos_congelados} produto(s) na movimentação"}


@router.post("/fechamentos/{id_fechamento}/reabrir")
def reabrir(id_fechamento: int,
            ctx: Contexto = Depends(requer_permissao("cmv.reabrir"))) -> dict:
    """Reabrir é exceção e fica registrado — é o que dá sentido ao fechamento."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT competencia, inicio, fim, ciclo, status FROM cmv_fechamentos WHERE id = %s",
            (id_fechamento,)
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
                            antes={"ciclo": f.get("ciclo"), "inicio": str(f["inicio"]),
                                   "fim": str(f["fim"])})
    return {"message": "Período reaberto — lançamentos retroativos voltam a ser aceitos"}
