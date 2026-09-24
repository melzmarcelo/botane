"""A regra de disponibilidade: dado dia, hora e pessoas, o que dá para marcar.

🔑 **É o coração do módulo, e é onde a maioria dos sistemas de reserva erra.** O
estudo em `docs/reservas-esboco.md` já dizia isso; o protótipo em
`apresentacao/reservas-prototipo.html` implementa a mesma regra em JavaScript e
serviu de especificação executável para este arquivo.

A regra, escrita:

1. As mesas candidatas são as **ativas, de salões ativos**.
2. Uma mesa está **presa** no horário `H` se existe reserva `R` viva cujo
   intervalo `[R.hora, R.hora + permanência(R.hora) + folga)` cruza
   `[H, H + permanência(H) + folga)`.
3. **Cabe** o grupo de `P` pessoas se houver mesa livre com `capacidade_max >= P`
   — **a menor que serve** — ou um par `junta_com` com as duas livres e a soma
   dos máximos `>= P`.

⚠️ **"Esgotado" depende do TAMANHO DO GRUPO.** No mesmo sábado às 12h pode não
haver mesa para 6 e haver para 2. Por isso a lista de horários só se calcula
DEPOIS de saber quantas pessoas são — e por isso lotação nunca é um número só.

⚠️ **Contar lugares livres não serve.** Quatro lugares livres em duas mesas de
dois não sentam um grupo de quatro. A regra aloca MESA, não soma cadeira.

⚠️ **Reserva PENDENTE segura a mesa.** Foi uma das duas descobertas do
protótipo: se não segurasse, a casa aprovaria no dia seguinte e descobriria que
não cabe. Só `CANCELADA` e `NAO_COMPARECEU` soltam.

⚠️ **A verificação e a gravação acontecem na MESMA transação, com trava por
(loja, dia).** É o caso que define a arquitetura: conferir e depois gravar é
onde o overbooking nasce. A casa já tem precedente — o razão de estoque usa
`SELECT … FOR UPDATE` no saldo, e o lote de reembolso usa
`pg_advisory_xact_lock`. Aqui é a segunda forma.
"""

from datetime import date, datetime, time, timedelta

from fastapi import HTTPException

from relogio import agora_da_casa
from services import reservas as cadastro

# Status que NÃO soltam a mesa. Ver o aviso do cabeçalho sobre `PENDENTE`.
VIVOS = ("PENDENTE", "CONFIRMADA", "CHEGOU", "ENCERRADA")

# ⚠️ Quando nenhuma faixa cobre a hora pedida. Não é chute: é o que dizer quando
# a casa configurou faixas que deixam um buraco — e a alternativa (recusar a
# reserva) seria pior, porque o buraco é erro de cadastro e quem paga seria o
# cliente. A tela de configuração é quem deve avisar da falta.
PERMANENCIA_RESERVA = 90


def _min(t: time) -> int:
    return t.hour * 60 + t.minute


def _hora(minutos: int) -> time:
    return time((minutos // 60) % 24, minutos % 60)


def _hm(t: time) -> str:
    return t.strftime("%H:%M")


def permanencia(faixas: list[dict], minuto: int) -> int:
    """Quanto tempo a mesa fica ocupada por uma reserva que começa neste minuto."""
    for f in faixas:
        if _min(f["de"]) <= minuto < _min(f["ate"]):
            return int(f["minutos"])
    return PERMANENCIA_RESERVA


def _faixas(cur, id_unidade: int) -> list[dict]:
    cur.execute(
        "SELECT de, ate, minutos FROM reserva_permanencias WHERE id_unidade = %s ORDER BY de",
        (id_unidade,),
    )
    return [dict(r) for r in cur.fetchall()]


def bloqueio_do_dia(cur, id_unidade: int, dia: date) -> str | None:
    """O motivo pelo qual a casa não recebe neste dia, se houver.

    ⚠️ É diferente de "o dia da semana está fechado": o horário vale toda
    semana, o bloqueio vale uma vez. Resolver feriado desmarcando a quarta-feira
    faria a casa fechar todas as quartas do ano.
    """
    cur.execute(
        """SELECT motivo FROM reserva_bloqueios
            WHERE id_unidade = %s AND %s BETWEEN de AND ate ORDER BY de LIMIT 1""",
        (id_unidade, dia),
    )
    linha = cur.fetchone()
    return linha["motivo"] if linha else None


def janela_do_dia(cur, id_unidade: int, dia: date) -> dict | None:
    """Abre, fecha e última reserva deste dia — ou None se a casa não recebe.

    ⚠️ **`isodow`, porque `reserva_horarios.dia_semana` é ISO** (1 = segunda …
    7 = domingo), igual a `parametros.fechamento_dia_semana`. O `dow` do Postgres
    é 0 = domingo e daria o dia errado sem erro nenhum.
    """
    cur.execute(
        """SELECT h.aberto, h.abre, h.fecha, h.ultima_reserva
             FROM reserva_horarios h
            WHERE h.id_unidade = %s AND h.dia_semana = extract(isodow FROM %s::date)""",
        (id_unidade, dia),
    )
    linha = cur.fetchone()
    if not linha or not linha["aberto"]:
        return None
    return dict(linha)


def _reservas_do_dia(cur, id_unidade: int, dia: date,
                     ignorar: int | None = None) -> list[dict]:
    """As reservas que seguram mesa neste dia, com as mesas de cada uma."""
    cur.execute(
        f"""SELECT r.id, r.hora, array_remove(array_agg(rm.id_mesa), NULL) AS mesas
              FROM reservas r
              LEFT JOIN reserva_mesas rm ON rm.id_reserva = r.id
             WHERE r.id_unidade = %s AND r.data = %s
               AND r.status = ANY(%s) AND (%s::bigint IS NULL OR r.id <> %s)
             GROUP BY r.id, r.hora""",
        (id_unidade, dia, list(VIVOS), ignorar, ignorar or 0),
    )
    return [dict(r) for r in cur.fetchall()]


def _presas(reservas: list[dict], faixas: list[dict], inicio: int, folga: int) -> set[int]:
    """As mesas ocupadas por quem cruza a janela que começa em `inicio`."""
    fim = inicio + permanencia(faixas, inicio) + folga
    presas: set[int] = set()
    for r in reservas:
        r_inicio = _min(r["hora"])
        r_fim = r_inicio + permanencia(faixas, r_inicio) + folga
        if r_inicio < fim and inicio < r_fim:
            presas.update(r["mesas"] or [])
    return presas


def alocar(mesas: list[dict], presas: set[int], pessoas: int) -> list[int] | None:
    """A alocação que atende o grupo, ou None. **A menor mesa que serve primeiro.**

    🔑 **A menor, e não a primeira que couber.** Pôr um casal na mesa de oito às
    12h é o que faz o grupo de oito não caber às 12h30 — e a recusa apareceria
    como "esgotado" sem que nada no salão estivesse cheio.

    ⚠️ Usa `capacidade_max`, não `lugares`: é a capacidade com a cadeira extra
    que decide se cabe. Os `lugares` são para o relatório de ocupação.
    """
    livres = [m for m in mesas if m["id"] not in presas]
    servem = sorted((m for m in livres if m["capacidade_max"] >= pessoas),
                    key=lambda m: (m["capacidade_max"], m["id"]))
    if servem:
        return [servem[0]["id"]]

    # A junta: duas mesas vizinhas, as duas livres.
    por_id = {m["id"]: m for m in livres}
    pares = []
    for m in livres:
        par = por_id.get(m["junta_com"])
        if par and m["capacidade_max"] + par["capacidade_max"] >= pessoas:
            pares.append((m["capacidade_max"] + par["capacidade_max"],
                          sorted([m["id"], par["id"]])))
    if pares:
        # Também a menor junta que serve, pela mesma razão de cima.
        pares.sort(key=lambda x: (x[0], x[1]))
        return pares[0][1]
    return None


def disponibilidade(cur, id_unidade: int, dia: date, pessoas: int,
                    ignorar: int | None = None) -> dict:
    """Os horários que aceitam um grupo de `pessoas` neste dia.

    `ignorar` é a reserva que está sendo REMARCADA: ela não pode disputar mesa
    consigo mesma, senão remarcar das 12h para as 12h30 esbarraria na própria
    permanência.
    """
    cur.execute(
        """SELECT folga_min, passo_min, teto_online, antecedencia_min_horas,
                  antecedencia_max_dias
             FROM reserva_config WHERE id_unidade = %s""",
        (id_unidade,),
    )
    cfg = cur.fetchone()
    if not cfg:
        # A configuração nasce na primeira visita à tela; sem ela, a resposta
        # honesta é "a casa ainda não disse quando atende".
        return {"data": dia.isoformat(), "pessoas": pessoas, "horarios": [],
                "motivo": "A configuração de reservas ainda não foi feita."}

    bloqueio = bloqueio_do_dia(cur, id_unidade, dia)
    if bloqueio:
        return {"data": dia.isoformat(), "pessoas": pessoas, "horarios": [],
                "motivo": f"A casa não recebe neste dia: {bloqueio}."}

    janela = janela_do_dia(cur, id_unidade, dia)
    if not janela:
        return {"data": dia.isoformat(), "pessoas": pessoas, "horarios": [],
                "motivo": "A casa não atende neste dia da semana."}

    mesas = cadastro._mesas_vivas(cur, id_unidade)
    if not mesas:
        return {"data": dia.isoformat(), "pessoas": pessoas, "horarios": [],
                "motivo": "Nenhuma mesa ativa cadastrada."}

    faixas = _faixas(cur, id_unidade)
    reservas = _reservas_do_dia(cur, id_unidade, dia, ignorar)
    folga = int(cfg["folga_min"])
    passo = int(cfg["passo_min"])

    horarios = []
    minuto = _min(janela["abre"])
    ultimo = _min(janela["ultima_reserva"])
    while minuto <= ultimo:
        presas = _presas(reservas, faixas, minuto, folga)
        onde = alocar(mesas, presas, pessoas)
        horarios.append({
            "hora": _hm(_hora(minuto)),
            "livre": onde is not None,
            # Quantas mesas ainda sobram para um grupo deste tamanho — é o que
            # deixa a tela dizer "últimas mesas" em vez de só verde ou vermelho.
            "mesas_livres": sum(1 for m in mesas
                                if m["id"] not in presas and m["capacidade_max"] >= pessoas),
            "sai_por_volta": _hm(_hora(minuto + permanencia(faixas, minuto))),
        })
        minuto += passo

    return {
        "data": dia.isoformat(),
        "pessoas": pessoas,
        "abre": _hm(janela["abre"]),
        "fecha": _hm(janela["fecha"]),
        "ultima_reserva": _hm(janela["ultima_reserva"]),
        "teto_online": int(cfg["teto_online"]),
        "maior_grupo": cadastro.maior_grupo(cur, id_unidade),
        "horarios": horarios,
        "motivo": None if any(h["livre"] for h in horarios) else
                  f"Não há mesa para {pessoas} pessoa(s) neste dia.",
    }


def limite_do_site(agora: datetime, antecedencia_horas: int) -> datetime:
    """O primeiro instante que o SITE ainda pode marcar.

    🔑 **Pedido do dono (23/09/2026):** *"como ainda não abriu a loja hoje, ainda
    podemos marcar, e conforme o dia anda, podemos permitir ainda em horários
    que ainda não chegaram — entrando às 10:00, marco para as 12:00."* É o
    agora mais a antecedência mínima da configuração.
    ⚠️ **Uma regra só para a LISTA e para a GRAVAÇÃO.** A lista oferecia os
    horários de hoje que já tinham passado, e a gravação os recusava: o
    cliente tocava num horário e ouvia "não".
    """
    return agora + timedelta(hours=antecedencia_horas)


def _travar_o_dia(cur, id_unidade: int, dia: date) -> None:
    """Serializa quem mexe neste (loja, dia) até o fim da transação.

    🔑 **É o caso que define a arquitetura.** Duas pessoas pedindo o mesmo
    horário ao mesmo tempo: conferir e depois gravar é onde o overbooking nasce.
    A trava é por (loja, dia) e não pela tabela inteira — sábado e domingo não
    disputam nada, e travar o módulo todo faria a casa parar de atender o
    telefone enquanto o site grava.

    ⚠️ `pg_advisory_xact_lock` solta sozinha no fim da transação, inclusive se
    ela abortar. É a mesma escolha do lote de reembolso do outro sistema da casa.
    """
    cur.execute("SELECT pg_advisory_xact_lock(%s, %s)",
                (id_unidade, int(dia.strftime("%Y%m%d"))))


def criar(cur, id_unidade: int, corpo, id_usuario: int | None) -> dict:
    """Marca a reserva — conferindo e gravando na MESMA transação."""
    _travar_o_dia(cur, id_unidade, corpo.data)

    cur.execute(
        """SELECT folga_min, teto_online, antecedencia_min_horas, antecedencia_max_dias
             FROM reserva_config WHERE id_unidade = %s""",
        (id_unidade,),
    )
    cfg = cur.fetchone()
    if not cfg:
        raise HTTPException(status_code=409,
                            detail="A configuração de reservas ainda não foi feita.")

    bloqueio = bloqueio_do_dia(cur, id_unidade, corpo.data)
    if bloqueio:
        raise HTTPException(status_code=409,
                            detail=f"A casa não recebe em {corpo.data:%d/%m}: {bloqueio}.")

    janela = janela_do_dia(cur, id_unidade, corpo.data)
    if not janela:
        raise HTTPException(status_code=409,
                            detail="A casa não atende neste dia da semana.")
    if not (janela["abre"] <= corpo.hora <= janela["ultima_reserva"]):
        raise HTTPException(
            status_code=409,
            detail=(f"Fora da janela de reservas: das {_hm(janela['abre'])} às "
                    f"{_hm(janela['ultima_reserva'])}."),
        )

    # ⚠️ **O teto e a antecedência valem para o SITE, não para o balcão.** Quem
    # liga fala com uma pessoa, e essa pessoa pode aceitar um grupo de doze
    # sabendo que vai juntar mesas na mão. Aplicar a regra do site ao balcão
    # tiraria da casa a decisão que é dela.
    if corpo.origem == "SITE":
        if corpo.pessoas > int(cfg["teto_online"]):
            raise HTTPException(
                status_code=409,
                detail=(f"Para grupos acima de {cfg['teto_online']} pessoas, fale com a "
                        "casa."),
            )
        # ⚠️ **A hora da CASA** (`relogio.py`). Era `datetime.now()`: no ar o
        # contêiner roda em UTC, três horas à frente, e às 09:00 uma reserva
        # para as 12:00 parecia ter antecedência ZERO — recusada.
        agora = agora_da_casa().replace(tzinfo=None)
        quando = datetime.combine(corpo.data, corpo.hora)
        if quando < limite_do_site(agora, int(cfg["antecedencia_min_horas"])):
            raise HTTPException(
                status_code=409,
                detail=(f"Reserva pelo site precisa de {cfg['antecedencia_min_horas']}h de "
                        "antecedência. Fale com a casa."),
            )
        if corpo.data - agora.date() > timedelta(days=int(cfg["antecedencia_max_dias"])):
            raise HTTPException(
                status_code=409,
                detail=f"A agenda vai até {cfg['antecedencia_max_dias']} dias à frente.",
            )

    mesas = cadastro._mesas_vivas(cur, id_unidade)
    faixas = _faixas(cur, id_unidade)
    reservas = _reservas_do_dia(cur, id_unidade, corpo.data)
    presas = _presas(reservas, faixas, _min(corpo.hora), int(cfg["folga_min"]))
    onde = alocar(mesas, presas, corpo.pessoas)
    if onde is None:
        raise HTTPException(
            status_code=409,
            detail=(f"Não há mesa livre para {corpo.pessoas} pessoa(s) às "
                    f"{_hm(corpo.hora)}. Veja os horários disponíveis."),
        )

    cur.execute(
        """INSERT INTO reservas (id_unidade, data, hora, pessoas, status, origem,
                                 id_pessoa, nome, telefone, objetivo,
                                 observacao_cliente, observacao_interna, criado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (id_unidade, corpo.data, corpo.hora, corpo.pessoas, corpo.status_inicial(),
         corpo.origem, corpo.id_pessoa, corpo.nome.strip(), corpo.telefone,
         corpo.objetivo, corpo.observacao_cliente, corpo.observacao_interna, id_usuario),
    )
    id_reserva = cur.fetchone()["id"]
    for id_mesa in onde:
        cur.execute("INSERT INTO reserva_mesas (id_reserva, id_mesa) VALUES (%s, %s)",
                    (id_reserva, id_mesa))

    nomes = [m["nome"] for m in mesas if m["id"] in onde]
    return {"id": id_reserva, "mesas": nomes, "status": corpo.status_inicial()}


def _travar_os_dias(cur, id_unidade: int, *dias: date) -> None:
    """Trava um ou dois dias, **sempre na mesma ordem**.

    ⚠️ **A ordem é o que impede o impasse.** Remarcar de sábado para domingo
    precisa dos dois dias travados; se uma requisição pegasse sábado→domingo e
    outra domingo→sábado ao mesmo tempo, cada uma seguraria o dia que a outra
    espera e as duas ficariam paradas até o banco matar uma. Pegando sempre do
    menor para o maior, isso não acontece — é a regra clássica, e é barata.
    """
    for dia in sorted(set(dias)):
        _travar_o_dia(cur, id_unidade, dia)


# ⚠️ **Só reserva que ainda não sentou se remarca.** `CHEGOU` quer dizer que as
# pessoas estão na mesa: mudar o horário delas não descreve nada que aconteça no
# salão. O resto já terminou o ciclo.
REMARCAVEIS = ("PENDENTE", "CONFIRMADA")


def remarcar(cur, id_unidade: int, id_reserva: int, corpo) -> dict:
    """Muda dia, hora ou número de pessoas — realocando a mesa.

    🔑 **É a ligação mais comum depois de marcar** (*"dá para passar para as
    13h?"*), e sem ela a recepção teria de cancelar e recriar — perdendo o
    histórico da reserva e o lugar na fila de quem marcou primeiro.

    ⚠️ **A reserva não pode disputar mesa CONSIGO MESMA.** Passar das 12h para
    as 12h30 esbarraria na própria permanência, e o sistema responderia "não há
    mesa" apontando para a mesa que a própria reserva ocupa. É para isso que a
    disponibilidade tem o `ignorar` — e é o único chamador dele.
    """
    cur.execute(
        """SELECT data, hora, pessoas, status, nome FROM reservas
            WHERE id = %s AND id_unidade = %s""",
        (id_reserva, id_unidade),
    )
    atual = cur.fetchone()
    if not atual:
        raise HTTPException(status_code=404, detail="Reserva não encontrada")
    if atual["status"] not in REMARCAVEIS:
        raise HTTPException(
            status_code=409,
            detail=(f"A reserva de {atual['nome']} está {atual['status']} e não se "
                    "remarca. Só dá para remarcar o que ainda não sentou."),
        )

    nova_data = corpo.data or atual["data"]
    nova_hora = corpo.hora or atual["hora"]
    novas_pessoas = corpo.pessoas or atual["pessoas"]
    _travar_os_dias(cur, id_unidade, atual["data"], nova_data)

    cur.execute(
        "SELECT folga_min FROM reserva_config WHERE id_unidade = %s", (id_unidade,)
    )
    cfg = cur.fetchone()
    if not cfg:
        raise HTTPException(status_code=409,
                            detail="A configuração de reservas ainda não foi feita.")

    bloqueio = bloqueio_do_dia(cur, id_unidade, nova_data)
    if bloqueio:
        raise HTTPException(status_code=409,
                            detail=f"A casa não recebe em {nova_data:%d/%m}: {bloqueio}.")
    janela = janela_do_dia(cur, id_unidade, nova_data)
    if not janela:
        raise HTTPException(status_code=409,
                            detail="A casa não atende neste dia da semana.")
    if not (janela["abre"] <= nova_hora <= janela["ultima_reserva"]):
        raise HTTPException(
            status_code=409,
            detail=(f"Fora da janela de reservas: das {_hm(janela['abre'])} às "
                    f"{_hm(janela['ultima_reserva'])}."),
        )

    mesas = cadastro._mesas_vivas(cur, id_unidade)
    faixas = _faixas(cur, id_unidade)
    # 🔑 `ignorar=id_reserva`: ela sai da conta de quem ocupa mesa, senão
    # disputaria com a versão antiga de si mesma.
    reservas = _reservas_do_dia(cur, id_unidade, nova_data, ignorar=id_reserva)
    presas = _presas(reservas, faixas, _min(nova_hora), int(cfg["folga_min"]))
    onde = alocar(mesas, presas, novas_pessoas)
    if onde is None:
        raise HTTPException(
            status_code=409,
            detail=(f"Não há mesa livre para {novas_pessoas} pessoa(s) às "
                    f"{_hm(nova_hora)} em {nova_data:%d/%m}. A reserva continua como "
                    "estava."),
        )

    cur.execute(
        """UPDATE reservas SET data = %s, hora = %s, pessoas = %s WHERE id = %s""",
        (nova_data, nova_hora, novas_pessoas, id_reserva),
    )
    # ⚠️ As mesas são reescritas: a alocação é resultado do cálculo, não algo que
    # alguém escolheu — casar linha a linha só deixaria mesa órfã presa à reserva.
    cur.execute("DELETE FROM reserva_mesas WHERE id_reserva = %s", (id_reserva,))
    for id_mesa in onde:
        cur.execute("INSERT INTO reserva_mesas (id_reserva, id_mesa) VALUES (%s, %s)",
                    (id_reserva, id_mesa))

    nomes = [m["nome"] for m in mesas if m["id"] in onde]
    return {
        "id": id_reserva,
        "antes": {"data": str(atual["data"]), "hora": _hm(atual["hora"]),
                  "pessoas": atual["pessoas"]},
        "depois": {"data": str(nova_data), "hora": _hm(nova_hora),
                   "pessoas": novas_pessoas},
        "mesas": nomes,
    }


def agenda(cur, id_unidade: int, dia: date) -> dict:
    """O dia inteiro, como a recepção olha."""
    cur.execute(
        """SELECT r.id, r.hora, r.pessoas, r.status, r.origem, r.nome, r.telefone,
                  r.objetivo, r.observacao_cliente, r.observacao_interna, r.id_pessoa,
                  coalesce(
                      (SELECT string_agg(m.nome, '+' ORDER BY m.nome)
                         FROM reserva_mesas rm JOIN mesas m ON m.id = rm.id_mesa
                        WHERE rm.id_reserva = r.id), '') AS mesas
             FROM reservas r
            WHERE r.id_unidade = %s AND r.data = %s
            ORDER BY r.hora, r.id""",
        (id_unidade, dia),
    )
    linhas = [dict(r) for r in cur.fetchall()]
    faixas = _faixas(cur, id_unidade)
    for linha in linhas:
        linha["hora"] = _hm(linha["hora"])
        linha["sai_por_volta"] = (
            None if linha["status"] in ("CANCELADA", "NAO_COMPARECEU")
            else _hm(_hora(_min(time.fromisoformat(linha["hora"]))
                           + permanencia(faixas, _min(time.fromisoformat(linha["hora"])))))
        )
    vivas = [x for x in linhas if x["status"] in VIVOS]
    janela = janela_do_dia(cur, id_unidade, dia)
    cur.execute("SELECT passo_min FROM reserva_config WHERE id_unidade = %s", (id_unidade,))
    cfg = cur.fetchone()
    return {
        "data": dia.isoformat(),
        "reservas": linhas,
        "esperados": sum(x["pessoas"] for x in vivas),
        "ativas": len(vivas),
        "aberta": janela is not None,
        "bloqueio": bloqueio_do_dia(cur, id_unidade, dia),
        "lugares": sum(m["lugares"] for m in cadastro._mesas_vivas(cur, id_unidade)),
        # 🔑 **A janela do dia, para a linha do tempo** (24/09/2026): a visão
        # macro desenha a ocupação de `abre` a `fecha`, de passo em passo. Nulos
        # quando a casa não atende no dia — aí a linha do tempo não se desenha.
        "abre": _hm(janela["abre"]) if janela else None,
        "fecha": _hm(janela["fecha"]) if janela else None,
        "passo": int(cfg["passo_min"]) if cfg else 30,
    }


def calendario(cur, id_unidade: int, inicio: date) -> dict:
    """O mês inteiro, um resumo por dia — a visão de calendário da agenda.

    🔑 **Pedido do dono (24/09/2026):** *"na agenda de reservas, ter uma visão de
    calendário, onde o usuário tem uma visão geral do que está reservado, e aí
    clicar no dia."*
    ⚠️ **Uma consulta agregada para o mês, não uma agenda por dia.** Trinta
    chamadas a `agenda()` fariam trinta idas ao banco por abertura de tela.
    ⚠️ **Conta só o que está VIVO** (`VIVOS`): reserva cancelada no calendário
    faria o dia parecer cheio sem ninguém vir. Os pendentes vêm à parte, porque
    são o que a recepção ainda precisa resolver.
    """
    fim = (inicio.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    cur.execute("SELECT dia_semana FROM reserva_horarios WHERE id_unidade = %s AND aberto",
                (id_unidade,))
    abertos = {r["dia_semana"] for r in cur.fetchall()}
    cur.execute(
        """SELECT de, ate, motivo FROM reserva_bloqueios
            WHERE id_unidade = %s AND ate >= %s AND de <= %s ORDER BY de""",
        (id_unidade, inicio, fim),
    )
    bloqueios = [dict(r) for r in cur.fetchall()]
    cur.execute(
        """SELECT data,
                  count(*) FILTER (WHERE status = ANY(%(vivos)s)) AS reservas,
                  coalesce(sum(pessoas) FILTER (WHERE status = ANY(%(vivos)s)), 0) AS pessoas,
                  count(*) FILTER (WHERE status = 'PENDENTE') AS pendentes
             FROM reservas
            WHERE id_unidade = %(u)s AND data BETWEEN %(de)s AND %(ate)s
            GROUP BY data""",
        {"vivos": list(VIVOS), "u": id_unidade, "de": inicio, "ate": fim},
    )
    por_dia = {r["data"]: dict(r) for r in cur.fetchall()}
    dias = []
    d = inicio
    while d <= fim:
        x = por_dia.get(d, {})
        dias.append({
            "data": d.isoformat(),
            # ⚠️ ISO, como `reserva_horarios.dia_semana`: 1 = segunda … 7 = domingo.
            "aberta": d.isoweekday() in abertos,
            "bloqueio": next((b["motivo"] for b in bloqueios if b["de"] <= d <= b["ate"]), None),
            "reservas": int(x.get("reservas") or 0),
            "pessoas": int(x.get("pessoas") or 0),
            "pendentes": int(x.get("pendentes") or 0),
        })
        d += timedelta(days=1)
    return {
        "mes": inicio.strftime("%Y-%m"),
        "dias": dias,
        "lugares": sum(m["lugares"] for m in cadastro._mesas_vivas(cur, id_unidade)),
    }


# ⚠️ **Para onde cada status pode ir.** Escrito como tabela porque "cancelar uma
# reserva que já foi embora" e "marcar chegada de quem cancelou" são erros de
# operação, e o sistema tem de recusá-los dizendo o que era possível — não
# gravar calado e deixar a agenda contar uma história impossível.
TRANSICOES = {
    "PENDENTE": ("CONFIRMADA", "CANCELADA"),
    "CONFIRMADA": ("CHEGOU", "CANCELADA", "NAO_COMPARECEU"),
    "CHEGOU": ("ENCERRADA", "CANCELADA"),
    "ENCERRADA": (),
    "CANCELADA": (),
    "NAO_COMPARECEU": (),
}


def mudar_status(cur, id_unidade: int, id_reserva: int, novo: str) -> dict:
    """Move a reserva de status — só pelos caminhos que existem.

    ⚠️ **A reserva não se apaga**, nem mesmo cancelada: é a mesma disciplina do
    razão. "Cancelada" é um fato, e apagar a linha levaria junto a resposta para
    "por que a mesa ficou vazia naquele sábado".
    """
    cur.execute(
        "SELECT status, nome FROM reservas WHERE id = %s AND id_unidade = %s",
        (id_reserva, id_unidade),
    )
    atual = cur.fetchone()
    if not atual:
        raise HTTPException(status_code=404, detail="Reserva não encontrada")
    permitidos = TRANSICOES.get(atual["status"], ())
    if novo not in permitidos:
        fim = (" — ela já terminou o ciclo." if not permitidos
               else f" — daqui só dá para ir a {', '.join(permitidos)}.")
        raise HTTPException(
            status_code=409,
            detail=f"A reserva de {atual['nome']} está {atual['status']}{fim}",
        )
    cur.execute(
        "UPDATE reservas SET status = %s, status_em = now() WHERE id = %s",
        (novo, id_reserva),
    )
    return {"id": id_reserva, "de": atual["status"], "para": novo}
