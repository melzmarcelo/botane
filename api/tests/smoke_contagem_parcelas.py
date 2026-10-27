"""Teste de fumaça: a contagem em PARCELAS — "3 UN + 948 ML" (migração 135).

🔑 Pedido do dono (27/10/2026), no teste do CAMPARI: estoque em UN, dose em ML, e na
prateleira as garrafas fechadas e UMA aberta. Confere:

    1. Cenário: um destilado em UN com ML cadastrado (garrafa de 1 L), 4 UN em estoque.
    2. 3 UN + 948 ML viram 3,948 UN; as parcelas voltam como digitadas, e o
       "informado" de uma parcela só fica vazio.
    3. Uma parcela só grava como a contagem de sempre (sem `parcelas`).
    4. Unidade que não converte é 400 e não grava nada; lista vazia é "não contei".
    5. Fechar acerta o saldo para 3,948 UN.
    6. Juntar unidades (apelidos) reaponta a unidade DENTRO das parcelas.

    python tests/smoke_contagem_parcelas.py      (API de pé na 9200)
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

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
local = garantir_local(chamar, token)
abertas: list[int] = []
atexit.register(lambda: [chamar("DELETE", f"/inventarios/{i}", token=token) for i in abertas])

print("1. cenário: destilado em UN, com ML cadastrado (garrafa de 1 L)")
st, p = chamar("POST", "/produtos", {"nome": f"DESTILADO PARCELA {marca}", "tipo": "REVENDA",
                                     "um_estoque": "UN", "status": "ATIVO"}, token=token)
idp = (p or {}).get("id")
checar("o produto nasce", bool(idp), (st, p))
chamar("PUT", f"/produtos/{idp}", {"id_local_padrao": local["id"]}, token=token)
st, r = chamar("PUT", f"/produtos/{idp}/unidades",
               {"itens": [{"um": "ML", "fator": 0.001}]}, token=token)
checar("1 ML = 0,001 UN", st == 200, (st, r))
st, r = chamar("POST", "/estoque/entradas", {"id_produto": idp, "quantidade": 4,
                                             "custo_unitario": 50, "id_local": local["id"],
                                             "documento": f"NF-PARC-{marca}"}, token=token)
checar("entram 4 UN", st in (200, 201), (st, r))
st, inv = chamar("POST", "/inventarios", {"locais": [local["id"]], "produtos": [idp], "cega": False},
                 token=token)
id_inv = (inv or {}).get("id")
if id_inv:
    abertas.append(id_inv)
checar("abre a contagem", st == 201, (st, inv))


def item_de(inv):
    return next((i for i in (inv or {}).get("itens", []) if i["id_produto"] == idp), None)


def contar(corpo_item):
    return chamar("PUT", f"/inventarios/{id_inv}/contagem",
                  {"itens": [{"id_produto": idp, "id_local": local["id"], **corpo_item}]},
                  token=token)


print("\n2. 3 UN + 948 ML")
st, inv = contar({"parcelas": [{"qtd": 3, "um": "UN"}, {"qtd": 948, "um": "ML"}]})
i = item_de(inv)
checar("grava", st == 200, (st, inv))
checar("a contagem é 3,948 UN", i and perto(i["qtd_contada"], 3.948), i)
checar("as parcelas voltam como digitadas",
       i and [(float(x["qtd"]), x["um"]) for x in i["parcelas"] or []]
       == [(3.0, "UN"), (948.0, "ML")], i and i["parcelas"])
checar("o informado de uma parcela só fica vazio",
       i and i["qtd_informada"] is None and i["um_informada"] is None, i)
checar("a diferença é −0,052 UN", i and perto(i["diferenca"], -0.052), i)

print("\n3. uma parcela só: a contagem de sempre")
st, inv = contar({"parcelas": [{"qtd": 3500, "um": "ML"}]})
i = item_de(inv)
checar("3.500 ML = 3,5 UN, sem parcelas guardadas",
       i and perto(i["qtd_contada"], 3.5) and i["parcelas"] is None
       and perto(i["qtd_informada"], 3500) and i["um_informada"] == "ML", i)
st, inv = contar({"qtd_contada": 2, "um": "UN"})
i = item_de(inv)
checar("e o pedido antigo (qtd_contada + um) segue igual",
       i and perto(i["qtd_contada"], 2) and i["parcelas"] is None, i)

print("\n4. o que não converte, e a lista vazia")
st, r = contar({"parcelas": [{"qtd": 3, "um": "UN"}, {"qtd": 1, "um": "KG"}]})
checar("KG num produto sem KG é 400", st == 400 and "KG" in str(r), (st, r))
st, inv = chamar("GET", f"/inventarios/{id_inv}", token=token)
checar("e nada mudou (segue 2 UN)", perto(item_de(inv)["qtd_contada"], 2), item_de(inv))
st, inv = contar({"parcelas": []})
checar("lista vazia é 'não contei'", st == 200 and item_de(inv)["qtd_contada"] is None,
       item_de(inv))

print("\n5. fechar acerta o saldo")
contar({"parcelas": [{"qtd": 3, "um": "UN"}, {"qtd": 948, "um": "ML"}]})
st, r = chamar("POST", f"/inventarios/{id_inv}/fechar", token=token)
checar("fecha", st == 200, (st, r))
if st == 200:
    abertas.remove(id_inv)
st, saldos = chamar("GET", f"/estoque/saldos?id_produto={idp}", token=token)
lista = saldos if isinstance(saldos, list) else (saldos or {}).get("itens", [])
s = next((x for x in lista if x.get("id_produto") == idp and x.get("id_local") == local["id"]),
         None)
checar("o saldo vira 3,948 UN", s and perto(s["quantidade"], 3.948), s or saldos)

print("\n6. juntar unidades reaponta a unidade dentro das parcelas")
sig = f"Q{marca[-4:]}"
st, r = chamar("POST", "/unidades-medida", {"sigla": sig, "nome": f"mililitro teste {marca}",
                                            "grandeza": "VOLUME", "fator_base": 1}, token=token)
checar("nasce uma unidade igual ao ML", st in (200, 201), (st, r))
chamar("PUT", f"/produtos/{idp}/unidades",
       {"itens": [{"um": "ML", "fator": 0.001}, {"um": sig, "fator": 0.001}]}, token=token)
st, inv2 = chamar("POST", "/inventarios", {"locais": [local["id"]], "produtos": [idp]},
                  token=token)
id_inv2 = (inv2 or {}).get("id")
if id_inv2:
    abertas.append(id_inv2)
st, inv2 = chamar("PUT", f"/inventarios/{id_inv2}/contagem",
                  {"itens": [{"id_produto": idp, "id_local": local["id"],
                              "parcelas": [{"qtd": 1, "um": "UN"}, {"qtd": 500, "um": sig}]}]},
                  token=token)
checar("conta 1 UN + 500 na unidade nova", st == 200
       and perto(item_de(inv2)["qtd_contada"], 1.5), (st, item_de(inv2)))
st, r = chamar("POST", f"/unidades-medida/{sig}/juntar", {"em": "ML"},
               token=token)
checar("junta a nova no ML", st == 200, (st, r))
st, inv2 = chamar("GET", f"/inventarios/{id_inv2}", token=token)
i = item_de(inv2)
checar("a parcela passa a dizer ML",
       i and [x["um"] for x in i["parcelas"] or []] == ["UN", "ML"], i and i["parcelas"])

chamar("DELETE", f"/produtos/{idp}", token=token)
print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
sys.exit(1 if falhas else 0)
