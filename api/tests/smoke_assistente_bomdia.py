"""O assistente pelo WhatsApp, etapa 5 (migração 155): o "bom dia" com as pendências.

🔑 Estudo em `docs/assistente-whatsapp-estudo.md`, etapa 5. O que se prova: só recebe quem ligou
a opção; só dentro da janela do horário e nos dias marcados; uma vez por dia; sai como MODELO da
Meta com os dois botões; a contagem respeita a permissão de quem recebe; "só com pendência"
pula quem não tem nada; "Ver pendências" vira pergunta ao Claude e "Parar" desliga.

⚠️ A varredura roda NESTE processo (`assistente_bomdia.varrer(agora=…)`), com um horário fingido:
a suíte não depende do relógio. O horário configurado fica seis horas longe da hora real, para o
laço da API (que varre de verdade a cada 30 s) não mandar junto. A Anthropic é a FALSA.

    python tests/smoke_assistente_bomdia.py        (API de pé na 9200, com DEBUG=true)
"""

import atexit
import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

import comum  # noqa: E402
from anthropic_falsa import AnthropicFalsa  # noqa: E402
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
import main  # noqa: E402,F401  — registra o app: a contagem chama a rota da agenda por dentro
from relogio import agora_da_casa  # noqa: E402
from services import assistente, assistente_bomdia  # noqa: E402

_st, eu = chamar("GET", "/auth/me", token=token)
ID_ADMIN, NOME_ADMIN = eu.get("id"), eu.get("nome")
PRIMEIRO = NOME_ADMIN.split(" ")[0]
marca = str(time.time_ns() // 100)[-6:]
PNID = f"PNIDBD{marca}"
SEGREDO = f"segredo-bd-{marca}"
FONE = f"55479{marca}88"
FONE_SO = f"55479{marca}99"
FALSA = AnthropicFalsa()
AGORA = agora_da_casa()
HORA = (AGORA.hour + 6) % 24
NA_JANELA = AGORA.replace(hour=HORA, minute=10, second=0, microsecond=0)
ANTES_DA_HORA = NA_JANELA.replace(minute=0).replace(hour=(HORA - 1) % 24)
DEPOIS = NA_JANELA.replace(hour=(HORA + 3) % 24)
HOJE = NA_JANELA.date()
central = comum.garantir_local(lambda m, c, corpo=None, token=None: chamar(m, c, corpo, token), token)
criados = {"produtos": []}

with get_cursor() as cur:
    cur.execute("SELECT now() AS agora")
    INICIO = cur.fetchone()["agora"]
    cur.execute("SELECT * FROM integracoes WHERE servico = 'WHATSAPP_ASSISTENTE' AND id_unidade IS NULL")
    CONEXAO_ANTES = cur.fetchone()
    CONEXAO_ANTES = dict(CONEXAO_ANTES) if CONEXAO_ANTES else None
    cur.execute("SELECT * FROM usuario_whatsapp WHERE id_usuario = %s", (ID_ADMIN,))
    VINCULO_ANTES = cur.fetchone()
    VINCULO_ANTES = dict(VINCULO_ANTES) if VINCULO_ANTES else None
    cur.execute("DELETE FROM usuario_whatsapp WHERE id_usuario = %s OR wa_id IN (%s, %s)",
                (ID_ADMIN, FONE, FONE_SO))
    cur.execute("INSERT INTO usuario_whatsapp (id_usuario, wa_id, verificado_em) VALUES (%s, %s, now())",
                (ID_ADMIN, FONE))
    # Quem só tem o assistente, sem permissão de agenda: a contagem dele dá zero.
    cur.execute("INSERT INTO papeis (nome, descricao) VALUES (%s, 'teste') RETURNING id",
                (f"Teste bom dia {marca}",))
    ID_PAPEL = cur.fetchone()["id"]
    cur.execute("INSERT INTO papel_permissoes (id_papel, chave) VALUES (%s, 'integracao.whatsapp_assistente')",
                (ID_PAPEL,))
    cur.execute("INSERT INTO usuarios (nome, email, senha_hash) VALUES (%s, %s, 'x') RETURNING id",
                ("Bia Sem Agenda", f"smoke.bomdia.{marca}@teste.com"))
    ID_SO = cur.fetchone()["id"]
    cur.execute("INSERT INTO usuario_papeis (id_usuario, id_papel, id_unidade) VALUES (%s, %s, NULL)",
                (ID_SO, ID_PAPEL))
    cur.execute("""INSERT INTO usuario_whatsapp (id_usuario, wa_id, verificado_em, bom_dia)
                   VALUES (%s, %s, now(), true)""", (ID_SO, FONE_SO))


def _devolver():
    with get_cursor() as cur:
        cur.execute("DELETE FROM assistente_mensagens WHERE criada_em >= %s", (INICIO,))
        cur.execute("DELETE FROM assistente_conversa WHERE id_usuario = ANY(%s) AND criada_em >= %s",
                    ([ID_ADMIN, ID_SO], INICIO))
        cur.execute("DELETE FROM usuario_whatsapp WHERE id_usuario = ANY(%s)", ([ID_ADMIN, ID_SO],))
        if VINCULO_ANTES:
            v = VINCULO_ANTES
            cur.execute(f"INSERT INTO usuario_whatsapp ({', '.join(v)}) VALUES "
                        f"({', '.join(['%s'] * len(v))})", list(v.values()))
        cur.execute("DELETE FROM usuario_papeis WHERE id_usuario = %s", (ID_SO,))
        cur.execute("DELETE FROM auditoria WHERE id_usuario = %s", (ID_SO,))
        cur.execute("DELETE FROM usuarios WHERE id = %s", (ID_SO,))
        cur.execute("DELETE FROM papeis WHERE id = %s", (ID_PAPEL,))
        cur.execute("DELETE FROM integracoes WHERE servico = 'WHATSAPP_ASSISTENTE' AND id_unidade IS NULL")
        if CONEXAO_ANTES:
            c = CONEXAO_ANTES
            cur.execute(f"INSERT INTO integracoes ({', '.join(c)}) VALUES "
                        f"({', '.join(['%s'] * len(c))})",
                        [Json(x) if isinstance(x, dict) else x for x in c.values()])
    for p in criados["produtos"]:
        chamar("DELETE", f"/produtos/{p}", token=token)
    FALSA.fechar()


atexit.register(_devolver)


def config(**kw):
    corpo = {"ativa": True, "modo": "simulado", "numero": "(99) 5555-0003", "phone_number_id": PNID,
             "api_versao": "v21.0", "app_secret": SEGREDO, "url_api": FALSA.url, "limite_diario": 500,
             "bom_dia_ligado": True, "bom_dia_hora": f"{HORA:02d}:00", "bom_dia_dias": [1, 2, 3, 4, 5, 6, 7],
             "bom_dia_so_com_pendencia": True} | kw
    return chamar("PUT", "/assistente/config", corpo, token)


def _post(corpo):
    bruto = json.dumps(corpo).encode()
    cab = {"X-Hub-Signature-256": "sha256=" + hmac.new(SEGREDO.encode(), bruto, hashlib.sha256).hexdigest()}
    return chamar("POST", "/publico/whatsapp/webhook", bruto, cabecalhos=cab)


_seq = [0]


def tocar(payload, fone=FONE):
    _seq[0] += 1
    return _post({"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": PNID}, "messages": [
        {"from": fone, "id": f"wamid.bd.{marca}.{_seq[0]}", "type": "button",
         "button": {"payload": payload, "text": "x"}}]}}]}]})


def bons_dias(fone=FONE):
    with get_cursor() as cur:
        cur.execute("""SELECT id, texto, modelo, status, telefone FROM assistente_mensagens
                        WHERE criada_em >= %s AND telefone = %s AND chave LIKE 'bomdia:%%'
                        ORDER BY id""", (INICIO, fone))
        return [dict(x) for x in cur.fetchall()]


def respostas(fone=FONE):
    with get_cursor() as cur:
        cur.execute("""SELECT id, texto FROM assistente_mensagens WHERE criada_em >= %s
                        AND telefone = %s ORDER BY id""", (INICIO, fone))
        return [dict(x) for x in cur.fetchall()]


def esperar(antes, segundos=15, fone=FONE):
    for _ in range(int(segundos / 0.3)):
        rs = respostas(fone)
        if len(rs) > antes:
            return rs[-1]
        time.sleep(0.3)
    return {}


def zerar_dia():
    with get_cursor() as cur:
        cur.execute("UPDATE usuario_whatsapp SET bom_dia_em = NULL WHERE id_usuario = ANY(%s)",
                    ([ID_ADMIN, ID_SO],))
        cur.execute("DELETE FROM assistente_mensagens WHERE criada_em >= %s AND chave LIKE 'bomdia:%%'",
                    (INICIO,))


print("0. o cenário: uma linha de hoje na agenda")
st, f = chamar("POST", "/produtos", {"nome": f"FARINHA BD {marca}", "tipo": "INSUMO", "um_estoque": "KG",
                                     "status": "ATIVO"}, token=token)
criados["produtos"].append((f or {}).get("id"))
st, p = chamar("POST", "/produtos", {"nome": f"PAO BD {marca}", "tipo": "PRODUZIDO", "um_estoque": "UN",
                                     "producao_propria": True, "status": "ATIVO",
                                     "id_local_padrao": central["id"]}, token=token)
pao = (p or {}).get("id")
criados["produtos"].append(pao)
st, fi = chamar("POST", "/fichas", {"id_produto": pao, "rendimento_qtd": 10, "rendimento_um": "UN",
                                    "porcoes": 10, "itens": [{"id_insumo": (f or {}).get("id"),
                                                              "qtd_bruta": 1, "um": "KG"}]}, token=token)
chamar("POST", f"/fichas/{(fi or {}).get('id')}/homologar", {}, token=token)
st, ag = chamar("POST", "/producao-agenda", {"id_produto": pao, "quantidade": 10,
                                             "data_prevista": str(date.today())}, token=token)
checar("a linha de hoje nasce", st == 201, (st, ag))

print("\n1. a configuração da casa")
st, r = config(bom_dia_hora="25:00")
checar("hora inválida é recusada (422)", st == 422, st)
st, r = config(bom_dia_dias=[0, 8])
checar("dia fora de 1–7 é recusado (422)", st == 422, st)
st, c = config()
bd = (c or {}).get("bom_dia") or {}
checar("grava, e devolve o texto do modelo e os botões para cadastrar na Meta",
       st == 200 and bd.get("ligado") and bd.get("hora") == f"{HORA:02d}:00" and bd.get("modelo") == "botane_bom_dia"
       and "{{1}}" in bd.get("texto_do_modelo", "") and bd.get("botoes") == ["Ver pendências", "Parar o bom dia"],
       (st, bd))

print("\n2. quem recebe, e quando")
assistente_bomdia.varrer(NA_JANELA)
checar("quem não ligou a opção não recebe", not bons_dias(), bons_dias())
zerar_dia()
st, v = chamar("PUT", "/assistente/vinculo/bom-dia", {"ligado": True}, token)
checar("a pessoa liga no Perfil; o estado diz a hora da casa",
       st == 200 and v.get("bom_dia") is True and (v.get("bom_dia_casa") or {}).get("hora") == f"{HORA:02d}:00",
       (st, v))
checar("antes da hora, nada", assistente_bomdia.varrer(ANTES_DA_HORA) == 0 and not bons_dias())
checar("passada a janela (2 h), nada — o contêiner que reinicia à tarde não manda bom dia",
       assistente_bomdia.varrer(DEPOIS) == 0 and not bons_dias())
config(bom_dia_dias=[d for d in range(1, 8) if d != NA_JANELA.isoweekday()])
checar("em dia não marcado, nada", assistente_bomdia.varrer(NA_JANELA) == 0 and not bons_dias())
config()
enviados = assistente_bomdia.varrer(NA_JANELA)
bd_admin = bons_dias()
checar("na janela, sai o bom dia", enviados >= 1 and len(bd_admin) == 1, (enviados, bd_admin))
m = bd_admin[0] if bd_admin else {}
modelo = m.get("modelo") or {}
n = int(str((modelo.get("variaveis") or ["", "0"])[1]).split(" ")[0]) if modelo.get("variaveis") and \
    modelo["variaveis"][1] != "nada" else 0
checar("com o primeiro nome e a contagem da agenda de hoje (a linha do cenário conta)",
       modelo.get("variaveis", [None])[0] == PRIMEIRO and n >= 1
       and m.get("texto") == f"Bom dia, {PRIMEIRO}! Hoje você tem {modelo['variaveis'][1]} na agenda de produção.",
       m)
checar("e saiu (modo simulado)", m.get("status") == "SIMULADA", m.get("status"))
carga = assistente._payload({"telefone": FONE, "texto": m.get("texto"), "modelo": modelo})
botoes = [x for x in carga.get("template", {}).get("components", []) if x.get("type") == "button"]
checar("vai como MODELO da Meta, com os dois botões de resposta rápida",
       carga.get("type") == "template" and carga["template"]["name"] == "botane_bom_dia"
       and [b["parameters"][0]["payload"] for b in botoes] == ["BOMDIA:VER", "BOMDIA:PARAR"], carga)
checar("uma vez por dia: a varredura seguinte não manda de novo",
       assistente_bomdia.varrer(NA_JANELA.replace(minute=40)) == 0 and len(bons_dias()) == 1)

print("\n3. \"só com pendência\"")
checar("quem não tem nada (sem permissão de agenda) não recebe", not bons_dias(FONE_SO), bons_dias(FONE_SO))
zerar_dia()
config(bom_dia_so_com_pendencia=False)
assistente_bomdia.varrer(NA_JANELA)
so = bons_dias(FONE_SO)
checar("desligado o \"só com pendência\", recebe — com \"nada\"",
       len(so) == 1 and "Hoje você tem nada" in (so[0].get("texto") or ""), so)

print("\n4. os botões")
FALSA.pedidos.clear()
antes = len(respostas())
tocar("BOMDIA:VER")
r = esperar(antes)
checar("\"Ver pendências\" vira a pergunta das pendências, respondida pelo Claude",
       (r.get("texto") or "").startswith("ok: Quais são as minhas pendências de hoje?"), r)
antes = len(respostas())
tocar("BOMDIA:PARAR")
r = esperar(antes)
with get_cursor() as cur:
    cur.execute("SELECT bom_dia FROM usuario_whatsapp WHERE id_usuario = %s", (ID_ADMIN,))
    ligado = cur.fetchone()["bom_dia"]
checar("\"Parar o bom dia\" desliga a opção e diz como voltar",
       "não mando mais o bom dia" in (r.get("texto") or "") and ligado is False, (r, ligado))

print("\n5. limpeza")
_devolver()
atexit.unregister(_devolver)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
