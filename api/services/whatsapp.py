"""Mensagens por WhatsApp — a API oficial da Meta (Cloud API), configurada por NÚMERO da loja.

🔑 **Pedido do dono (28/09/2026):** *"envio de mensagens via WhatsApp para clientes, como
reservas, confirmação de reserva, prêmios e outros assuntos, de forma configurável; e a
confirmação de presença via WhatsApp, recebendo a opção selecionada pelo cliente."* E:
*"API da Meta direto … numa aba nova dentro da loja: a loja faz toda a validação com a Meta e
só informa como vamos usar — fica configurável para outros clientes."*
Estudo em `docs/whatsapp-estudo.md`.

Como funciona:
1. Um fato acontece (reserva confirmada, prêmio ganho…) → `enfileirar` grava a mensagem em
   `whatsapp_mensagens`, se o aviso estiver ligado NAQUELA loja, com o número por onde sai
   (`_por_onde`: o do pedido → o do aviso → o principal, o primeiro conectado — 146).
2. O laço (`laco`) acorda a cada 30 s e envia o que venceu — o lembrete nasce agendado para
   X horas antes da reserva.
3. A Meta chama o webhook: entregue / lida / falhou, e os BOTÕES do lembrete ("Confirmo",
   "Preciso cancelar"), que viram a presença da reserva ou o cancelamento.

⚠️ **Mensagem que a casa inicia é SEMPRE um modelo aprovado pela Meta** (template): aqui só se
diz o NOME dele e as variáveis. O texto de cada aviso vai pronto para a loja submeter.
⚠️ **Modo simulado** (padrão, e sempre que faltar credencial): a mensagem vai para o
histórico marcada SIMULADA e não sai — o mesmo desenho do Omie. É o que permite testar tudo
antes de a conta na Meta ficar pronta.
"""

import asyncio
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta

import httpx
from fastapi import HTTPException

from database import get_cursor
from relogio import agora_da_casa
from services import erros, segredos

API_VERSAO_PADRAO = "v21.0"
INTERVALO_DE_CHECAGEM = 30          # segundos
TENTATIVAS_MAXIMAS = 3

# ---------------------------------------------------------------- o catálogo de avisos
# 🔑 **O texto de cada aviso vai PRONTO** para a loja cadastrar o modelo na Meta: {{n}} são
# as variáveis, na ordem de `variaveis`. `botoes` só existem no lembrete — é por eles que o
# cliente confirma ou cancela. `antecedencia`: horas (lembrete) ou dias (prêmio vencendo).
EVENTOS: dict[str, dict] = {
    "RESERVA_RECEBIDA": {
        "nome": "Reserva recebida (aguardando a casa)",
        "quando": "Ao marcar pelo site, quando a casa confirma à mão",
        "modelo": "reserva_recebida",
        "texto": "Olá, {{1}}! Recebemos seu pedido de reserva no {{2}} para {{3}} às {{4}}, "
                 "{{5}} pessoa(s). Assim que a casa confirmar, avisamos por aqui.",
        "variaveis": ["nome", "casa", "data", "hora", "pessoas"],
        "categoria": "Utilidade",
    },
    "RESERVA_CONFIRMADA": {
        "nome": "Reserva confirmada",
        "quando": "Ao confirmar a reserva (na hora ou pela casa)",
        "modelo": "reserva_confirmada",
        "texto": "Olá, {{1}}! Sua reserva no {{2}} está confirmada para {{3}} às {{4}}, "
                 "{{5}} pessoa(s). Até lá!",
        "variaveis": ["nome", "casa", "data", "hora", "pessoas"],
        "categoria": "Utilidade",
    },
    "RESERVA_LEMBRETE": {
        "nome": "Lembrete com confirmação de presença",
        "quando": "Horas antes da reserva",
        "modelo": "reserva_lembrete",
        "texto": "Olá, {{1}}! Lembrete da sua reserva no {{2}}: {{3}} às {{4}}, {{5}} "
                 "pessoa(s). Você confirma sua presença?",
        "variaveis": ["nome", "casa", "data", "hora", "pessoas"],
        "botoes": ["Confirmo", "Preciso cancelar"],
        "categoria": "Utilidade",
        "antecedencia": 3, "unidade": "horas antes",
    },
    "RESERVA_CANCELADA": {
        "nome": "Reserva cancelada pela casa",
        "quando": "Quando a casa cancela a reserva",
        "modelo": "reserva_cancelada",
        "texto": "Olá, {{1}}. Sua reserva no {{2}} para {{3}} às {{4}} foi cancelada. Se "
                 "precisar, fale com a gente por aqui.",
        "variaveis": ["nome", "casa", "data", "hora"],
        "categoria": "Utilidade",
    },
    "PREMIO_GANHO": {
        "nome": "Prêmio da fidelidade conquistado",
        "quando": "Ao completar o cartão fidelidade",
        "modelo": "fidelidade_premio",
        "texto": "Parabéns, {{1}}! Você completou seu cartão fidelidade no {{2}} e ganhou: "
                 "{{3}}. Vale a partir da sua próxima visita, até {{4}}. Código: {{5}}.",
        "variaveis": ["nome", "casa", "premio", "vence", "codigo"],
        "categoria": "Utilidade",
    },
    "PREMIO_VENCENDO": {
        "nome": "Prêmio da fidelidade vencendo",
        "quando": "Dias antes de o prêmio vencer",
        "modelo": "fidelidade_vencendo",
        "texto": "Olá, {{1}}! Seu prêmio {{2}} no {{3}} vence em {{4}}. Código: {{5}}. "
                 "Esperamos você!",
        "variaveis": ["nome", "premio", "casa", "vence", "codigo"],
        "categoria": "Utilidade",
        "antecedencia": 3, "unidade": "dias antes",
    },
    # 🔑 Pedidos pelo catálogo (101): por enquanto só o "confirmado" (decisão do dono).
    "PEDIDO_CONFIRMADO": {
        "nome": "Pedido do site confirmado",
        "quando": "Quando a casa confirma um pedido feito pelo catálogo",
        "modelo": "pedido_confirmado",
        "texto": "Olá, {{1}}! Seu pedido nº {{2}} no {{3}} está confirmado: {{4}}, "
                 "{{5}}. Total: R$ {{6}}. Obrigado!",
        "variaveis": ["nome", "numero", "casa", "retirada/entrega", "quando", "total"],
        "categoria": "Utilidade",
    },
    "ANIVERSARIO": {
        "nome": "Aniversário do cliente",
        "quando": "No dia do aniversário (quem não pediu para parar)",
        "modelo": "aniversario",
        "texto": "Feliz aniversário, {{1}}! O {{2}} deseja um dia especial. Venha comemorar "
                 "com a gente!",
        "variaveis": ["nome", "casa"],
        "categoria": "Marketing",
    },
}
# As respostas ao botão: texto livre, dentro da janela de 24 h que o toque do cliente abre.
RESPOSTA = "RESPOSTA"
PALAVRAS_DE_SAIDA = {"PARAR", "SAIR", "STOP", "CANCELAR MENSAGENS"}


# ---------------------------------------------------------------- configuração
# 🔑 **A conexão é de cada NÚMERO** (146, pedido do dono, 30/10/2026): cada número da loja
# (`unidade_whatsapps`) pode ter a dele — ou nenhuma, e aí só serve para o cliente chamar.
_CAMPOS = """id, id_unidade, rotulo, numero, principal, conectado, modo, phone_number_id,
             waba_id, api_versao, verify_token, credenciais, conta_do_principal,
             ultimo_status, ultima_mensagem"""


def _conexoes(cur, id_unidade: int) -> list[dict]:
    """Os números da loja com a conexão de cada um, o principal primeiro.

    `cred` é o que o envio usa: o do próprio número, ou o do principal quando o número está
    marcado "usar a conta do principal". `cred_propria` é só o dele (o "configurado" da tela).
    """
    cur.execute(f"""SELECT {_CAMPOS} FROM unidade_whatsapps WHERE id_unidade = %s
                     ORDER BY principal DESC, ordem, id""", (id_unidade,))
    linhas = [dict(r) for r in cur.fetchall()]
    for x in linhas:
        bruto = x.pop("credenciais")
        x["cred_propria"] = segredos.decifrar(bruto) if bruto else {}
    principal = next((x for x in linhas if x["principal"]), None)
    for x in linhas:
        usa = x["conta_do_principal"] and principal and principal["id"] != x["id"]
        x["cred"] = principal["cred_propria"] if usa else x["cred_propria"]
    return linhas


def _conexao(cur, id_whatsapp: int | None) -> dict | None:
    if not id_whatsapp:
        return None
    cur.execute("SELECT id_unidade FROM unidade_whatsapps WHERE id = %s", (id_whatsapp,))
    linha = cur.fetchone()
    if not linha:
        return None
    return next((x for x in _conexoes(cur, linha["id_unidade"]) if x["id"] == id_whatsapp), None)


def _avisos(cur, id_unidade: int) -> dict[str, dict]:
    cur.execute("SELECT * FROM whatsapp_avisos WHERE id_unidade = %s", (id_unidade,))
    gravados = {r["evento"]: dict(r) for r in cur.fetchall()}
    saida = {}
    for evento, e in EVENTOS.items():
        g = gravados.get(evento, {})
        saida[evento] = {
            "evento": evento, "ativo": bool(g.get("ativo")),
            "modelo": g.get("modelo") or e["modelo"], "idioma": g.get("idioma") or "pt_BR",
            "antecedencia": g.get("antecedencia") if g.get("antecedencia") is not None
            else e.get("antecedencia"),
            "id_whatsapp": g.get("id_whatsapp"),
        }
    return saida


def _por_onde(cur, id_unidade: int, evento: str, id_whatsapp: int | None = None) -> dict | None:
    """O número conectado por onde a mensagem sai.

    A ordem: o pedido explícito (o número do catálogo do pedido; o número que recebeu a
    resposta do cliente) → o número escolhido no aviso → o principal. ⚠️ O primeiro que estiver
    CONECTADO ganha: número desligado não segura o aviso, ele sai pelo seguinte. Nenhum
    conectado: não sai.
    """
    conexoes = {c["id"]: c for c in _conexoes(cur, id_unidade)}
    candidatos = [id_whatsapp]
    if evento in EVENTOS:
        candidatos.append(_avisos(cur, id_unidade)[evento]["id_whatsapp"])
    candidatos.append(next((c["id"] for c in conexoes.values() if c["principal"]), None))
    for i in candidatos:
        c = conexoes.get(i)
        if c and c["conectado"]:
            return c
    return None


def _garantir_verify_token(cur, conexoes: list[dict]) -> None:
    """O token de verificação do webhook nasce na primeira visita: a loja o cola na Meta."""
    for c in conexoes:
        if not c["verify_token"]:
            c["verify_token"] = secrets.token_urlsafe(18)
            cur.execute("UPDATE unidade_whatsapps SET verify_token = %s WHERE id = %s",
                        (c["verify_token"], c["id"]))


def configuracao(cur, id_unidade: int, url_publica: str) -> dict:
    """A aba WhatsApp da loja. ⚠️ O token e o segredo NUNCA voltam — só "configurado"."""
    conexoes = _conexoes(cur, id_unidade)
    _garantir_verify_token(cur, conexoes)
    avisos = _avisos(cur, id_unidade)
    return {
        "webhook_url": f"{url_publica}/publico/whatsapp/webhook",
        "numeros": [{
            "id": c["id"], "rotulo": c["rotulo"], "numero": c["numero"],
            "principal": c["principal"], "conectado": c["conectado"], "modo": c["modo"],
            "phone_number_id": c["phone_number_id"], "waba_id": c["waba_id"],
            "api_versao": c["api_versao"] or API_VERSAO_PADRAO,
            "verify_token": c["verify_token"], "conta_do_principal": c["conta_do_principal"],
            "token_configurado": bool(c["cred_propria"].get("token")),
            "segredo_configurado": bool(c["cred_propria"].get("app_secret")),
            "ultimo_status": c["ultimo_status"], "ultima_mensagem": c["ultima_mensagem"],
        } for c in conexoes],
        "avisos": [{**EVENTOS[ev], **avisos[ev]} for ev in EVENTOS],
    }


def salvar(cur, id_unidade: int, body) -> None:
    """Grava os números (com a conexão de cada um) e os avisos.

    ⚠️ Token/segredo em branco = mantém o que já está. `body.numeros` ausente = não mexe neles.
    """
    from services import whatsapps_da_loja

    chaves: dict[str, int] = {}
    if body.numeros is not None:
        antes = {c["id"]: c for c in _conexoes(cur, id_unidade)}
        ids = whatsapps_da_loja.gravar_com_ids(
            cur, id_unidade, [n.model_dump() for n in body.numeros])
        pnids: dict[str, int] = {}
        for n, id_w in zip(body.numeros, ids):
            if id_w is None:
                continue
            chaves[str(id_w)] = id_w
            if n.chave:
                chaves[n.chave] = id_w
            pnid = (n.phone_number_id or "").strip() or None
            if pnid:
                if pnid in pnids:
                    raise HTTPException(status_code=422, detail=(
                        f"O identificador {pnid} da Meta está em dois números: cada número tem o dele."))
                pnids[pnid] = id_w
                cur.execute("""SELECT 1 FROM unidade_whatsapps
                                WHERE phone_number_id = %s AND id_unidade <> %s""",
                            (pnid, id_unidade))
                if cur.fetchone():
                    raise HTTPException(status_code=422, detail=(
                        f"O identificador {pnid} da Meta já é de um número de outra loja."))
            cred = dict((antes.get(id_w) or {}).get("cred_propria") or {})
            if (n.token or "").strip():
                cred["token"] = n.token.strip()
            if (n.app_secret or "").strip():
                cred["app_secret"] = n.app_secret.strip()
            # ⚠️ O identificador sai agora e volta no fim: o índice único não aceita o mesmo
            # em dois números nem por um instante (a casa pode ter trocado entre eles).
            cur.execute(
                """UPDATE unidade_whatsapps
                      SET phone_number_id = NULL, conectado = %s, modo = %s, waba_id = %s,
                          api_versao = %s, credenciais = %s, conta_do_principal = %s
                    WHERE id = %s""",
                (n.conectado, n.modo, (n.waba_id or "").strip() or None,
                 (n.api_versao or "").strip() or None, segredos.cifrar(cred) if cred else None,
                 n.conta_do_principal, id_w),
            )
        for pnid, id_w in pnids.items():
            cur.execute("UPDATE unidade_whatsapps SET phone_number_id = %s WHERE id = %s",
                        (pnid, id_w))
        # O envio de verdade precisa do identificador e de um token (o dele ou o do principal).
        conexoes = _conexoes(cur, id_unidade)
        _garantir_verify_token(cur, conexoes)
        for c in conexoes:
            if c["conectado"] and c["modo"] == "real" and not (
                    c["cred"].get("token") and c["phone_number_id"]):
                raise HTTPException(status_code=400, detail=(
                    f"Para enviar de verdade pelo {c['rotulo']} ({c['numero']}), informe o "
                    "identificador do número e o token da Meta."))
    else:
        chaves = {str(c["id"]): c["id"] for c in _conexoes(cur, id_unidade)}
    for a in body.avisos:
        if a.evento not in EVENTOS:
            raise HTTPException(status_code=400, detail=f"Aviso desconhecido: {a.evento}.")
        cur.execute(
            """INSERT INTO whatsapp_avisos (id_unidade, evento, ativo, modelo, idioma, antecedencia,
                                            id_whatsapp)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id_unidade, evento) DO UPDATE
                   SET ativo = EXCLUDED.ativo, modelo = EXCLUDED.modelo,
                       idioma = EXCLUDED.idioma, antecedencia = EXCLUDED.antecedencia,
                       id_whatsapp = EXCLUDED.id_whatsapp, atualizado_em = now()""",
            (id_unidade, a.evento, a.ativo, (a.modelo or "").strip() or None,
             (a.idioma or "pt_BR").strip(), a.antecedencia, chaves.get(a.whatsapp or "")),
        )


# ---------------------------------------------------------------- a fila
def telefone_internacional(telefone: str | None) -> str | None:
    """"(47) 99910-5033" → "5547999105033". Sem DDD não dá: devolve None."""
    d = re.sub(r"\D", "", telefone or "")
    if len(d) in (10, 11):
        return "55" + d
    if len(d) in (12, 13) and d.startswith("55"):
        return d
    return None


def _montar(evento: str, variaveis: list[str]) -> str:
    texto = EVENTOS[evento]["texto"] if evento in EVENTOS else "{{1}}"
    for n, v in enumerate(variaveis, start=1):
        texto = texto.replace("{{%d}}" % n, str(v))
    return texto


def _casa(cur, id_unidade: int) -> str:
    cur.execute("SELECT nome_fantasia, razao_social FROM empresa WHERE id = 1")
    e = cur.fetchone() or {}
    return e.get("nome_fantasia") or e.get("razao_social") or "Nossa casa"


def enfileirar(cur, id_unidade: int, evento: str, chave: str, telefone: str | None,
               variaveis: list, *, nome: str | None = None, id_reserva: int | None = None,
               id_cliente: int | None = None, agendada_para: datetime | None = None,
               ignorar_aviso: bool = False, id_pedido: int | None = None,
               id_whatsapp: int | None = None) -> bool:
    """Põe a mensagem na fila — se a loja tem número conectado e o aviso está ligado.

    ⚠️ **A mesma mensagem não entra duas vezes** (índice único em evento + chave): o
    disparo pode ser chamado de novo sem medo.
    🔑 O número por onde sai é decidido AQUI e gravado na mensagem (`_por_onde`).
    """
    if not ignorar_aviso and not _avisos(cur, id_unidade)[evento]["ativo"]:
        return False
    numero = _por_onde(cur, id_unidade, evento, id_whatsapp)
    if not numero:
        return False
    fone = telefone_internacional(telefone)
    if not fone:
        return False
    vs = [str(v) for v in variaveis]
    cur.execute(
        """INSERT INTO whatsapp_mensagens (id_unidade, evento, chave, id_reserva, id_cliente,
                                           telefone, nome, variaveis, texto, agendada_para,
                                           id_pedido, id_whatsapp)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s, now()), %s, %s)
           ON CONFLICT (id_unidade, evento, chave) DO NOTHING RETURNING id""",
        (id_unidade, evento, chave, id_reserva, id_cliente, fone, nome, json.dumps(vs),
         _montar(evento, vs) if evento != RESPOSTA else vs[0], agendada_para, id_pedido,
         numero["id"]),
    )
    return cur.fetchone() is not None


# ---------------------------------------------------------------- os disparos
def reserva_mudou(cur, id_unidade: int, id_reserva: int, pela_casa: bool = True) -> None:
    """Chamado depois de criar, confirmar, remarcar ou cancelar uma reserva."""
    cur.execute(
        """SELECT id, data, hora, pessoas, nome, telefone, status, id_cliente
             FROM reservas WHERE id = %s AND id_unidade = %s""",
        (id_reserva, id_unidade),
    )
    r = cur.fetchone()
    if not r:
        return
    r = dict(r)
    casa = _casa(cur, id_unidade)
    chave = f"{r['id']}:{r['data']}:{r['hora']:%H%M}"
    variaveis = [(r["nome"] or "").split(" ")[0] or "cliente", casa,
                 f"{r['data']:%d/%m}", f"{r['hora']:%H:%M}", r["pessoas"]]
    comum = {"nome": r["nome"], "id_reserva": r["id"], "id_cliente": r["id_cliente"]}
    # Remarcou: o lembrete e a confirmação da data antiga saem da fila.
    cur.execute(
        """UPDATE whatsapp_mensagens SET status = 'CANCELADA', atualizada_em = now(),
                  erro = 'A reserva mudou antes do envio.'
            WHERE id_reserva = %s AND status = 'FILA' AND chave <> %s""",
        (r["id"], chave),
    )
    if r["status"] == "PENDENTE":
        enfileirar(cur, id_unidade, "RESERVA_RECEBIDA", f"{r['id']}", r["telefone"],
                   variaveis, **comum)
    elif r["status"] == "CONFIRMADA":
        enfileirar(cur, id_unidade, "RESERVA_CONFIRMADA", chave, r["telefone"], variaveis,
                   **comum)
        horas = _avisos(cur, id_unidade)["RESERVA_LEMBRETE"]["antecedencia"] or 3
        # A hora da reserva é da CASA; a fila guarda em UTC pelo `timestamptz`.
        quando = datetime.combine(r["data"], r["hora"]).replace(
            tzinfo=agora_da_casa().tzinfo) - timedelta(hours=int(horas))
        if quando > agora_da_casa():
            enfileirar(cur, id_unidade, "RESERVA_LEMBRETE", chave, r["telefone"], variaveis,
                       agendada_para=quando, **comum)
    elif r["status"] in ("CANCELADA", "NAO_COMPARECEU"):
        cur.execute(
            """UPDATE whatsapp_mensagens SET status = 'CANCELADA', atualizada_em = now(),
                      erro = 'A reserva foi cancelada antes do envio.'
                WHERE id_reserva = %s AND status = 'FILA'""",
            (r["id"],),
        )
        if r["status"] == "CANCELADA" and pela_casa:
            enfileirar(cur, id_unidade, "RESERVA_CANCELADA", f"{r['id']}", r["telefone"],
                       variaveis[:4], **comum)


def premio_ganho(cur, id_unidade: int, id_cliente: int, premio: dict) -> None:
    cur.execute("SELECT nome, telefone FROM reserva_clientes WHERE id = %s", (id_cliente,))
    c = cur.fetchone()
    if not c:
        return
    vence = datetime.fromisoformat(premio["vence_em"]).strftime("%d/%m/%Y")
    enfileirar(cur, id_unidade, "PREMIO_GANHO", premio["codigo"], c["telefone"],
               [c["nome"].split(" ")[0], _casa(cur, id_unidade), premio["premio"], vence,
                premio["codigo"]], nome=c["nome"], id_cliente=id_cliente)


def pedido_confirmado(cur, id_unidade: int, id_pedido: int) -> None:
    """O "pedido confirmado", já com o total final (a casa pode ter trocado produtos)."""
    cur.execute(
        """SELECT p.numero, p.nome, p.telefone, p.modo, p.para_quando, p.total, p.id_cliente,
                  c.id_whatsapp
             FROM pedidos p LEFT JOIN catalogos c ON c.id = p.id_catalogo
            WHERE p.id = %s AND p.id_unidade = %s""", (id_pedido, id_unidade))
    p = cur.fetchone()
    if not p:
        return
    from zoneinfo import ZoneInfo
    from config import FUSO_DA_CASA
    quando = p["para_quando"].astimezone(ZoneInfo(FUSO_DA_CASA))
    modo = "para retirar na loja" if p["modo"] == "RETIRADA" else "para entrega"
    enfileirar(cur, id_unidade, "PEDIDO_CONFIRMADO", f"pedido:{id_pedido}", p["telefone"],
               [p["nome"].split(" ")[0], p["numero"], _casa(cur, id_unidade), modo,
                quando.strftime("%d/%m às %H:%M"), f"{p['total']:.2f}".replace(".", ",")],
               nome=p["nome"], id_cliente=p["id_cliente"], id_pedido=id_pedido,
               # 🔑 146: sai pelo número do catálogo de onde veio o pedido, se conectado.
               id_whatsapp=p["id_whatsapp"])


def varrer(cur) -> int:
    """Os avisos que nascem de uma DATA: prêmio vencendo e aniversário. Idempotente."""
    hoje = agora_da_casa().date()
    n = 0
    cur.execute(
        """SELECT a.id_unidade, a.evento, a.antecedencia FROM whatsapp_avisos a
            WHERE a.ativo AND a.evento IN ('PREMIO_VENCENDO', 'ANIVERSARIO')
              AND EXISTS (SELECT 1 FROM unidade_whatsapps w
                           WHERE w.id_unidade = a.id_unidade AND w.conectado)""")
    for a in [dict(x) for x in cur.fetchall()]:
        casa = _casa(cur, a["id_unidade"])
        if a["evento"] == "PREMIO_VENCENDO":
            alvo = hoje + timedelta(days=int(a["antecedencia"] or 3))
            cur.execute(
                """SELECT p.id, p.codigo, p.premio, p.vence_em, c.id AS id_cliente, c.nome,
                          c.telefone
                     FROM fidelidade_premios p JOIN reserva_clientes c ON c.id = p.id_cliente
                    WHERE p.usado_em IS NULL AND p.vence_em = %s AND p.id_unidade = %s""",
                (alvo, a["id_unidade"]),
            )
            for p in cur.fetchall():
                n += enfileirar(cur, a["id_unidade"], "PREMIO_VENCENDO",
                                f"{p['id']}:{p['vence_em']}", p["telefone"],
                                [p["nome"].split(" ")[0], p["premio"], casa,
                                 f"{p['vence_em']:%d/%m}", p["codigo"]],
                                nome=p["nome"], id_cliente=p["id_cliente"])
        else:
            cur.execute(
                """SELECT id, nome, telefone FROM reserva_clientes
                    WHERE nascimento IS NOT NULL AND whatsapp_optout_em IS NULL
                      AND extract(month FROM nascimento) = %s
                      AND extract(day FROM nascimento) = %s
                      AND (id_unidade = %s OR id_unidade IS NULL)""",
                (hoje.month, hoje.day, a["id_unidade"]),
            )
            for c in cur.fetchall():
                n += enfileirar(cur, a["id_unidade"], "ANIVERSARIO", f"{c['id']}:{hoje.year}",
                                c["telefone"], [c["nome"].split(" ")[0], casa],
                                nome=c["nome"], id_cliente=c["id"])
    return n


# ---------------------------------------------------------------- o envio
def _payload(msg: dict, aviso: dict | None) -> dict:
    if msg["evento"] == RESPOSTA:
        return {"messaging_product": "whatsapp", "to": msg["telefone"], "type": "text",
                "text": {"body": msg["texto"]}}
    componentes = [{"type": "body", "parameters": [
        {"type": "text", "text": v} for v in (msg["variaveis"] or [])]}]
    for i, acao in enumerate(("CONFIRMAR", "CANCELAR")
                             if EVENTOS[msg["evento"]].get("botoes") else ()):
        # 🔑 O `payload` do botão volta no webhook: é assim que se sabe QUAL mensagem (e
        # portanto qual reserva) o cliente respondeu.
        componentes.append({"type": "button", "sub_type": "quick_reply", "index": str(i),
                            "parameters": [{"type": "payload", "payload": f"{acao}:{msg['id']}"}]})
    return {"messaging_product": "whatsapp", "to": msg["telefone"], "type": "template",
            "template": {"name": aviso["modelo"], "language": {"code": aviso["idioma"]},
                         "components": componentes}}


def _enviar_um(cur, msg: dict) -> None:
    integ = _conexao(cur, msg.get("id_whatsapp"))
    if not integ or not integ["conectado"]:
        cur.execute("""UPDATE whatsapp_mensagens SET status = 'CANCELADA', atualizada_em = now(),
                              erro = 'O número foi desligado ou removido.' WHERE id = %s""",
                    (msg["id"],))
        return
    if integ["modo"] != "real":
        cur.execute("""UPDATE whatsapp_mensagens SET status = 'SIMULADA', enviada_em = now(),
                              atualizada_em = now() WHERE id = %s""", (msg["id"],))
        return
    aviso = None if msg["evento"] == RESPOSTA else _avisos(cur, msg["id_unidade"])[msg["evento"]]
    url = (f"https://graph.facebook.com/{integ['api_versao'] or API_VERSAO_PADRAO}/"
           f"{integ['phone_number_id']}/messages")
    try:
        r = httpx.post(url, json=_payload(msg, aviso), timeout=15,
                       headers={"Authorization": f"Bearer {integ['cred'].get('token')}"})
        dados = r.json() if r.content else {}
        if r.status_code >= 400:
            raise RuntimeError((dados.get("error") or {}).get("message") or f"HTTP {r.status_code}")
        wamid = ((dados.get("messages") or [{}])[0]).get("id")
        cur.execute("""UPDATE whatsapp_mensagens SET status = 'ENVIADA', enviada_em = now(),
                              id_meta = %s, erro = NULL, atualizada_em = now() WHERE id = %s""",
                    (wamid, msg["id"]))
        cur.execute("""UPDATE unidade_whatsapps SET ultimo_status = 'ok', ultima_mensagem = NULL
                        WHERE id = %s""", (integ["id"],))
    except Exception as e:  # noqa: BLE001
        tentativas = int(msg["tentativas"]) + 1
        falhou = tentativas >= TENTATIVAS_MAXIMAS
        cur.execute(
            """UPDATE whatsapp_mensagens
                  SET tentativas = %s, erro = %s, atualizada_em = now(),
                      status = CASE WHEN %s THEN 'FALHOU' ELSE 'FILA' END,
                      agendada_para = now() + interval '5 minutes'
                WHERE id = %s""",
            (tentativas, str(e)[:500], falhou, msg["id"]),
        )
        cur.execute("""UPDATE unidade_whatsapps SET ultimo_status = 'erro', ultima_mensagem = %s
                        WHERE id = %s""", (str(e)[:500], integ["id"]))


def processar_fila(limite: int = 20) -> int:
    """Envia o que venceu. ⚠️ `SKIP LOCKED`: dois processos nunca pegam a mesma mensagem."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT id, id_unidade, evento, telefone, variaveis, texto, tentativas, id_whatsapp
                 FROM whatsapp_mensagens
                WHERE status = 'FILA' AND agendada_para <= now()
                ORDER BY agendada_para, id LIMIT %s FOR UPDATE SKIP LOCKED""",
            (limite,),
        )
        msgs = [dict(r) for r in cur.fetchall()]
        for m in msgs:
            _enviar_um(cur, m)
    return len(msgs)


_ultima_varredura: datetime | None = None


async def laco(parar: asyncio.Event) -> None:
    """Acorda a cada 30 s: envia a fila; a cada 10 min, varre os avisos de data.

    ⚠️ Nada aqui pode levantar: um agendador que morre no primeiro erro some sem avisar.
    """
    global _ultima_varredura
    while not parar.is_set():
        try:
            await asyncio.wait_for(parar.wait(), timeout=INTERVALO_DE_CHECAGEM)
            return
        except asyncio.TimeoutError:
            pass
        try:
            # ⚠️ Aqui o relógio do contêiner serve: é um INTERVALO (passaram dez
            # minutos?), não uma hora do dia — o fuso some na subtração.
            agora = datetime.now()
            if not _ultima_varredura or agora - _ultima_varredura > timedelta(minutes=10):
                _ultima_varredura = agora
                await asyncio.to_thread(_varrer_com_cursor)
            await asyncio.to_thread(processar_fila)
        except Exception as e:  # noqa: BLE001
            await asyncio.to_thread(erros.registrar, "whatsapp", e)


def _varrer_com_cursor() -> None:
    with get_cursor() as cur:
        varrer(cur)


# ---------------------------------------------------------------- o webhook
def verificar_webhook(cur, token: str | None) -> bool:
    """A Meta confere o webhook com o token que a loja colou lá."""
    if not token:
        return False
    cur.execute("SELECT 1 FROM unidade_whatsapps WHERE verify_token = %s", (token,))
    return cur.fetchone() is not None


def _loja_do_numero(cur, phone_number_id: str | None) -> tuple[int, dict] | None:
    """O número (e a loja dele) pelo identificador que a Meta manda no webhook."""
    cur.execute("SELECT id, id_unidade FROM unidade_whatsapps WHERE phone_number_id = %s",
                (str(phone_number_id or ""),))
    linha = cur.fetchone()
    if not linha:
        return None
    return linha["id_unidade"], _conexao(cur, linha["id"])


def assinatura_valida(corpo: bytes, assinatura: str | None, app_secret: str | None) -> bool:
    """`X-Hub-Signature-256` = sha256 HMAC do corpo com o segredo do app. Sem segredo, recusa."""
    if not app_secret or not assinatura or not assinatura.startswith("sha256="):
        return False
    esperado = hmac.new(app_secret.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, assinatura.split("=", 1)[1])


_ORDEM = {"FILA": 0, "SIMULADA": 1, "ENVIADA": 1, "ENTREGUE": 2, "LIDA": 3, "RESPONDIDA": 4,
          "FALHOU": 1, "CANCELADA": 0}
_DA_META = {"sent": "ENVIADA", "delivered": "ENTREGUE", "read": "LIDA", "failed": "FALHOU"}


def receber(cur, corpo: bytes, assinatura: str | None) -> dict:
    """O que a Meta avisa: estados das mensagens e as respostas dos clientes.

    ⚠️ **Nada muda sem a assinatura da loja conferida** — o webhook é público, e sem ela
    qualquer um cancelaria reserva alheia mandando um JSON.
    """
    try:
        dados = json.loads(corpo or b"{}")
    except ValueError:
        raise HTTPException(status_code=400, detail="Corpo inválido.")
    feito = {"estados": 0, "respostas": 0}
    for entrada in dados.get("entry") or []:
        for mudanca in entrada.get("changes") or []:
            valor = mudanca.get("value") or {}
            achado = _loja_do_numero(cur, (valor.get("metadata") or {}).get("phone_number_id"))
            if not achado:
                continue
            id_unidade, integ = achado
            if not assinatura_valida(corpo, assinatura, integ["cred"].get("app_secret")):
                raise HTTPException(status_code=403, detail="Assinatura inválida.")
            for st in valor.get("statuses") or []:
                novo = _DA_META.get(st.get("status"))
                if not novo:
                    continue
                cur.execute("SELECT id, status FROM whatsapp_mensagens WHERE id_meta = %s",
                            (st.get("id"),))
                m = cur.fetchone()
                # ⚠️ Só avança: "entregue" atrasado não desfaz o "lida" que já chegou.
                if m and (_ORDEM.get(novo, 0) > _ORDEM.get(m["status"], 0) or novo == "FALHOU"):
                    erro = ((st.get("errors") or [{}])[0]).get("title") if novo == "FALHOU" else None
                    cur.execute("""UPDATE whatsapp_mensagens SET status = %s, erro = coalesce(%s, erro),
                                          atualizada_em = now() WHERE id = %s""",
                                (novo, erro, m["id"]))
                    feito["estados"] += 1
            for msg in valor.get("messages") or []:
                feito["respostas"] += _resposta(cur, id_unidade, msg, integ["id"])
    return feito


def _resposta(cur, id_unidade: int, msg: dict, id_whatsapp: int) -> int:
    payload = None
    if msg.get("type") == "button":
        payload = (msg.get("button") or {}).get("payload")
    elif msg.get("type") == "interactive":
        payload = ((msg.get("interactive") or {}).get("button_reply") or {}).get("id")
    elif msg.get("type") == "text":
        texto = ((msg.get("text") or {}).get("body") or "").strip().upper()
        if texto in PALAVRAS_DE_SAIDA:
            fone = re.sub(r"\D", "", msg.get("from") or "")
            cur.execute("""UPDATE reserva_clientes SET whatsapp_optout_em = now()
                            WHERE %s LIKE '%%' || telefone AND whatsapp_optout_em IS NULL""",
                        (fone,))
            return 1
        return 0
    if not payload or ":" not in payload:
        return 0
    acao, _, id_msg = payload.partition(":")
    if not id_msg.isdigit():
        return 0
    cur.execute("""SELECT id, id_reserva, nome, telefone, status FROM whatsapp_mensagens
                    WHERE id = %s AND id_unidade = %s FOR UPDATE""", (int(id_msg), id_unidade))
    m = cur.fetchone()
    if not m or not m["id_reserva"]:
        return 0
    cur.execute("""UPDATE whatsapp_mensagens SET status = 'RESPONDIDA', resposta = %s,
                          respondida_em = now(), atualizada_em = now() WHERE id = %s""",
                (acao, m["id"]))
    cur.execute("SELECT id, status, presenca FROM reservas WHERE id = %s", (m["id_reserva"],))
    reserva = cur.fetchone()
    if not reserva:
        return 1
    primeiro = (m["nome"] or "").split(" ")[0] or "cliente"
    if acao == "CONFIRMAR":
        cur.execute("""UPDATE reservas SET presenca = 'CONFIRMADA', presenca_em = now()
                        WHERE id = %s""", (reserva["id"],))
        texto = f"Obrigado, {primeiro}! Sua presença está confirmada. Até logo!"
    elif acao == "CANCELAR":
        cur.execute("""UPDATE reservas SET presenca = 'CANCELOU', presenca_em = now()
                        WHERE id = %s""", (reserva["id"],))
        if reserva["status"] in ("PENDENTE", "CONFIRMADA"):
            from services import reservas_agenda as agenda
            agenda.mudar_status(cur, id_unidade, reserva["id"], "CANCELADA")
            # O cancelamento foi do CLIENTE: sem o aviso "a casa cancelou".
            reserva_mudou(cur, id_unidade, reserva["id"], pela_casa=False)
        texto = f"Tudo certo, {primeiro}: sua reserva foi cancelada. Esperamos você numa próxima!"
    else:
        return 1
    # A resposta é TEXTO LIVRE: o toque do cliente abriu a janela de 24 h.
    enfileirar(cur, id_unidade, RESPOSTA, f"{m['id']}:{acao}", m["telefone"], [texto],
               nome=m["nome"], id_reserva=reserva["id"], ignorar_aviso=True,
               # A resposta volta pelo número que o cliente tocou: é a conversa dele.
               id_whatsapp=id_whatsapp)
    return 1

