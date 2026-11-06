"""O assistente pelo WhatsApp, etapa 4 (migração 154): LANÇAR produção, com confirmação por botão.

🔑 **Pedido do dono (06/11/2026):** *"depois posso confirmar a produção e o sistema já lança e
coloca em estoque"*. Estudo em `docs/assistente-whatsapp-estudo.md`.

O que se prova: o Claude pedir uma gravação NÃO grava — nasce a prévia (do sistema) com os botões;
Cancelar não lança; Confirmar lança uma vez só, como a pessoa, e a auditoria marca `whatsapp`;
botão de outra pessoa, vencido ou repetido não lança; quem não tem `integracao.whatsapp_lancar`
nem recebe as ferramentas de lançar.

⚠️ Contra a Anthropic FALSA (`tests/anthropic_falsa.py`) — só com DEBUG. O estoque é de verdade
(produto e insumo de teste, com a marca da rodada): movimento não se apaga, então os produtos de
teste ficam inativos no fim.

    python tests/smoke_assistente_lancar.py        (API de pé na 9200, com DEBUG=true)
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
_st, eu = chamar("GET", "/auth/me", token=token)
ID_ADMIN = eu.get("id")
marca = str(time.time_ns() // 100)[-6:]
PNID = f"PNIDLAN{marca}"
SEGREDO = f"segredo-lan-{marca}"
FONE = f"55479{marca}66"
FONE_SO_CONSULTA = f"55479{marca}77"
FALSA = AnthropicFalsa()
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
                (ID_ADMIN, FONE, FONE_SO_CONSULTA))
    cur.execute("INSERT INTO usuario_whatsapp (id_usuario, wa_id, verificado_em) VALUES (%s, %s, now())",
                (ID_ADMIN, FONE))
    # Quem só CONSULTA: um papel com o assistente e sem `integracao.whatsapp_lancar`.
    cur.execute("INSERT INTO papeis (nome, descricao) VALUES (%s, 'teste') RETURNING id",
                (f"Teste so consulta {marca}",))
    ID_PAPEL = cur.fetchone()["id"]
    cur.execute("INSERT INTO papel_permissoes (id_papel, chave) VALUES (%s, 'integracao.whatsapp_assistente')",
                (ID_PAPEL,))
    cur.execute("""INSERT INTO usuarios (nome, email, senha_hash) VALUES (%s, %s, 'x') RETURNING id""",
                ("So Consulta Teste", f"smoke.soconsulta.{marca}@teste.com"))
    ID_SO = cur.fetchone()["id"]
    cur.execute("INSERT INTO usuario_papeis (id_usuario, id_papel, id_unidade) VALUES (%s, %s, NULL)",
                (ID_SO, ID_PAPEL))
    cur.execute("INSERT INTO usuario_whatsapp (id_usuario, wa_id, verificado_em) VALUES (%s, %s, now())",
                (ID_SO, FONE_SO_CONSULTA))


def _devolver():
    with get_cursor() as cur:
        cur.execute("DELETE FROM assistente_mensagens WHERE criada_em >= %s", (INICIO,))
        cur.execute("DELETE FROM assistente_conversa WHERE id_usuario = ANY(%s) AND criada_em >= %s",
                    ([ID_ADMIN, ID_SO], INICIO))
        cur.execute("DELETE FROM assistente_acoes WHERE id_usuario = ANY(%s) AND criada_em >= %s",
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
chamar("PUT", "/assistente/config", {
    "ativa": True, "modo": "simulado", "numero": "(99) 5555-0002", "phone_number_id": PNID,
    "api_versao": "v21.0", "app_secret": SEGREDO, "url_api": FALSA.url, "limite_diario": 500}, token)


def _post(corpo):
    bruto = json.dumps(corpo).encode()
    cab = {"X-Hub-Signature-256": "sha256=" + hmac.new(SEGREDO.encode(), bruto, hashlib.sha256).hexdigest()}
    return chamar("POST", "/publico/whatsapp/webhook", bruto, cabecalhos=cab)


_seq = [0]


def mensagem(m, fone=FONE):
    _seq[0] += 1
    m = {"from": fone, "id": m.pop("id", None) or f"wamid.lan.{marca}.{_seq[0]}"} | m
    return _post({"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": PNID},
                                                    "messages": [m]}}]}]})


def falar(texto, fone=FONE):
    return mensagem({"type": "text", "text": {"body": texto}}, fone)


def tocar(id_botao, fone=FONE, id_meta=None):
    return mensagem({"type": "interactive", "id": id_meta,
                     "interactive": {"type": "button_reply",
                                     "button_reply": {"id": id_botao, "title": "x"}}}, fone)


def respostas(fone=FONE):
    with get_cursor() as cur:
        cur.execute("""SELECT id, texto, botoes FROM assistente_mensagens
                        WHERE criada_em >= %s AND telefone = %s ORDER BY id""", (INICIO, fone))
        return [dict(x) for x in cur.fetchall()]


def esperar(antes, quantas=1, segundos=15, fone=FONE):
    for _ in range(int(segundos / 0.3)):
        rs = respostas(fone)
        if len(rs) >= antes + quantas:
            time.sleep(0.3)
            return respostas(fone)[antes:]
        time.sleep(0.3)
    return respostas(fone)[antes:]


def acao(id_acao):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM assistente_acoes WHERE id = %s", (id_acao,))
        r = cur.fetchone()
        return dict(r) if r else {}


def saldo(id_produto):
    st, lista = chamar("GET", f"/estoque/saldos?id_produto={id_produto}", token=token)
    lista = lista if isinstance(lista, list) else (lista or {}).get("itens", [])
    return sum(float(x["quantidade"]) for x in lista)


def propor(texto):
    """Fala e espera a resposta do Claude + a mensagem com botões. Devolve (id da ação, botões)."""
    antes = len(respostas())
    falar(texto)
    novas = esperar(antes, 2)
    com_botao = next((x for x in novas if x.get("botoes")), {})
    ids = [b["id"] for b in com_botao.get("botoes") or []]
    id_acao = int(ids[0].rsplit(":", 1)[1]) if ids else 0
    return id_acao, com_botao, novas


print("0. o cenário: farinha no estoque, pão com ficha homologada, uma linha na agenda")
st, f = chamar("POST", "/produtos", {"nome": f"FARINHA LAN {marca}", "tipo": "INSUMO",
                                     "um_estoque": "KG", "status": "ATIVO"}, token=token)
farinha = (f or {}).get("id")
criados["produtos"].append(farinha)
chamar("PUT", f"/produtos/{farinha}", {"id_local_padrao": central["id"]}, token=token)
chamar("POST", "/estoque/entradas", {"id_produto": farinha, "quantidade": 5, "custo_unitario": 4,
                                     "id_local": central["id"], "documento": f"NF-LAN-{marca}"}, token=token)
st, p = chamar("POST", "/produtos", {"nome": f"PAO LAN {marca}", "tipo": "PRODUZIDO", "um_estoque": "UN",
                                     "producao_propria": True, "status": "ATIVO",
                                     "id_local_padrao": central["id"]}, token=token)
pao = (p or {}).get("id")
criados["produtos"].append(pao)
st, fi = chamar("POST", "/fichas", {"id_produto": pao, "rendimento_qtd": 10, "rendimento_um": "UN",
                                    "porcoes": 10, "itens": [{"id_insumo": farinha, "qtd_bruta": 1,
                                                              "um": "KG"}]}, token=token)
st_h, _ = chamar("POST", f"/fichas/{(fi or {}).get('id')}/homologar", {}, token=token)
st, ag = chamar("POST", "/producao-agenda", {"id_produto": pao, "quantidade": 10,
                                             "data_prevista": str(date.today())}, token=token)
AGENDA = (ag or {}).get("id")
checar("o cenário nasce", farinha and pao and st_h == 200 and AGENDA, (farinha, pao, st_h, ag))

print("\n1. pedir para lançar NÃO lança: vem a prévia com os botões")
FALSA.pedidos.clear()
id1, msg_botoes, novas = propor(f"lance agenda {AGENDA}")
nomes = {t["name"] for t in (FALSA.pedidos[0] if FALSA.pedidos else {}).get("tools") or []}
sistema = FALSA.pedidos[0]["system"][0]["text"] if FALSA.pedidos else ""
checar("quem pode lançar recebe as duas ferramentas de produção, e o sistema diz como",
       {"produzir_da_agenda", "produzir"} <= nomes and "pode LANÇAR PRODUÇÃO" in sistema, nomes)
volta = FALSA.pedidos[1]["messages"][-1]["content"][0] if len(FALSA.pedidos) > 1 else {}
checar("ao Claude volta \"preparado, não lançado\", sem erro",
       not volta.get("is_error") and "PREPARADO, NÃO LANÇADO" in str(volta.get("content")), volta)
corpo = msg_botoes.get("texto") or ""
checar("a prévia é do sistema: produto, quantidade e o que sai do estoque",
       corpo.startswith("Confirma o lançamento?") and f"10 UN de *PAO LAN {marca}*" in corpo
       and f"FARINHA LAN {marca}: 1 KG" in corpo, corpo)
checar("com os botões Confirmar e Cancelar, que carregam o id da ação",
       [b["id"] for b in msg_botoes.get("botoes") or []] == [f"ACAO:CONFIRMAR:{id1}", f"ACAO:CANCELAR:{id1}"]
       and all(len(b["titulo"]) <= 20 for b in msg_botoes["botoes"]), msg_botoes.get("botoes"))
a1 = acao(id1)
checar("a ação fica PENDENTE com os argumentos que vão ser gravados",
       a1.get("status") == "PENDENTE" and a1.get("ferramenta") == "produzir_da_agenda"
       and a1.get("argumentos") == {"id_agenda": AGENDA}, a1)
saldo_pao = saldo(pao)
checar("e nada entrou no estoque ainda", saldo_pao == 0, saldo_pao)

print("\n2. Cancelar")
antes = len(respostas())
tocar(f"ACAO:CANCELAR:{id1}")
r = esperar(antes)
checar("cancela: nada foi lançado", r and r[-1]["texto"] == "Cancelado. Nada foi lançado."
       and acao(id1).get("status") == "CANCELADA", r)
antes = len(respostas())
tocar(f"ACAO:CONFIRMAR:{id1}")
r = esperar(antes)
checar("confirmar depois de cancelar não lança", r and "foi cancelado" in r[-1]["texto"]
       and saldo(pao) == 0, r)

print("\n3. Confirmar")
id2, _b, _n = propor(f"lance agenda {AGENDA}")
antes = len(respostas())
TOQUE = f"wamid.lan.{marca}.toque"
tocar(f"ACAO:CONFIRMAR:{id2}", id_meta=TOQUE)
r = esperar(antes, 2)
textos = [x["texto"] for x in r]
checar("responde \"lançando\" e depois \"lançado\", com o produto",
       "Lançando…" in textos and any(t.startswith("✅ Lançado:") and f"PAO LAN {marca}" in t for t in textos), textos)
checar("a ação fica EXECUTADA, com o resultado da rota", acao(id2).get("status") == "EXECUTADA"
       and acao(id2).get("resultado"), acao(id2))
checar("o pão entrou no estoque: 10 UN", saldo(pao) == 10, saldo(pao))
_st, linha = chamar("GET", f"/producao-agenda/{AGENDA}", token=token)
checar("e a linha saiu da agenda", (linha or {}).get("status") not in (None, "PENDENTE", "PLANEJADA"), linha)
with get_cursor() as cur:
    cur.execute("""SELECT count(*) AS n FROM auditoria WHERE origem = 'whatsapp' AND id_usuario = %s
                    AND em >= %s""", (ID_ADMIN, INICIO))
    n_aud = cur.fetchone()["n"]
checar("a auditoria marca a origem: whatsapp", n_aud >= 1, n_aud)
tocar(f"ACAO:CONFIRMAR:{id2}", id_meta=TOQUE)
time.sleep(2)
checar("a Meta reenviando o toque não lança de novo", saldo(pao) == 10, saldo(pao))
antes = len(respostas())
tocar(f"ACAO:CONFIRMAR:{id2}")
r = esperar(antes)
checar("um segundo toque (mensagem nova) diz que já foi feito", r and "já foi feito" in r[-1]["texto"]
       and saldo(pao) == 10, r)

print("\n4. o que não pode")
with get_cursor() as cur:
    cur.execute("""INSERT INTO assistente_acoes (id_usuario, ferramenta, argumentos, resumo, expira_em)
                   VALUES (%s, 'produzir', '{"id_produto": 1, "quantidade": 1}', 'x',
                           now() + interval '10 minutes') RETURNING id""", (ID_SO,))
    alheia = cur.fetchone()["id"]
antes = len(respostas())
tocar(f"ACAO:CONFIRMAR:{alheia}")
r = esperar(antes)
checar("botão com o id da ação de OUTRA pessoa não lança", r and "Não encontrei" in r[-1]["texto"]
       and acao(alheia).get("status") == "PENDENTE", r)
id3, _b, _n = propor(f"produza {pao} 5")
checar("produção avulsa: a prévia diz quanto e de quê",
       f"*Produzir:* 5 UN de *PAO LAN {marca}*" in (_b.get("texto") or ""), _b.get("texto"))
id4, _b, _n = propor(f"produza {pao} 3")
checar("uma proposta nova derruba a anterior", acao(id3).get("status") == "EXPIRADA"
       and acao(id4).get("status") == "PENDENTE", (acao(id3).get("status"), acao(id4).get("status")))
with get_cursor() as cur:
    cur.execute("UPDATE assistente_acoes SET expira_em = now() - interval '1 minute' WHERE id = %s", (id4,))
antes = len(respostas())
tocar(f"ACAO:CONFIRMAR:{id4}")
r = esperar(antes)
checar("confirmação vencida não lança", r and "venceu" in r[-1]["texto"] and saldo(pao) == 10, r)
FALSA.pedidos.clear()
antes = len(respostas(FONE_SO_CONSULTA))
falar(f"lance agenda {AGENDA}", FONE_SO_CONSULTA)
r = esperar(antes, fone=FONE_SO_CONSULTA)
nomes = {t["name"] for t in (FALSA.pedidos[0] if FALSA.pedidos else {}).get("tools") or []}
checar("quem só consulta nem recebe as ferramentas de lançar", FALSA.pedidos and not
       ({"produzir_da_agenda", "produzir"} & nomes), nomes & {"produzir_da_agenda", "produzir"})
checar("e o pedido de lançar volta como indisponível", r and "não está disponível" in r[-1]["texto"], r)

print("\n5. limpeza")
_devolver()
atexit.unregister(_devolver)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
