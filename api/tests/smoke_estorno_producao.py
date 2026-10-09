"""Estornar uma produção inteira, de uma vez.

Pedido do dono (09/10/2026): *"faz o botão de estornar produção."* O caminho era
Estoque ▸ Movimentos, um estorno por linha — a entrada do produzido e depois cada
insumo. `POST /estoque/producoes/{id}/estornar` faz o mesmo, na ordem certa.

O que esta suíte afirma:
1. o produzido sai, os insumos voltam, e a lista marca a produção como estornada
2. estornar de novo é recusado
3. o que já foi usado não volta: recusa com os dois números
4. a produção que nasceu de uma venda se desfaz cancelando a venda
5. quem só produz não desfaz

    python tests/smoke_estorno_producao.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, "tests")
sys.path.insert(0, ".")
from comum import garantir_cozinha, garantir_locais  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []


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
            return e.code, {"detail": bruto.decode(errors="replace")[:300]}


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
assert st == 200, r
token = r["access_token"]

marca = str(time.time_ns() // 100)[-6:]
hoje = date.today().isoformat()
locais = garantir_locais(chamar, token)
principal = next((x for x in locais if x.get("principal")), locais[0])
criados: list[int] = []


def saldo_de(id_produto):
    """A soma em todos os locais: a ficha consome de onde o insumo está."""
    _st, linhas = chamar("GET", f"/estoque/saldos?id_produto={id_produto}", token=token)
    return round(sum(float(x["quantidade"]) for x in linhas or []), 4)


def na_lista(id_producao):
    _st, lista = chamar("GET", "/estoque/producoes?limite=50", token=token)
    return next((x for x in lista or [] if x["id"] == id_producao), {})


def produto(sufixo, **campos):
    st, r = chamar("POST", "/produtos", {
        "codigo": f"EP{sufixo}-{marca}", "nome": f"Estorno prod {sufixo} {marca}",
        "um_estoque": "UN", "controla_estoque": True, "status": "ATIVO", **campos,
    }, token=token)
    assert st == 201, (st, r)
    criados.append(r["id"])
    return r["id"]


print("1. um insumo, e um produzido para estoque")
insumo = produto("INS", tipo="INSUMO", um_estoque="KG", id_local_padrao=principal["id"])
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": insumo, "quantidade": 20, "custo_unitario": 5,
    "id_local": principal["id"], "documento": f"EP-{marca}"}, token=token)
checar("o insumo entra: 20 KG a 5,00", st == 201, (st, r))
molho = produto("MOL", tipo="PRODUZIDO", producao_propria=True,
                modo_producao="PARA_ESTOQUE", id_local_padrao=principal["id"])
st, r = chamar("POST", "/fichas", {
    "id_produto": molho, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": insumo, "qtd_bruta": 1, "um": "KG"}]}, token=token)
chamar("POST", f"/fichas/{r.get('id')}/homologar", token=token)

st, r = chamar("POST", "/estoque/producoes", {
    "id_produto": molho, "quantidade": 4, "id_local": principal["id"]}, token=token)
producao = r.get("id")
checar("produz 4 unidades", st == 201, (st, r))
checar("o insumo baixou para 16 e o molho entrou com 4",
       saldo_de(insumo) == 16.0 and saldo_de(molho) == 4.0, (saldo_de(insumo), saldo_de(molho)))
checar("a produção nasce na lista sem estar estornada",
       na_lista(producao).get("estornada") is False, na_lista(producao))

print("\n2. estornar desfaz a produção inteira")
st, r = chamar("POST", f"/estoque/producoes/{producao}/estornar", {}, token=token)
checar("estornar responde", st == 201, (st, r))
# A entrada do molho e a saída do insumo: dois movimentos, dois estornos.
checar("e devolve os dois movimentos", r.get("estornados") == 2, r)
checar("o insumo volta para 20", saldo_de(insumo) == 20.0, saldo_de(insumo))
checar("e o molho sai da prateleira", saldo_de(molho) == 0.0, saldo_de(molho))
# ⚠️ A linha FICA: produção desfeita continua sendo história.
checar("a produção continua na lista, marcada como estornada",
       na_lista(producao).get("estornada") is True, na_lista(producao))
# 🔑 Nada é apagado: o razão ganha os contrários, apontando para os originais.
st, movs = chamar("GET", f"/estoque/movimentos?id_produto={molho}", token=token)
checar("no razão ficam a entrada e o estorno dela",
       sorted(m["tipo"] for m in movs or []) == ["ENTRADA_PRODUCAO", "ESTORNO_SAIDA"],
       [m["tipo"] for m in movs or []])

st, r = chamar("POST", f"/estoque/producoes/{producao}/estornar", {}, token=token)
checar("estornar de novo é recusado", st == 400 and "já foi estornada" in str(r), (st, r))
st, r = chamar("POST", "/estoque/producoes/99999999/estornar", {}, token=token)
checar("produção inexistente é 404", st == 404, st)

print("\n3. o que já foi usado não volta")
st, r = chamar("POST", "/estoque/producoes", {
    "id_produto": molho, "quantidade": 4, "id_local": principal["id"]}, token=token)
usada = r.get("id")
st, r = chamar("POST", "/estoque/saidas", {
    "id_produto": molho, "quantidade": 3, "id_local": principal["id"]}, token=token)
checar("três das quatro unidades são consumidas", st == 201, (st, r))
st, r = chamar("POST", f"/estoque/producoes/{usada}/estornar", {}, token=token)
# ⚠️ Tirar a entrada deixaria -3 na prateleira, com custo provisório. A recusa
# diz os dois números e manda para o ajuste.
checar("estornar é recusado, dizendo quanto entrou e quanto resta",
       st == 409 and "já foi usada" in str(r) and "ajuste" in str(r), (st, r))
checar("e nada se mexeu: o insumo segue em 16 e o molho em 1",
       saldo_de(insumo) == 16.0 and saldo_de(molho) == 1.0, (saldo_de(insumo), saldo_de(molho)))
checar("a produção continua de pé na lista", na_lista(usada).get("estornada") is False,
       na_lista(usada))

print("\n4. a produção que nasceu de uma venda")
cafe = produto("CAF", tipo="PRODUZIDO", producao_propria=True, modo_producao="NA_HORA",
               id_local_padrao=principal["id"])
st, r = chamar("POST", "/fichas", {
    "id_produto": cafe, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": insumo, "qtd_bruta": 0.5, "um": "KG"}]}, token=token)
chamar("POST", f"/fichas/{r.get('id')}/homologar", token=token)
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": hoje, "documento": f"EP-{marca}", "origem": "MANUAL", "canal": "BALCAO",
    "itens": [{"id_produto": cafe, "quantidade": 2, "valor_unitario": 9}]}]}, token=token)
checar("a venda do café produz na hora", st == 201 and r.get("produzidos_na_hora") == 1, (st, r))
st, lista = chamar("GET", "/estoque/producoes?limite=50", token=token)
da_venda = next((x for x in lista or [] if x["id_produto"] == cafe), {})
checar("a produção da venda aparece ligada a ela", bool(da_venda.get("id_venda")), da_venda)

st, r = chamar("POST", f"/estoque/producoes/{da_venda.get('id')}/estornar", {}, token=token)
# ⚠️ Estornar só a produção deixaria a saída da venda sem a entrada que a
# sustenta, e o café "na hora" com saldo negativo.
checar("estornar a produção de uma venda de pé é recusado, mandando cancelar a venda",
       st == 409 and "cancele a venda" in str(r), (st, r))
st, r = chamar("DELETE", f"/vendas/{da_venda.get('id_venda')}", token=token)
checar("cancelar a venda desfaz a produção junto", st == 200 and r.get("estornados") == 3, (st, r))
checar("e a lista mostra essa produção como estornada",
       na_lista(da_venda.get("id")).get("estornada") is True, na_lista(da_venda.get("id")))

print("\n5. quem só produz não desfaz")
tk_coz = garantir_cozinha(chamar, token)
st, r = chamar("POST", f"/estoque/producoes/{usada}/estornar", {}, token=tk_coz)
checar("a cozinha não estorna produção", st == 403, st)

for id_produto in reversed(criados):
    chamar("DELETE", f"/produtos/{id_produto}", token=token)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print(f"  - {x}")
sys.exit(1 if falhas else 0)
