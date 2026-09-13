"""O rendimento que vem da SOMA dos ingredientes, e o tamanho da porção.

🔑 **Pedido do dono (12/09/2026):** *"de onde vem o rendimento da receita? tem
como ser gerada automaticamente? o sistema que a cliente utiliza soma todos os
ingredientes e gera isto automaticamente. E hoje temos somente a quantidade de
porções que rende, mas podemos ter ao contrário: informar os gramas/kg/un e ele
calcular quantas porções rende"*.

A fórmula é a da área: **Σ (líquido convertido para massa × fator de cocção)**.

⚠️ **Três coisas que a conta precisa saber, e cada uma tem checagem aqui:**
  1. G, ML e UN não somam sozinhos — ML entra por densidade 1 (dito na resposta)
     e UN só entra se o produto disser quanto pesa uma unidade.
  2. O que soma é o LÍQUIDO: 1 kg de cenoura com casca vira 800 g na panela.
  3. O fator de cocção muda o RENDIMENTO e não o custo — está escrito na coluna
     desde a migração 006 e não era lido por ninguém até agora.

⚠️ **Nada é gravado pela sugestão.** `rendimento_qtd` divide o consumo na
produção, então recalcular sozinho mudaria o custo unitário de tudo que a ficha
produz, calado.

    python tests/smoke_rendimento.py        (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []
marca = uuid.uuid4().hex[:6].upper()
produtos: list[int] = []
fichas: list[int] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + urllib.parse.quote(caminho, safe="/?=&"), method=metodo)
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


def perto(a, b, tol=0.01):
    return abs(float(a or 0) - float(b)) < tol


def novo(nome, tipo, um, **extra):
    _st, r = chamar("POST", "/produtos", {
        "nome": f"{nome} {marca}", "tipo": tipo, "um_estoque": um,
        "status": "ATIVO", "controla_estoque": True, **extra,
    }, token)
    if r.get("id"):
        produtos.append(r["id"])
    return r.get("id")


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))

print("\n1. o cenario: farinha em G, leite em ML e ovo em UN")
farinha = novo("Rend farinha", "INSUMO", "G")
leite = novo("Rend leite", "INSUMO", "ML")
ovo = novo("Rend ovo", "INSUMO", "UN")
# 🔑 O ovo so entra na soma se o cadastro disser quanto pesa UM. E a mesma
# equivalencia de peso da tela de unidades: 1 UN = 50 G.
st, r = chamar("PUT", f"/produtos/{ovo}/unidades",
               {"itens": [{"um": "G", "fator": 1 / 50, "padrao": True}]}, token)
checar("o ovo ganha a equivalencia de peso (1 UN = 50 G)", st == 200, (st, r))

itens = [
    {"id_insumo": farinha, "qtd_bruta": 500, "um": "G"},
    {"id_insumo": leite, "qtd_bruta": 250, "um": "ML"},
    {"id_insumo": ovo, "qtd_bruta": 3, "um": "UN"},
]

print("\n2. a soma: 500 G + 250 ML + 3 ovos de 50 G = 900 G")
st, s1 = chamar("POST", "/fichas/rendimento-sugerido", {"itens": itens}, token)
checar("a rota responde", st == 200, (st, s1))
checar("somando 900 G", perto(s1.get("qtd"), 900), s1)
checar("em G, que e a unidade da soma", s1.get("um") == "G", s1.get("um"))
# ⚠️ A densidade 1 e suposicao, e a resposta tem de dizer que a usou — erraria
# feio em oleo (0,92) e em mel (1,42).
checar("avisando que assumiu 1 ML = 1 G", s1.get("assumiu_densidade") is True, s1)
checar("e sem ninguem de fora da conta", s1.get("itens_fora") == [], s1.get("itens_fora"))

print("\n3. a resposta sai na unidade da ficha")
st, s2 = chamar("POST", "/fichas/rendimento-sugerido", {"itens": itens, "um": "KG"}, token)
checar("pedindo KG, vem 0,9 KG", perto(s2.get("qtd"), 0.9, 0.0001) and s2.get("um") == "KG", s2)

print("\n4. o que soma e o LIQUIDO, nao o bruto")
# 1 kg de cenoura com casca vira 800 g na panela: o bruto e o que sai do estoque
# e custa; o liquido e o que entra no prato.
liquidos = [{"id_insumo": farinha, "qtd_bruta": 1000, "qtd_liquida": 800, "um": "G"}]
st, s3 = chamar("POST", "/fichas/rendimento-sugerido", {"itens": liquidos}, token)
checar("com liquida informada, soma 800 e nao 1000", perto(s3.get("qtd"), 800), s3)

print("\n5. o fator de coccao entra na conta — e so nela")
# Bolo perde agua no forno. 500 G de farinha a 0,9 dao 450 G.
coccao = [{"id_insumo": farinha, "qtd_bruta": 500, "um": "G", "fator_coccao": 0.9}]
st, s4 = chamar("POST", "/fichas/rendimento-sugerido", {"itens": coccao}, token)
checar("coccao 0,9 sobre 500 G da 450 G", perto(s4.get("qtd"), 450), s4)
# ⚠️ E arroz GANHA peso: o fator maior que 1 tambem vale.
crescer = [{"id_insumo": farinha, "qtd_bruta": 200, "um": "G", "fator_coccao": 2.5}]
st, s5 = chamar("POST", "/fichas/rendimento-sugerido", {"itens": crescer}, token)
checar("coccao 2,5 sobre 200 G da 500 G", perto(s5.get("qtd"), 500), s5)

print("\n6. quem nao sabe dizer o peso fica de FORA, e aparece")
# ⚠️ Somar "3 UN" como 3 G seria dizer que tres ovos pesam tres gramas. O item
# sai da conta e a resposta o nomeia: rendimento que ignora metade da receita em
# silencio e pior que rendimento nenhum.
sem_peso = novo("Rend caixa sem peso", "INSUMO", "UN")
st, s6 = chamar("POST", "/fichas/rendimento-sugerido", {
    "itens": [{"id_insumo": farinha, "qtd_bruta": 100, "um": "G"},
              {"id_insumo": sem_peso, "qtd_bruta": 2, "um": "UN"}]}, token)
checar("a soma leva so o que sabe (100 G)", perto(s6.get("qtd"), 100), s6)
checar("e o item sem peso vem nomeado em itens_fora",
       len(s6.get("itens_fora") or []) == 1
       and marca in (s6["itens_fora"][0].get("nome") or ""), s6.get("itens_fora"))

print("\n7. o tamanho da porcao, gravado e devolvido")
bolo = novo("Rend bolo", "PRODUZIDO", "KG", producao_propria=True)
st, f = chamar("POST", "/fichas", {
    "id_produto": bolo, "rendimento_qtd": 2, "rendimento_um": "KG", "porcoes": 8,
    "porcao_qtd": 0.25, "itens": itens,
}, token)
checar("cria ficha com o tamanho da porcao", st == 201, (st, f))
if f.get("id"):
    fichas.append(f["id"])
st, d = chamar("GET", f"/fichas/{f.get('id')}", token=token)
checar("e o GET devolve 0,25 KG por porcao", perto(d.get("porcao_qtd"), 0.25, 0.0001),
       d.get("porcao_qtd"))
# 2 KG / 0,25 KG = 8 porcoes: os dois lados do mesmo dado batem.
checar("que fecha com as 8 porcoes gravadas",
       perto(float(d.get("rendimento_qtd") or 0) / float(d.get("porcao_qtd") or 1), 8), d)

st, r = chamar("PUT", f"/fichas/{f['id']}", {"porcao_qtd": 0.5, "porcoes": 4}, token)
checar("o PUT muda o tamanho", st == 200, (st, r))
st, d2 = chamar("GET", f"/fichas/{f['id']}", token=token)
checar("e o novo tamanho volta", perto(d2.get("porcao_qtd"), 0.5, 0.0001), d2.get("porcao_qtd"))

# ⚠️ NULO e resposta: quem nao informa nao passa a afirmar que a porcao vale 1.
st, f2 = chamar("POST", "/fichas", {
    "id_produto": novo("Rend torta", "PRODUZIDO", "UN", producao_propria=True),
    "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 10, "itens": itens,
}, token)
if f2.get("id"):
    fichas.append(f2["id"])
st, d3 = chamar("GET", f"/fichas/{f2.get('id')}", token=token)
checar("sem informar, o tamanho fica NULO", d3.get("porcao_qtd") is None, d3.get("porcao_qtd"))

print("\n8. a copia leva o tamanho da porcao junto")
# Duplicar e nova versao passam pelo MESMO `_copiar_ficha`: se o campo novo
# ficasse fora dele, a copia nasceria sem o tamanho e ninguem notaria.
st, nv = chamar("POST", f"/fichas/{fichas[0]}/nova-versao", token=token)
if nv.get("id"):
    fichas.append(nv["id"])
st, d4 = chamar("GET", f"/fichas/{nv.get('id')}", token=token)
checar("a nova versao nasce com o mesmo tamanho de porcao",
       perto(d4.get("porcao_qtd"), 0.5, 0.0001), d4.get("porcao_qtd"))

print("\n9. limpeza")
for fid in reversed(fichas):
    chamar("DELETE", f"/fichas/{fid}", token=token)
for pid in produtos:
    chamar("DELETE", f"/produtos/{pid}", token=token)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
raise SystemExit(1 if falhas else 0)
