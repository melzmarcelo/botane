"""Teste de fumaça da alteração múltipla de produtos.

🔑 **O pedido do dono (09/09/2026):** "selecionar vários produtos e inativar, ou
selecionar vários e colocar em um tipo ou categoria ou setor". O catálogo tem
3.183 produtos e 2.229 vieram do Omie sem categoria nem setor — arrumar um a um
são quatro passos por produto, e ninguém faz duas mil vezes.

⚠️ **A prévia vem antes, e é a MESMA função da aplicação.** Duas implementações
divergiriam no primeiro caso especial, e a divergência apareceria como "a prévia
prometeu 300 e mudou 280" — sem ninguém saber qual das duas estava certa. Esta
suíte cobra as duas pelo mesmo cenário.

    python tests/smoke_alteracao_multipla.py        (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []
marca = uuid.uuid4().hex[:6].upper()
criados: list[int] = []


def chamar(metodo, caminho, corpo=None, token=None):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
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


def criar(nome, **extra):
    corpo = {"codigo": f"AM{len(criados)}-{marca}", "nome": f"{nome} {marca}",
             "tipo": "INSUMO", "um_estoque": "UN", "controla_estoque": True,
             "status": "ATIVO", **extra}
    _st, r = chamar("POST", "/produtos", corpo, token=token)
    if r.get("id"):
        criados.append(r["id"])
    return r.get("id")


def do_banco(id_produto, colunas):
    with get_cursor() as cur:
        cur.execute(f"SELECT {', '.join(colunas)} FROM produtos WHERE id = %s", (id_produto,))
        return dict(cur.fetchone() or {})


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token), (st, r))
init_pool()

st, cats = chamar("GET", "/categorias", token=token)
categoria = (cats or [{}])[0].get("id")
st, sets_ = chamar("GET", "/setores", token=token)
setor = (sets_ or [{}])[0].get("id")
checar("a base tem categoria e setor para usar", bool(categoria and setor), (categoria, setor))


print("\n1. o cenario: quatro produtos, um deles de producao propria")
a = criar("MULTIPLA A")
b = criar("MULTIPLA B")
ja_na_categoria = criar("MULTIPLA C", id_categoria=categoria)
prato = criar("MULTIPLA PRATO", tipo="PRODUZIDO", producao_propria=True)
checar("os produtos nascem", all([a, b, ja_na_categoria, prato]), criados)


print("\n2. a PREVIA nao escreve, e separa quem ja estava assim")
st, prev = chamar("POST", "/produtos/alteracao-multipla", {
    "ids": [a, b, ja_na_categoria], "id_categoria": categoria}, token=token)
checar("a previa responde", st == 200, (st, prev))
checar("dois mudariam", len(prev["mudam"]) == 2, prev["message"])
# 🔑 "Ja estava assim" nao e mudanca: dizer "3 alterados" quando um ja estava
# certo nao informa nada a quem marcou trinta linhas.
checar("e um ja estava na categoria", len(prev["iguais"]) == 1, prev["message"])
checar("a previa diz que NAO aplicou", prev.get("aplicado") is False, prev)
checar("e nada foi gravado", do_banco(a, ["id_categoria"])["id_categoria"] is None,
       do_banco(a, ["id_categoria"]))


print("\n3. aplicar muda so quem precisava")
st, ap = chamar("POST", "/produtos/alteracao-multipla", {
    "ids": [a, b, ja_na_categoria], "id_categoria": categoria, "simular": False}, token=token)
checar("a aplicacao responde", st == 200, (st, ap))
checar("dois mudaram", len(ap["mudam"]) == 2, ap["message"])
checar("e agora o A tem a categoria",
       do_banco(a, ["id_categoria"])["id_categoria"] == categoria, do_banco(a, ["id_categoria"]))
checar("o B tambem",
       do_banco(b, ["id_categoria"])["id_categoria"] == categoria, do_banco(b, ["id_categoria"]))


print("\n4. producao propria RECUSA o tipo que nao a aceita, e os outros seguem")
# ⚠️ O banco recusa `producao_propria` fora de PRODUZIDO/KIT. Num lote sem esta
# guarda, um unico prato derrubaria a transacao inteira -- e os outros 299 nao
# mudariam, sem nada dizendo por que.
st, r4 = chamar("POST", "/produtos/alteracao-multipla", {
    "ids": [a, b, prato], "tipo": "REVENDA", "simular": False}, token=token)
checar("a chamada responde 200, nao 500", st == 200, (st, r4))
checar("dois mudaram de tipo", len(r4["mudam"]) == 2, r4["message"])
checar("e o prato foi RECUSADO, nomeado", len(r4["recusados"]) == 1, r4["recusados"])
checar("dizendo por que",
       "produ" in (r4["recusados"][0].get("motivo") or "").lower(), r4["recusados"])
checar("o A virou REVENDA", do_banco(a, ["tipo"])["tipo"] == "REVENDA", do_banco(a, ["tipo"]))
# 🔑 A recusa de um NAO pode desfazer os outros: o lote e util justamente por
# nao exigir que tudo esteja perfeito.
checar("e o prato continua PRODUZIDO", do_banco(prato, ["tipo"])["tipo"] == "PRODUZIDO",
       do_banco(prato, ["tipo"]))


print("\n5. inativar em lote")
st, r5 = chamar("POST", "/produtos/alteracao-multipla", {
    "ids": [a, b], "ativo": False, "simular": False}, token=token)
checar("os dois sao inativados", len(r5["mudam"]) == 2, r5["message"])
checar("e o banco confirma", do_banco(a, ["ativo"])["ativo"] is False, do_banco(a, ["ativo"]))
# E volta.
chamar("POST", "/produtos/alteracao-multipla",
       {"ids": [a], "ativo": True, "simular": False}, token=token)
checar("reativar tambem funciona", do_banco(a, ["ativo"])["ativo"] is True, do_banco(a, ["ativo"]))


print("\n6. o setor tambem, e os dois campos juntos")
st, r6 = chamar("POST", "/produtos/alteracao-multipla", {
    "ids": [a, b], "id_setor": setor, "tipo": "INSUMO", "simular": False}, token=token)
checar("setor e tipo mudam na mesma passada", len(r6["mudam"]) == 2, r6["message"])
d = do_banco(a, ["id_setor", "tipo"])
checar("e os dois valores estao no banco",
       d["id_setor"] == setor and d["tipo"] == "INSUMO", d)


print("\n7. o que o servidor recusa de entrada")
st, r7 = chamar("POST", "/produtos/alteracao-multipla", {"ids": [a]}, token=token)
checar("sem nenhuma alteracao escolhida, nao faz nada",
       not r7["mudam"] and "Nenhuma altera" in r7["message"], r7)
st, r8 = chamar("POST", "/produtos/alteracao-multipla",
                {"ids": [], "id_setor": setor}, token=token)
checar("sem produto escolhido, tambem nao", not r8["mudam"], r8)
st, r9 = chamar("POST", "/produtos/alteracao-multipla",
                {"ids": [a], "tipo": "INVENTADO", "simular": False}, token=token)
checar("tipo invalido e recusado", "inv" in r9["message"].lower(), r9)
checar("e nada mudou", do_banco(a, ["tipo"])["tipo"] == "INSUMO", do_banco(a, ["tipo"]))

# ⚠️ `simular` e VERDADEIRO por padrao: um chamador que esqueca o campo recebe a
# previa, nunca uma escrita em trezentos cadastros.
st, r10 = chamar("POST", "/produtos/alteracao-multipla",
                 {"ids": [b], "tipo": "EMBALAGEM"}, token=token)
checar("sem `simular`, o padrao e a PREVIA", r10.get("aplicado") is False, r10)
checar("e o produto nao mudou", do_banco(b, ["tipo"])["tipo"] == "INSUMO", do_banco(b, ["tipo"]))

st, r11 = chamar("POST", "/produtos/alteracao-multipla", {"ids": [a], "ativo": False})
checar("sem autenticacao e barrado", st in (401, 403), st)


for pid in criados:
    chamar("DELETE", f"/produtos/{pid}", token=token)
with get_cursor() as cur:
    cur.execute("DELETE FROM produtos WHERE id = ANY(%s)", (criados,))

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
raise SystemExit(1 if falhas else 0)
