"""O assistente pelo WhatsApp, etapa 3 (migração 153): o áudio vira texto e segue para o Claude.

🔑 **Pedido do dono (06/11/2026):** *"pela manhã mando um áudio ou um texto para este
número…"*. Estudo em `docs/assistente-whatsapp-estudo.md`.

⚠️ Contra a Meta, a transcrição e a Anthropic FALSAS (`tests/falsos_assistente.py`,
`tests/anthropic_falsa.py`), apontadas pela configuração do assistente — o que só vale com
DEBUG. Nada sai para a internet, nada é cobrado.

    python tests/smoke_assistente_audio.py        (API de pé na 9200, com DEBUG=true)
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
from falsos_assistente import MetaFalsa, TranscricaoFalsa  # noqa: E402
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
ID_ADMIN = eu.get("id")
marca = str(time.time_ns() // 100)[-6:]
PNID = f"PNIDAUD{marca}"
SEGREDO = f"segredo-aud-{marca}"
FONE = f"55479{marca}55"
ANTHROPIC, META, TRANSCRICAO = AnthropicFalsa(), MetaFalsa(), TranscricaoFalsa()

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
    # A conexão nasce limpa: sem transcrição e sem chave guardada de outra rodada.
    cur.execute("DELETE FROM integracoes WHERE servico = 'WHATSAPP_ASSISTENTE' AND id_unidade IS NULL")


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
    for s in (ANTHROPIC, META, TRANSCRICAO):
        s.fechar()


atexit.register(_devolver)


def config(**kw):
    corpo = {"ativa": True, "modo": "simulado", "numero": "(99) 5555-0001", "phone_number_id": PNID,
             "api_versao": "v21.0", "app_secret": SEGREDO, "url_api": ANTHROPIC.url,
             "url_meta": META.url, "url_transcricao": TRANSCRICAO.url, "limite_diario": 500} | kw
    return chamar("PUT", "/assistente/config", corpo, token)


def _post(corpo):
    bruto = json.dumps(corpo).encode()
    cab = {"X-Hub-Signature-256": "sha256=" + hmac.new(SEGREDO.encode(), bruto, hashlib.sha256).hexdigest()}
    return chamar("POST", "/publico/whatsapp/webhook", bruto, cabecalhos=cab)


_seq = [0]


def mandar(tipo, **conteudo):
    _seq[0] += 1
    m = {"from": FONE, "id": f"wamid.aud.{marca}.{_seq[0]}", "type": tipo} | conteudo
    return _post({"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": PNID},
                                                    "messages": [m]}}]}]})


def audio(midia):
    return mandar("audio", audio={"id": midia, "mime_type": "audio/ogg; codecs=opus", "voice": True})


def cutucar():
    return _post({"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": PNID},
                                                    "statuses": []}}]}]})


def respostas():
    with get_cursor() as cur:
        cur.execute("""SELECT id, texto FROM assistente_mensagens
                        WHERE criada_em >= %s AND telefone = %s ORDER BY id""", (INICIO, FONE))
        return [dict(x) for x in cur.fetchall()]


def esperar(antes, segundos=15):
    for _ in range(int(segundos / 0.3)):
        rs = respostas()
        if len(rs) > antes:
            return rs[-1]
        time.sleep(0.3)
    return {}


def ultima_pergunta():
    with get_cursor() as cur:
        cur.execute("""SELECT id, texto, status, tentativas, de_audio, midia_id, transcrito_em
                         FROM assistente_conversa WHERE id_usuario = %s AND papel = 'usuario'
                          AND criada_em >= %s ORDER BY id DESC LIMIT 1""", (ID_ADMIN, INICIO))
        r = cur.fetchone()
        return dict(r) if r else {}


print("1. sem transcrição configurada")
st, c = config()
checar("a configuração lista os provedores (OpenAI e Groq) e começa sem transcrição",
       st == 200 and {p["id"] for p in c.get("provedores_transcricao") or []} == {"openai", "groq"}
       and c.get("transcricao_provedor") == "", (st, c))
antes = len(respostas())
audio("sem_transcricao")
r = esperar(antes, 5)
checar("áudio recebe na hora: ainda não ouço, escreva", "ainda não consigo ouvir áudio" in (r.get("texto") or ""), r)
checar("e não vira pergunta", not ultima_pergunta(), ultima_pergunta())

print("\n2. com a transcrição (Groq)")
st, c = config(transcricao_provedor="groq", transcricao_chave=f"gsk-{marca}")
checar("grava o provedor; a chave volta só como configurada",
       st == 200 and c.get("transcricao_provedor") == "groq" and c.get("transcricao_chave_configurada")
       and f"gsk-{marca}" not in json.dumps(c), (st, c))
st, r = config(transcricao_provedor="whisperzinho")
checar("provedor desconhecido é recusado (422)", st == 422, (st, r))
config(transcricao_provedor="groq")
ANTHROPIC.pedidos.clear()
antes = len(respostas())
audio("quais_as_pendencias_da_agenda")
r = esperar(antes)
checar("a resposta mostra o que ouviu e responde com a ferramenta",
       (r.get("texto") or "").startswith("🎤 _Ouvi: “quais as pendencias da agenda”_")
       and "RESULTADO: " in r["texto"], r)
p = ultima_pergunta()
checar("a pergunta guarda o texto ouvido (o áudio não fica)",
       p.get("texto") == "quais as pendencias da agenda" and p.get("de_audio") and p.get("transcrito_em")
       and p.get("status") == "RESPONDIDA", p)
mp = [x for x in META.pedidos if "quais_as" in x["caminho"]]
checar("baixa da Meta em dois passos (a URL, depois os bytes), com o token",
       len(mp) == 2 and mp[0]["caminho"].startswith("/v21.0/") and mp[1]["caminho"].startswith("/midia/")
       and all(x["auth"] == "Bearer teste" for x in mp), mp)
tp = TRANSCRICAO.pedidos[-1] if TRANSCRICAO.pedidos else {}
checar("transcreve com a chave e o modelo padrão do Groq, em português",
       tp.get("caminho") == "/v1/audio/transcriptions" and tp.get("auth") == f"Bearer gsk-{marca}"
       and b"whisper-large-v3-turbo" in tp.get("corpo", b"") and b'name="language"' in tp.get("corpo", b"")
       and b"multipart/form-data" in tp.get("tipo", "").encode(), {k: tp.get(k) for k in ("caminho", "auth")})
pergunta = (ANTHROPIC.pedidos[0]["messages"][-1]["content"] if ANTHROPIC.pedidos else "")
checar("o Claude é avisado de que a pergunta veio de áudio transcrito",
       "ÁUDIO transcrito" in pergunta and pergunta.endswith("quais as pendencias da agenda"), pergunta[-200:])

print("\n3. o que dá errado")
antes = len(respostas())
audio("silencio")
r = esperar(antes)
checar("áudio sem fala: pede para repetir ou escrever", "Não consegui entender o áudio" in (r.get("texto") or ""), r)
antes = len(respostas())
audio("expirada")
r = esperar(antes)
checar("mídia que a Meta não entrega mais: avisa e pede de novo",
       "Não consegui baixar o áudio da Meta" in (r.get("texto") or ""), r)
antes = len(respostas())
audio("longa")
r = esperar(antes)
checar("áudio longo demais: recusa sem baixar", "longo demais" in (r.get("texto") or "")
       and not any("/midia/longa" in x["caminho"] for x in META.pedidos), r)
TRANSCRICAO.ocupado = True
antes = len(respostas())
audio("tente_de_novo")
time.sleep(3)
p = ultima_pergunta()
checar("transcrição fora do ar: volta para a fila, sem responder ainda",
       p.get("status") == "PENDENTE" and p.get("tentativas") == 1 and p.get("transcrito_em") is None
       and len(respostas()) == antes, p)
TRANSCRICAO.ocupado = False
with get_cursor() as cur:
    cur.execute("UPDATE assistente_conversa SET tentar_apos = now() WHERE id = %s", (p.get("id"),))
cutucar()
r = esperar(antes)
checar("na nova tentativa, ouve e responde", "Ouvi: “tente de novo”" in (r.get("texto") or ""), r)

print("\n4. o que não é texto nem áudio")
antes = len(respostas())
mandar("image", image={"id": "foto1"})
r = esperar(antes, 5)
checar("foto: diz que entende texto e áudio", "Entendo texto e áudio" in (r.get("texto") or ""), r)

print("\n5. limpeza")
_devolver()
atexit.unregister(_devolver)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
