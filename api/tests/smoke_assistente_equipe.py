"""O assistente pelo WhatsApp, etapa 6 (migração 164): os avisos à EQUIPE e o número compartilhado.

🔑 Pedido do dono (25/11/2026): reserva nova e pedido novo avisam a equipe pelo WhatsApp, com
Confirmar / Recusar; o mesmo número serve aos clientes e à equipe; as reservas do dia entram no bom
dia. O que se prova:
- o assistente usa um número de LOJA (número e token vêm de lá; o token não é copiado);
- só recebe quem ligou o aviso, está vinculado e pode AGIR naquela loja;
- reserva PENDENTE avisa; confirmada sozinha não; o reenvio não avisa duas vezes;
- o toque confirma/recusa com a permissão de quem tocou (e sem ela, nada muda); toque repetido
  não muda de novo; a auditoria marca `whatsapp`;
- no número compartilhado, o botão do lembrete do CLIENTE continua indo para a reserva dele, e o
  funcionário vinculado que escreve vai para o assistente; o cliente que escreve recebe uma
  resposta por dia dizendo que o número não é lido;
- o bom dia conta as reservas do dia.

Tudo em MODO SIMULADO; a Anthropic é a FALSA.

    python tests/smoke_assistente_equipe.py        (API de pé na 9200, com DEBUG=true)
"""

import atexit
import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from anthropic_falsa import AnthropicFalsa  # noqa: E402
from comum import preservar_reserva  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402
from psycopg2.extras import Json  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None, cabecalhos=None):
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
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": b.decode(errors="replace")}


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {str(detalhe)[:700]}")


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()
import main  # noqa: E402,F401  — registra o app (o bom dia chama a rota da agenda por dentro)
from relogio import agora_da_casa  # noqa: E402
from services import assistente, assistente_bomdia, assistente_equipe  # noqa: E402

_st, eu = chamar("GET", "/auth/me", token=token)
ID_ADMIN, PRIMEIRO = eu.get("id"), (eu.get("nome") or "").split(" ")[0]
UNIDADE = (eu.get("unidades") or [{}])[0].get("id")
devolver_a_reserva = preservar_reserva(UNIDADE)
marca = str(time.time_ns() // 100)[-6:]
PNID = f"PNIDEQ{marca}"
SEGREDO = f"segredo-eq-{marca}"
TOKEN_LOJA = f"tok-loja-{marca}"
FONE_LOJA = f"(99) 7{marca[:4]}-{marca[2:6]}"
FONE_ADMIN = f"55479{marca}11"
FONE_SEM = f"55479{marca}22"      # vinculado, com o assistente, SEM reservas.editar
FONE_CLIENTE = f"55479{marca}33"
FALSA = AnthropicFalsa()
AMANHA = date.today() + timedelta(days=2)

with get_cursor() as cur:
    cur.execute("SELECT now() AS agora")
    INICIO = cur.fetchone()["agora"]
    cur.execute("SELECT * FROM unidade_whatsapps WHERE id_unidade = %s", (UNIDADE,))
    NUMEROS_ANTES = [dict(x) for x in cur.fetchall()]
    cur.execute("SELECT whatsapp FROM unidades WHERE id = %s", (UNIDADE,))
    ESPELHO_ANTES = cur.fetchone()["whatsapp"]
    cur.execute("SELECT * FROM whatsapp_avisos WHERE id_unidade = %s", (UNIDADE,))
    AVISOS_ANTES = [dict(x) for x in cur.fetchall()]
    cur.execute("SELECT id, id_whatsapp FROM catalogos WHERE id_whatsapp IS NOT NULL")
    CATALOGOS_ANTES = [dict(x) for x in cur.fetchall()]
    cur.execute("SELECT * FROM integracoes WHERE servico = 'WHATSAPP_ASSISTENTE' AND id_unidade IS NULL")
    CONEXAO_ANTES = cur.fetchone()
    CONEXAO_ANTES = dict(CONEXAO_ANTES) if CONEXAO_ANTES else None
    cur.execute("SELECT * FROM usuario_whatsapp WHERE id_usuario = %s", (ID_ADMIN,))
    VINCULO_ANTES = cur.fetchone()
    VINCULO_ANTES = dict(VINCULO_ANTES) if VINCULO_ANTES else None
    cur.execute("DELETE FROM usuario_whatsapp WHERE id_usuario = %s OR wa_id IN (%s, %s)",
                (ID_ADMIN, FONE_ADMIN, FONE_SEM))
    cur.execute("""INSERT INTO usuario_whatsapp (id_usuario, wa_id, verificado_em)
                   VALUES (%s, %s, now())""", (ID_ADMIN, FONE_ADMIN))
    # Quem tem o assistente e vê reservas, mas NÃO pode mudá-las.
    cur.execute("INSERT INTO papeis (nome, descricao) VALUES (%s, 'teste') RETURNING id",
                (f"Teste equipe {marca}",))
    ID_PAPEL = cur.fetchone()["id"]
    for chave in ("integracao.whatsapp_assistente", "reservas.ver"):
        cur.execute("INSERT INTO papel_permissoes (id_papel, chave) VALUES (%s, %s)", (ID_PAPEL, chave))
    cur.execute("INSERT INTO usuarios (nome, email, senha_hash) VALUES (%s, %s, 'x') RETURNING id",
                ("Rui Sem Permissao", f"smoke.equipe.{marca}@teste.com"))
    ID_SEM = cur.fetchone()["id"]
    cur.execute("INSERT INTO usuario_papeis (id_usuario, id_papel, id_unidade) VALUES (%s, %s, NULL)",
                (ID_SEM, ID_PAPEL))
    cur.execute("""INSERT INTO usuario_whatsapp (id_usuario, wa_id, verificado_em, avisos_reserva)
                   VALUES (%s, %s, now(), true)""", (ID_SEM, FONE_SEM))
    cur.execute("SELECT id FROM produtos ORDER BY id LIMIT 1")
    UM_PRODUTO = cur.fetchone()["id"]
criados = {"pedidos": []}


def _devolver():
    with get_cursor() as cur:
        cur.execute("DELETE FROM assistente_mensagens WHERE criada_em >= %s", (INICIO,))
        cur.execute("DELETE FROM assistente_conversa WHERE criada_em >= %s", (INICIO,))
        cur.execute("DELETE FROM whatsapp_mensagens WHERE id_unidade = %s AND criada_em >= %s",
                    (UNIDADE, INICIO))
        if criados["pedidos"]:
            cur.execute("DELETE FROM pedido_historico WHERE id_pedido = ANY(%s)", (criados["pedidos"],))
            cur.execute("DELETE FROM pedidos WHERE id = ANY(%s)", (criados["pedidos"],))
        cur.execute("DELETE FROM usuario_whatsapp WHERE id_usuario = ANY(%s)", ([ID_ADMIN, ID_SEM],))
        if VINCULO_ANTES:
            v = VINCULO_ANTES
            cur.execute(f"INSERT INTO usuario_whatsapp ({', '.join(v)}) VALUES "
                        f"({', '.join(['%s'] * len(v))})", list(v.values()))
        cur.execute("DELETE FROM usuario_papeis WHERE id_usuario = %s", (ID_SEM,))
        cur.execute("DELETE FROM auditoria WHERE id_usuario = %s", (ID_SEM,))
        cur.execute("DELETE FROM usuarios WHERE id = %s", (ID_SEM,))
        cur.execute("DELETE FROM papeis WHERE id = %s", (ID_PAPEL,))
        cur.execute("DELETE FROM integracoes WHERE servico = 'WHATSAPP_ASSISTENTE' AND id_unidade IS NULL")
        if CONEXAO_ANTES:
            c = CONEXAO_ANTES
            cur.execute(f"INSERT INTO integracoes ({', '.join(c)}) VALUES "
                        f"({', '.join(['%s'] * len(c))})",
                        [Json(x) if isinstance(x, dict) else x for x in c.values()])
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
            cur.execute("UPDATE catalogos SET id_whatsapp = %s WHERE id = %s", (c["id_whatsapp"], c["id"]))
    FALSA.fechar()


atexit.register(_devolver)


def _post(corpo):
    bruto = json.dumps(corpo).encode()
    cab = {"X-Hub-Signature-256": "sha256=" + hmac.new(SEGREDO.encode(), bruto, hashlib.sha256).hexdigest()}
    return chamar("POST", "/publico/whatsapp/webhook", bruto, cabecalhos=cab)


_seq = [0]


def mensagem(fone, **campos):
    _seq[0] += 1
    return _post({"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": PNID}, "messages": [
        {"from": fone, "id": f"wamid.eq.{marca}.{_seq[0]}", **campos}]}}]}]})


def tocar(payload, fone=FONE_ADMIN):
    return mensagem(fone, type="button", button={"payload": payload, "text": "x"})


def da_equipe(fone=FONE_ADMIN, chave_like="%"):
    with get_cursor() as cur:
        cur.execute("""SELECT id, chave, texto, modelo, status FROM assistente_mensagens
                        WHERE criada_em >= %s AND telefone = %s AND chave LIKE %s ORDER BY id""",
                    (INICIO, fone, chave_like))
        return [dict(x) for x in cur.fetchall()]


def esperar(fone, antes, segundos=15):
    for _ in range(int(segundos / 0.3)):
        rs = da_equipe(fone)
        if len(rs) > antes:
            return rs[-1]
        time.sleep(0.3)
    return {}


def da_loja(evento=None):
    with get_cursor() as cur:
        cur.execute("""SELECT id, evento, chave, texto, telefone, status FROM whatsapp_mensagens
                        WHERE id_unidade = %s AND criada_em >= %s
                          AND (%s::text IS NULL OR evento = %s) ORDER BY id""",
                    (UNIDADE, INICIO, evento, evento))
        return [dict(x) for x in cur.fetchall()]


def status_reserva(id_r):
    with get_cursor() as cur:
        cur.execute("SELECT status FROM reservas WHERE id = %s", (id_r,))
        return cur.fetchone()["status"]


print("0. o cenário: a loja com um número conectado, salão, reservas que esperam a casa")
chamar("PUT", f"/unidades/{UNIDADE}/parametros", {"reservas_ligado": True}, token)
with get_cursor() as cur:
    cur.execute("""DELETE FROM reserva_mesas WHERE id_reserva IN
                     (SELECT id FROM reservas WHERE id_unidade = %s)""", (UNIDADE,))
    cur.execute("DELETE FROM reservas WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM reserva_bloqueios WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM reserva_dias_especiais WHERE id_unidade = %s", (UNIDADE,))
_st, sal = chamar("POST", "/reservas/saloes", {"nome": f"Salao EQ {marca}"}, token)
for n in range(1, 5):
    chamar("POST", "/reservas/mesas", {"id_salao": sal.get("id"), "nome": f"EQ{marca}-{n}", "lugares": 4}, token)
_st, cfg = chamar("GET", "/reservas/configuracao", token=token)
st, _r = chamar("PUT", "/reservas/configuracao", {
    **cfg, "confirmacao": "MANUAL", "antecedencia_min_horas": 0, "teto_online": 20,
    "horarios": [{"dia_semana": d, "aberto": True, "abre": "08:00", "fecha": "23:30",
                  "ultima_reserva": "22:00"} for d in range(1, 8)],
    "permanencias": [{"nome": "Unica", "de": "08:00", "ate": "23:30", "minutos": 60}]}, token)
checar("a agenda do cenário grava (confirmação manual)", st == 200, _r)

_st, c = chamar("GET", f"/unidades/{UNIDADE}/whatsapp", token=token)
OUTROS = [{"id": n["id"], "rotulo": n["rotulo"], "numero": n["numero"], "principal": False,
           "conectado": False, "modo": "simulado"} for n in c.get("numeros") or []]
avisos_loja = [{"evento": e, "ativo": True, "modelo": e.lower(), "idioma": "pt_BR",
                "antecedencia": 3 if e == "RESERVA_LEMBRETE" else None}
               for e in ("RESERVA_RECEBIDA", "RESERVA_CONFIRMADA", "RESERVA_LEMBRETE", "RESERVA_CANCELADA")]
st, c = chamar("PUT", f"/unidades/{UNIDADE}/whatsapp", {"numeros": [
    {"chave": "A", "rotulo": "Avisos", "numero": FONE_LOJA, "principal": True, "conectado": True,
     "modo": "simulado", "phone_number_id": PNID, "api_versao": "v21.0", "token": TOKEN_LOJA,
     "app_secret": SEGREDO}] + OUTROS, "avisos": avisos_loja}, token)
ID_W = next((n["id"] for n in (c or {}).get("numeros") or [] if n["numero"] == FONE_LOJA), None)
checar("o número da loja grava, conectado", st == 200 and ID_W, (st, c))


def config(**kw):
    corpo = {"ativa": True, "modo": "simulado", "id_whatsapp_loja": ID_W, "url_api": FALSA.url,
             "limite_diario": 500, "equipe_reserva_ligado": True, "equipe_pedido_ligado": True} | kw
    return chamar("PUT", "/assistente/config", corpo, token)


def reservar(hora, nome, fone, origem="SITE"):
    st, r = chamar("POST", "/reservas", {"data": str(AMANHA), "hora": hora, "pessoas": 3, "nome": nome,
                                         "telefone": fone, "origem": origem}, token)
    return st, r


print("\n1. o assistente no número da loja")
st, r = config(phone_number_id=PNID, id_whatsapp_loja=None, numero="(99) 5555-0009")
checar("digitar a identificação de um número de loja é recusado (422) — escolhe-se o número",
       st == 422 and "Número de loja" in str(r), (st, r))
st, r = config(id_whatsapp_loja=999999)
checar("número de loja que não existe é recusado (422)", st == 422, (st, r))
st, c = config()
checar("grava com o número da loja: número e identificação vêm de lá",
       st == 200 and c.get("compartilhado") and c.get("numero") == FONE_LOJA
       and c.get("phone_number_id") == PNID and c.get("token_configurado")
       and any(n["id"] == ID_W for n in c.get("numeros_das_lojas") or []), (st, c))
checar("os avisos à equipe voltam com os textos para a Meta e os botões",
       (c.get("equipe") or {}).get("reserva", {}).get("ligado")
       and "{{6}}" in c["equipe"]["reserva"]["texto_do_modelo"]
       and "{{7}}" in c["equipe"]["pedido"]["texto_do_modelo"]
       and c["equipe"]["botoes"] == ["Confirmar", "Recusar"], c.get("equipe"))
with get_cursor() as cur:
    cur.execute("SELECT credenciais, config FROM integracoes WHERE servico = 'WHATSAPP_ASSISTENTE' AND id_unidade IS NULL")
    linha = cur.fetchone()
    from services import segredos
    propria = segredos.decifrar(linha["credenciais"]) if linha["credenciais"] else {}
checar("o token da loja NÃO é copiado para a linha do assistente",
       propria.get("token") != TOKEN_LOJA and propria.get("app_secret") != SEGREDO
       and not linha["config"].get("phone_number_id"), linha["config"])
st, c = config(modo="real")
checar("enviar de verdade usa o token da loja (sem digitar de novo)", st == 200 and c.get("modo") == "real", (st, c))
config()

print("\n2. o Perfil: cada pessoa escolhe")
st, v = chamar("GET", "/assistente/vinculo", token=token)
ae = (v or {}).get("avisos_equipe") or {}
checar("o estado diz que a casa ligou e que o admin pode agir",
       ae.get("reserva", {}).get("casa") and ae["reserva"]["pode"] and not ae["reserva"]["ligado"]
       and ae.get("pedido", {}).get("pode"), ae)
st, v = chamar("PUT", "/assistente/vinculo/avisos", {"reserva": True, "pedido": True}, token)
checar("liga os dois avisos", st == 200 and v["avisos_equipe"]["reserva"]["ligado"]
       and v["avisos_equipe"]["pedido"]["ligado"], (st, v))

print("\n3. a reserva nova")
st, res = reservar("19:00", "Paula Pendente", "47999400001")
ID_R = (res or {}).get("id")
checar("a reserva do site nasce PENDENTE", st == 201 and res.get("status") == "PENDENTE", (st, res))
with get_cursor() as cur:
    n = assistente_equipe.reserva_nova(cur, UNIDADE, ID_R)
    n2 = assistente_equipe.reserva_nova(cur, UNIDADE, ID_R)
avisos_admin = da_equipe(FONE_ADMIN, "equipe:reserva:%")
m = avisos_admin[0] if avisos_admin else {}
modelo = m.get("modelo") or {}
checar("o admin recebe UM aviso (o reenvio não repete)", n == 1 and n2 == 0 and len(avisos_admin) == 1,
       (n, n2, avisos_admin))
checar("quem não pode mudar reservas não recebe, mesmo com a opção ligada",
       not da_equipe(FONE_SEM, "equipe:reserva:%"))
checar("vai como modelo, com o resumo e os botões Confirmar / Recusar",
       modelo.get("nome") == "botane_reserva_nova" and modelo.get("variaveis", [None] * 5)[1] == "Paula Pendente"
       and modelo["variaveis"][3] == "19:00" and modelo["variaveis"][4] == "3"
       and modelo.get("botoes") == [f"EQUIPE:reserva:CONFIRMAR:{ID_R}", f"EQUIPE:reserva:RECUSAR:{ID_R}"]
       and "Paula Pendente" in m.get("texto", ""), m)
carga = assistente._payload({"telefone": FONE_ADMIN, "texto": m.get("texto"), "modelo": modelo})
checar("o envio monta o modelo com os dois botões de resposta rápida",
       carga.get("type") == "template"
       and [b["parameters"][0]["payload"] for b in carga["template"]["components"] if b["type"] == "button"]
       == modelo.get("botoes"), carga)
st, conf = reservar("12:00", "Caio Balcao", "47999400002", origem="BALCAO")
with get_cursor() as cur:
    checar("reserva já confirmada não avisa a equipe",
           assistente_equipe.reserva_nova(cur, UNIDADE, conf.get("id")) == 0)

print("\n4. o toque")
antes = len(da_equipe(FONE_SEM))
tocar(f"EQUIPE:reserva:CONFIRMAR:{ID_R}", fone=FONE_SEM)
r = esperar(FONE_SEM, antes)
checar("sem reservas.editar, o toque não muda nada", "não pode mudar as reservas" in (r.get("texto") or "")
       and status_reserva(ID_R) == "PENDENTE", (r, status_reserva(ID_R)))
antes = len(da_equipe())
tocar(f"EQUIPE:reserva:CONFIRMAR:{ID_R}")
r = esperar(FONE_ADMIN, antes)
checar("o admin confirma pelo botão", status_reserva(ID_R) == "CONFIRMADA"
       and (r.get("texto") or "").startswith(f"Feito, {PRIMEIRO}") and "confirmada" in r["texto"], r)
checar("o cliente recebe o aviso de confirmada (e o lembrete), como pela tela",
       any(x["evento"] == "RESERVA_CONFIRMADA" for x in da_loja()), da_loja())
with get_cursor() as cur:
    cur.execute("""SELECT origem, id_usuario FROM auditoria WHERE entidade = 'reserva' AND id_entidade = %s
                    AND acao = 'status' ORDER BY id DESC LIMIT 1""", (str(ID_R),))
    aud = cur.fetchone() or {}
checar("a auditoria marca a origem whatsapp e quem tocou", aud.get("origem") == "whatsapp"
       and aud.get("id_usuario") == ID_ADMIN, aud)
antes = len(da_equipe())
tocar(f"EQUIPE:reserva:RECUSAR:{ID_R}")
r = esperar(FONE_ADMIN, antes)
checar("recusar depois de confirmada: nada muda, e a resposta diz o porquê",
       status_reserva(ID_R) == "CONFIRMADA" and "Nada mudou" in (r.get("texto") or ""), r)
st, res2 = reservar("20:00", "Quim Recusa", "47999400003")
antes = len(da_equipe())
tocar(f"EQUIPE:reserva:RECUSAR:{res2.get('id')}")
r = esperar(FONE_ADMIN, antes)
checar("Recusar cancela a reserva pendente", status_reserva(res2.get("id")) == "CANCELADA"
       and "recusada" in (r.get("texto") or ""), r)

print("\n5. o pedido novo")
with get_cursor() as cur:
    cur.execute("SELECT coalesce(max(numero), 0) + 1000 AS n FROM pedidos WHERE id_unidade = %s", (UNIDADE,))
    NUM = cur.fetchone()["n"]
    cur.execute("""INSERT INTO pedidos (id_unidade, numero, nome, telefone, modo, para_quando,
                                        forma_pagamento, subtotal, total, chave)
                   VALUES (%s, %s, 'Rita Pedido', '47999400004', 'RETIRADA', now() + interval '2 hours',
                           'RETIRADA', 42.5, 42.5, %s) RETURNING id""", (UNIDADE, NUM, f"eq-{marca}"))
    ID_P = cur.fetchone()["id"]
    criados["pedidos"].append(ID_P)
    cur.execute("""INSERT INTO pedido_itens (id_pedido, id_produto, nome, quantidade, preco_unitario, total, ordem)
                   VALUES (%s, %s, 'Pao de fermentacao\nnatural', 2, 15, 30, 0),
                          (%s, %s, 'Cafe', 1.5, 8.33, 12.5, 1)""", (ID_P, UM_PRODUTO, ID_P, UM_PRODUTO))
    n = assistente_equipe.pedido_novo(cur, UNIDADE, ID_P)
p = (da_equipe(FONE_ADMIN, "equipe:pedido:%") or [{}])[0]
pv = (p.get("modelo") or {}).get("variaveis") or []
checar("o pedido novo avisa, com número, itens numa linha só e total",
       n == 1 and pv[:1] == [str(NUM)] and pv[5] == "2x Pao de fermentacao natural, 1,5x Cafe"
       and pv[6] == "42,50" and all("\n" not in x for x in pv), (n, p))
antes = len(da_equipe())
tocar(f"EQUIPE:pedido:CONFIRMAR:{ID_P}")
r = esperar(FONE_ADMIN, antes)
with get_cursor() as cur:
    cur.execute("SELECT situacao, confirmado_por FROM pedidos WHERE id = %s", (ID_P,))
    ped = cur.fetchone()
checar("Confirmar confirma o pedido em nome de quem tocou", ped["situacao"] == "CONFIRMADO"
       and ped["confirmado_por"] == ID_ADMIN and "confirmado" in (r.get("texto") or ""), (ped, r))
antes = len(da_equipe())
tocar(f"EQUIPE:pedido:RECUSAR:{ID_P}")
r = esperar(FONE_ADMIN, antes)
checar("recusar pedido já confirmado: nada muda", "Nada mudou" in (r.get("texto") or ""), r)

print("\n6. o número compartilhado: cada um para o seu lado")
with get_cursor() as cur:
    cur.execute("SELECT id FROM whatsapp_mensagens WHERE id_unidade = %s AND evento = 'RESERVA_LEMBRETE' "
                "AND id_reserva = %s ORDER BY id DESC LIMIT 1", (UNIDADE, ID_R))
    lemb = cur.fetchone()
tocar(f"CONFIRMAR:{lemb['id'] if lemb else 0}", fone="5547999400001")
with get_cursor() as cur:
    cur.execute("SELECT presenca FROM reservas WHERE id = %s", (ID_R,))
    pres = cur.fetchone()["presenca"]
checar("o botão do lembrete do CLIENTE vai para a reserva dele (presença confirmada)",
       lemb and pres == "CONFIRMADA", (lemb, pres))
FALSA.pedidos.clear()
antes = len(da_equipe())
mensagem(FONE_ADMIN, type="text", text={"body": "quais as reservas de hoje?"})
r = esperar(FONE_ADMIN, antes)
checar("o funcionário vinculado que escreve fala com o assistente",
       (r.get("texto") or "").startswith("ok: "), r)
mensagem(FONE_CLIENTE, type="text", text={"body": "oi, posso levar meu cachorro?"})
mensagem(FONE_CLIENTE, type="text", text={"body": "alô?"})
resp = [x for x in da_loja("RESPOSTA") if x["telefone"] == FONE_CLIENTE]
checar("o cliente que escreve recebe UMA resposta por dia: o número não é lido",
       len(resp) == 1 and "não recebe mensagens" in resp[0]["texto"], resp)
checar("e o cliente não cai no assistente", not da_equipe(FONE_CLIENTE))

print("\n7. o bom dia conta as reservas do dia")
checar("o resumo junta agenda e reservas",
       assistente_bomdia.resumo(3, 2, 9) == "3 itens na agenda de produção e 2 reservas (9 pessoas)"
       and assistente_bomdia.resumo(0, 1, 1) == "1 reserva (1 pessoa)"
       and assistente_bomdia.resumo(0, 0, 0) == "nada pendente")
n_res, pessoas = assistente_bomdia.contar_reservas(ID_ADMIN, AMANHA)
checar("conta as reservas vivas do dia (a recusada não)", n_res == 2 and pessoas == 6, (n_res, pessoas))
checar("quem só vê reservas também conta", assistente_bomdia.contar_reservas(ID_SEM, AMANHA)[0] == 2)
checar("o texto do modelo não termina em variável",
       not assistente_bomdia.TEXTO_DO_MODELO.rstrip().endswith("}}"))

print("\n8. limpeza")
_devolver()
atexit.unregister(_devolver)
devolver_a_reserva()

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
