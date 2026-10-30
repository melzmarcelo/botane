"""WhatsApp por loja: a fila, os avisos, o modo simulado e o webhook da Meta (migração 099),
com a conexão por NÚMERO da loja (146).

🔑 **Pedido do dono (28/09/2026):** mensagens configuráveis por loja (reserva, confirmação,
prêmio…) e a confirmação de presença pelo WhatsApp, recebendo o botão que o cliente tocou.
🔑 **E (30/10/2026):** cada número da loja com a configuração completa — enviar e receber os
retornos —, e cada aviso dizendo por qual número sai.

Tudo em MODO SIMULADO: nenhuma mensagem sai para a Meta. O webhook é exercitado com o corpo
que a Meta manda, assinado (e não assinado) com o segredo do app.

    python tests/smoke_whatsapp.py        (API de pé na 9200)
"""

import atexit
import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import preservar_reserva  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None, cabecalhos=None, cru=False):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for k, v in (cabecalhos or {}).items():
        req.add_header(k, v)
    dados = corpo if isinstance(corpo, bytes) else (
        json.dumps(corpo, default=str).encode() if corpo is not None else None)
    try:
        with urllib.request.urlopen(req, dados, timeout=60) as r:
            b = r.read()
            return r.status, (b.decode() if cru else json.loads(b or b"null")), dict(r.headers)
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b or b"null"), {}
        except json.JSONDecodeError:
            return e.code, {"detail": b.decode(errors="replace")}, {}


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


_st, r, _h = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()
_st, eu, _h = chamar("GET", "/auth/me", token=token)
UNIDADE = (eu.get("unidades") or [{}])[0].get("id")
devolver_a_reserva = preservar_reserva(UNIDADE)
marca = str(time.time_ns() // 100)[-6:]
PNID = f"PNID{marca}"        # o número A, principal
PNID_B = f"PNIDB{marca}"     # o número B, na conta do principal
SEGREDO = f"segredo-{marca}"
FONE_A = f"(99) 9{marca[:4]}-{marca[2:6]}"
FONE_B = f"(99) 8{marca[:4]}-{marca[2:6]}"

# Os números da loja (com a conexão de cada um) e os avisos: fotografados e devolvidos no fim,
# com os MESMOS ids — é o que catálogos, avisos e mensagens guardam.
with get_cursor() as cur:
    cur.execute("SELECT * FROM unidade_whatsapps WHERE id_unidade = %s", (UNIDADE,))
    NUMEROS_ANTES = [dict(x) for x in cur.fetchall()]
    cur.execute("SELECT whatsapp FROM unidades WHERE id = %s", (UNIDADE,))
    ESPELHO_ANTES = cur.fetchone()["whatsapp"]
    cur.execute("SELECT * FROM whatsapp_avisos WHERE id_unidade = %s", (UNIDADE,))
    AVISOS_ANTES = [dict(x) for x in cur.fetchall()]
    cur.execute("SELECT id, id_whatsapp FROM catalogos WHERE id_whatsapp IS NOT NULL")
    CATALOGOS_ANTES = [dict(x) for x in cur.fetchall()]


def _devolver():
    with get_cursor() as cur:
        cur.execute("DELETE FROM whatsapp_mensagens WHERE id_unidade = %s AND criada_em >= %s",
                    (UNIDADE, INICIO))
        cur.execute("DELETE FROM whatsapp_avisos WHERE id_unidade = %s", (UNIDADE,))
        ids = [n["id"] for n in NUMEROS_ANTES]
        cur.execute("DELETE FROM unidade_whatsapps WHERE id_unidade = %s AND NOT (id = ANY(%s))",
                    (UNIDADE, ids))
        cur.execute("""UPDATE unidade_whatsapps SET principal = false, phone_number_id = NULL
                        WHERE id_unidade = %s""", (UNIDADE,))
        for n in NUMEROS_ANTES:
            colunas = list(n)
            cur.execute(
                f"""INSERT INTO unidade_whatsapps ({', '.join(colunas)})
                    VALUES ({', '.join(['%s'] * len(colunas))})
                    ON CONFLICT (id) DO UPDATE SET
                    {', '.join(f"{c} = EXCLUDED.{c}" for c in colunas if c != 'id')}""",
                list(n.values()))
        cur.execute("UPDATE unidades SET whatsapp = %s WHERE id = %s", (ESPELHO_ANTES, UNIDADE))
        for a in AVISOS_ANTES:
            cur.execute(f"INSERT INTO whatsapp_avisos ({', '.join(a)}) VALUES "
                        f"({', '.join(['%s'] * len(a))})", list(a.values()))
        for c in CATALOGOS_ANTES:
            cur.execute("UPDATE catalogos SET id_whatsapp = %s WHERE id = %s",
                        (c["id_whatsapp"], c["id"]))


with get_cursor() as cur:
    cur.execute("SELECT now() AS agora")
    INICIO = cur.fetchone()["agora"]
atexit.register(_devolver)


def msgs(evento=None, id_reserva=None):
    with get_cursor() as cur:
        cur.execute(
            """SELECT id, evento, status, agendada_para, chave, id_meta, resposta, texto
                 FROM whatsapp_mensagens
                WHERE id_unidade = %s AND criada_em >= %s
                  AND (%s::text IS NULL OR evento = %s)
                  AND (%s::int IS NULL OR id_reserva = %s)
                ORDER BY id""",
            (UNIDADE, INICIO, evento, evento, id_reserva, id_reserva))
        return [dict(x) for x in cur.fetchall()]


def processar():
    from services import whatsapp
    return whatsapp.processar_fila()


def webhook(corpo: dict, assinar=True):
    bruto = json.dumps(corpo).encode()
    cab = {}
    if assinar:
        cab["X-Hub-Signature-256"] = "sha256=" + hmac.new(
            SEGREDO.encode(), bruto, hashlib.sha256).hexdigest()
    return chamar("POST", "/publico/whatsapp/webhook", bruto, cabecalhos=cab)


def botao(payload, fone="5547999300009", pnid=None):
    return {"entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": pnid or PNID},
        "messages": [{"from": fone, "type": "button",
                      "button": {"payload": payload, "text": "x"}}]}}]}]}


print("0. o cenário: Portal ligado, salão com mesa, casa aberta todo dia")
chamar("PUT", f"/unidades/{UNIDADE}/parametros", {"reservas_ligado": True}, token)
with get_cursor() as cur:
    cur.execute("""DELETE FROM reserva_mesas WHERE id_reserva IN
                     (SELECT id FROM reservas WHERE id_unidade = %s)""", (UNIDADE,))
    cur.execute("DELETE FROM reservas WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM reserva_bloqueios WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM reserva_dias_especiais WHERE id_unidade = %s", (UNIDADE,))
_st, sal, _h = chamar("POST", "/reservas/saloes", {"nome": f"Salao WA {marca}"}, token)
for n in range(1, 4):
    chamar("POST", "/reservas/mesas", {"id_salao": sal.get("id"), "nome": f"WA{marca}-{n}",
                                       "lugares": 4}, token)
_st, cfg, _h = chamar("GET", "/reservas/configuracao", token=token)
st, _r, _h = chamar("PUT", "/reservas/configuracao", {
    **cfg, "confirmacao": "AUTOMATICA", "antecedencia_min_horas": 0,
    "horarios": [{"dia_semana": d, "aberto": True, "abre": "08:00", "fecha": "23:30",
                  "ultima_reserva": "22:00"} for d in range(1, 8)],
    "permanencias": [{"nome": "Unica", "de": "08:00", "ate": "23:30", "minutos": 60}]}, token)
checar("a agenda do cenário grava", st == 200, _r)
AMANHA = date.today() + timedelta(days=2)


def reservar(hora, nome="Wanda Teste", fone="47999300009"):
    st, r, _h = chamar("POST", "/reservas", {"data": str(AMANHA), "hora": hora, "pessoas": 2,
                                             "nome": nome, "telefone": fone,
                                             "origem": "BALCAO"}, token)
    return st, r


print("\n1. a configuração da loja: os números e a conexão de cada um")
st, c, _h = chamar("GET", f"/unidades/{UNIDADE}/whatsapp", token=token)
checar("cada número da loja tem o seu token de verificação do webhook",
       st == 200 and all(n.get("verify_token") for n in c.get("numeros") or []), (st, c))
checar("com os 8 avisos e o texto pronto de cada modelo",
       len(c.get("avisos") or []) == 8 and all("{{1}}" in a["texto"] for a in c["avisos"]),
       len(c.get("avisos") or []))
# Os números que já eram da loja ficam (desconectados e sem o ★); A e B entram.
OUTROS = [{"id": n["id"], "rotulo": n["rotulo"], "numero": n["numero"], "principal": False,
           "conectado": False, "modo": "simulado"} for n in c.get("numeros") or []]


def numeros(conectado=True, modo="simulado", token_a="", segredo="", conectado_b=False,
            modo_b="simulado", com_b=True):
    """O corpo de `numeros`: A (principal) e B (na conta do principal), com os ids gravados."""
    atuais = {n["numero"]: n["id"] for n in
              chamar("GET", f"/unidades/{UNIDADE}/whatsapp", token=token)[1]["numeros"]}
    lista = [{"id": atuais.get(FONE_A), "chave": "A", "rotulo": "Atendimento", "numero": FONE_A,
              "principal": True, "conectado": conectado, "modo": modo, "phone_number_id": PNID,
              "api_versao": "v21.0", "token": token_a, "app_secret": segredo}]
    if com_b:
        lista.append({"id": atuais.get(FONE_B), "chave": "B", "rotulo": "Encomendas",
                      "numero": FONE_B, "conectado": conectado_b, "modo": modo_b,
                      "phone_number_id": PNID_B, "conta_do_principal": True})
    return lista + [dict(o) for o in OUTROS]


def gravar(avisos_=None, **kw):
    return chamar("PUT", f"/unidades/{UNIDADE}/whatsapp",
                  {"numeros": numeros(**kw), "avisos": avisos_ or []}, token)


def numero(c_, fone):
    return next((n for n in c_.get("numeros") or [] if n["numero"] == fone), {})


st, r, _h = gravar(modo="real")
checar("enviar de verdade sem token é recusado", st == 400, (st, r))
avisos = [{"evento": e, "ativo": e in ("RESERVA_CONFIRMADA", "RESERVA_LEMBRETE",
                                        "RESERVA_CANCELADA", "PREMIO_GANHO"),
           "modelo": e.lower(), "idioma": "pt_BR",
           "antecedencia": 3 if e == "RESERVA_LEMBRETE" else None}
          for e in ("RESERVA_RECEBIDA", "RESERVA_CONFIRMADA", "RESERVA_LEMBRETE",
                    "RESERVA_CANCELADA", "PREMIO_GANHO", "PREMIO_VENCENDO", "ANIVERSARIO")]
st, c, _h = gravar(avisos, token_a=f"tok-{marca}", segredo=SEGREDO)
A = numero(c, FONE_A)
B = numero(c, FONE_B)
checar("liga o A em modo simulado, com token e segredo guardados (e ele é o principal)",
       st == 200 and A.get("conectado") and A.get("principal") and A.get("token_configurado")
       and A.get("segredo_configurado"), (st, c))
checar("e o token NÃO volta na resposta", f"tok-{marca}" not in json.dumps(c)
       and SEGREDO not in json.dumps(c))
checar("o B nasce com o seu token de verificação, na conta do principal",
       B.get("verify_token") and B.get("conta_do_principal") and not B.get("token_configurado"), B)
st, c, _h = gravar(avisos)
checar("salvar de novo com o token em branco MANTÉM o token",
       numero(c, FONE_A).get("token_configurado"), c)
st, c, _h = gravar(avisos, conectado_b=True, modo_b="real")
checar("o B pode enviar de verdade com o token do principal (sem digitar de novo)",
       st == 200 and numero(c, FONE_B).get("modo") == "real", (st, c))
gravar(avisos)
VERIFY = A.get("verify_token")

print("\n2. a reserva confirmada: aviso na hora e lembrete agendado")
st, res = reservar("19:00")
checar("a reserva nasce confirmada", st == 201 and res.get("status") == "CONFIRMADA", (st, res))
ID_R = res.get("id")
conf = msgs("RESERVA_CONFIRMADA", ID_R)
lemb = msgs("RESERVA_LEMBRETE", ID_R)
checar("a confirmação entra na fila", len(conf) == 1 and conf[0]["status"] == "FILA", conf)
esperado = datetime.combine(AMANHA, datetime.strptime("16:00", "%H:%M").time())
checar("e o lembrete, agendado 3 horas antes",
       len(lemb) == 1 and lemb[0]["agendada_para"].replace(tzinfo=None) - esperado
       < timedelta(hours=4), lemb)
processar()
checar("o modo simulado marca a confirmação como SIMULADA (e ela não sai)",
       msgs("RESERVA_CONFIRMADA", ID_R)[0]["status"] == "SIMULADA", msgs("RESERVA_CONFIRMADA", ID_R))
checar("o lembrete espera a hora dele", msgs("RESERVA_LEMBRETE", ID_R)[0]["status"] == "FILA")
checar("com o texto montado", "Wanda" in (conf[0]["texto"] or "") and "19:00" in conf[0]["texto"],
       conf[0]["texto"])

st, _r, _h = chamar("PUT", f"/reservas/{ID_R}", {"data": str(AMANHA), "hora": "20:00",
                                                  "pessoas": 2}, token)
lembretes = msgs("RESERVA_LEMBRETE", ID_R)
checar("remarcar cancela o lembrete antigo e agenda o novo",
       st == 200 and [m["status"] for m in lembretes] == ["CANCELADA", "FILA"], (st, lembretes))
checar("e manda a nova confirmação", len(msgs("RESERVA_CONFIRMADA", ID_R)) == 2)
chamar("PUT", f"/reservas/{ID_R}", {"data": str(AMANHA), "hora": "20:00", "pessoas": 2}, token)
checar("a mesma mudança de novo não duplica nada (índice único)",
       len(msgs("RESERVA_CONFIRMADA", ID_R)) == 2 and len(msgs("RESERVA_LEMBRETE", ID_R)) == 2)

print("\n3. o webhook: verificação e assinatura")
st, r, _h = chamar("GET", f"/publico/whatsapp/webhook?hub.mode=subscribe&hub.verify_token={VERIFY}"
                          "&hub.challenge=12345", cru=True)
checar("a Meta confere o endereço com o token da loja", st == 200 and r == "12345", (st, r))
st, r, _h = chamar("GET", "/publico/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=errado"
                          "&hub.challenge=1")
checar("token errado: 403", st == 403, st)
lembrete = msgs("RESERVA_LEMBRETE", ID_R)[-1]
st, r, _h = webhook(botao(f"CONFIRMAR:{lembrete['id']}"), assinar=False)
checar("sem a assinatura da Meta, nada muda (403)", st == 403, (st, r))
with get_cursor() as cur:
    cur.execute("SELECT presenca FROM reservas WHERE id = %s", (ID_R,))
    checar("e a presença continua vazia", cur.fetchone()["presenca"] is None)

print("\n4. o cliente toca \"Confirmo\"")
st, r, _h = webhook(botao(f"CONFIRMAR:{lembrete['id']}"))
checar("o webhook assinado é aceito", st == 200 and r.get("respostas") == 1, (st, r))
with get_cursor() as cur:
    cur.execute("SELECT status, presenca FROM reservas WHERE id = %s", (ID_R,))
    rr = dict(cur.fetchone())
checar("a reserva ganha a presença confirmada (e continua CONFIRMADA)",
       rr == {"status": "CONFIRMADA", "presenca": "CONFIRMADA"}, rr)
checar("o lembrete fica RESPONDIDA com o botão",
       msgs("RESERVA_LEMBRETE", ID_R)[-1]["status"] == "RESPONDIDA"
       and msgs("RESERVA_LEMBRETE", ID_R)[-1]["resposta"] == "CONFIRMAR")
resp = msgs("RESPOSTA", ID_R)
checar("e o cliente recebe o agradecimento (texto livre, janela de 24 h)",
       len(resp) == 1 and "confirmada" in (resp[0]["texto"] or ""), resp)
st, _r, _h = chamar("GET", f"/reservas/agenda?data={AMANHA}", token=token)
checar("a agenda mostra a presença", any(x.get("presenca") == "CONFIRMADA"
                                         for x in _r.get("reservas", [])))

print("\n5. os estados da Meta só avançam")
conf_id = msgs("RESERVA_CONFIRMADA", ID_R)[-1]["id"]
with get_cursor() as cur:
    cur.execute("UPDATE whatsapp_mensagens SET id_meta = %s, status = 'ENVIADA' WHERE id = %s",
                (f"wamid.{marca}", conf_id))


def estado(s):
    return webhook({"entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": PNID},
        "statuses": [{"id": f"wamid.{marca}", "status": s}]}}]}]})


estado("read")
estado("delivered")
st_final = next(m for m in msgs("RESERVA_CONFIRMADA", ID_R) if m["id"] == conf_id)["status"]
checar("\"lida\" não volta para \"entregue\" quando o aviso chega atrasado", st_final == "LIDA",
       st_final)

print("\n6. o cliente toca \"Preciso cancelar\"")
st, res2 = reservar("12:00", nome="Carlos Cancela", fone="47999300008")
ID_R2 = res2.get("id")
lemb2 = msgs("RESERVA_LEMBRETE", ID_R2)[-1]
st, r, _h = webhook(botao(f"CANCELAR:{lemb2['id']}", fone="5547999300008"))
with get_cursor() as cur:
    cur.execute("SELECT status, presenca FROM reservas WHERE id = %s", (ID_R2,))
    rr2 = dict(cur.fetchone())
checar("a reserva é CANCELADA e a mesa volta a ficar livre",
       rr2 == {"status": "CANCELADA", "presenca": "CANCELOU"}, rr2)
checar("sem o aviso \"a casa cancelou\" (foi o cliente)", not msgs("RESERVA_CANCELADA", ID_R2))
checar("e com a resposta ao cliente",
       any("cancelada" in (m["texto"] or "") for m in msgs("RESPOSTA", ID_R2)))

print("\n7. a casa cancela")
st, res3 = reservar("13:00", nome="Dora Casa", fone="47999300007")
ID_R3 = res3.get("id")
chamar("PUT", f"/reservas/{ID_R3}/status", {"status": "CANCELADA"}, token)
checar("o cliente é avisado de que a casa cancelou", len(msgs("RESERVA_CANCELADA", ID_R3)) == 1)
checar("e o lembrete sai da fila",
       all(m["status"] == "CANCELADA" for m in msgs("RESERVA_LEMBRETE", ID_R3)))

print("\n8. aviso desligado, PARAR e o teste pela tela")
avisos_off = [dict(a, ativo=False) if a["evento"] == "RESERVA_CONFIRMADA" else a for a in avisos]
gravar(avisos_off)
st, res4 = reservar("14:00", nome="Eva Desligado", fone="47999300006")
checar("com o aviso desligado, nada entra na fila", not msgs("RESERVA_CONFIRMADA", res4.get("id")))
with get_cursor() as cur:
    cur.execute("""INSERT INTO reserva_clientes (id_unidade, telefone, nome)
                   VALUES (%s, %s, 'Pedro Parar') ON CONFLICT (telefone) DO NOTHING""",
                (UNIDADE, f"4799930{marca[-4:]}"))
webhook({"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": PNID},
         "messages": [{"from": f"554799930{marca[-4:]}", "type": "text",
                       "text": {"body": "parar"}}]}}]}]})
with get_cursor() as cur:
    cur.execute("SELECT whatsapp_optout_em FROM reserva_clientes WHERE telefone = %s",
                (f"4799930{marca[-4:]}",))
    optout = (cur.fetchone() or {}).get("whatsapp_optout_em")
    cur.execute("DELETE FROM reserva_clientes WHERE telefone = %s", (f"4799930{marca[-4:]}",))
checar("quem responde PARAR sai dos avisos de marketing", optout is not None, optout)
st, r, _h = chamar("POST", f"/unidades/{UNIDADE}/whatsapp/teste",
                   {"telefone": "(47) 99930-0005", "evento": "PREMIO_GANHO"}, token)
checar("o teste pela tela passa pela fila e é processado", st == 200, (st, r))
st, hist, cab = chamar("GET", f"/unidades/{UNIDADE}/whatsapp/mensagens?limite=5", token=token)
checar("o histórico lista, paginado, com o teste SIMULADA no topo",
       st == 200 and hist and hist[0]["status"] == "SIMULADA"
       and {k.lower(): v for k, v in cab.items()}.get("x-total"), (st, hist[:1], cab))
gravar(avisos, conectado=False)
st, res5 = reservar("15:00", nome="Fabio Fora", fone="47999300004")
checar("com nenhum número conectado, nada entra na fila", not msgs(id_reserva=res5.get("id")))

print("\n8b. o envio de verdade (com a Meta simulada dentro do teste)")
# ⚠️ Sem conta na Meta: troca o `httpx.post` do serviço por um falso, que devolve o que a
# Meta devolveria — e guarda o pedido, para conferir o que o Botané MANDARIA.
from services import whatsapp as wa  # noqa: E402

gravar(avisos, modo="real", token_a=f"tok-{marca}")
pedidos = []


class _Resposta:
    def __init__(self, codigo, corpo):
        self.status_code, self._corpo = codigo, corpo
        self.content = json.dumps(corpo).encode()

    def json(self):
        return self._corpo


def _meta_ok(url, json=None, headers=None, timeout=None):  # noqa: A002
    pedidos.append({"url": url, "json": json, "headers": headers})
    return _Resposta(200, {"messages": [{"id": f"wamid.real.{len(pedidos)}"}]})


original = wa.httpx.post
wa.httpx.post = _meta_ok
try:
    with get_cursor() as cur:
        wa.enfileirar(cur, UNIDADE, "RESERVA_LEMBRETE", f"real:{marca}", "47999300003",
                      ["Gil", "Casa", "01/01", "12:00", 2], nome="Gil", ignorar_aviso=True)
    processar()
finally:
    wa.httpx.post = original
env = msgs("RESERVA_LEMBRETE")[-1]
p0 = (pedidos or [{}])[0]
tpl = (p0.get("json") or {}).get("template") or {}
checar("vai para a Graph API do número da loja, com o token",
       p0.get("url", "").endswith(f"/v21.0/{PNID}/messages")
       and p0.get("headers", {}).get("Authorization") == f"Bearer tok-{marca}", p0.get("url"))
checar("como MODELO, com o nome e as variáveis na ordem",
       tpl.get("name") == "reserva_lembrete" and [x["text"] for x in tpl["components"][0]["parameters"]]
       == ["Gil", "Casa", "01/01", "12:00", "2"], tpl)
checar("e os dois botões levam a referência da mensagem",
       [c["parameters"][0]["payload"] for c in tpl["components"][1:]]
       == [f"CONFIRMAR:{env['id']}", f"CANCELAR:{env['id']}"], tpl.get("components"))
checar("a mensagem fica ENVIADA com o id da Meta",
       env["status"] == "ENVIADA" and env["id_meta"] == "wamid.real.1", env)


def _meta_erro(url, json=None, headers=None, timeout=None):  # noqa: A002
    return _Resposta(400, {"error": {"message": "Template name does not exist"}})


wa.httpx.post = _meta_erro
try:
    with get_cursor() as cur:
        wa.enfileirar(cur, UNIDADE, "PREMIO_GANHO", f"erro:{marca}", "47999300002",
                      ["a", "b", "c", "d", "e"], ignorar_aviso=True)
    processar()
finally:
    wa.httpx.post = original
with get_cursor() as cur:
    cur.execute("""SELECT status, tentativas, erro FROM whatsapp_mensagens
                    WHERE chave = %s""", (f"erro:{marca}",))
    falha = dict(cur.fetchone())
checar("a Meta recusou: volta para a fila com o motivo, para tentar de novo",
       falha["status"] == "FILA" and falha["tentativas"] == 1
       and "Template name" in (falha["erro"] or ""), falha)
st, c, _h = chamar("GET", f"/unidades/{UNIDADE}/whatsapp", token=token)
checar("e a tela da loja mostra o último erro, no número que falhou",
       "Template name" in (numero(c, FONE_A).get("ultima_mensagem") or ""), numero(c, FONE_A))

print("\n8c. vários números: cada aviso sai pelo seu, e a resposta volta pelo mesmo")
A_ID, B_ID = numero(c, FONE_A)["id"], numero(c, FONE_B)["id"]
avisos_b = [dict(a, whatsapp="B") if a["evento"] == "RESERVA_LEMBRETE" else a for a in avisos]
st, c, _h = gravar(avisos_b, conectado_b=True)
lemb_aviso = next(a for a in c.get("avisos", []) if a["evento"] == "RESERVA_LEMBRETE")
checar("o aviso aponta para o B pela chave dele (mesmo número ainda sem id na tela)",
       st == 200 and lemb_aviso.get("id_whatsapp") == B_ID, (st, lemb_aviso))
st, res6 = reservar("18:00", nome="Helena Dois", fone="47999300001")
ID_R6 = res6.get("id")


def numero_da_msg(evento, id_reserva):
    with get_cursor() as cur:
        cur.execute("""SELECT id, id_whatsapp FROM whatsapp_mensagens WHERE evento = %s
                        AND id_reserva = %s ORDER BY id DESC LIMIT 1""", (evento, id_reserva))
        return dict(cur.fetchone() or {})


checar("a confirmação sai pelo principal (A)",
       numero_da_msg("RESERVA_CONFIRMADA", ID_R6).get("id_whatsapp") == A_ID)
lemb6 = numero_da_msg("RESERVA_LEMBRETE", ID_R6)
checar("e o lembrete pelo número escolhido (B)", lemb6.get("id_whatsapp") == B_ID, lemb6)
st, r, _h = webhook(botao(f"CONFIRMAR:{lemb6.get('id')}", fone="5547999300001", pnid=PNID_B))
checar("o \"Confirmo\" chega pelo B, assinado com o segredo do principal (mesmo app)",
       st == 200 and r.get("respostas") == 1, (st, r))
checar("e o agradecimento volta pelo B", numero_da_msg("RESPOSTA", ID_R6).get("id_whatsapp") == B_ID,
       numero_da_msg("RESPOSTA", ID_R6))
st, r, _h = chamar("GET", f"/publico/whatsapp/webhook?hub.mode=subscribe&hub.verify_token="
                          f"{numero(c, FONE_B)['verify_token']}&hub.challenge=777", cru=True)
checar("a Meta confere o webhook com o token de verificação do B", st == 200 and r == "777", (st, r))

pedidos.clear()
wa.httpx.post = _meta_ok
try:
    gravar(avisos_b, modo="real", conectado_b=True, modo_b="real")
    with get_cursor() as cur:
        wa.enfileirar(cur, UNIDADE, "PEDIDO_CONFIRMADO", f"pedido-b:{marca}", "47999300003",
                      ["Ivo", "12", "Casa", "para retirar", "01/01 às 12:00", "10,00"],
                      ignorar_aviso=True, id_whatsapp=B_ID)
    processar()
finally:
    wa.httpx.post = original
p_b = next((x for x in pedidos if (x.get("json") or {}).get("template", {}).get("name")
            == "pedido_confirmado"), {})
checar("o número pedido (o do catálogo) envia de verdade: Graph API do B, token do principal",
       p_b.get("url", "").endswith(f"/{PNID_B}/messages")
       and p_b.get("headers", {}).get("Authorization") == f"Bearer tok-{marca}", p_b.get("url"))

gravar(avisos_b, conectado_b=False)
st, res7 = reservar("17:00", nome="Ines Desliga", fone="47999300011")
checar("B desconectado: o lembrete escolhido para ele sai pelo principal",
       numero_da_msg("RESERVA_LEMBRETE", res7.get("id")).get("id_whatsapp") == A_ID)
st, r, _h = chamar("PUT", f"/unidades/{UNIDADE}/whatsapp", {"numeros": [
    dict(n, phone_number_id=PNID) for n in numeros()], "avisos": avisos_b}, token)
checar("o mesmo identificador da Meta em dois números: recusa", st == 422, (st, r))
st, c, _h = gravar(avisos_b, com_b=False)
lemb_aviso = next(a for a in c.get("avisos", []) if a["evento"] == "RESERVA_LEMBRETE")
checar("removido o B, o aviso volta ao principal", st == 200 and lemb_aviso.get("id_whatsapp") is None,
       (st, lemb_aviso))
with get_cursor() as cur:
    cur.execute("SELECT whatsapp FROM unidades WHERE id = %s", (UNIDADE,))
    checar("e o cadastro da loja espelha o principal (A)", cur.fetchone()["whatsapp"] == FONE_A)

print("\n9. limpeza")
_devolver()
devolver_a_reserva()

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
