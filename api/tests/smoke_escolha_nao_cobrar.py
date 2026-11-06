"""Item de escolha que NÃO cobra a opção: a embalagem da cesta de graça (migração 150).

🔑 **Pedido do dono (06/11/2026):** "Monte sua cesta" com Cesta Grande e Cesta Média — *"Não
cobrar o item, aí este preço não é apresentado"*, e, perguntado, *"não cobra, a embalagem sai
de graça"*. Confere: a marca grava e volta no cadastro; o site e a mesa mostram a cesta SEM
preço e a opção a zero (com a marca); o pedido de teste cobra só os itens e leva a embalagem a
R$ 0; desligada, tudo volta a cobrar. As prévias usadas aqui não gravam nada.

    python tests/smoke_escolha_nao_cobrar.py      (API de pé)
"""

import atexit
import json
import sys
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
MARCA = uuid.uuid4().hex[:6].upper()
ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=40) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")}


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
produtos: list[int] = []


def _devolver():
    with get_cursor() as cur:
        cur.execute("DELETE FROM catalogos WHERE nome LIKE %s", (f"%{MARCA}%",))
        cur.execute("UPDATE produtos SET ativo = false WHERE id = ANY(%s)", (produtos,))


atexit.register(_devolver)


def produto(nome, preco):
    _st, p = chamar("POST", "/produtos", {"nome": f"{nome} {MARCA}", "tipo": "INSUMO",
                                          "um_estoque": "UN", "controla_estoque": False}, token)
    _st, atual = chamar("GET", f"/produtos/{p['id']}", token=token)
    chamar("PUT", f"/produtos/{p['id']}", {**atual, "integrado_pdv": True, "preco_venda": preco}, token)
    produtos.append(p["id"])
    return p["id"]


print("0. cenário: Cesta Grande (40) e Média (30); itens Geleia (12) e Pão (8), de 2 a 3")
GRANDE, MEDIA = produto("CESTA GRANDE", 40), produto("CESTA MEDIA", 30)
GELEIA, PAO = produto("NC GELEIA", 12), produto("NC PAO", 8)
for cesta in (GRANDE, MEDIA):
    chamar("PUT", f"/produtos/{cesta}/adicionais", [
        {"nome": "Itens da cesta", "minimo": 2, "maximo": 3, "permite_repetir": True,
         "opcoes": [{"nome": "Geleia", "id_produto_ref": GELEIA},
                    {"nome": "Pão", "id_produto_ref": PAO}]}], token)
_st, cat = chamar("POST", "/catalogos", {"nome": f"Cesta gratis {MARCA}", "origem": "PRODUTOS",
                                         "situacao": "ATIVO"}, token)
ID_CAT = cat["id"]
_st, g = chamar("POST", f"/catalogos/{ID_CAT}/categorias", {"nome": "Presentes"}, token)

print("\n1. o cadastro")
st, item = chamar("POST", f"/catalogos/categorias/{g['id']}/escolhas",
                  {"nome": "Monte sua cesta", "nao_cobrar": True,
                   "opcoes": [{"id_produto": GRANDE, "rotulo": "Grande"},
                              {"id_produto": MEDIA, "rotulo": "Média"}]}, token)
checar("cria a cesta com 'não cobrar'", st == 201, (st, item))
_st, ct = chamar("GET", f"/catalogos/{ID_CAT}/conteudo", token=token)
it = next(i for c in ct["categorias"] for i in c["itens"] if i["id"] == item["id"])
checar("o cadastro devolve a marca e a linha SEM preço", it.get("nao_cobrar") is True
       and it["preco"] is None, (it.get("nao_cobrar"), it["preco"]))
checar("e cada opção guarda o preço do produto (40 e 30)",
       [float(o["preco_produto"]) for o in it["escolhas"]] == [40, 30], it["escolhas"])

print("\n2. o site e a mesa")
_st, site = chamar("GET", f"/catalogos/{ID_CAT}/previa-site", token=token)
s = next(i for c in site["categorias"] for i in c["itens"] if i["id"] == item["id"])
checar("no site a cesta sai sem preço e com a marca", s["preco"] is None and s["nao_cobrar"] is True, s)
checar("e as opções a zero", [o["preco"] for o in s["escolhas"]] == [0, 0], s["escolhas"])
checar("os itens da cesta continuam com preço",
       {o["nome"]: o["preco"] for o in s["escolhas"][0]["adicionais"][0]["opcoes"]} == {"Geleia": 12, "Pão": 8},
       s["escolhas"][0]["adicionais"])
_st, feed = chamar("GET", f"/cardapio-vivo/previa?id_catalogo={ID_CAT}", token=token)
f = next((i for i in feed.get("itens", []) if i["id"] == item["id"]), {})
checar("na mesa também: sem preço, marca e opções a zero",
       f.get("preco") is None and f.get("nao_cobrar") is True
       and [o["preco"] for o in f.get("escolhas") or []] == [0, 0], f)

print("\n3. o pedido cobra só os itens")
op_grande = s["escolhas"][0]["id"]
ad = {o["nome"]: o["id"] for o in s["escolhas"][0]["adicionais"][0]["opcoes"]}
corpo = {"modo": "RETIRADA", "itens": [{"id_item": item["id"], "quantidade": 1, "escolha": op_grande,
                                        "adicionais": [ad["Geleia"], ad["Geleia"], ad["Pão"]]}]}
st, t = chamar("POST", f"/catalogos/{ID_CAT}/pedido-teste", corpo, token)
linha = (t or {}).get("itens", [{}])[0]
checar("Grande + 2 geleias + 1 pão = R$ 32 (a embalagem a zero)",
       st == 200 and float(t["total"]) == 32, (st, t))
checar("a linha leva a embalagem pelo nome", "Grande" in linha.get("nome", ""), linha)
corpo_curto = {**corpo, "itens": [{**corpo["itens"][0], "adicionais": [ad["Pão"]]}]}
st, t = chamar("POST", f"/catalogos/{ID_CAT}/pedido-teste", corpo_curto, token)
checar("o mínimo conta só os itens: 1 item é recusado (422)", st == 422, (st, t))

print("\n4. desligado, volta a cobrar")
st, r = chamar("PUT", f"/catalogos/itens/{item['id']}/escolha",
               {"nome": "Monte sua cesta", "nao_cobrar": False,
                "opcoes": [{"id_produto": GRANDE, "rotulo": "Grande"},
                           {"id_produto": MEDIA, "rotulo": "Média"}]}, token)
checar("desligar grava", st == 200, (st, r))
_st, site = chamar("GET", f"/catalogos/{ID_CAT}/previa-site", token=token)
s = next(i for c in site["categorias"] for i in c["itens"] if i["id"] == item["id"])
checar("o cartão volta a 'a partir de 30'", s["preco"] == 30 and s["nao_cobrar"] is False, s)
# ⚠️ Salvar o item regrava as opções: os ids mudam, e o pedido precisa dos novos.
ad = {o["nome"]: o["id"] for o in s["escolhas"][0]["adicionais"][0]["opcoes"]}
corpo = {"modo": "RETIRADA", "itens": [{"id_item": item["id"], "quantidade": 1,
                                        "escolha": s["escolhas"][0]["id"],
                                        "adicionais": [ad["Geleia"], ad["Geleia"], ad["Pão"]]}]}
st, t = chamar("POST", f"/catalogos/{ID_CAT}/pedido-teste", corpo, token)
checar("e o pedido cobra a embalagem: 40 + 32 = R$ 72", st == 200 and float(t["total"]) == 72, (st, t))
with get_cursor() as cur:
    cur.execute("""SELECT 1 FROM auditoria WHERE entidade = 'catalogo_item' AND id_entidade::text = %s
                     AND acao = 'atualizar_escolha' AND antes::text LIKE '%%nao_cobrar%%'""",
                (str(item["id"]),))
    checar("a troca fica na auditoria com o valor de antes", cur.fetchone() is not None)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
