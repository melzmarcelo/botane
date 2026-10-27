"""Teste de fumaça: quem PRODUZ não é, por força, a quem o produto pertence (migração 137).

🔑 Pedido do dono (27/10/2026): *"a Confeitaria produz bolachas que vão junto com o
café. A produção é responsabilidade da Confeitaria. Mas após pronto, este produto vai
direto para o estoque da Cafeteria."* Confere:

    1. Cenário: setores Confeitaria e Cafeteria, um local de cada; farinha no
       estoque central E na Confeitaria; a bolacha é da Cafeteria (setor e local) e
       "produzida por" Confeitaria.
    2. O cadastro grava e devolve o setor que produz.
    3. A prévia diz as duas pontas: produz Confeitaria, entra na Cafeteria; e
       procura a farinha na Confeitaria.
    4. Produzir: a farinha sai da CONFEITARIA, a bolacha entra na CAFETERIA.
    5. Sem o setor que produz, a farinha sai do lugar de sempre (o central).
    6. O destino de verdade (o defeito achado): escolher um local onde o produto
       MORA faz o produzido entrar lá; escolher um onde ele não mora, não.
    7. O painel inicial mostra a tarefa para quem é da Confeitaria, não da Cafeteria.

    python tests/smoke_setor_que_produz.py      (API de pé na 9200)
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, "tests")
from comum import garantir_local  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
ok = 0
falhas: list[str] = []
marca = str(int(time.time()))[-6:]


def chamar(metodo, caminho, corpo=None, token=None):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=90) as r:
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


def perto(a, b, tol=0.0001):
    return a is not None and abs(float(a) - float(b)) <= tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
central = garantir_local(chamar, token)
criados: dict = {"produtos": [], "locais": [], "setores": [], "usuario": None}


def _limpar():
    try:
        if criados["usuario"]:
            chamar("DELETE", f"/usuarios/{criados['usuario']}", token=token)
        for p in criados["produtos"]:
            chamar("DELETE", f"/produtos/{p}", token=token)
        for l in criados["locais"]:
            chamar("DELETE", f"/locais/{l}", token=token)
        for s in criados["setores"]:
            chamar("DELETE", f"/setores/{s}", token=token)
    except Exception:
        pass


atexit.register(_limpar)


def saldo(id_produto, id_local):
    st, lista = chamar("GET", f"/estoque/saldos?id_produto={id_produto}", token=token)
    lista = lista if isinstance(lista, list) else (lista or {}).get("itens", [])
    return sum(float(x["quantidade"]) for x in lista if x.get("id_local") == id_local)


print("1. cenário: Confeitaria produz, Cafeteria guarda")
setor = {}
for chave in ("CONF", "CAFE"):
    st, s = chamar("POST", "/setores", {"nome": f"{chave} QUEM PRODUZ {marca}"}, token=token)
    setor[chave] = (s or {}).get("id")
    criados["setores"].append(setor[chave])
local = {}
for chave in ("CONF", "CAFE", "VITRINE"):
    st, l = chamar("POST", "/locais", {"nome": f"{chave} QP {marca}", "tipo": "SECO",
                                       "id_setor": setor.get(chave)}, token=token)
    local[chave] = (l or {}).get("id")
    criados["locais"].append(local[chave])
checar("setores e locais nascem", all(setor.values()) and all(local.values()), (setor, local))

st, f = chamar("POST", "/produtos", {"nome": f"FARINHA QP {marca}", "tipo": "INSUMO",
                                     "um_estoque": "KG", "status": "ATIVO"}, token=token)
farinha = f["id"]
criados["produtos"].append(farinha)
chamar("PUT", f"/produtos/{farinha}", {"id_local_padrao": central["id"]}, token=token)
for onde in (central["id"], local["CONF"]):
    chamar("POST", "/estoque/entradas", {"id_produto": farinha, "quantidade": 5,
                                         "custo_unitario": 4, "id_local": onde,
                                         "documento": f"NF-QP-{marca}"}, token=token)

st, b = chamar("POST", "/produtos", {
    "nome": f"BOLACHA QP {marca}", "tipo": "PRODUZIDO", "um_estoque": "UN",
    "producao_propria": True, "status": "ATIVO", "id_setor": setor["CAFE"],
    "id_setor_producao": setor["CONF"], "id_local_padrao": local["CAFE"]}, token=token)
bolacha = (b or {}).get("id")
criados["produtos"].append(bolacha)
checar("a bolacha nasce da Cafeteria, produzida pela Confeitaria", st == 201, (st, b))
st, fi = chamar("POST", "/fichas", {"id_produto": bolacha, "rendimento_qtd": 10,
                                    "rendimento_um": "UN", "porcoes": 10,
                                    "itens": [{"id_insumo": farinha, "qtd_bruta": 1,
                                               "um": "KG"}]}, token=token)
st, _ = chamar("POST", f"/fichas/{(fi or {}).get('id')}/homologar", {}, token=token)
checar("a ficha (10 bolachas por 1 KG de farinha) é homologada", st == 200, st)

print("\n2. o cadastro grava e devolve quem produz")
st, p = chamar("GET", f"/produtos/{bolacha}", token=token)
checar("id_setor_producao e o nome voltam",
       p.get("id_setor_producao") == setor["CONF"]
       and p.get("setor_producao") == f"CONF QUEM PRODUZ {marca}", p)

print("\n3. a prévia diz as duas pontas")
st, prev = chamar("GET", f"/producao-agenda/necessario?id_produto={bolacha}&quantidade=10",
                  token=token)
checar("produz: Confeitaria → entra em: Cafeteria",
       prev.get("setor_que_produz") == f"CONF QUEM PRODUZ {marca}"
       and prev.get("id_local_destino") == local["CAFE"], (st, prev))
linha = next((i for i in prev.get("itens", []) if i["id_produto"] == farinha), {})
checar("e a farinha é procurada na Confeitaria (5 KG lá)", perto(linha.get("saldo_no_local"), 5),
       linha)

print("\n4. produzir")
st, r = chamar("POST", "/estoque/producoes", {"id_produto": bolacha, "quantidade": 10},
               token=token)
checar("produz", st == 201, (st, r))
checar("a farinha sai da CONFEITARIA (5 → 4) e o central fica (5)",
       perto(saldo(farinha, local["CONF"]), 4) and perto(saldo(farinha, central["id"]), 5),
       (saldo(farinha, local["CONF"]), saldo(farinha, central["id"])))
checar("a bolacha entra na CAFETERIA", perto(saldo(bolacha, local["CAFE"]), 10)
       and r.get("id_local") == local["CAFE"], (saldo(bolacha, local["CAFE"]), r.get("id_local")))

print("\n5. sem o setor que produz, o lugar de sempre")
chamar("PUT", f"/produtos/{bolacha}", {"id_setor_producao": None}, token=token)
st, p = chamar("GET", f"/produtos/{bolacha}", token=token)
checar("o campo se limpa", p.get("id_setor_producao") is None, p.get("id_setor_producao"))
st, r = chamar("POST", "/estoque/producoes",
               {"id_produto": bolacha, "quantidade": 10, "id_local": central["id"]}, token=token)
checar("a farinha sai do central (5 → 4), a Confeitaria fica (4)",
       perto(saldo(farinha, central["id"]), 4) and perto(saldo(farinha, local["CONF"]), 4),
       (saldo(farinha, central["id"]), saldo(farinha, local["CONF"])))

print("\n6. o destino de verdade")
checar("o central, onde a bolacha NÃO mora, não vira destino: entrou na Cafeteria",
       perto(saldo(bolacha, local["CAFE"]), 20) and r.get("id_local") == local["CAFE"],
       (saldo(bolacha, local["CAFE"]), r.get("id_local")))
st, _ = chamar("POST", f"/produtos/{bolacha}/locais", {"id_local": local["VITRINE"]},
               token=token)
checar("a bolacha passa a morar também na vitrine", st in (200, 201), st)
st, r = chamar("POST", "/estoque/producoes",
               {"id_produto": bolacha, "quantidade": 10, "id_local": local["VITRINE"]},
               token=token)
checar("produzida PARA a vitrine, entra na vitrine",
       perto(saldo(bolacha, local["VITRINE"]), 10) and r.get("id_local") == local["VITRINE"],
       (saldo(bolacha, local["VITRINE"]), r.get("id_local")))
st, prev = chamar("GET", f"/producao-agenda/necessario?id_produto={bolacha}&quantidade=10"
                  f"&id_local={local['VITRINE']}", token=token)
checar("e a prévia diz o mesmo destino", prev.get("id_local_destino") == local["VITRINE"], prev)

print("\n7. o painel mostra a tarefa para quem PRODUZ")
chamar("PUT", f"/produtos/{bolacha}", {"id_setor_producao": setor["CONF"]}, token=token)
st, ag = chamar("POST", "/producao-agenda", {"id_produto": bolacha, "quantidade": 10,
                                             "data_prevista": date.today() + timedelta(days=1)},
                token=token)
checar("agenda", st == 201, (st, ag))
st, papeis = chamar("GET", "/papeis", token=token)
papel = next((x for x in (papeis or []) if x["nome"] == "Cozinha"), None)


def painel_de(id_setor, sufixo):
    email = f"smoke.qp{sufixo}{marca}@botane.com.br"
    st, u = chamar("POST", "/usuarios", {"nome": f"QP {sufixo} {marca}", "email": email,
                                         "senha": "smoke-qp-12345",
                                         "papeis": [{"id_papel": papel["id"]}],
                                         "setores": [id_setor]}, token=token)
    st, ent = chamar("POST", "/auth/login", {"email": email, "senha": "smoke-qp-12345"})
    st, pn = chamar("GET", "/inicio", token=(ent or {}).get("access_token"))
    chamar("DELETE", f"/usuarios/{(u or {}).get('id')}", token=token)
    return [l["produto"] for l in ((pn or {}).get("producao") or {}).get("linhas", [])]


checar("quem é da Confeitaria vê a bolacha",
       f"BOLACHA QP {marca}" in painel_de(setor["CONF"], "conf"))
checar("quem é da Cafeteria NÃO vê", f"BOLACHA QP {marca}" not in painel_de(setor["CAFE"], "cafe"))
chamar("DELETE", f"/producao-agenda/{(ag or {}).get('id')}", token=token)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
sys.exit(1 if falhas else 0)
