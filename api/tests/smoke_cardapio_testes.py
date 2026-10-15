"""Cardápio Vivo, fase 3 (migração 116): testes A/B de mídia e de ordem, e as sugestões de destaque.

🔑 **Decisões do dono (15/10/2026)**: mídia = vídeo × foto; ordem = atual × sugerida; vencedor
pela TAXA DE ADIÇÃO; destaque é sugerido e o gerente aprova.

⚠️ O resultado precisa de amostra (100 sessões por braço): a suíte FABRICA sessões direto no
banco, sorteando o braço pela mesma conta que o feed usa (`SQL_VARIANTE`).

    python tests/smoke_cardapio_testes.py        (API de pé na 9200)
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from base64 import b64decode

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import preservar_reserva  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
MARCA = str(time.time_ns() // 100)[-6:]
ok = 0
falhas: list[str] = []
PNG = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+wSzIAAAABlBMVEX///+/v7+jQ3Y5AAAA"
                "DklEQVQI12P4AIX8EAgALgAD/aNpbtEAAAAASUVORK5CYII=")


def chamar(metodo, caminho, corpo=None, token=None, bruto=None, tipo="application/json"):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", tipo)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = bruto if bruto is not None else (json.dumps(corpo, default=str).encode() if corpo is not None else None)
    try:
        with urllib.request.urlopen(req, dados, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": b.decode(errors="replace")}


def enviar_foto(caminho, token):
    limite = uuid.uuid4().hex
    corpo = (f"--{limite}\r\nContent-Disposition: form-data; name=\"arquivo\"; filename=\"f.png\"\r\n"
             f"Content-Type: image/png\r\n\r\n").encode() + PNG + f"\r\n--{limite}--\r\n".encode()
    return chamar("POST", caminho, token=token, bruto=corpo, tipo=f"multipart/form-data; boundary={limite}")


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()
_st, eu = chamar("GET", "/auth/me", token=token)
U = (eu.get("unidades") or [{}])[0].get("id") or 1
preservar_reserva(U)
with get_cursor() as cur:
    cur.execute("SELECT * FROM cardapio_config WHERE id_unidade = %s", (U,))
    _CFG = cur.fetchone()
    _CFG = dict(_CFG) if _CFG else None


def _devolver():
    with get_cursor() as cur:
        cur.execute("DELETE FROM cardapio_config WHERE id_unidade = %s", (U,))
        if _CFG:
            cols = list(_CFG)
            cur.execute(f"INSERT INTO cardapio_config ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                        [_CFG[c] for c in cols])
        cur.execute("DELETE FROM catalogos WHERE nome LIKE %s", (f"%{MARCA}%",))


atexit.register(_devolver)
_st, par = chamar("GET", f"/unidades/{U}/parametros", token=token)
chamar("PUT", f"/unidades/{U}/parametros", {**par, "reservas_ligado": True}, token)


def produto(nome, preco):
    _st, p = chamar("POST", "/produtos", {"nome": f"{nome} {MARCA}", "tipo": "INSUMO", "um_estoque": "UN",
                                          "controla_estoque": False}, token)
    _st, atual = chamar("GET", f"/produtos/{p['id']}", token=token)
    chamar("PUT", f"/produtos/{p['id']}", {**atual, "integrado_pdv": True, "preco_venda": preco}, token)
    return p["id"]


print("0. cenário: um cardápio de três pratos; o primeiro com vídeo E foto")
_st, cat = chamar("POST", "/catalogos", {"nome": f"AB {MARCA}", "origem": "PRODUTOS", "situacao": "ATIVO"}, token)
ID_CAT = cat["id"]
_st, g = chamar("POST", f"/catalogos/{ID_CAT}/categorias", {"nome": "Pratos"}, token)
A, B, C = produto("AB RISOTO", 58), produto("AB SUCO", 12), produto("AB TORTA", 20)
itens = {}
for n, pid in (("A", A), ("B", B), ("C", C)):
    _st, it = chamar("POST", f"/catalogos/categorias/{g['id']}/itens", {"id_produto": pid}, token)
    itens[n] = it["id"]
enviar_foto(f"/produtos/{A}/foto", token)
with get_cursor() as cur:
    # O vídeo de verdade é coberto pela suíte da fase 1; aqui basta o produto TER um.
    cur.execute("UPDATE produtos SET video_url = '/arquivos/teste-ab.mp4', video_capa_url = NULL WHERE id = %s", (A,))
chamar("PUT", "/cardapio-vivo/config", {"id_catalogo": ID_CAT, "modo": "VITRINE", "fonte": "NEWSREADER",
                                        "retencao_meses": 13}, token)

print("\n1. criar os testes")
st, r = chamar("POST", "/cardapio-vivo/testes", {"tipo": "MIDIA", "id_item": itens["B"]}, token)
checar("prato sem vídeo não entra em teste de mídia (409)", st == 409 and "vídeo E foto" in r["detail"], (st, r))
st, tm = chamar("POST", "/cardapio-vivo/testes", {"tipo": "MIDIA", "id_item": itens["A"]}, token)
checar("prato com vídeo e foto: o teste de mídia começa", st == 201 and tm.get("aberto"), (st, tm))
st, r = chamar("POST", "/cardapio-vivo/testes", {"tipo": "MIDIA", "id_item": itens["A"]}, token)
checar("um teste aberto por prato", st == 409, (st, r))
st, r = chamar("POST", "/cardapio-vivo/testes", {"tipo": "ORDEM"}, token)
checar("ordem sugerida igual à atual: não há o que comparar (409)", st == 409, (st, r))
chamar("PUT", f"/catalogos/itens/{itens['C']}/marcas", {"destaque": True}, token)
st, to = chamar("POST", "/cardapio-vivo/testes", {"tipo": "ORDEM"}, token)
checar("com a torta em destaque, a ordem sugerida muda e o teste de ordem começa", st == 201, (st, to))

print("\n2. o feed: cada sessão no seu braço, sempre o mesmo")
with get_cursor() as cur:
    braco = {}
    while len(braco) < 2:
        s = str(uuid.uuid4())
        cur.execute("SELECT abs(hashtext(%s::text || ':' || %s::text)) %% 2 AS m", (s, tm["id"]))
        braco.setdefault("A" if cur.fetchone()["m"] == 0 else "B", s)


def feed(sessao=None):
    _st, f = chamar("GET", f"/publico/cardapio/loja/{U}" + (f"?sessao={sessao}" if sessao else ""))
    return f


fa, fb = feed(braco["A"]), feed(braco["B"])
ma = next(i for i in fa["itens"] if i["id"] == itens["A"])["midia"]["tipo"]
mb = next(i for i in fb["itens"] if i["id"] == itens["A"])["midia"]["tipo"]
checar("o braço A do teste de mídia vê o VÍDEO", ma == "VIDEO", ma)
checar("o braço B vê a FOTO", mb == "FOTO", mb)
checar("a mesma sessão cai sempre no mesmo braço",
       next(i for i in feed(braco["B"])["itens"] if i["id"] == itens["A"])["midia"]["tipo"] == "FOTO")
checar("sem sessão (ou na prévia) ninguém entra em teste: vídeo",
       next(i for i in feed()["itens"] if i["id"] == itens["A"])["midia"]["tipo"] == "VIDEO")
with get_cursor() as cur:
    ordens = {}
    for _ in range(40):
        s = str(uuid.uuid4())
        cur.execute("SELECT abs(hashtext(%s::text || ':' || %s::text)) %% 2 AS m", (s, to["id"]))
        ordens.setdefault("A" if cur.fetchone()["m"] == 0 else "B", s)
oa = [i["id"] for i in feed(ordens["A"])["itens"]]
ob = [i["id"] for i in feed(ordens["B"])["itens"]]
checar("no teste de ordem, A vê a ordem do catálogo", oa == [itens["A"], itens["B"], itens["C"]], oa)
checar("e B vê a sugerida (a torta em destaque sobe)", ob[0] == itens["C"], ob)

print("\n3. o resultado: taxa de adição por braço, com amostra mínima")
st, lista = chamar("GET", "/cardapio-vivo/testes", token=token)
r0 = next(t for t in lista if t["id"] == tm["id"])["resultado"]
checar("sem sessões, a conclusão é 'amostra pequena'", r0["conclusao"] == "AMOSTRA_PEQUENA", r0)
with get_cursor() as cur:
    # 🔑 300 sessões fabricadas: o braço é o da MESMA conta do feed; B adiciona o dobro.
    feitas = {"A": [0, 0], "B": [0, 0]}
    for n in range(300):
        s = str(uuid.uuid4())
        cur.execute("SELECT abs(hashtext(%s::text || ':' || %s::text)) %% 2 AS m", (s, tm["id"]))
        b = "A" if cur.fetchone()["m"] == 0 else "B"
        adiciona = (n % 10) < (2 if b == "A" else 5)
        cur.execute("""INSERT INTO cardapio_sessoes (id, id_unidade, modo) VALUES (%s, %s, 'VITRINE')""", (s, U))
        cur.execute("""INSERT INTO cardapio_eventos (id_sessao, id_unidade, tipo, id_item, id_produto, modo, midia,
                                                     duracao_ms)
                       VALUES (%s, %s, 'viu_item', %s, %s, 'VITRINE', %s, 3000)""",
                    (s, U, itens["A"], A, "VIDEO" if b == "A" else "FOTO"))
        if adiciona:
            cur.execute("""INSERT INTO cardapio_eventos (id_sessao, id_unidade, tipo, id_item, id_produto, modo)
                           VALUES (%s, %s, 'adicionou', %s, %s, 'VITRINE')""", (s, U, itens["A"], A))
        feitas[b][0] += 1
        feitas[b][1] += int(adiciona)
st, t1 = chamar("POST", f"/cardapio-vivo/testes/{tm['id']}/encerrar", token=token)
res = t1.get("resultado", {})
checar("as sessões expostas batem com as fabricadas, por braço",
       res.get("A", {}).get("sessoes") == feitas["A"][0] and res.get("B", {}).get("sessoes") == feitas["B"][0],
       (res, feitas))
checar("a foto (B) adiciona mais e vence, com p-valor abaixo de 5%",
       res.get("conclusao") == "B_VENCE" and res.get("p_valor") is not None and res["p_valor"] < 0.05, res)
checar("encerrar grava o vencedor", t1.get("vencedor") == "B" and t1.get("aberto") is False, t1)
st, r = chamar("POST", f"/cardapio-vivo/testes/{tm['id']}/encerrar", token=token)
checar("encerrar de novo: 409", st == 409, st)

print("\n4. aplicar o vencedor")
st, t2 = chamar("POST", f"/cardapio-vivo/testes/{tm['id']}/aplicar", {"variante": "B"}, token)
checar("aplicar a foto responde 200", st == 200 and t2.get("aplicado_em"), (st, t2))
checar("e agora TODOS veem a foto do prato, sem teste nenhum",
       next(i for i in feed()["itens"] if i["id"] == itens["A"])["midia"]["tipo"] == "FOTO")
st, t3 = chamar("POST", f"/cardapio-vivo/testes/{to['id']}/aplicar", {"variante": "B"}, token)
checar("aplicar a ordem sugerida encerra o teste", st == 200 and t3.get("aberto") is False, (st, t3))
checar("e a ordem do catálogo passa a ser a sugerida", [i["id"] for i in feed()["itens"]][0] == itens["C"],
       [i["id"] for i in feed()["itens"]])
from services import cardapio_testes as ct  # noqa: E402
checar("amostra pequena nunca aponta vencedor", ct._proporcoes(50, 40, 50, 5)["conclusao"] == "AMOSTRA_PEQUENA")
checar("taxas iguais: sem diferença", ct._proporcoes(200, 40, 200, 40)["conclusao"] == "SEM_DIFERENCA")

print("\n5. sugestões de destaque: o sistema sugere, o gerente aprova")
chamar("PUT", f"/catalogos/itens/{itens['B']}/marcas", {"objetivo": "LANCAMENTO"}, token)
from datetime import date  # noqa: E402
hoje = date.today()
st, sug = chamar("GET", f"/cardapio-vivo/destaques/sugestoes?de={hoje}&ate={hoje}", token=token)
por = {s["id_item"]: s for s in sug} if st == 200 else {}
checar("o lançamento com pouca atenção é sugerido para destaque",
       por.get(itens["B"], {}).get("acao") == "POR" and "lançamento" in por[itens["B"]]["motivo"], sug)
checar("a torta, em destaque e sem atenção nem venda, é sugerida para sair do destaque",
       por.get(itens["C"], {}).get("acao") == "TIRAR", sug)
with get_cursor() as cur:
    cur.execute("SELECT destaque FROM catalogo_itens WHERE id = %s", (itens["B"],))
    checar("sugerir NÃO muda o cardápio", cur.fetchone()["destaque"] is False)
st, ap = chamar("POST", "/cardapio-vivo/destaques/aplicar",
                [{"id_item": itens["B"], "destaque": True}, {"id_item": itens["C"], "destaque": False}], token)
checar("aprovar aplica os dois", st == 200 and len(ap.get("feitos", [])) == 2, (st, ap))
with get_cursor() as cur:
    cur.execute("SELECT id, destaque FROM catalogo_itens WHERE id = ANY(%s)", ([itens["B"], itens["C"]],))
    d = {r["id"]: r["destaque"] for r in cur.fetchall()}
checar("e o cardápio muda", d == {itens["B"]: True, itens["C"]: False}, d)
st, r = chamar("POST", "/cardapio-vivo/destaques/aplicar", [{"id_item": 999999, "destaque": True}], token)
checar("item de outra casa (ou inexistente): 404", st == 404, st)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
