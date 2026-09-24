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
                  so_no_horario, token, site_url FROM fidelidade_config WHERE id = 1""")
    c = dict(cur.fetchone())
    c["dias_pontua"] = sorted(c["dias_pontua"])
    c["dias_consumo"] = sorted(c["dias_consumo"])
    return c


def salvar(cur, body) -> dict:
    cur.execute(
        """UPDATE fidelidade_config
              SET visitas = %s, premio = %s, validade_dias = %s, dias_pontua = %s,
                  dias_consumo = %s, so_no_horario = %s, site_url = %s,
                  atualizado_em = now()
            WHERE id = 1""",
        (body.visitas, body.premio.strip(), body.validade_dias, sorted(set(body.dias_pontua)),
         sorted(set(body.dias_consumo)), body.so_no_horario,
         body.site_url.strip().rstrip("/")),
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
    }


def _status(p: dict, hoje: date) -> str:
    if p["usado_em"]:
        return "USADO"
    return "VENCIDO" if p["vence_em"] < hoje else "DISPONIVEL"


def cartao(cur, id_cliente: int) -> dict:
    """O cartão do cliente: quantas visitas no atual, quanto falta e os prêmios."""
    cfg = config(cur)
    hoje = agora_da_casa().date()
    cur.execute(
        """SELECT data FROM fidelidade_checkins
            WHERE id_cliente = %s AND id_premio IS NULL ORDER BY data""",
        (id_cliente,),
    )
    abertas = [r["data"] for r in cur.fetchall()]
    cur.execute(
        """SELECT codigo, premio, vence_em, dias_consumo, emitido_em, usado_em
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
            "consumo": dias_em_texto(p["dias_consumo"]),
            "status": _status(p, hoje),
        })
    cur.execute("SELECT termo_versao FROM reserva_clientes WHERE id = %s", (id_cliente,))
    versao = (cur.fetchone() or {}).get("termo_versao")
    visitas = len(abertas)
    return {
        **regras(cfg),
        "no_cartao": visitas,
        # ⚠️ Nunca negativo: baixar `visitas` na configuração não pode dizer ao
        # cliente que faltam "-2" — o próximo check-in fecha o cartão.
        "faltam": max(cfg["visitas"] - visitas, 0),
        "datas": [d.isoformat() for d in abertas],
        "hoje_ja_fez": hoje in abertas or _ja_fez_hoje(cur, id_cliente, hoje),
        "premios": premios,
        # 🔑 LGPD: o termo em vigor cita a fidelidade; quem aceitou o anterior
        # aceita de novo antes do primeiro check-in.
        "precisa_termo": versao != termo.VERSAO,
    }


def _ja_fez_hoje(cur, id_cliente: int, hoje: date) -> bool:
    # O check-in de hoje pode já estar DENTRO de um prêmio (o que fechou o cartão).
    cur.execute("SELECT 1 FROM fidelidade_checkins WHERE id_cliente = %s AND data = %s",
                (id_cliente, hoje))
    return cur.fetchone() is not None


def _codigo(cur) -> str:
    for _ in range(20):
        c = "".join(secrets.choice(_ALFABETO) for _ in range(6))
        cur.execute("SELECT 1 FROM fidelidade_premios WHERE codigo = %s", (c,))
        if not cur.fetchone():
            return c
    raise HTTPException(status_code=500, detail="Não foi possível gerar o código do prêmio.")


def checkin(cur, id_unidade: int, id_cliente: int, token: str,
            agora: datetime | None = None) -> dict:
    """Marca a visita de hoje — e fecha o cartão se ela for a que faltava.

    ⚠️ **Trava por CLIENTE** (`pg_advisory_xact_lock`): duas abas fazendo o
    check-in que completa o cartão ao mesmo tempo gerariam dois prêmios.
    """
    if not ligada(cur, id_unidade):
        raise HTTPException(status_code=404, detail="Esta casa não tem programa de fidelidade.")
    cfg = config(cur)
    if not token or not secrets.compare_digest(str(token), cfg["token"]):
        raise HTTPException(
            status_code=403,
            detail="Este QR code não vale mais. Peça à equipe o QR code da mesa.")
    agora = agora or agora_da_casa().replace(tzinfo=None)
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
                detail="O check-in vale com a casa aberta — faça na mesa, durante a visita.")

    cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", (910, id_cliente))
    cur.execute(
        """INSERT INTO fidelidade_checkins (id_cliente, id_unidade, data)
           VALUES (%s, %s, %s) ON CONFLICT (id_cliente, data) DO NOTHING RETURNING id""",
        (id_cliente, id_unidade, hoje),
    )
    if not cur.fetchone():
        raise HTTPException(status_code=409,
                            detail="Você já fez o check-in de hoje. Volte num próximo dia!")

    cur.execute(
        """SELECT id FROM fidelidade_checkins WHERE id_cliente = %s AND id_premio IS NULL
            ORDER BY data, id""",
        (id_cliente,),
    )
    abertas = [r["id"] for r in cur.fetchall()]
    premio = None
    if len(abertas) >= cfg["visitas"]:
        codigo = _codigo(cur)
        vence = hoje + timedelta(days=cfg["validade_dias"])
        cur.execute(
            """INSERT INTO fidelidade_premios (id_cliente, id_unidade, codigo, premio, visitas,
                                               dias_consumo, vence_em)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (id_cliente, id_unidade, codigo, cfg["premio"], cfg["visitas"],
             cfg["dias_consumo"], vence),
        )
        id_premio = cur.fetchone()["id"]
        # As MAIS ANTIGAS fecham o cartão; o que sobrar (se a meta baixou) segue.
        cur.execute("UPDATE fidelidade_checkins SET id_premio = %s WHERE id = ANY(%s)",
                    (id_premio, abertas[:cfg["visitas"]]))
        premio = {"codigo": codigo, "premio": cfg["premio"], "vence_em": vence.isoformat(),
                  "consumo": dias_em_texto(cfg["dias_consumo"])}
    return {"premio_novo": premio, **cartao(cur, id_cliente)}


def entregar(cur, id_unidade: int, codigo: str, id_usuario: int | None) -> dict:
    """O balcão entrega o prêmio. Uma vez, num dia de consumo, antes de vencer."""
    cur.execute(
        """SELECT p.id, p.premio, p.vence_em, p.dias_consumo, p.usado_em, c.nome
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
    if hoje.isoweekday() not in p["dias_consumo"]:
        raise HTTPException(
            status_code=409,
            detail=f"Este prêmio vale de {dias_em_texto(p['dias_consumo'])} — hoje não.")
    cur.execute(
        """UPDATE fidelidade_premios SET usado_em = now(), usado_por = %s, id_unidade_uso = %s
            WHERE id = %s""",
        (id_usuario, id_unidade, p["id"]),
    )
    return {"id": p["id"], "premio": p["premio"], "cliente": p["nome"]}


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
        SELECT p.id, p.codigo, p.premio, p.visitas, p.emitido_em, p.vence_em, p.usado_em,
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
    x["pode_hoje"] = x["status"] == "DISPONIVEL" and hoje.isoweekday() in x["dias_consumo"]
    x["consumo"] = dias_em_texto(x.pop("dias_consumo"))
    for campo in ("emitido_em", "usado_em", "vence_em"):
        x[campo] = x[campo].isoformat() if x[campo] else None
    return x
