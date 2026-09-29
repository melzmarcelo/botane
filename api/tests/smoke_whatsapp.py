"""WhatsApp por loja: a fila, os avisos, o modo simulado e o webhook da Meta (migração 099).

🔑 **Pedido do dono (28/09/2026):** mensagens configuráveis por loja (reserva, confirmação,
prêmio…) e a confirmação de presença pelo WhatsApp, recebendo o botão que o cliente tocou.

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
PNID = f"PNID{marca}"
SEGREDO = f"segredo-{marca}"

# A integração e os avisos da loja: fotografados e devolvidos no fim.
with get_cursor() as cur:
    cur.execute("SELECT * FROM integracoes WHERE id_unidade = %s AND servico = 'whatsapp'",
                (UNIDADE,))
    INTEG_ANTES = cur.fetchone()
    INTEG_ANTES = dict(INTEG_ANTES) if INTEG_ANTES else None
    cur.execute("SELECT * FROM whatsapp_avisos WHERE id_unidade = %s", (UNIDADE,))
    AVISOS_ANTES = [dict(x) for x in cur.fetchall()]


def _devolver():
    with get_cursor() as cur:
        cur.execute("DELETE FROM whatsapp_mensagens WHERE id_unidade = %s AND criada_em >= %s",
                    (UNIDADE, INICIO))
        cur.execute("DELETE FROM whatsapp_avisos WHERE id_unidade = %s", (UNIDADE,))
        for a in AVISOS_ANTES:
            cur.execute(f"INSERT INTO whatsapp_avisos ({', '.join(a)}) VALUES "
                        f"({', '.join(['%s'] * len(a))})", list(a.values()))
        cur.execute("DELETE FROM integracoes WHERE id_unidade = %s AND servico = 'whatsapp'",
                    (UNIDADE,))
        if INTEG_ANTES:
            i = {k: v for k, v in INTEG_ANTES.items() if k != "id"}
            cur.execute(f"INSERT INTO integracoes ({', '.join(i)}) VALUES "
                        f"({', '.join(['%s'] * len(i))})",
                        [json.dumps(v) if k == "config" and v is not None else v
                         for k, v in i.items()])


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


def botao(payload, fone="5547999300009"):
    return {"entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": PNID},
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


print("\n1. a configuração da loja")
st, c, _h = chamar("GET", f"/unidades/{UNIDADE}/whatsapp", token=token)
checar("nasce desligada, em modo simulado, com o token de verificação do webhook",
       st == 200 and c.get("modo") == "simulado" and c.get("verify_token"), (st, c))
checar("com os 7 avisos e o texto pronto de cada modelo",
       len(c.get("avisos") or []) == 8 and all("{{1}}" in a["texto"] for a in c["avisos"]),
       len(c.get("avisos") or []))
VERIFY = c.get("verify_token")
base = {"ativa": True, "modo": "real", "phone_number_id": PNID, "numero": "(47) 99910-5033",
        "api_versao": "v21.0", "token": "", "app_secret": "", "avisos": []}
st, r, _h = chamar("PUT", f"/unidades/{UNIDADE}/whatsapp", base, token)
checar("enviar de verdade sem token é recusado", st == 400, (st, r))
avisos = [{"evento": e, "ativo": e in ("RESERVA_CONFIRMADA", "RESERVA_LEMBRETE",
                                        "RESERVA_CANCELADA", "PREMIO_GANHO"),
           "modelo": e.lower(), "idioma": "pt_BR",
           "antecedencia": 3 if e == "RESERVA_LEMBRETE" else None}
          for e in ("RESERVA_RECEBIDA", "RESERVA_CONFIRMADA", "RESERVA_LEMBRETE",
                    "RESERVA_CANCELADA", "PREMIO_GANHO", "PREMIO_VENCENDO", "ANIVERSARIO")]
st, c, _h = chamar("PUT", f"/unidades/{UNIDADE}/whatsapp",
                   {**base, "modo": "simulado", "token": f"tok-{marca}",
                    "app_secret": SEGREDO, "avisos": avisos}, token)
checar("liga em modo simulado, com token e segredo guardados",
       st == 200 and c.get("token_configurado") and c.get("segredo_configurado"), (st, c))
checar("e o token NÃO volta na resposta", f"tok-{marca}" not in json.dumps(c)
       and SEGREDO not in json.dumps(c))
st, c, _h = chamar("PUT", f"/unidades/{UNIDADE}/whatsapp", {**base, "modo": "simulado",
                                                           "avisos": avisos}, token)
checar("salvar de novo com o token em branco MANTÉM o token", c.get("token_configurado"), c)

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
chamar("PUT", f"/unidades/{UNIDADE}/whatsapp", {**base, "modo": "simulado", "avisos": avisos_off},
       token)
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
chamar("PUT", f"/unidades/{UNIDADE}/whatsapp", {**base, "ativa": False, "modo": "simulado",
                                               "avisos": avisos}, token)
st, res5 = reservar("15:00", nome="Fabio Fora", fone="47999300004")
checar("com o WhatsApp desligado na loja, nada entra na fila", not msgs(id_reserva=res5.get("id")))

print("\n8b. o envio de verdade (com a Meta simulada dentro do teste)")
# ⚠️ Sem conta na Meta: troca o `httpx.post` do serviço por um falso, que devolve o que a
# Meta devolveria — e guarda o pedido, para conferir o que o Botané MANDARIA.
from services import whatsapp as wa  # noqa: E402

chamar("PUT", f"/unidades/{UNIDADE}/whatsapp", {**base, "ativa": True, "modo": "real",
                                               "token": f"tok-{marca}", "avisos": avisos}, token)
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
checar("e a tela da loja mostra o último erro", "Template name" in (c.get("ultima_mensagem") or ""),
       c.get("ultima_mensagem"))

print("\n9. limpeza")
_devolver()
devolver_a_reserva()

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
