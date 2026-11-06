"""O assistente pelo WhatsApp, etapa 2 (migração 152): a conversa — o Claude responde consultas
com as ferramentas de LEITURA do conector, como o próprio usuário.

🔑 **Pedido do dono (06/11/2026):** *"mando um texto pedindo quais as minhas pendências para
hoje. Aí ele retorna: para hoje precisa produzir 10 pães…"*. Estudo em
`docs/assistente-whatsapp-estudo.md`.

⚠️ Contra uma Anthropic FALSA (`tests/anthropic_falsa.py`), apontada pela configuração do
assistente (`url_api`, que só vale com DEBUG): nada sai para a internet, nada é cobrado. O que
se prova é o caminho inteiro — webhook, pergunta guardada, laço de ferramentas com a credencial
do usuário, histórico, erros, limite — e o que vai em cada pedido à API.

    python tests/smoke_assistente_conversa.py        (API de pé na 9200, com DEBUG=true)
"""

import atexit
import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

import comum  # noqa: E402,F401
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
        print(f"  FALHA {nome} {str(detalhe)[:600]}")


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()
_st, eu = chamar("GET", "/auth/me", token=token)
ID_ADMIN, NOME_ADMIN = eu.get("id"), eu.get("nome")
marca = str(time.time_ns() // 100)[-6:]
PNID = f"PNIDCONV{marca}"
SEGREDO = f"segredo-conv-{marca}"
FONE = f"55479{marca}44"
FALSA = AnthropicFalsa()

with get_cursor() as cur:
    cur.execute("SELECT now() AS agora")
    INICIO = cur.fetchone()["agora"]
    cur.execute("SELECT * FROM integracoes WHERE servico = 'WHATSAPP_ASSISTENTE' AND id_unidade IS NULL")
    CONEXAO_ANTES = cur.fetchone()
    CONEXAO_ANTES = dict(CONEXAO_ANTES) if CONEXAO_ANTES else None
    cur.execute("SELECT * FROM usuario_whatsapp WHERE id_usuario = %s", (ID_ADMIN,))
    VINCULO_ANTES = cur.fetchone()
    VINCULO_ANTES = dict(VINCULO_ANTES) if VINCULO_ANTES else None
    cur.execute("DELETE FROM usuario_whatsapp WHERE id_usuario = %s OR wa_id = %s", (ID_ADMIN, FONE))
    cur.execute("INSERT INTO usuario_whatsapp (id_usuario, wa_id, verificado_em) VALUES (%s, %s, now())",
                (ID_ADMIN, FONE))


def _devolver():
    with get_cursor() as cur:
        cur.execute("DELETE FROM assistente_mensagens WHERE criada_em >= %s", (INICIO,))
        cur.execute("DELETE FROM assistente_conversa WHERE id_usuario = %s AND criada_em >= %s",
                    (ID_ADMIN, INICIO))
        cur.execute("DELETE FROM usuario_whatsapp WHERE id_usuario = %s", (ID_ADMIN,))
        if VINCULO_ANTES:
            v = VINCULO_ANTES
            cur.execute(f"INSERT INTO usuario_whatsapp ({', '.join(v)}) VALUES "
                        f"({', '.join(['%s'] * len(v))})", list(v.values()))
        cur.execute("DELETE FROM integracoes WHERE servico = 'WHATSAPP_ASSISTENTE' AND id_unidade IS NULL")
        if CONEXAO_ANTES:
            c = CONEXAO_ANTES
            cur.execute(f"INSERT INTO integracoes ({', '.join(c)}) VALUES "
                        f"({', '.join(['%s'] * len(c))})",
                        [Json(x) if isinstance(x, dict) else x for x in c.values()])
    FALSA.fechar()


atexit.register(_devolver)


def config(**kw):
    corpo = {"ativa": True, "modo": "simulado", "numero": "(99) 5555-0000", "phone_number_id": PNID,
             "api_versao": "v21.0", "app_secret": SEGREDO, "url_api": FALSA.url,
             "limite_diario": 500, "modelo": ""} | kw
    return chamar("PUT", "/assistente/config", corpo, token)


def _post(corpo):
    bruto = json.dumps(corpo).encode()
    cab = {"X-Hub-Signature-256": "sha256=" + hmac.new(SEGREDO.encode(), bruto, hashlib.sha256).hexdigest()}
    return chamar("POST", "/publico/whatsapp/webhook", bruto, cabecalhos=cab)


_seq = [0]


def falar(texto, tipo="text"):
    _seq[0] += 1
    m = {"from": FONE, "id": f"wamid.conv.{marca}.{_seq[0]}", "type": tipo}
    if tipo == "text":
        m["text"] = {"body": texto}
    return _post({"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": PNID},
                                                    "messages": [m]}}]}]})


def cutucar():
    """Um webhook só de estado: dispara o processamento das pendentes, como na vida real."""
    return _post({"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": PNID},
                                                    "statuses": []}}]}]})


def respostas():
    with get_cursor() as cur:
        cur.execute("""SELECT id, texto, status FROM assistente_mensagens
                        WHERE criada_em >= %s AND telefone = %s ORDER BY id""", (INICIO, FONE))
        return [dict(x) for x in cur.fetchall()]


def esperar_resposta(antes, segundos=15):
    for _ in range(int(segundos / 0.3)):
        rs = respostas()
        if len(rs) > antes:
            return rs[-1]
        time.sleep(0.3)
    return {}


def perguntar(texto):
    antes = len(respostas())
    falar(texto)
    return esperar_resposta(antes)


def conversa():
    with get_cursor() as cur:
        cur.execute("""SELECT id, papel, texto, status, tentativas, uso FROM assistente_conversa
                        WHERE id_usuario = %s AND criada_em >= %s ORDER BY id""", (ID_ADMIN, INICIO))
        return [dict(x) for x in cur.fetchall()]


print("1. a configuração da conversa")
st, c = config()
checar("grava, com o modelo padrão e o limite por dia", st == 200 and c.get("modelo_padrao") == "claude-opus-5-5"
       and c.get("limite_diario") == 500, (st, c))
checar("e diz se a chave da Anthropic (a da Tradução) existe", "chave_anthropic" in c, c)

print("\n2. uma pergunta que usa ferramenta")
FALSA.pedidos.clear()
FALSA.cabecalhos.clear()
r1 = perguntar("quais minhas pendências da agenda de hoje?")
checar("a resposta vem do resultado da ferramenta, chamada como o usuário",
       (r1.get("texto") or "").startswith("RESULTADO: ") and "erro" not in r1["texto"][:20], r1)
p1 = FALSA.pedidos[0] if FALSA.pedidos else {}
nomes = {t["name"] for t in p1.get("tools") or []}
from services import mcp_ferramentas  # noqa: E402
leitura = {f.nome for f in mcp_ferramentas.FERRAMENTAS if not f.grava}
# 154: o admin tem `integracao.whatsapp_lancar`, então recebe também as duas de produção (que só
# PROPÕEM — ver smoke_assistente_lancar). Nenhuma outra de gravação.
checar("o Claude recebe as ferramentas de LEITURA do conector, e de gravação só as de produção",
       nomes == leitura | {"produzir_da_agenda", "produzir"}, (len(nomes), len(leitura)))
checar("as ferramentas vão em ordem estável (o cache depende disso)",
       [t["name"] for t in p1.get("tools") or []] == sorted(nomes))
checar("o sistema é fixo e marcado para cache",
       (p1.get("system") or [{}])[0].get("cache_control") == {"type": "ephemeral"}
       and "Agora:" not in p1["system"][0]["text"], p1.get("system"))
checar("modelo padrão claude-opus-5-5, esforço baixo, com o retorno em outro modelo se recusar",
       p1.get("model") == "claude-opus-5-5" and p1.get("output_config") == {"effort": "low"}
       and p1.get("fallbacks") == "default"
       and FALSA.cabecalhos[0].get("anthropic-beta") == "server-side-fallback-2026-07-01",
       {k: p1.get(k) for k in ("model", "output_config", "fallbacks")})
pergunta1 = p1["messages"][-1]["content"] if p1 else ""
checar("a data, o nome e as lojas vão NA MENSAGEM (não no sistema)",
       "Agora:" in pergunta1 and f"Quem pergunta: {NOME_ADMIN}" in pergunta1 and "Lojas que vê:" in pergunta1,
       pergunta1[:300])
p2 = FALSA.pedidos[1] if len(FALSA.pedidos) > 1 else {}
volta = (p2.get("messages") or [{}, {}])[-2:]
checar("na volta da ferramenta, o conteúdo do Claude vai inteiro e o resultado logo depois",
       len(volta) == 2 and volta[0].get("role") == "assistant"
       and any(b.get("type") == "tool_use" for b in volta[0].get("content") or [])
       and volta[1]["content"][0].get("type") == "tool_result", volta)
cv = conversa()
checar("a conversa guarda a pergunta (respondida) e a resposta, com o uso e a ferramenta",
       len(cv) == 2 and cv[0]["status"] == "RESPONDIDA" and cv[1]["papel"] == "assistente"
       and (cv[1]["uso"] or {}).get("ferramentas") == ["agenda_producao"]
       and (cv[1]["uso"] or {}).get("voltas") == 2, cv)

print("\n3. o histórico vai junto")
FALSA.pedidos.clear()
r2 = perguntar("e para amanhã?")
msgs = (FALSA.pedidos[0] if FALSA.pedidos else {}).get("messages") or []
checar("a pergunta anterior e a resposta dela vão antes, alternando",
       msgs and msgs[0]["role"] == "user"
       and [m["role"] for m in msgs[-3:]] == ["user", "assistant", "user"]
       and "agenda" in msgs[-3]["content"] and msgs[-2]["content"].startswith("RESULTADO"), msgs[-3:])
checar("e a resposta sai", (r2.get("texto") or "").startswith("ok: e para amanhã"), r2)

print("\n4. o que não pode")
r3 = perguntar("pode gravar a produção")
# 154: `produzir` sem argumentos: a prévia nem se monta, nada é proposto nem gravado.
checar("ferramenta que grava não é chamada: sem argumentos, volta como erro ao Claude",
       "RESULTADO (erro): Não deu para preparar o lançamento" in (r3.get("texto") or ""), r3)
r4 = perguntar("recuse isto")
checar("recusa da API vira uma frase educada", (r4.get("texto") or "").startswith("Não posso ajudar"), r4)

print("\n5. a API ocupada")
antes = len(respostas())
falar("está ocupado?")
time.sleep(3)
pend = [x for x in conversa() if x["texto"] == "está ocupado?"]
checar("529: a pergunta volta a PENDENTE para tentar de novo, sem resposta ainda",
       pend and pend[0]["status"] == "PENDENTE" and pend[0]["tentativas"] == 1
       and len(respostas()) == antes, pend)
with get_cursor() as cur:
    cur.execute("""UPDATE assistente_conversa SET texto = 'agora sim', tentar_apos = now()
                    WHERE id = %s""", (pend[0]["id"] if pend else 0,))
cutucar()
r5 = esperar_resposta(antes)
checar("na nova tentativa, responde", (r5.get("texto") or "").startswith("ok: agora sim"), r5)

print("\n6. duas mensagens seguidas viram uma pergunta")
with get_cursor() as cur:
    for i, t in enumerate(("bom dia", "tudo certo?")):
        cur.execute("""INSERT INTO assistente_conversa (id_usuario, papel, texto, id_meta, status)
                       VALUES (%s, 'usuario', %s, %s, 'PENDENTE')""", (ID_ADMIN, t, f"junta.{marca}.{i}"))
FALSA.pedidos.clear()
antes = len(respostas())
cutucar()
r6 = esperar_resposta(antes)
time.sleep(1)
checar("um pedido só, com as duas falas, e uma resposta",
       len(FALSA.pedidos) == 1 and "bom dia\ntudo certo?" in FALSA.pedidos[0]["messages"][-1]["content"]
       and len(respostas()) == antes + 1, (len(FALSA.pedidos), r6))

print("\n7. o modelo e o limite")
config(modelo="claude-haiku-5-5")
FALSA.pedidos.clear()
FALSA.cabecalhos.clear()
perguntar("teste de modelo")
p = FALSA.pedidos[0] if FALSA.pedidos else {}
checar("Haiku 5.5: sem o retorno em outro modelo (não existe para ele), com esforço",
       p.get("model") == "claude-haiku-5-5" and "fallbacks" not in p
       and "anthropic-beta" not in (FALSA.cabecalhos[0] if FALSA.cabecalhos else {})
       and p.get("output_config") == {"effort": "low"}, p.get("model"))
st, r = config(modelo="gpt-4")
checar("modelo que não é Claude é recusado (422)", st == 422, (st, r))
with get_cursor() as cur:
    from services import assistente_conversa
    hoje = assistente_conversa.perguntas_hoje(cur, ID_ADMIN)
config(limite_diario=hoje)
FALSA.pedidos.clear()
r7 = perguntar("mais uma")
checar("no limite do dia: avisa, sem chamar o Claude",
       "limite de" in (r7.get("texto") or "") and not FALSA.pedidos, (r7, len(FALSA.pedidos)))

print("\n8. sem chave da Anthropic")
with get_cursor() as cur:
    from services import traducao
    tem_chave = bool(traducao._config(cur).get("chave"))
if tem_chave:
    print("  (pulado: a base tem chave da Anthropic de verdade — o teste chamaria a API real)")
else:
    config(url_api="")
    r8 = perguntar("alguém aí?")
    checar("sem chave, responde onde se cadastra", "Integrações ▸ Tradução" in (r8.get("texto") or ""), r8)

print("\n9. limpeza")
_devolver()
atexit.unregister(_devolver)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
