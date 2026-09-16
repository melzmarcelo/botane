"""A mesma ficha com processos diferentes: a prateleira decide o rendimento.

🔑 **Pedido do dono (12/09/2026):** *"a mesma ficha pode ter processos
diferentes. Vamos fazer a massa de pizza e estocar para servir como insumo para
pizza, mas podemos ter producao de massa de pizza que vai para a vitrine. Podemos
criar no produto mais de um local, qual seria o local que o PDV consome. Ai
dentro da ficha tecnica podemos ter os locais e informar rendimentos e porcoes
por local, e ao programar a producao seleciona qual local sera produzido"*. E o
rendimento muda de verdade: a da vitrine vai ao forno.

⚠️ **`id_local_padrao` fazia TRES papeis** — de onde a venda baixa, de onde os
insumos saem e para onde a producao entrega. Com uma coluna so, pôr a Vitrine
como "o local do produto" fazia a receita da pizza comer a massa DA VITRINE.
`id_local_venda` separa o primeiro papel.

⚠️ **O rendimento por local DIVIDE o consumo** (`lotes = quantidade /
rendimento`): e o objetivo do pedido, e e por isso que a resposta diz qual
rendimento valeu.

    python tests/smoke_rendimento_por_local.py        (API de pe na 9200)
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
produtos: list[int] = []
fichas: list[int] = []
locais: list[int] = []


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


def local(nome):
    _st, r = chamar("POST", "/locais", {"nome": f"{nome} {marca}"}, token)
    if r.get("id"):
        locais.append(r["id"])
    return r.get("id")


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()

print("\n1. o cenario: a camara e a vitrine")
camara = local("Camara ensaio")
vitrine = local("Vitrine ensaio")
checar("as duas prateleiras nascem", bool(camara) and bool(vitrine), (camara, vitrine))

farinha = novo("Rloc farinha", "INSUMO", "KG")
chamar("POST", "/estoque/entradas", {
    "id_produto": farinha, "quantidade": 100, "custo_unitario": 5, "id_local": camara,
}, token)
# ⚠️ A massa mora nas DUAS prateleiras: insumo na camara, mercadoria na vitrine.
massa = novo("Rloc massa", "PRODUZIDO", "KG", producao_propria=True,
             id_local_padrao=camara)
chamar("POST", f"/produtos/{massa}/locais", {"id_local": vitrine}, token)

st, f = chamar("POST", "/fichas", {
    "id_produto": massa, "rendimento_qtd": 10, "rendimento_um": "KG", "porcoes": 1,
    "itens": [{"id_insumo": farinha, "qtd_bruta": 6, "um": "KG"}],
}, token)
fichas.append(f.get("id"))
checar("a ficha da massa rende 10 KG com 6 KG de farinha", st == 201, (st, f))

print("\n2. os MODOS de rendimento")
# 🔑 Pedido do dono (16/09/2026): o modo tem NOME e vale para uma prateleira
# ou um setor inteiro. A da vitrine vai ao forno e perde agua: o MESMO lote rende
# 8 KG, nao 10.
st, r = chamar("PUT", f"/fichas/{f['id']}/modos", {"itens": [
    {"nome": "Vitrine", "id_local": vitrine, "rendimento_qtd": 8,
     "observacao": "assada, perde agua"},
]}, token)
checar("grava o modo da vitrine", st == 200, (st, r))
st, d = chamar("GET", f"/fichas/{f['id']}", token=token)
checar("a ficha devolve o modo, com nome e prateleira",
       len(d.get("modos") or []) == 1
       and d["modos"][0].get("nome") == "Vitrine"
       and perto(d["modos"][0].get("rendimento_qtd"), 8)
       and marca in (d["modos"][0].get("local") or ""), d.get("modos"))
# ⚠️ Dois modos com o mesmo NOME sao uma escolha impossivel de fazer certo.
st, r = chamar("PUT", f"/fichas/{f['id']}/modos", {"itens": [
    {"nome": "Vitrine", "id_local": vitrine, "rendimento_qtd": 8},
    {"nome": "vitrine", "id_local": vitrine, "rendimento_qtd": 9},
]}, token)
checar("recusa o mesmo nome duas vezes", st == 400, (st, r))
# 🔑 Mas a mesma PRATELEIRA com dois modos e legitimo -- e era o indice unico
# de `ficha_locais` que impedia exatamente o que o dono pediu.
st, r = chamar("PUT", f"/fichas/{f['id']}/modos", {"itens": [
    {"nome": "Vitrine", "id_local": vitrine, "rendimento_qtd": 8},
    {"nome": "Vitrine mini", "id_local": vitrine, "rendimento_qtd": 8, "porcoes": 40},
]}, token)
checar("aceita dois modos na MESMA prateleira", st == 200, (st, r))
st, r = chamar("PUT", f"/fichas/{f['id']}/modos", {"itens": [
    {"nome": "Fora", "id_local": 99999999, "rendimento_qtd": 8},
]}, token)
checar("e recusa prateleira que nao e desta loja", st == 400, (st, r))
# Repoe o modo bom (a checagem acima nao gravou nada).
chamar("PUT", f"/fichas/{f['id']}/modos", {"itens": [
    {"nome": "Vitrine", "id_local": vitrine, "rendimento_qtd": 8, "porcoes": 20,
     "porcao_qtd": 0.4},
]}, token)
chamar("POST", f"/fichas/{f['id']}/homologar", None, token)

print("\n3. a previa: o rendimento do destino DIVIDE o consumo")
# Camara: rende 10, produzir 10 = 1 lote = 6 KG de farinha.
# A folha que se leva para a bancada: `GET /producao-agenda/necessario` roda a
# MESMA conta da producao, e e por isso que ela tem de ver o mesmo rendimento.
st, p1 = chamar("GET", f"/producao-agenda/necessario?id_produto={massa}"
                       f"&quantidade=10&id_local={camara}", token=token)
checar("a previa da camara responde", st == 200, (st, p1))
checar("na camara o rendimento e o da ficha (10)",
       perto(p1.get("rendimento_qtd"), 10) and p1.get("rendimento_do_local") is False, p1)
checar("e o consumo e de 6 KG de farinha",
       perto((p1.get("itens") or [{}])[0].get("necessario"), 6), p1.get("itens"))

# Vitrine: rende 8, produzir 8 = 1 lote = 6 KG; produzir 10 = 1,25 lotes = 7,5 KG.
st, p2 = chamar("GET", f"/producao-agenda/necessario?id_produto={massa}"
                       f"&quantidade=10&id_local={vitrine}", token=token)
checar("na vitrine o rendimento e o do LOCAL (8)",
       perto(p2.get("rendimento_qtd"), 8) and p2.get("rendimento_do_local") is True, p2)
checar("e o consumo sobe para 7,5 KG de farinha",
       perto((p2.get("itens") or [{}])[0].get("necessario"), 7.5), p2.get("itens"))

print("\n4. produzir usa o mesmo rendimento que a previa mostrou")
st, r1 = chamar("POST", "/estoque/producoes",
                {"id_produto": massa, "quantidade": 10, "id_local": camara}, token)
checar("produz 10 KG para a camara", st == 201, (st, r1))
checar("com o rendimento da ficha", r1.get("rendimento_do_local") is False
       and perto(r1.get("rendimento_qtd"), 10), r1)
consumo1 = sum(float(c["quantidade"]) for c in (r1.get("consumos") or []))
checar("consumindo 6 KG", perto(consumo1, 6), consumo1)

st, r2 = chamar("POST", "/estoque/producoes",
                {"id_produto": massa, "quantidade": 10, "id_local": vitrine}, token)
checar("produz 10 KG para a vitrine", st == 201, (st, r2))
checar("com o rendimento do LOCAL", r2.get("rendimento_do_local") is True
       and perto(r2.get("rendimento_qtd"), 8), r2)
consumo2 = sum(float(c["quantidade"]) for c in (r2.get("consumos") or []))
checar("consumindo 7,5 KG — o mesmo numero da previa", perto(consumo2, 7.5), consumo2)

print("\n5. de onde a VENDA baixa")
# ⚠️ Sem `id_local_venda`, a venda tira do `id_local_padrao` (a camara) — e era
# esse o furo: a massa da vitrine ficava lá para sempre.
with get_cursor() as cur:
    cur.execute("SELECT id_local_venda FROM produtos WHERE id = %s", (massa,))
    checar("o produto nasce SEM local de venda", cur.fetchone()["id_local_venda"] is None)
st, r = chamar("PUT", f"/produtos/{massa}", {"id_local_venda": vitrine}, token)
checar("o cadastro aceita o local de venda", st == 200, (st, r))
with get_cursor() as cur:
    cur.execute("SELECT id_local_padrao, id_local_venda FROM produtos WHERE id = %s", (massa,))
    linha = cur.fetchone()
checar("e os dois papeis ficam separados: padrao na camara, venda na vitrine",
       linha["id_local_padrao"] == camara and linha["id_local_venda"] == vitrine, dict(linha))

print("\n6. a copia da ficha leva os destinos")
st, nv = chamar("POST", f"/fichas/{f['id']}/nova-versao", token=token)
fichas.append(nv.get("id"))
st, d2 = chamar("GET", f"/fichas/{nv.get('id')}", token=token)
checar("a nova versao nasce com o modo da vitrine",
       len(d2.get("modos") or []) == 1 and perto(d2["modos"][0]["rendimento_qtd"], 8)
       and d2["modos"][0]["nome"] == "Vitrine", d2.get("modos"))

print("\n7. ficha homologada nao troca de rendimento")
# O rendimento divide o consumo: mexer nele numa ficha publicada mudaria o custo
# ja apurado. E a mesma trava dos itens.
st, r = chamar("PUT", f"/fichas/{f['id']}/modos", {"itens": [
    {"nome": "Vitrine", "id_local": vitrine, "rendimento_qtd": 7},
]}, token)
checar("recusa mexer nos modos de ficha homologada", st == 400, (st, r))

print("\n7b. o modo com NOME, o modo do SETOR e a quantidade sugerida")
# 🔑 **Pedido do dono (16/09/2026):** *"podemos criar mais modos de rendimento
# para diferentes setores, com um nome, e este sera o modo selecionado ao agendar
# ou produzir. Modo padrao e a receita toda para estoque; podemos ter um Modo
# Consumo, com o setor Bar e 30 porcoes; ou outro onde as porcoes sao menores."*
# 🔑 **O que o modo muda nao e escala, e a PORCAO.** Produzir 30 em vez de 60
# sempre funcionou; o que nao existia era a mesma massa render OUTRA COISA -- os
# mesmos 10 KG em 120 unidades menores, que e outro custo unitario e outra
# contagem de estoque.
st, setores = chamar("GET", "/setores", token=token)
id_setor = (setores or [{}])[0].get("id")
bar = local("Bar ensaio")
if id_setor:
    chamar("PUT", f"/locais/{bar}", {"nome": f"Bar ensaio {marca}", "id_setor": id_setor,
                                     "tipo": "SECO"}, token)

biscoito = novo("Rloc biscoito", "PRODUZIDO", "UN", producao_propria=True,
                id_local_padrao=camara)
chamar("POST", f"/produtos/{biscoito}/locais", {"id_local": bar}, token)
st, fb = chamar("POST", "/fichas", {
    "id_produto": biscoito, "rendimento_qtd": 10, "rendimento_um": "KG", "porcoes": 60,
    "itens": [{"id_insumo": farinha, "qtd_bruta": 6, "um": "KG"}],
}, token)
fichas.append(fb.get("id"))
checar("a ficha do biscoito rende 10 KG em 60 porcoes", st == 201, (st, fb))

st, r = chamar("PUT", f"/fichas/{fb['id']}/modos", {"itens": [
    {"nome": "Consumo Bar", "id_setor": id_setor, "rendimento_qtd": 10, "porcoes": 60,
     "quantidade_sugerida": 30},
    {"nome": "Mini", "rendimento_qtd": 10, "porcoes": 120},
]}, token)
checar("grava os dois modos", st == 200, (st, r))
st, d = chamar("GET", f"/fichas/{fb['id']}", token=token)
modos = {m["nome"]: m for m in (d.get("modos") or [])}
checar("a ficha devolve os dois, com setor e sugestao",
       len(modos) == 2 and modos.get("Consumo Bar", {}).get("quantidade_sugerida") == 30,
       d.get("modos"))
chamar("POST", f"/fichas/{fb['id']}/homologar", None, token)

id_mini = modos.get("Mini", {}).get("id")
id_bar = modos.get("Consumo Bar", {}).get("id")

# ⚠️ Sem modo, valem as 60 porcoes da ficha: 60 UN = 1 receita = 6 KG.
st, sem = chamar("GET",
                 f"/producao-agenda/necessario?id_produto={biscoito}&quantidade=60"
                 f"&id_local={camara}", token=token)
checar("sem modo, 60 unidades dao uma receita", perto(sem.get("lotes"), 1), sem.get("lotes"))
# 🔑 A afirmacao central: no Mini a MESMA massa faz 120 unidades, entao 60
# unidades sao MEIA receita -- metade da farinha, e cada biscoito custa metade.
st, mini = chamar("GET",
                  f"/producao-agenda/necessario?id_produto={biscoito}&quantidade=60"
                  f"&id_local={camara}&id_modo={id_mini}", token=token)
checar("no modo Mini, 60 unidades sao MEIA receita", perto(mini.get("lotes"), 0.5),
       mini.get("lotes"))
checar("e a farinha cai pela metade",
       perto((mini.get("itens") or [{}])[0].get("necessario"), 3),
       (mini.get("itens") or [{}])[0])
checar("a resposta diz qual modo valeu", mini.get("modo") == "Mini", mini.get("modo"))
# ⚠️ E pedir em RECEITAS no modo Mini rende 120, nao 60.
st, umaMini = chamar("GET",
                     f"/producao-agenda/necessario?id_produto={biscoito}&quantidade=1"
                     f"&id_local={camara}&id_modo={id_mini}&medida=RECEITAS", token=token)
checar("uma receita no modo Mini da 120 unidades", perto(umaMini.get("quantidade"), 120),
       umaMini.get("quantidade"))

# 🔑 O modo do SETOR vem escolhido sozinho quando a prateleira de destino e de
# la -- e o que poupa repetir o cadastro em cada prateleira do Bar.
if id_setor:
    st, porSetor = chamar("GET",
                          f"/producao-agenda/necessario?id_produto={biscoito}&quantidade=30"
                          f"&id_local={bar}", token=token)
    checar("a prateleira do Bar herda o modo do SETOR",
           porSetor.get("modo") == "Consumo Bar", porSetor.get("modo"))

# ⚠️ Modo de OUTRA ficha e RECUSA, nao silencio: cair no padrao produziria
# com outro rendimento do que a tela mostrou, e ninguem veria.
st, r = chamar("GET",
               f"/producao-agenda/necessario?id_produto={biscoito}&quantidade=10"
               f"&id_local={camara}&id_modo=99999999", token=token)
checar("modo que nao e desta ficha e recusado", st == 400, (st, r))

# 🔑 **O modo fica GRAVADO na linha da agenda.** Sem isto, agendar o Mini e
# cumprir tres dias depois sairia pelo rendimento padrao: a quantidade certa
# saindo da receita errada, e a diferenca so aparecendo na contagem.
st, ag = chamar("POST", "/producao-agenda", {
    "id_produto": biscoito, "quantidade": 60, "id_local": camara, "id_modo": id_mini,
    "data_prevista": None}, token)
checar("agendar no modo Mini responde", st == 201, (st, ag))
st, lista = chamar("GET", "/producao-agenda", token=token)
linha = next((x for x in (lista or {}).get("linhas", []) if x["id"] == ag.get("id")), None)
checar("e a linha da agenda mostra o modo", (linha or {}).get("modo") == "Mini", linha)

st, saldo_antes = chamar("GET", f"/estoque/saldos?id_produto={farinha}", token=token)
tinha = sum(float(x["quantidade"]) for x in (saldo_antes or []))
st, r = chamar("POST", f"/producao-agenda/{ag['id']}/produzir", {}, token)
checar("cumprir a linha produz", st == 200, (st, r))
st, saldo_depois = chamar("GET", f"/estoque/saldos?id_produto={farinha}", token=token)
ficou = sum(float(x["quantidade"]) for x in (saldo_depois or []))
# A prova: pelo modo Mini, 60 unidades gastam 3 KG. Pelo padrao gastariam 6.
checar("e gasta a farinha do MODO PLANEJADO, nao a do padrao",
       perto(tinha - ficou, 3), (tinha, ficou))

id_bar  # o modo do setor fica cadastrado; a checagem dele e a de heranca acima


print("\n8. limpeza")
for fid in reversed([x for x in fichas if x]):
    chamar("DELETE", f"/fichas/{fid}", token=token)
for pid in produtos:
    chamar("DELETE", f"/produtos/{pid}", token=token)
for lid in locais:
    chamar("DELETE", f"/locais/{lid}", token=token)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
