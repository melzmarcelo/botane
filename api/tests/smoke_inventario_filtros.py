"""Teste de fumaça do inventário por recorte.

Contar a despensa inteira é raro. O que a casa faz é contar a câmara fria, ou
só as bebidas, ou só o hortifrúti antes da feira. Até aqui a única pergunta era
o LOCAL — quem quisesse contar um pedaço escolhia produto por produto.

O que este arquivo cobra:

1. a prévia responde ANTES de abrir, e o filtro estreita de verdade
2. os quatro filtros combinam com E, não com OU
3. contagem sem local escolhido cobre vários — e cada par produto × local é uma linha
4. **cega por padrão**: quem não disse nada não vê o saldo esperado
5. contar sem dizer o local, com o produto em dois, é RECUSADO (não adivinhado)
6. o fechamento lança o ajuste no local do ITEM, não num local qualquer
7. duas contagens não podem disputar o mesmo produto no mesmo local
8. o nome se troca depois, inclusive com a contagem fechada

    python tests/smoke_inventario_filtros.py            (API de pé na 9200)

⚠️ Cria os PRÓPRIOS produtos e locais, com marca de tempo, e fecha o que abriu:
a base é compartilhada, e contagem aberta esquecida bloqueia as outras suítes
pela guarda de choque.
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
from comum import garantir_locais, garantir_setores  # noqa: E402

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


def perto(a, b, tol=0.01):
    return a is not None and abs(float(a) - float(b)) < tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]

marca = str(time.time_ns())[-6:]
abertas: list[int] = []


def limpar():
    """Contagem aberta esquecida bloqueia as outras suítes pela guarda de choque."""
    for id_inv in abertas:
        chamar("DELETE", f"/inventarios/{id_inv}", token=token)


atexit.register(limpar)


print("0. cenário: dois produtos, dois locais, dois setores")
locais = garantir_locais(chamar, token, 2)
setores = garantir_setores(chamar, token, 2)
l1, l2 = locais[0], locais[1]
s1, s2 = setores[0], setores[1]

# ⚠️ Um produto EM DOIS LOCAIS — o caso que só passou a existir agora, e o que
# quebra tudo o que supunha "um local por contagem".
st, r = chamar("POST", "/produtos", {
    "codigo": f"INVA{marca}", "nome": f"Caixa dupla {marca}", "tipo": "EMBALAGEM",
    "um_estoque": "UN", "id_setor": s1["id"],
}, token=token)
checar("cria o produto que vive em dois locais", st == 201, (st, r))
duplo = r.get("id")

st, r = chamar("POST", "/produtos", {
    "codigo": f"INVB{marca}", "nome": f"Insumo do setor 2 {marca}", "tipo": "INSUMO",
    "um_estoque": "KG", "id_setor": s2["id"],
}, token=token)
checar("e o de outro setor e outro tipo", st == 201, (st, r))
outro = r.get("id")

for id_produto, id_local, quantidade in ((duplo, l1["id"], 10), (duplo, l2["id"], 4),
                                         (outro, l1["id"], 7)):
    st, r = chamar("POST", "/estoque/entradas", {
        "id_produto": id_produto, "quantidade": quantidade, "custo_unitario": 2,
        "id_local": id_local,
    }, token=token)
    checar(f"entrada de {quantidade} lançada", st == 201, (st, r))


print("\n1. a prévia responde antes de abrir")
st, p = chamar("GET", f"/inventarios/previa?locais={l1['id']}&locais={l2['id']}"
                      f"&setores={s1['id']}", token=token)
checar("a prévia responde", st == 200, st)
# ⚠️ **Afirma sobre o PRÓPRIO produto, não sobre o total.** As rodadas
# anteriores deixam "Caixa dupla NNNNNN" na base — produto com movimento não é
# apagado —, e um total esperado erraria a partir da segunda vez. O que importa
# é que o produto DESTE teste apareça uma vez por prateleira.
# ⚠️ `.upper()`: o nome do produto é normalizado pelo banco (migração
# 036), e a suíte afirma sobre o que foi GRAVADO, não sobre o que mandou.
meus = [a for a in p.get("amostra", [])
        if a["produto"] == f"Caixa dupla {marca}".upper()]
checar("o produto em dois locais dá DUAS linhas para um produto só",
       len(meus) == 2, meus or p.get("amostra"))
checar("e cada uma num local diferente", len({a["local"] for a in meus}) == 2, meus)
checar("com a prévia dizendo de quais locais", len(p.get("locais", [])) >= 2,
       p.get("locais"))


print("\n2. os filtros combinam com E, não com OU")
st, p = chamar("GET", f"/inventarios/previa?setores={s1['id']}&tipos=INSUMO", token=token)
# ⚠️ O produto do setor 1 é EMBALAGEM e o INSUMO é do setor 2: a interseção é
# vazia. Se fosse OU, viriam os dois — e a contagem traria o que ninguém pediu.
achou_meus = [a for a in p.get("amostra", []) if marca in a["produto"]]
checar("setor 1 + tipo insumo não traz nenhum dos dois", not achou_meus, achou_meus)

st, p = chamar("GET", f"/inventarios/previa?setores={s2['id']}&tipos=INSUMO", token=token)
checar("setor 2 + tipo insumo traz o insumo do setor 2",
       any(f"Insumo do setor 2 {marca}".upper() == a["produto"]
           for a in p.get("amostra", [])),
       p.get("amostra"))


print("\n3. contagem sem local escolhido cobre vários")
st, inv = chamar("POST", "/inventarios", {
    "nome": f"Recorte {marca}", "setores": [s1["id"]],
    "locais": [l1["id"], l2["id"]],
}, token=token)
checar("abre a contagem pelo recorte", st == 201, (st, inv))
id_inv = inv.get("id")
if id_inv:
    abertas.append(id_inv)
checar("o cabeçalho NÃO tem local único", inv.get("id_local") is None, inv.get("id_local"))
checar("e o nome é o que foi dado", inv.get("nome") == f"Recorte {marca}", inv.get("nome"))
minhas = [i for i in inv.get("itens", [])
          if i["produto"] == f"Caixa dupla {marca}".upper()]
checar("com duas linhas para o produto deste teste, uma por prateleira",
       len(minhas) == 2, [i["produto"] for i in inv.get("itens", [])])
checar("e cada linha diz o local dela",
       len({i.get("local") for i in minhas}) == 2, [i.get("local") for i in minhas])
checar("o filtro fica gravado, para explicar a lista depois",
       (inv.get("filtros") or {}).get("setores") == [s1["nome"]], inv.get("filtros"))


print("\n4. cega por padrão")
# ⚠️ Ninguém pediu cega e ninguém pediu o contrário: o padrão é esconder. Ver o
# esperado transforma a contagem em conferência.
checar("nasce cega sem ninguém pedir", inv.get("cega") is True, inv.get("cega"))
checar("e o saldo esperado NÃO sai do servidor",
       all(i.get("qtd_sistema") is None for i in inv.get("itens", [])),
       [i.get("qtd_sistema") for i in inv.get("itens", [])])

st, aberta = chamar("POST", "/inventarios", {
    "nome": f"Nao cega {marca}", "produtos": [outro], "locais": [l1["id"]], "cega": False,
}, token=token)
checar("quem pede não-cega recebe o saldo", st == 201
       and aberta["itens"][0].get("qtd_sistema") is not None, (st, aberta))
if aberta.get("id"):
    abertas.append(aberta["id"])


print("\n5. contar sem dizer o local, com o produto em dois, é recusado")
st, r = chamar("PUT", f"/inventarios/{id_inv}/contagem",
               {"itens": [{"id_produto": duplo, "qtd_contada": 9}]}, token=token)
checar("recusa em vez de adivinhar a prateleira", st == 400, (st, r))
checar("e a recusa diz quantos locais são",
       "2 locais" in str(r.get("detail", "")), r.get("detail"))

st, r = chamar("PUT", f"/inventarios/{id_inv}/contagem", {"itens": [
    {"id_produto": duplo, "id_local": l1["id"], "qtd_contada": 9},
    {"id_produto": duplo, "id_local": l2["id"], "qtd_contada": 4},
]}, token=token)
checar("com o local, grava as duas", st == 200 and r.get("contados") == 2, (st, r))
checar("e a cega continua sem mostrar o esperado",
       all(i.get("qtd_sistema") is None for i in r.get("itens", [])),
       [i.get("qtd_sistema") for i in r.get("itens", [])])


print("\n6. o fechamento lança no local do ITEM")
st, r = chamar("POST", f"/inventarios/{id_inv}/fechar", token=token)
checar("fecha a contagem", st == 200, (st, r))
# 10 contados como 9 no local 1 (−1); 4 contados como 4 no local 2 (sem ajuste).
checar("um ajuste só, o do local que divergiu", r.get("ajustes") == 1, r)
if id_inv in abertas:
    abertas.remove(id_inv)

st, saldos = chamar("GET", f"/estoque/saldos?busca=Caixa dupla {marca}", token=token)
por_local = {s.get("local"): float(s["quantidade"]) for s in (saldos or [])}
checar("o local contado a menos foi acertado", perto(por_local.get(l1["nome"]), 9), por_local)
# ⚠️ A prova de que o local do item mandou: um fechamento que lançasse tudo no
# cabeçalho teria zerado ou dobrado o outro local.
checar("e o outro local ficou intacto", perto(por_local.get(l2["nome"]), 4), por_local)

st, fechada = chamar("GET", f"/inventarios/{id_inv}", token=token)
checar("fechada, a contagem mostra o que estava escondido",
       all(i.get("qtd_sistema") is not None for i in fechada.get("itens", [])),
       [i.get("qtd_sistema") for i in fechada.get("itens", [])])


print("\n7. duas contagens não disputam o mesmo produto e local")
st, a = chamar("POST", "/inventarios", {
    "nome": f"Primeira {marca}", "produtos": [outro], "locais": [l1["id"]],
}, token=token)
# A não-cega da fase 4 já pegou este par: o choque é com ela.
checar("a segunda contagem do mesmo par é recusada", st == 409, (st, a))
checar("e a recusa nomeia o produto, o local e a contagem",
       all(p in str(a.get("detail", "")) for p in ("em", "contagem #")), a.get("detail"))
if a.get("id"):
    abertas.append(a["id"])

# ⚠️ Mas contar OUTRO recorte no mesmo local é legítimo — foi por isso que a
# guarda deixou de ser "um inventário aberto por local".
st, b = chamar("POST", "/inventarios", {
    "nome": f"Outro recorte {marca}", "produtos": [duplo], "locais": [l1["id"]],
}, token=token)
checar("outro recorte no mesmo local é aceito", st == 201, (st, b))
if b.get("id"):
    abertas.append(b["id"])


print("\n8. o nome se troca depois")
st, r = chamar("PUT", f"/inventarios/{id_inv}/nome",
               {"nome": f"Contagem do Natal {marca}"}, token=token)
checar("renomeia mesmo a contagem FECHADA", st == 200, (st, r))
st, r = chamar("GET", f"/inventarios/{id_inv}", token=token)
checar("e o nome novo fica", r.get("nome") == f"Contagem do Natal {marca}", r.get("nome"))
st, r = chamar("PUT", "/inventarios/99999999/nome", {"nome": "Nada"}, token=token)
checar("renomear o que não existe devolve 404", st == 404, st)


print("\n9. recorte vazio não vira contagem")
st, r = chamar("POST", "/inventarios", {"tipos": ["KIT"], "locais": [l2["id"]]}, token=token)
# ⚠️ Abrir uma contagem sem linha nenhuma é abrir o que não se pode contar, e a
# recusa tem de dizer por quê — senão parece bug da tela.
checar("recorte sem produto é recusado", st == 400, (st, r))
checar("e a recusa explica que só entra o que tem saldo",
       "saldo" in str(r.get("detail", "")), r.get("detail"))


print("\n10. limpeza")
# ⚠️ Os produtos saem no fim. Com movimento eles viram INATIVOS em vez de serem
# apagados — e é isso que os tira do recorte da próxima rodada: sem esta linha,
# cada execução deixava mais uma "Caixa dupla" com saldo para a seguinte contar.
for id_produto in (duplo, outro):
    if id_produto:
        chamar("DELETE", f"/produtos/{id_produto}", token=token)

for id_inv in list(abertas):
    st, r = chamar("DELETE", f"/inventarios/{id_inv}", token=token)
    checar(f"cancela a contagem {id_inv}", st == 200, (st, r))
    abertas.remove(id_inv)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
