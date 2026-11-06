"""O assistente pelo WhatsApp, etapa 1 (migração 151): o número do assistente — UM, da casa — e
o vínculo telefone ↔ usuário pelo código.

🔑 **Pedido do dono (06/11/2026):** vincular o próprio telefone no usuário e conversar com o
sistema pelo WhatsApp; e o número compartilhado entre as lojas (quem vê duas lojas pergunta uma
vez só). Estudo em `docs/assistente-whatsapp-estudo.md`.

Tudo em MODO SIMULADO: nada sai para a Meta. O webhook é exercitado com o corpo que a Meta
manda, assinado com o segredo do app.

    python tests/smoke_assistente_whatsapp.py        (API de pé na 9200)
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

import comum  # noqa: E402,F401  (saída que não morre em cp1252)
from database import get_cursor, init_pool  # noqa: E402
from seguranca import hash_senha  # noqa: E402

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
            b = r.read()
            try:
                return r.status, json.loads(b or b"null")
            except json.JSONDecodeError:
                return r.status, b.decode()
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
        print(f"  FALHA {nome} {detalhe}")


def entrar(email, senha):
    _st, r = chamar("POST", "/auth/login", {"email": email, "senha": senha})
    return (r or {}).get("access_token")


token = entrar(*ADMIN)
checar("o administrador entra", bool(token))
init_pool()
_st, eu = chamar("GET", "/auth/me", token=token)
ID_ADMIN = eu.get("id")
marca = str(time.time_ns() // 100)[-6:]
PNID = f"PNIDASS{marca}"
SEGREDO = f"segredo-ass-{marca}"
NUMERO_ASS = f"(99) 7{marca[:4]}-{marca[2:6]}"
FONE_DONO = f"55479{marca}11"          # o WhatsApp de quem vincula (como a Meta manda)
FONE_ESTRANHO = f"55479{marca}22"
EMAIL_SEM = f"smoke.assistente.{marca}@teste.com"

with get_cursor() as cur:
    cur.execute("SELECT now() AS agora")
    INICIO = cur.fetchone()["agora"]
    cur.execute("SELECT * FROM integracoes WHERE servico = 'WHATSAPP_ASSISTENTE' AND id_unidade IS NULL")
    CONEXAO_ANTES = cur.fetchone()
    CONEXAO_ANTES = dict(CONEXAO_ANTES) if CONEXAO_ANTES else None
    cur.execute("SELECT * FROM usuario_whatsapp WHERE id_usuario = %s", (ID_ADMIN,))
    VINCULO_ANTES = cur.fetchone()
    VINCULO_ANTES = dict(VINCULO_ANTES) if VINCULO_ANTES else None
    # Quem não tem a permissão: um usuário sem papel nenhum, e SEM loja nenhuma.
    cur.execute("""INSERT INTO usuarios (nome, email, senha_hash) VALUES (%s, %s, %s)
                   RETURNING id""", ("Sem Assistente Teste", EMAIL_SEM, hash_senha("teste12345")))
    ID_SEM = cur.fetchone()["id"]


def _devolver():
    with get_cursor() as cur:
        cur.execute("DELETE FROM assistente_mensagens WHERE criada_em >= %s", (INICIO,))
        cur.execute("DELETE FROM usuario_whatsapp WHERE id_usuario = ANY(%s)", ([ID_ADMIN, ID_SEM],))
        cur.execute("DELETE FROM integracoes WHERE servico = 'WHATSAPP_ASSISTENTE' AND id_unidade IS NULL")
        for linha in (CONEXAO_ANTES, ):
            if linha:
                cur.execute(f"INSERT INTO integracoes ({', '.join(linha)}) VALUES "
                            f"({', '.join(['%s'] * len(linha))})", list(linha.values()))
        if VINCULO_ANTES:
            v = VINCULO_ANTES
            cur.execute(f"INSERT INTO usuario_whatsapp ({', '.join(v)}) VALUES "
                        f"({', '.join(['%s'] * len(v))})", list(v.values()))
        cur.execute("DELETE FROM auditoria WHERE id_usuario = %s", (ID_SEM,))
        cur.execute("DELETE FROM usuarios WHERE id = %s", (ID_SEM,))


atexit.register(_devolver)


def webhook(corpo, assinar=True):
    bruto = json.dumps(corpo).encode()
    cab = {}
    if assinar:
        cab["X-Hub-Signature-256"] = "sha256=" + hmac.new(
            SEGREDO.encode(), bruto, hashlib.sha256).hexdigest()
    st, r = chamar("POST", "/publico/whatsapp/webhook", bruto, cabecalhos=cab)
    time.sleep(0.3)   # a resposta sai numa tarefa depois do 200
    return st, r


_seq = [0]


def mensagem(fone, texto=None, tipo="text", id_meta=None):
    _seq[0] += 1
    m = {"from": fone, "id": id_meta or f"wamid.{marca}.{_seq[0]}", "type": tipo}
    if tipo == "text":
        m["text"] = {"body": texto}
    elif tipo == "audio":
        m["audio"] = {"id": "midia1", "mime_type": "audio/ogg"}
    return {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": PNID},
                                              "messages": [m]}}]}]}


def respostas(fone=None):
    with get_cursor() as cur:
        cur.execute(
            """SELECT id, texto, telefone, status, id_usuario FROM assistente_mensagens
                WHERE criada_em >= %s AND (%s::text IS NULL OR telefone = %s) ORDER BY id""",
            (INICIO, fone, fone))
        return [dict(x) for x in cur.fetchall()]


def vinculo(id_usuario):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM usuario_whatsapp WHERE id_usuario = %s", (id_usuario,))
        r = cur.fetchone()
        return dict(r) if r else {}


def config(**kw):
    corpo = {"ativa": True, "modo": "simulado", "numero": NUMERO_ASS, "phone_number_id": PNID,
             "api_versao": "v21.0", "app_secret": SEGREDO} | kw
    return chamar("PUT", "/assistente/config", corpo, token)


print("1. o número do assistente, da casa, em Integrações")
chamar("DELETE", "/assistente/vinculo", token=token)
with get_cursor() as cur:
    cur.execute("DELETE FROM integracoes WHERE servico = 'WHATSAPP_ASSISTENTE' AND id_unidade IS NULL")
st, g = chamar("POST", "/assistente/vinculo/codigo", token=token)
checar("sem o número ligado, não há código para gerar (409)", st == 409, (st, g))
st, c = chamar("GET", "/assistente/config", token=token)
checar("a configuração nasce desligada, com token de verificação e o webhook de sempre",
       st == 200 and c.get("ativa") is False and c.get("verify_token")
       and c.get("webhook_url", "").endswith("/publico/whatsapp/webhook"), (st, c))
VERIFY = c.get("verify_token")
st, r = config(modo="real")
checar("enviar de verdade sem token é recusado (400)", st == 400, (st, r))
with get_cursor() as cur:
    cur.execute("SELECT phone_number_id FROM unidade_whatsapps WHERE phone_number_id IS NOT NULL LIMIT 1")
    da_loja = cur.fetchone()
if da_loja:
    st, r = config(phone_number_id=da_loja["phone_number_id"])
    checar("o identificador de um número de loja não serve ao assistente (422)", st == 422, (st, r))
st, c = config()
checar("grava o número, ligado e em modo simulado",
       st == 200 and c.get("ativa") and c.get("segredo_configurado") and "app_secret" not in c
       and c.get("verify_token") == VERIFY, (st, c))
st, r = chamar("GET", f"/publico/whatsapp/webhook?hub.mode=subscribe&hub.verify_token={VERIFY}"
                      "&hub.challenge=4242")
checar("a Meta confere o webhook com o token de verificação do assistente",
       st == 200 and str(r) == "4242", (st, r))
token_sem = entrar(EMAIL_SEM, "teste12345")
st, r = chamar("GET", "/assistente/config", token=token_sem)
checar("configurar exige admin.integracoes (403)", st == 403, (st, r))

print("\n2. o vínculo pela tela: estado e código")
st, v = chamar("GET", "/assistente/vinculo", token=token)
checar("quem tem a permissão vê o estado e o número para chamar",
       st == 200 and v.get("vinculado") is False and (v.get("assistente") or {}).get("numero") == NUMERO_ASS,
       (st, v))
st, r = chamar("GET", "/assistente/vinculo", token=token_sem)
checar("quem não tem a permissão leva 403", st == 403, (st, r))
st, g = chamar("POST", "/assistente/vinculo/codigo", token=token)
CODIGO = g.get("codigo") or ""
link = (g.get("assistente") or {}).get("link") or ""
checar("o código tem 8 caracteres e fica pendente",
       st == 200 and len(CODIGO) == 8 and g.get("codigo_pendente") is True, (st, g))
checar("o link do WhatsApp já leva o texto com o código",
       f"?text=BOTANE%20{CODIGO}" in link and "wa.me/5599" in link, link)
checar("o banco guarda só o hash do código",
       vinculo(ID_ADMIN).get("codigo_hash") == hashlib.sha256(CODIGO.encode()).hexdigest())
st, v = chamar("GET", "/assistente/vinculo", token=token)
checar("o estado diz que há código pendente, sem mostrá-lo",
       v.get("codigo_pendente") is True and "codigo" not in v, v)

print("\n3. o webhook liga o telefone que mandou o código")
st, r = webhook(mensagem(FONE_DONO, f"BOTANE {CODIGO}"), assinar=False)
checar("sem a assinatura da Meta, nada muda (403)", st == 403 and not vinculo(ID_ADMIN).get("wa_id"),
       (st, r))
MSG_VINCULO = mensagem(FONE_DONO, f"Olá! botane {CODIGO.lower()}")
st, r = webhook(MSG_VINCULO)
vv = vinculo(ID_ADMIN)
checar("o código (mesmo em minúsculas, no meio do texto) liga o número",
       st == 200 and vv.get("wa_id") == FONE_DONO and vv.get("verificado_em"), (st, r, vv))
checar("e o código deixa de existir", vv.get("codigo_hash") is None)
rs = respostas(FONE_DONO)
checar("a resposta \"Pronto\" vai para a fila do assistente, já processada (simulada)",
       len(rs) == 1 and rs[0]["texto"].startswith("Pronto,") and rs[0]["status"] == "SIMULADA"
       and rs[0]["id_usuario"] == ID_ADMIN, rs)
with get_cursor() as cur:
    cur.execute("SELECT count(*) AS n FROM whatsapp_mensagens WHERE criada_em >= %s", (INICIO,))
    checar("e nada cai no histórico de WhatsApp das lojas", cur.fetchone()["n"] == 0)
webhook(MSG_VINCULO)
checar("a Meta reenviando a mesma mensagem não gera segunda resposta",
       len(respostas(FONE_DONO)) == 1, respostas(FONE_DONO))
st, v = chamar("GET", "/assistente/vinculo", token=token)
checar("a tela mostra o telefone vinculado, formatado",
       v.get("vinculado") is True and (v.get("telefone") or "").startswith("+55 (47)"), v)
with get_cursor() as cur:
    cur.execute("""SELECT 1 FROM auditoria WHERE entidade = 'assistente_whatsapp'
                    AND acao = 'vincular' AND id_usuario = %s AND em >= %s""", (ID_ADMIN, INICIO))
    checar("a auditoria registra o vínculo", cur.fetchone() is not None)

print("\n4. quem está vinculado é reconhecido")
webhook(mensagem(FONE_DONO, "quais minhas pendências hoje?"))
ultima = respostas(FONE_DONO)[-1]
checar("texto: responde pelo nome", "Reconheci você" in (ultima["texto"] or ""), ultima)
webhook(mensagem(FONE_DONO, tipo="audio"))
ultima = respostas(FONE_DONO)[-1]
checar("áudio: avisa que por enquanto só entende texto", "só entendo" in (ultima["texto"] or ""),
       ultima)
mid = respostas(FONE_DONO)[-1]["id"]
with get_cursor() as cur:
    cur.execute("UPDATE assistente_mensagens SET id_meta = %s WHERE id = %s", (f"wamid.out.{marca}", mid))
webhook({"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": PNID}, "statuses": [
    {"id": f"wamid.out.{marca}", "status": "read"}]}}]}]})
checar("o \"lida\" da Meta chega à resposta do assistente",
       next(x for x in respostas(FONE_DONO) if x["id"] == mid)["status"] == "LIDA")

print("\n5. quem não está vinculado")
webhook(mensagem(FONE_ESTRANHO, "oi"))
webhook(mensagem(FONE_ESTRANHO, "oi de novo"))
rs = respostas(FONE_ESTRANHO)
checar("número desconhecido recebe UMA resposta por dia, que não fala de ninguém",
       len(rs) == 1 and "não está ligado" in rs[0]["texto"], rs)
webhook(mensagem(FONE_ESTRANHO, f"BOTANE {CODIGO}"))
checar("o código já usado não liga outro telefone",
       vinculo(ID_ADMIN).get("wa_id") == FONE_DONO and len(respostas(FONE_ESTRANHO)) == 1)
st, g2 = chamar("POST", "/assistente/vinculo/codigo", token=token)
with get_cursor() as cur:
    cur.execute("""UPDATE usuario_whatsapp SET codigo_expira_em = now() - interval '1 minute'
                    WHERE id_usuario = %s""", (ID_ADMIN,))
webhook(mensagem(FONE_ESTRANHO, f"BOTANE {g2.get('codigo')}"))
checar("o código vencido não liga nada", vinculo(ID_ADMIN).get("wa_id") == FONE_DONO)
checar("e pedir código novo não desfaz o vínculo que já existia",
       chamar("GET", "/assistente/vinculo", token=token)[1].get("vinculado") is True)

print("\n6. o aparelho muda de mãos; o usuário sem a permissão (e sem loja)")
with get_cursor() as cur:
    cur.execute("""INSERT INTO usuario_whatsapp (id_usuario, codigo_hash, codigo_expira_em)
                   VALUES (%s, %s, now() + interval '10 minutes')""",
                (ID_SEM, hashlib.sha256(b"ZZZZ2222").hexdigest()))
webhook(mensagem(FONE_DONO, "BOTANE ZZZZ2222"))
checar("quem prova a posse fica com o número, e ele sai do usuário anterior",
       vinculo(ID_SEM).get("wa_id") == FONE_DONO and not vinculo(ID_ADMIN).get("wa_id"),
       (vinculo(ID_SEM), vinculo(ID_ADMIN)))
webhook(mensagem(FONE_DONO, "bom dia"))
ultima = respostas(FONE_DONO)[-1]
checar("sem a permissão: avisa que o assistente não está liberado",
       "não tem o assistente liberado" in (ultima["texto"] or ""), ultima)
with get_cursor() as cur:
    cur.execute("UPDATE usuarios SET ativo = false WHERE id = %s", (ID_SEM,))
webhook(mensagem(FONE_DONO, "ainda sou eu"))
ultima = respostas(FONE_DONO)[-1]
checar("usuário desativado deixa de ser reconhecido", "não está ligado" in (ultima["texto"] or ""),
       ultima)

print("\n7. desligar e desvincular")
st, g3 = chamar("POST", "/assistente/vinculo/codigo", token=token)
webhook(mensagem(FONE_DONO, f"BOTANE {g3.get('codigo')}"))
checar("religa o administrador", vinculo(ID_ADMIN).get("wa_id") == FONE_DONO)
config(ativa=False)
with get_cursor() as cur:
    from services import assistente
    assistente.responder(cur, f"teste-desligado-{marca}", FONE_DONO, "x", ID_ADMIN)
assistente.processar_fila()
checar("com o número desligado, a resposta na fila é cancelada",
       respostas(FONE_DONO)[-1]["status"] == "CANCELADA", respostas(FONE_DONO)[-1])
st, v = chamar("GET", "/assistente/vinculo", token=token)
checar("e o Perfil não oferece número para chamar", st == 200 and v.get("assistente") is None, v)
st, v = chamar("DELETE", "/assistente/vinculo", token=token)
checar("desvincular apaga o vínculo", st == 200 and v.get("vinculado") is False
       and not vinculo(ID_ADMIN), (st, v))

print("\n8. limpeza")
_devolver()
atexit.unregister(_devolver)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
