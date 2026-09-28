"""A fidelidade do Portal de Clientes: o cartão de visitas com check-in por QR code.

🔑 **Pedido do dono (24/09/2026):** *"O cupom será por visita … um QRCode na mesa,
que o cliente lê e realiza o check-in. Após 10, ele recebe um almoço grátis."* A
regra, escrita:

1. O QR da mesa abre o site com a loja e o `token` do programa. O cliente se
   identifica pelo telefone (o mesmo cadastro da reserva) e faz o check-in.
2. Conta **uma visita por dia** (índice único no banco), só nos `dias_pontua` e,
   com `so_no_horario`, só com a casa aberta.
3. Ao juntar `visitas` check-ins ainda sem prêmio, nasce um **prêmio**: um código,
   uma validade (`validade_dias`) e os `dias_consumo` — congelados nele.
4. O balcão entrega o prêmio pelo código, só num dia de consumo e antes de vencer.

⚠️ **Um programa para a REDE** (o cadastro já é único), ligado POR LOJA em
`reserva_config.fidelidade_ligada`. Estudo em `docs/fidelidade-estudo.md`.
"""

import math
import secrets
from datetime import date, datetime, timedelta

from fastapi import HTTPException

from relogio import agora_da_casa
from services import reservas_agenda as agenda
from services import termo_consentimento as termo

NOMES = {1: "segunda", 2: "terça", 3: "quarta", 4: "quinta", 5: "sexta", 6: "sábado",
         7: "domingo"}
CURTOS = {1: "Seg", 2: "Ter", 3: "Qua", 4: "Qui", 5: "Sex", 6: "Sáb", 7: "Dom"}

# ⚠️ Sem 0/O, 1/I/L: o código é lido em voz alta no balcão e digitado de uma tela
# de celular. Letra que se confunde vira "código inválido" com o cliente na frente.
_ALFABETO = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def dias_em_texto(dias: list[int]) -> str:
    """{1..5} → "segunda a sexta"; {1,3,5} → "Seg, Qua, Sex"."""
    d = sorted(set(dias))
    if not d:
        return "nenhum dia"
    if len(d) == 7:
        return "todos os dias"
    if len(d) > 2 and d == list(range(d[0], d[-1] + 1)):
        return f"{NOMES[d[0]]} a {NOMES[d[-1]]}"
    return ", ".join(CURTOS[x] for x in d)


def config(cur) -> dict:
    cur.execute(
        """SELECT visitas, premio, validade_dias, dias_pontua, dias_consumo,
                  so_no_horario, token, site_url, exige_local, raio_m,
                  metodo, codigo_validade_min
             FROM fidelidade_config WHERE id = 1""")
    c = dict(cur.fetchone())
    c["dias_pontua"] = sorted(c["dias_pontua"])
    c["dias_consumo"] = sorted(c["dias_consumo"])
    return c


def salvar(cur, body) -> dict:
    cur.execute(
        """UPDATE fidelidade_config
              SET visitas = %s, premio = %s, validade_dias = %s, dias_pontua = %s,
                  dias_consumo = %s, so_no_horario = %s, site_url = %s,
                  exige_local = %s, raio_m = %s, metodo = %s, codigo_validade_min = %s,
                  atualizado_em = now()
            WHERE id = 1""",
        (body.visitas, body.premio.strip(), body.validade_dias, sorted(set(body.dias_pontua)),
         sorted(set(body.dias_consumo)), body.so_no_horario,
         body.site_url.strip().rstrip("/"), body.exige_local, body.raio_m,
         body.metodo, body.codigo_validade_min),
    )
    return config(cur)


def novo_token(cur) -> str:
    """Troca o segredo do QR. ⚠️ Os QR já impressos param de valer na hora."""
    token = secrets.token_hex(6)
    cur.execute("UPDATE fidelidade_config SET token = %s, atualizado_em = now() WHERE id = 1",
                (token,))
    return token


def ligada(cur, id_unidade: int) -> bool:
    cur.execute(
        """SELECT c.fidelidade_ligada FROM reserva_config c
             JOIN parametros p ON p.id_unidade = c.id_unidade
            WHERE c.id_unidade = %s AND p.reservas_ligado""",
        (id_unidade,),
    )
    linha = cur.fetchone()
    return bool(linha and linha["fidelidade_ligada"])


def link_do_qr(cfg: dict, id_unidade: int) -> str:
    """O endereço que o QR da mesa abre — a loja e o segredo, e nada do cliente."""
    return f"{cfg['site_url']}/?loja={id_unidade}&checkin={cfg['token']}"


def regras(cfg: dict) -> dict:
    """O que o site mostra ao cliente — sem o token, que é da mesa."""
    return {
        "visitas": cfg["visitas"],
        "premio": cfg["premio"],
        "validade_dias": cfg["validade_dias"],
        "pontua": dias_em_texto(cfg["dias_pontua"]),
        "consumo": dias_em_texto(cfg["dias_consumo"]),
        # O site só pede a localização quando a casa exige — pedir sem usar é
        # coletar dado pessoal à toa. ⚠️ E nunca no código do caixa (097): ali quem
        # confirma a presença é o atendente.
        "exige_local": cfg["exige_local"] and cfg["metodo"] == "QRCODE_MESA",
        # 🔑 Como a visita se confirma (097): o QR da mesa conta sozinho; o do caixa
        # espera o código que o atendente passa.
        "metodo": cfg["metodo"],
    }


# ---------------------------------------------------------------- localização
# 🔑 **Pedido do dono (24/09/2026):** *"validar a localização ao ler o QR code e contar
# a visita … configurável."* (migração 092). Quem decide é o SERVIDOR, pela distância.

# ⚠️ Acima disto o celular não sabe onde está (sem GPS, só pela rede): aceitar seria
# contar visita de quem está a quilômetros; recusar pedindo para tentar de novo é o certo.
PRECISAO_MAXIMA_M = 1000


def local_da_loja(cur, id_unidade: int) -> tuple[float, float] | None:
    cur.execute("SELECT latitude, longitude FROM unidades WHERE id = %s", (id_unidade,))
    r = cur.fetchone()
    if not r or r["latitude"] is None or r["longitude"] is None:
        return None
    return float(r["latitude"]), float(r["longitude"])


def definir_local(cur, id_unidade: int, latitude: float, longitude: float) -> None:
    cur.execute("UPDATE unidades SET latitude = %s, longitude = %s WHERE id = %s",
                (round(latitude, 6), round(longitude, 6), id_unidade))


def distancia_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distância em metros entre dois pontos (haversine) — sobra para 200 m."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def conferir_local(cur, id_unidade: int, cfg: dict, posicao: dict | None) -> int | None:
    """A distância até a loja, se a casa exige estar nela — ou a recusa que explica.

    ⚠️ **Desconta a margem de erro que o PRÓPRIO celular informa** (até o raio): dentro
    de prédio o GPS erra 20 a 100 m, e sem isso o cliente sentado no salão seria
    recusado. Nunca mais que o raio, senão uma margem de 3 km aprovaria qualquer um.
    """
    if not cfg["exige_local"]:
        return None
    loja = local_da_loja(cur, id_unidade)
    if not loja:
        raise HTTPException(
            status_code=409,
            detail="Esta casa ainda não configurou a localização do check-in. Avise a equipe.")
    if not posicao or posicao.get("latitude") is None or posicao.get("longitude") is None:
        raise HTTPException(
            status_code=409,
            detail="Para contar a visita, permita o acesso à localização — ela só confirma "
                   "que você está na casa.")
    precisao = float(posicao.get("precisao") or 0)
    if precisao > PRECISAO_MAXIMA_M:
        raise HTTPException(
            status_code=409,
            detail="Não conseguimos saber onde você está com precisão. Ligue a localização "
                   "(GPS) do celular e tente de novo.")
    d = distancia_m(loja, (float(posicao["latitude"]), float(posicao["longitude"])))
    if d - min(precisao, cfg["raio_m"]) > cfg["raio_m"]:
        longe = f"{d / 1000:.1f} km".replace(".", ",") if d >= 1000 else f"{d:.0f} m"
        raise HTTPException(
            status_code=409,
            detail=f"O check-in vale dentro da casa, e você parece estar a {longe} dela.")
    return round(d)


def _status(p: dict, hoje: date) -> str:
    if p["usado_em"]:
        return "USADO"
    return "VENCIDO" if p["vence_em"] < hoje else "DISPONIVEL"


def cartao(cur, id_cliente: int) -> dict:
    """O cartão do cliente: quantas visitas no atual, quanto falta e os prêmios."""
    cfg = config(cur)
    hoje = agora_da_casa().date()
    cur.execute(
        """SELECT data, selos FROM fidelidade_checkins
            WHERE id_cliente = %s AND id_premio IS NULL ORDER BY data, parte""",
        (id_cliente,),
    )
    linhas = [dict(r) for r in cur.fetchall()]
    abertas = [r["data"] for r in linhas]
    cur.execute(
        """SELECT codigo, premio, vence_em, vale_de, dias_consumo, emitido_em, usado_em
             FROM fidelidade_premios WHERE id_cliente = %s ORDER BY emitido_em DESC LIMIT 20""",
        (id_cliente,),
    )
    premios = []
    for p in cur.fetchall():
        p = dict(p)
        premios.append({
            "codigo": p["codigo"],
            "premio": p["premio"],
            "vence_em": p["vence_em"].isoformat(),
            # 🔑 Vale da PRÓXIMA visita em diante (093): o site diz "a partir de …".
            "vale_de": p["vale_de"].isoformat(),
            "consumo": dias_em_texto(p["dias_consumo"]),
            "status": _status(p, hoje),
        })
    cur.execute("SELECT termo_versao FROM reserva_clientes WHERE id = %s", (id_cliente,))
    versao = (cur.fetchone() or {}).get("termo_versao")
    # 🔑 O cartão conta SELOS, não linhas (097): uma visita pode valer mais de um.
    visitas = sum(int(r["selos"]) for r in linhas)
    return {
        **regras(cfg),
        "no_cartao": visitas,
        # ⚠️ Nunca negativo: baixar `visitas` na configuração não pode dizer ao
        # cliente que faltam "-2" — o próximo check-in fecha o cartão.
        "faltam": max(cfg["visitas"] - visitas, 0),
        "datas": sorted({d.isoformat() for d in abertas}),
        "hoje_ja_fez": hoje in abertas or _ja_fez_hoje(cur, id_cliente, hoje),
        "premios": premios,
        # 🔑 LGPD: o termo em vigor cita a fidelidade; quem aceitou o anterior
        # aceita de novo antes do primeiro check-in.
        "precisa_termo": versao != termo.VERSAO,
    }


def _ja_fez_hoje(cur, id_cliente: int, hoje: date) -> bool:
    # O check-in de hoje pode já estar DENTRO de um prêmio (o que fechou o cartão).
    # ⚠️ Só a `parte 0` é a visita: o selo dado à mão (098) fica numa parte acima e não
    # tira do cliente a visita de verdade daquele dia.
    cur.execute("""SELECT 1 FROM fidelidade_checkins
                    WHERE id_cliente = %s AND data = %s AND parte = 0""",
                (id_cliente, hoje))
    return cur.fetchone() is not None


def _codigo(cur) -> str:
    for _ in range(20):
        c = "".join(secrets.choice(_ALFABETO) for _ in range(6))
        cur.execute("SELECT 1 FROM fidelidade_premios WHERE codigo = %s", (c,))
        if not cur.fetchone():
            return c
    raise HTTPException(status_code=500, detail="Não foi possível gerar o código do prêmio.")


def _validar_token(cfg: dict, token: str | None) -> None:
    if not token or not secrets.compare_digest(str(token), cfg["token"]):
        raise HTTPException(
            status_code=403,
            detail="Este QR code não vale mais. Peça à equipe o QR code atual.")


def _validar_dia(cur, id_unidade: int, cfg: dict, agora: datetime) -> None:
    """Hoje conta, e a casa está aberta — as regras baratas, iguais nos dois métodos."""
    hoje = agora.date()
    if hoje.isoweekday() not in cfg["dias_pontua"]:
        raise HTTPException(
            status_code=409,
            detail=f"As visitas contam de {dias_em_texto(cfg['dias_pontua'])}. Hoje não conta.")
    if cfg["so_no_horario"]:
        dia = agenda.janelas(cur, id_unidade, hoje, hoje)[hoje]
        janela = dia["janela"]
        if not dia["aberta"] or not (janela["abre"] <= agora.time() <= janela["fecha"]):
            raise HTTPException(
                status_code=409,
                detail="A visita vale com a casa aberta — faça durante a visita.")


def _pode_pontuar_hoje(cur, id_cliente: int, hoje: date) -> None:
    """Uma visita por dia, e a visita do prêmio não conta — nos dois métodos."""
    # 🔑 **A visita do prêmio não conta carimbo** (pedido do dono, 24/09/2026: *"no
    # próximo é grátis e não vale o carimbo"*). Prêmio já entregue hoje → hoje não pontua.
    # O caso inverso (check-in feito ANTES de pedir o prêmio) é desfeito em `entregar`.
    if _usou_premio_hoje(cur, id_cliente, hoje):
        raise HTTPException(
            status_code=409,
            detail="Hoje você usou seu prêmio — a visita do prêmio não conta carimbo. "
                   "O cartão novo começa na próxima visita!")
    if _ja_fez_hoje(cur, id_cliente, hoje):
        raise HTTPException(status_code=409,
                            detail="Sua visita de hoje já está marcada. Volte num próximo dia!")


def _registrar_visita(cur, id_unidade: int, id_cliente: int, hoje: date, selos: int,
                      distancia: int | None, cfg: dict, origem: str = "QRCODE") -> list[dict]:
    """Grava a visita de hoje com `selos` e fecha quantos cartões ela completar.

    ⚠️ **Trava por CLIENTE** (`pg_advisory_xact_lock`): duas abas marcando a visita que
    completa o cartão ao mesmo tempo gerariam dois prêmios.
    """
    cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", (910, id_cliente))
    _pode_pontuar_hoje(cur, id_cliente, hoje)
    cur.execute(
        """INSERT INTO fidelidade_checkins (id_cliente, id_unidade, data, distancia_m, selos,
                                           origem)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON CONFLICT (id_cliente, data, parte) DO NOTHING RETURNING id""",
        (id_cliente, id_unidade, hoje, distancia, selos, origem),
    )
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=409,
                            detail="Sua visita de hoje já está marcada. Volte num próximo dia!")
    cfg["_id_checkin"] = linha["id"]
    return _fechar_cartoes(cur, id_unidade, id_cliente, hoje, cfg)


def _fechar_cartoes(cur, id_unidade: int, id_cliente: int, hoje: date,
                    cfg: dict) -> list[dict]:
    """Enquanto os selos abertos cobrirem um cartão, fecha um cartão — e emite o prêmio.

    🔑 **A sobra passa para o cartão seguinte** (097): a visita de 3 selos que completa um
    cartão com 1 é repartida — 1 vai para o prêmio, 2 ficam numa linha `parte` nova do
    mesmo dia. As MAIS ANTIGAS fecham primeiro.
    """
    premios = []
    meta = int(cfg["visitas"])
    while True:
        cur.execute(
            """SELECT id, data, parte, selos FROM fidelidade_checkins
                WHERE id_cliente = %s AND id_premio IS NULL ORDER BY data, parte, id""",
            (id_cliente,),
        )
        abertas = [dict(r) for r in cur.fetchall()]
        if sum(int(a["selos"]) for a in abertas) < meta:
            return premios
        usadas, falta = [], meta
        for a in abertas:
            if falta <= 0:
                break
            if int(a["selos"]) > falta:
                # Reparte: o que sobra desta visita vai para uma parte nova do mesmo dia.
                cur.execute(
                    """SELECT coalesce(max(parte), 0) + 1 AS proxima FROM fidelidade_checkins
                        WHERE id_cliente = %s AND data = %s""",
                    (id_cliente, a["data"]),
                )
                proxima = cur.fetchone()["proxima"]
                cur.execute(
                    """INSERT INTO fidelidade_checkins (id_cliente, id_unidade, data, selos, parte,
                                                       origem, motivo, concedido_por)
                       SELECT id_cliente, id_unidade, data, %s, %s, origem, motivo, concedido_por
                         FROM fidelidade_checkins WHERE id = %s""",
                    (int(a["selos"]) - falta, proxima, a["id"]),
                )
                cur.execute("UPDATE fidelidade_checkins SET selos = %s WHERE id = %s",
                            (falta, a["id"]))
                falta = 0
            else:
                falta -= int(a["selos"])
            usadas.append(a["id"])

        codigo = _codigo(cur)
        vence = hoje + timedelta(days=cfg["validade_dias"])
        # 🔑 **"A cada 10, no próximo é grátis"** (pedido do dono, 24/09/2026): o prêmio
        # do cartão completado hoje vale a partir do DIA SEGUINTE — a próxima visita.
        vale_de = hoje + timedelta(days=1)
        cur.execute(
            """INSERT INTO fidelidade_premios (id_cliente, id_unidade, codigo, premio, visitas,
                                               dias_consumo, vence_em, vale_de)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (id_cliente, id_unidade, codigo, cfg["premio"], meta,
             cfg["dias_consumo"], vence, vale_de),
        )
        id_premio = cur.fetchone()["id"]
        cur.execute("UPDATE fidelidade_checkins SET id_premio = %s WHERE id = ANY(%s)",
                    (id_premio, usadas))
        premios.append({"codigo": codigo, "premio": cfg["premio"], "vence_em": vence.isoformat(),
                        "vale_de": vale_de.isoformat(),
                        "consumo": dias_em_texto(cfg["dias_consumo"])})
        # 🔑 WhatsApp (099): "você ganhou", se o aviso estiver ligado na loja.
        from services import whatsapp
        whatsapp.premio_ganho(cur, id_unidade, id_cliente, premios[-1])


def _resposta(cur, id_cliente: int, premios: list[dict]) -> dict:
    return {"premio_novo": premios[-1] if premios else None, "premios_novos": premios,
            **cartao(cur, id_cliente)}


def checkin(cur, id_unidade: int, id_cliente: int, token: str,
            agora: datetime | None = None, posicao: dict | None = None) -> dict:
    """O QR da MESA: marca a visita de hoje (1 selo) — e fecha o cartão se completar."""
    if not ligada(cur, id_unidade):
        raise HTTPException(status_code=404, detail="Esta casa não tem programa de fidelidade.")
    cfg = config(cur)
    _validar_token(cfg, token)
    if cfg["metodo"] != "QRCODE_MESA":
        # ⚠️ Com o código do caixa (097), o QR sozinho não conta: é o atendente que
        # confirma a visita. Aceitar aqui seria um atalho em volta dele.
        raise HTTPException(
            status_code=409,
            detail="Nesta casa a visita se confirma com o código que o caixa passa.")
    agora = agora or agora_da_casa().replace(tzinfo=None)
    _validar_dia(cur, id_unidade, cfg, agora)
    # Por último, depois das regras baratas: a mensagem de "dia que não conta" é mais
    # útil que a de distância, e não depende de permissão nenhuma.
    distancia = conferir_local(cur, id_unidade, cfg, posicao)
    premios = _registrar_visita(cur, id_unidade, id_cliente, agora.date(), 1, distancia, cfg)
    return _resposta(cur, id_cliente, premios)


# ------------------------------------------------------------ código do caixa (097)
# 🔑 **Pedido do dono (27/09/2026):** *"no caixa tem um QR code, o cliente lê e aparece uma
# tela aguardando um código. Na tela do nosso sistema aparecem os códigos e clientes; o
# usuário passa o código para o cliente confirmar a visita … e informa a quantidade de
# selos, por padrão 1."*
# ⚠️ **O código NUNCA sai para o celular** — só para a tela do caixa. É ele que prova que
# alguém da casa viu o cliente.

TENTATIVAS_MAXIMAS = 5


def _vencer_pedidos(cur, id_unidade: int | None = None) -> None:
    cur.execute(
        """UPDATE fidelidade_solicitacoes SET status = 'VENCIDA'
            WHERE status = 'PENDENTE' AND expira_em < now()
              AND (%s::int IS NULL OR id_unidade = %s)""",
        (id_unidade, id_unidade),
    )


def _codigo_do_caixa(cur, id_unidade: int) -> str:
    """4 algarismos — o atendente FALA o código; letra e zero à esquerda viram dúvida."""
    for _ in range(50):
        c = str(secrets.randbelow(9000) + 1000)
        cur.execute(
            """SELECT 1 FROM fidelidade_solicitacoes
                WHERE id_unidade = %s AND status = 'PENDENTE' AND codigo = %s""",
            (id_unidade, c),
        )
        if not cur.fetchone():
            return c
    raise HTTPException(status_code=503, detail="Muitos pedidos ao mesmo tempo. Tente de novo.")


def solicitar(cur, id_unidade: int, id_cliente: int, token: str,
              agora: datetime | None = None) -> dict:
    """O cliente leu o QR do caixa: nasce (ou volta) o pedido de código dele.

    ⚠️ Ler de novo devolve o MESMO pedido enquanto ele vale — um por cliente, garantido
    pelo índice único parcial.
    """
    if not ligada(cur, id_unidade):
        raise HTTPException(status_code=404, detail="Esta casa não tem programa de fidelidade.")
    cfg = config(cur)
    _validar_token(cfg, token)
    if cfg["metodo"] != "CODIGO_CAIXA":
        raise HTTPException(status_code=409,
                            detail="Nesta casa a visita se marca pelo QR code da mesa.")
    agora = agora or agora_da_casa().replace(tzinfo=None)
    _validar_dia(cur, id_unidade, cfg, agora)
    _pode_pontuar_hoje(cur, id_cliente, agora.date())
    _vencer_pedidos(cur, id_unidade)
    cur.execute(
        """SELECT id, id_unidade, expira_em, criada_em FROM fidelidade_solicitacoes
            WHERE id_cliente = %s AND status = 'PENDENTE'""",
        (id_cliente,),
    )
    pedido = cur.fetchone()
    if pedido and pedido["id_unidade"] != id_unidade:
        # Pediu na outra loja e veio para esta: o de lá não serve aqui.
        cur.execute("UPDATE fidelidade_solicitacoes SET status = 'CANCELADA' WHERE id = %s",
                    (pedido["id"],))
        pedido = None
    if not pedido:
        cur.execute(
            """INSERT INTO fidelidade_solicitacoes (id_cliente, id_unidade, codigo, expira_em)
               VALUES (%s, %s, %s, now() + make_interval(mins => %s))
               RETURNING id, expira_em, criada_em""",
            (id_cliente, id_unidade, _codigo_do_caixa(cur, id_unidade),
             int(cfg["codigo_validade_min"])),
        )
        pedido = cur.fetchone()
    return {"status": "PENDENTE", "expira_em": pedido["expira_em"].isoformat(),
            "mensagem": "Peça o código no caixa e digite aqui."}


def confirmar(cur, id_unidade: int, id_cliente: int, codigo: str,
              agora: datetime | None = None) -> tuple[dict | None, str | None]:
    """O cliente digitou o código. Devolve `(resposta, None)` ou `(None, erro)`.

    ⚠️ **O erro VOLTA em vez de estourar**: a tentativa errada precisa ficar gravada (é
    ela que cancela o pedido na quinta), e uma exceção desfaria a gravação junto.
    """
    agora = agora or agora_da_casa().replace(tzinfo=None)
    cur.execute(
        """SELECT id, codigo, selos, expira_em, tentativas FROM fidelidade_solicitacoes
            WHERE id_cliente = %s AND id_unidade = %s AND status = 'PENDENTE'
            FOR UPDATE""",
        (id_cliente, id_unidade),
    )
    pedido = cur.fetchone()
    if not pedido:
        return None, "Não há pedido de código em aberto. Leia o QR code do caixa de novo."
    cur.execute("SELECT now() > %s AS vencido", (pedido["expira_em"],))
    if cur.fetchone()["vencido"]:
        cur.execute("UPDATE fidelidade_solicitacoes SET status = 'VENCIDA' WHERE id = %s",
                    (pedido["id"],))
        return None, "O código venceu. Leia o QR code do caixa de novo."
    if (codigo or "").strip() != pedido["codigo"]:
        tentativas = int(pedido["tentativas"]) + 1
        cancelou = tentativas >= TENTATIVAS_MAXIMAS
        cur.execute(
            """UPDATE fidelidade_solicitacoes
                  SET tentativas = %s, status = CASE WHEN %s THEN 'CANCELADA' ELSE status END
                WHERE id = %s""",
            (tentativas, cancelou, pedido["id"]),
        )
        if cancelou:
            return None, "Código errado muitas vezes. Leia o QR code do caixa de novo."
        return None, "O código não confere. Confira com o caixa e digite de novo."

    cfg = config(cur)
    _validar_dia(cur, id_unidade, cfg, agora)
    premios = _registrar_visita(cur, id_unidade, id_cliente, agora.date(),
                                int(pedido["selos"]), None, cfg, origem="CODIGO")
    cur.execute(
        """UPDATE fidelidade_solicitacoes
              SET status = 'CONFIRMADA', confirmada_em = now(), id_checkin = %s
            WHERE id = %s""",
        (cfg.get("_id_checkin"), pedido["id"]),
    )
    return {"selos": int(pedido["selos"]), **_resposta(cur, id_cliente, premios)}, None


def pedidos_do_caixa(cur, id_unidade: int) -> dict:
    """A tela do caixa: os pedidos pendentes (com o código) e os confirmados de hoje."""
    _vencer_pedidos(cur, id_unidade)
    cur.execute(
        """SELECT s.id, s.codigo, s.selos, s.status, s.criada_em, s.expira_em,
                  s.confirmada_em, s.tentativas, c.nome, c.telefone
             FROM fidelidade_solicitacoes s JOIN reserva_clientes c ON c.id = s.id_cliente
            WHERE s.id_unidade = %s
              AND (s.status = 'PENDENTE'
                   OR (s.status = 'CONFIRMADA'
                       AND (s.confirmada_em AT TIME ZONE 'America/Sao_Paulo')::date
                           = (now() AT TIME ZONE 'America/Sao_Paulo')::date))
            ORDER BY (s.status = 'PENDENTE') DESC, s.criada_em DESC
            LIMIT 60""",
        (id_unidade,),
    )
    linhas = []
    for r in cur.fetchall():
        r = dict(r)
        for campo in ("criada_em", "expira_em", "confirmada_em"):
            r[campo] = r[campo].isoformat() if r[campo] else None
        linhas.append(r)
    return {"pendentes": [x for x in linhas if x["status"] == "PENDENTE"],
            "confirmados": [x for x in linhas if x["status"] == "CONFIRMADA"]}


def _pedido_pendente(cur, id_unidade: int, id_pedido: int) -> dict:
    _vencer_pedidos(cur, id_unidade)
    cur.execute(
        """SELECT id, status FROM fidelidade_solicitacoes
            WHERE id = %s AND id_unidade = %s FOR UPDATE""",
        (id_pedido, id_unidade),
    )
    p = cur.fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="Pedido de código não encontrado.")
    if p["status"] != "PENDENTE":
        raise HTTPException(status_code=409,
                            detail="Este pedido não está mais aguardando o código.")
    return dict(p)


def definir_selos(cur, id_unidade: int, id_pedido: int, selos: int,
                  id_usuario: int | None) -> None:
    """O caixa diz quantos selos esta visita vale — antes de o cliente digitar."""
    _pedido_pendente(cur, id_unidade, id_pedido)
    cur.execute("UPDATE fidelidade_solicitacoes SET selos = %s, atendido_por = %s WHERE id = %s",
                (selos, id_usuario, id_pedido))


def cancelar_pedido(cur, id_unidade: int, id_pedido: int, id_usuario: int | None) -> None:
    _pedido_pendente(cur, id_unidade, id_pedido)
    cur.execute(
        """UPDATE fidelidade_solicitacoes SET status = 'CANCELADA', atendido_por = %s
            WHERE id = %s""",
        (id_usuario, id_pedido),
    )


def _usou_premio_hoje(cur, id_cliente: int, hoje: date) -> bool:
    cur.execute(
        """SELECT 1 FROM fidelidade_premios
            WHERE id_cliente = %s
              AND (usado_em AT TIME ZONE 'America/Sao_Paulo')::date = %s""",
        (id_cliente, hoje),
    )
    return cur.fetchone() is not None


def entregar(cur, id_unidade: int, codigo: str, id_usuario: int | None) -> dict:
    """O balcão entrega o prêmio. Uma vez, da próxima visita em diante, num dia de
    consumo, antes de vencer — e o carimbo da visita do prêmio sai."""
    cur.execute(
        """SELECT p.id, p.id_cliente, p.premio, p.vence_em, p.vale_de, p.dias_consumo,
                  p.usado_em, c.nome
             FROM fidelidade_premios p JOIN reserva_clientes c ON c.id = p.id_cliente
            WHERE p.codigo = %s FOR UPDATE OF p""",
        ((codigo or "").strip().upper(),),
    )
    p = cur.fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="Código de prêmio não encontrado.")
    hoje = agora_da_casa().date()
    if p["usado_em"]:
        raise HTTPException(
            status_code=409,
            detail=f"Este prêmio já foi entregue em {p['usado_em']:%d/%m/%Y}.")
    if p["vence_em"] < hoje:
        raise HTTPException(status_code=409,
                            detail=f"Este prêmio venceu em {p['vence_em']:%d/%m/%Y}.")
    if hoje < p["vale_de"]:
        raise HTTPException(
            status_code=409,
            detail=f"Este prêmio vale a partir da próxima visita ({p['vale_de']:%d/%m}) — "
                   "o cartão foi completado hoje.")
    if hoje.isoweekday() not in p["dias_consumo"]:
        raise HTTPException(
            status_code=409,
            detail=f"Este prêmio vale de {dias_em_texto(p['dias_consumo'])} — hoje não.")
    cur.execute(
        """UPDATE fidelidade_premios SET usado_em = now(), usado_por = %s, id_unidade_uso = %s
            WHERE id = %s""",
        (id_usuario, id_unidade, p["id"]),
    )
    # 🔑 **A visita do prêmio não conta carimbo**: se o cliente leu o QR ao chegar e só
    # depois pediu o prêmio, o check-in de hoje sai. ⚠️ Só o que está ABERTO (sem
    # prêmio): um check-in que fechou outro cartão hoje já virou prêmio e fica.
    cur.execute(
        """DELETE FROM fidelidade_checkins
            WHERE id_cliente = %s AND data = %s AND id_premio IS NULL RETURNING id""",
        (p["id_cliente"], hoje),
    )
    tirou = cur.fetchone() is not None
    return {"id": p["id"], "premio": p["premio"], "cliente": p["nome"],
            "carimbo_retirado": tirou}


def consulta_premios(status: str | None, busca: str | None) -> tuple[str, list]:
    """Os prêmios, para o grid do balcão — SEM `LIMIT` (quem corta é `pagina`)."""
    onde, params = [], []
    if status == "DISPONIVEL":
        onde.append("p.usado_em IS NULL AND p.vence_em >= (now() AT TIME ZONE 'America/Sao_Paulo')::date")
    elif status == "USADO":
        onde.append("p.usado_em IS NOT NULL")
    elif status == "VENCIDO":
        onde.append("p.usado_em IS NULL AND p.vence_em < (now() AT TIME ZONE 'America/Sao_Paulo')::date")
    texto = (busca or "").strip()
    if texto:
        digitos = "".join(ch for ch in texto if ch.isdigit())
        filtro = ["c.nome ILIKE %s", "p.codigo = upper(%s)"]
        params += [f"%{texto}%", texto]
        if len(digitos) >= 3:
            filtro.append("c.telefone LIKE %s")
            params.append(f"%{digitos}%")
        onde.append("(" + " OR ".join(filtro) + ")")
    sql = f"""
        SELECT p.id, p.codigo, p.premio, p.visitas, p.emitido_em, p.vence_em, p.vale_de,
               p.usado_em,
               p.dias_consumo, c.nome, c.telefone,
               coalesce(u.apelido, u.nome) AS loja, coalesce(uu.apelido, uu.nome) AS loja_uso,
               us.nome AS entregue_por
          FROM fidelidade_premios p
          JOIN reserva_clientes c ON c.id = p.id_cliente
          LEFT JOIN unidades u ON u.id = p.id_unidade
          LEFT JOIN unidades uu ON uu.id = p.id_unidade_uso
          LEFT JOIN usuarios us ON us.id = p.usado_por
         {"WHERE " + " AND ".join(onde) if onde else ""}
         ORDER BY (p.usado_em IS NULL) DESC, p.emitido_em DESC, p.id DESC"""
    return sql, params


def linha_do_premio(x: dict, hoje: date) -> dict:
    x = dict(x)
    x["status"] = _status(x, hoje)
    x["pode_hoje"] = (x["status"] == "DISPONIVEL" and x["vale_de"] <= hoje
                      and hoje.isoweekday() in x["dias_consumo"])
    x["consumo"] = dias_em_texto(x.pop("dias_consumo"))
    for campo in ("emitido_em", "usado_em", "vence_em", "vale_de"):
        x[campo] = x[campo].isoformat() if x[campo] else None
    return x


# ---------------------------------------------------------------- o painel (098)
# 🔑 **Pedido do dono (27/09/2026):** *"uma tela para verificar os selos, os resgates, a
# validade, ajustar o vencimento, dar selos, visualizar tudo que diz respeito ao plano de
# fidelidade em uma só tela."* O programa é da REDE: o painel também.

def resumo(cur) -> dict:
    """Os números do programa, para o topo do painel."""
    cur.execute(
        """SELECT
             (SELECT count(DISTINCT id_cliente) FROM fidelidade_checkins) AS participantes,
             (SELECT coalesce(sum(selos), 0) FROM fidelidade_checkins
               WHERE id_premio IS NULL) AS selos_abertos,
             (SELECT count(*) FROM fidelidade_premios
               WHERE usado_em IS NULL AND vence_em >= %(hoje)s) AS premios_disponiveis,
             (SELECT count(*) FROM fidelidade_premios
               WHERE usado_em IS NULL AND vence_em BETWEEN %(hoje)s AND %(semana)s)
                 AS vencendo_7_dias,
             (SELECT count(*) FROM fidelidade_premios
               WHERE usado_em IS NULL AND vence_em < %(hoje)s) AS premios_vencidos,
             (SELECT count(*) FROM fidelidade_premios
               WHERE (usado_em AT TIME ZONE 'America/Sao_Paulo')::date >= %(mes)s)
                 AS entregues_no_mes,
             (SELECT count(*) FROM fidelidade_checkins
               WHERE data = %(hoje)s AND parte = 0) AS visitas_hoje""",
        {"hoje": _hoje(), "semana": _hoje() + timedelta(days=7),
         "mes": _hoje().replace(day=1)},
    )
    return {k: int(v or 0) for k, v in dict(cur.fetchone()).items()}


def _hoje() -> date:
    return agora_da_casa().date()


def consulta_participantes(busca: str | None, filtro: str | None) -> tuple[str, list]:
    """Quem participa (tem selo ou prêmio), para o grid do painel — SEM `LIMIT`."""
    onde, params = [], []
    texto = (busca or "").strip()
    if texto:
        digitos = "".join(ch for ch in texto if ch.isdigit())
        if len(digitos) >= 3:
            onde.append("(c.nome ILIKE %s OR c.telefone LIKE %s)")
            params += [f"%{texto}%", f"%{digitos}%"]
        else:
            onde.append("c.nome ILIKE %s")
            params.append(f"%{texto}%")
    hoje = _hoje()
    if filtro == "com_premio":
        onde.append("x.disponiveis > 0")
    elif filtro == "vencendo":
        onde.append("x.proximo_vencimento BETWEEN %s AND %s")
        params += [hoje, hoje + timedelta(days=7)]
    elif filtro == "vencidos":
        onde.append("x.vencidos > 0")
    sql = f"""
        SELECT * FROM (
          SELECT c.id, c.nome, c.telefone,
                 (SELECT coalesce(sum(f.selos), 0) FROM fidelidade_checkins f
                   WHERE f.id_cliente = c.id AND f.id_premio IS NULL) AS no_cartao,
                 (SELECT count(*) FROM fidelidade_checkins f
                   WHERE f.id_cliente = c.id AND f.parte = 0) AS visitas,
                 (SELECT max(f.data) FROM fidelidade_checkins f
                   WHERE f.id_cliente = c.id AND f.parte = 0) AS ultima_visita,
                 (SELECT count(*) FROM fidelidade_premios p
                   WHERE p.id_cliente = c.id AND p.usado_em IS NULL
                     AND p.vence_em >= '{hoje.isoformat()}') AS disponiveis,
                 (SELECT count(*) FROM fidelidade_premios p
                   WHERE p.id_cliente = c.id AND p.usado_em IS NULL
                     AND p.vence_em < '{hoje.isoformat()}') AS vencidos,
                 (SELECT count(*) FROM fidelidade_premios p
                   WHERE p.id_cliente = c.id AND p.usado_em IS NOT NULL) AS usados,
                 (SELECT min(p.vence_em) FROM fidelidade_premios p
                   WHERE p.id_cliente = c.id AND p.usado_em IS NULL
                     AND p.vence_em >= '{hoje.isoformat()}') AS proximo_vencimento
            FROM reserva_clientes c
           WHERE EXISTS (SELECT 1 FROM fidelidade_checkins f WHERE f.id_cliente = c.id)
              OR EXISTS (SELECT 1 FROM fidelidade_premios p WHERE p.id_cliente = c.id)
        ) x
        JOIN reserva_clientes c ON c.id = x.id
        {"WHERE " + " AND ".join(onde) if onde else ""}
        ORDER BY x.ultima_visita DESC NULLS LAST, lower(x.nome)"""
    return sql, params


def ficha(cur, id_cliente: int) -> dict:
    """Tudo de um cliente no programa: cartão, visitas, prêmios e pedidos de código."""
    cur.execute("SELECT id, nome, telefone, termo_versao FROM reserva_clientes WHERE id = %s",
                (id_cliente,))
    cliente = cur.fetchone()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    hoje = _hoje()
    cur.execute(
        """SELECT f.id, f.data, f.parte, f.selos, f.origem, f.motivo, f.distancia_m,
                  f.criado_em, f.id_premio, p.codigo AS premio_codigo,
                  coalesce(u.apelido, u.nome) AS loja, us.nome AS concedido_por
             FROM fidelidade_checkins f
             LEFT JOIN fidelidade_premios p ON p.id = f.id_premio
             LEFT JOIN unidades u ON u.id = f.id_unidade
             LEFT JOIN usuarios us ON us.id = f.concedido_por
            WHERE f.id_cliente = %s
            ORDER BY f.data DESC, f.parte DESC, f.id DESC
            LIMIT 200""",
        (id_cliente,),
    )
    visitas = []
    for v in cur.fetchall():
        v = dict(v)
        v["data"] = v["data"].isoformat()
        v["criado_em"] = v["criado_em"].isoformat() if v["criado_em"] else None
        visitas.append(v)
    cur.execute(
        """SELECT p.id, p.codigo, p.premio, p.visitas, p.emitido_em, p.vale_de, p.vence_em,
                  p.vencimento_original, p.usado_em, p.dias_consumo,
                  coalesce(u.apelido, u.nome) AS loja, coalesce(uu.apelido, uu.nome) AS loja_uso,
                  us.nome AS entregue_por, c.nome, c.telefone
             FROM fidelidade_premios p
             JOIN reserva_clientes c ON c.id = p.id_cliente
             LEFT JOIN unidades u ON u.id = p.id_unidade
             LEFT JOIN unidades uu ON uu.id = p.id_unidade_uso
             LEFT JOIN usuarios us ON us.id = p.usado_por
            WHERE p.id_cliente = %s
            ORDER BY p.emitido_em DESC""",
        (id_cliente,),
    )
    premios = []
    for p in cur.fetchall():
        p = linha_do_premio(dict(p), hoje)
        p["vencimento_original"] = (p["vencimento_original"].isoformat()
                                    if p["vencimento_original"] else None)
        premios.append(p)
    cur.execute(
        """SELECT s.id, s.status, s.selos, s.criada_em, s.confirmada_em, s.tentativas,
                  coalesce(u.apelido, u.nome) AS loja
             FROM fidelidade_solicitacoes s LEFT JOIN unidades u ON u.id = s.id_unidade
            WHERE s.id_cliente = %s ORDER BY s.criada_em DESC LIMIT 20""",
        (id_cliente,),
    )
    pedidos = []
    for r in cur.fetchall():
        r = dict(r)
        for campo in ("criada_em", "confirmada_em"):
            r[campo] = r[campo].isoformat() if r[campo] else None
        pedidos.append(r)
    return {"cliente": dict(cliente), "cartao": cartao(cur, id_cliente), "visitas": visitas,
            "premios": premios, "pedidos": pedidos}


def dar_selos(cur, id_unidade: int, id_cliente: int, selos: int, motivo: str,
              id_usuario: int | None) -> list[dict]:
    """A gerência dá selos (cortesia, correção). Fecha cartões como uma visita fecharia.

    ⚠️ **Não é a visita do dia**: entra numa `parte` acima de zero, e o cliente ainda
    pode fazer a visita de verdade hoje. ⚠️ Sem regra de dia/horário/local: quem dá é a
    casa, de propósito — e fica gravado quem deu e por quê.
    """
    cur.execute("SELECT 1 FROM reserva_clientes WHERE id = %s", (id_cliente,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    cfg = config(cur)
    hoje = _hoje()
    cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", (910, id_cliente))
    cur.execute(
        """SELECT greatest(coalesce(max(parte), 0), 0) + 1 AS parte FROM fidelidade_checkins
            WHERE id_cliente = %s AND data = %s""",
        (id_cliente, hoje),
    )
    parte = cur.fetchone()["parte"]
    cur.execute(
        """INSERT INTO fidelidade_checkins (id_cliente, id_unidade, data, selos, parte, origem,
                                           motivo, concedido_por)
           VALUES (%s, %s, %s, %s, %s, 'MANUAL', %s, %s)""",
        (id_cliente, id_unidade, hoje, selos, parte, motivo.strip(), id_usuario),
    )
    return _fechar_cartoes(cur, id_unidade, id_cliente, hoje, cfg)


def retirar_selo(cur, id_checkin: int) -> dict:
    """Tira um lançamento de selos ainda ABERTO (engano). ⚠️ O que virou prêmio não sai."""
    cur.execute(
        """SELECT id, id_cliente, data, selos, origem, id_premio FROM fidelidade_checkins
            WHERE id = %s FOR UPDATE""",
        (id_checkin,),
    )
    v = cur.fetchone()
    if not v:
        raise HTTPException(status_code=404, detail="Lançamento de selos não encontrado.")
    if v["id_premio"]:
        raise HTTPException(
            status_code=409,
            detail="Estes selos já viraram prêmio — não se tiram. Se foi engano, trate o prêmio.")
    cur.execute("UPDATE fidelidade_solicitacoes SET id_checkin = NULL WHERE id_checkin = %s",
                (id_checkin,))
    cur.execute("DELETE FROM fidelidade_checkins WHERE id = %s", (id_checkin,))
    return dict(v)


def ajustar_vencimento(cur, id_premio: int, vence_em: date) -> dict:
    """Muda a validade de um prêmio ainda não usado. Guarda a data original na 1ª mudança."""
    cur.execute(
        """SELECT id, codigo, vale_de, vence_em, usado_em FROM fidelidade_premios
            WHERE id = %s FOR UPDATE""",
        (id_premio,),
    )
    p = cur.fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="Prêmio não encontrado.")
    if p["usado_em"]:
        raise HTTPException(status_code=409, detail="Prêmio já entregue: a validade não importa mais.")
    if vence_em < p["vale_de"]:
        raise HTTPException(
            status_code=400,
            detail=f"O prêmio só começa a valer em {p['vale_de']:%d/%m/%Y}; vencer antes não faz sentido.")
    cur.execute(
        """UPDATE fidelidade_premios
              SET vencimento_original = coalesce(vencimento_original, vence_em), vence_em = %s
            WHERE id = %s""",
        (vence_em, id_premio),
    )
    return {"codigo": p["codigo"], "antes": p["vence_em"].isoformat(), "depois": vence_em.isoformat()}
