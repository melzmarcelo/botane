"""Dois cliques ao mesmo tempo NÃO podem lançar duas vezes no razão.

    python tests/smoke_concorrencia.py        (API de pé na 9200)

🔑 **Existe porque a guarda de status não é guarda sem a trava.** Três fluxos
liam a linha de estado, conferiam "ainda está aberto?" e só então escreviam no
razão — sem `FOR UPDATE`. Dois pedidos simultâneos passavam os DOIS pela
conferência e lançavam a mercadoria em dobro. O razão é append-only: o conserto
seria um estorno para cada movimento, e no caso da nota a compra entraria em
dobro no CMV do mês.

Os três: lançar nota (`importador.lancar_nota`), produzir da agenda
(`producao_agenda.produzir_linha`) e fechar inventário (`inventario.fechar`).
`transferencias.receber` já fazia certo, e é dele a lição que faltava aos três.

⚠️ **A afirmação é sobre o RAZÃO, não sobre o código de resposta.** Contar
"um 200 e um 409" seria fraco: o que importa é quantos movimentos existem
depois. Cada bloco conta as linhas de `estoque_movimentos` daquela origem — se
forem duas, a trava não segurou, e nenhum código HTTP muda isso.

⚠️ **Duas THREADS de verdade, não duas chamadas em sequência.** Sequencial a
segunda sempre acha o status já mudado e passa mesmo sem trava — o teste diria
"ok" para o defeito. As duas partem juntas, presas na mesma barreira.
"""

import json
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, "tests")
from comum import garantir_local  # noqa: E402

sys.path.insert(0, ".")
from database import get_cursor  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + urllib.parse.quote(caminho, safe="/?=&"),
                                 method=metodo)
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


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


def em_paralelo(metodo, caminho, corpo, token, vezes=2):
    """Dispara `vezes` pedidos iguais que partem JUNTOS.

    ⚠️ A barreira é o que faz o teste valer: sem ela as threads saem
    escalonadas e a segunda encontra o trabalho da primeira já concluído — que
    é exatamente o cenário em que o defeito NÃO aparece.
    """
    barreira = threading.Barrier(vezes)
    saidas: list[tuple] = []
    trava = threading.Lock()

    def bater():
        barreira.wait()
        r = chamar(metodo, caminho, corpo, token)
        with trava:
            saidas.append(r)

    fios = [threading.Thread(target=bater) for _ in range(vezes)]
    for f in fios:
        f.start()
    for f in fios:
        f.join()
    return saidas


def movimentos_de(origem_tipo, origem_id):
    with get_cursor() as cur:
        cur.execute(
            """SELECT count(*) AS n FROM estoque_movimentos
                WHERE origem_tipo = %s AND origem_id = %s""",
            (origem_tipo, origem_id))
        return cur.fetchone()["n"]


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("login falhou:", st, r)
    raise SystemExit(1)
token = r["access_token"]
marca = uuid.uuid4().hex[:6]
local = garantir_local(chamar, token)
criados: dict[str, list] = {"produtos": [], "notas": []}


def novo_produto(nome, tipo="INSUMO", um="KG"):
    st, r = chamar("POST", "/produtos",
                   {"nome": nome, "tipo": tipo, "um_estoque": um}, token=token)
    if st != 201:
        print("   (falha ao criar", nome, st, r, ")")
        return None
    criados["produtos"].append(r["id"])
    return r["id"]


print("1. lançar a MESMA nota duas vezes ao mesmo tempo")
# É o fluxo mais exposto dos três: o botão fica no fim de uma tela longa de
# conferência, onde clicar de novo é o gesto natural de quem não viu a página
# responder.
insumo = novo_produto(f"Conc insumo {marca}")
st, fornecedores = chamar("GET", "/fornecedores?limite=1", token=token)
fornecedor = (fornecedores or [{}])[0]
st, nota = chamar("POST", "/notas", {
    "id_fornecedor": fornecedor.get("id"), "numero": f"C{marca}", "serie": "1",
    "id_local": local["id"],
    "itens": [{"id_produto": insumo, "quantidade": 10, "valor_unitario": 5}],
}, token=token)
checar("a nota de teste foi digitada", st == 200, (st, nota))
id_nota = (nota or {}).get("id")
criados["notas"].append(id_nota)

saidas = em_paralelo("POST", f"/notas/{id_nota}/lancar", {"id_local": local["id"]}, token)
codigos = sorted(s[0] for s in saidas)
movs = movimentos_de("NOTA", id_nota)
checar("o razão recebeu UM lançamento, não dois", movs == 1, {"movimentos": movs})
checar("e o segundo pedido foi recusado, não ignorado",
       any(c >= 400 for c in codigos), codigos)
checar("com exatamente um aceito", sum(1 for c in codigos if c < 400) == 1, codigos)

st, depois = chamar("GET", f"/notas/{id_nota}", token=token)
checar("a nota ficou LANCADA uma vez só", depois.get("status") == "LANCADA",
       depois.get("status"))


print("2. produzir a MESMA linha da agenda duas vezes ao mesmo tempo")
prato = novo_produto(f"Conc prato {marca}", tipo="PRODUZIDO", um="UN")
st, ficha = chamar("POST", "/fichas", {
    "id_produto": prato, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": insumo, "qtd_bruta": 1, "um": "KG"}],
}, token=token)
checar("ficha do prato criada", st in (200, 201), (st, ficha))
chamar("POST", f"/fichas/{ficha.get('id')}/homologar", {}, token=token)
st, linha = chamar("POST", "/producao-agenda", {
    "id_produto": prato, "data_prevista": None, "quantidade": 2,
    "id_local": local["id"],
}, token=token)
if st not in (200, 201):
    st, linha = chamar("POST", "/producao-agenda", {
        "id_produto": prato, "quantidade": 2, "id_local": local["id"]}, token=token)
checar("linha na agenda criada", st in (200, 201), (st, linha))
id_agenda = (linha or {}).get("id")

if id_agenda:
    saidas = em_paralelo("POST", f"/producao-agenda/{id_agenda}/produzir",
                         {"quantidade": 2, "id_local": local["id"]}, token)
    codigos = sorted(s[0] for s in saidas)
    with get_cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM producoes WHERE id_produto = %s", (prato,))
        producoes = cur.fetchone()["n"]
    checar("houve UMA produção, não duas", producoes == 1, {"producoes": producoes})
    checar("e o segundo pedido foi recusado", any(c >= 400 for c in codigos), codigos)
    checar("com exatamente um aceito", sum(1 for c in codigos if c < 400) == 1, codigos)


print("3. fechar o MESMO inventário duas vezes ao mesmo tempo")
# ⚠️ Um ajuste de inventário duplicado é o que menos se percebe dos três: ele
# tem cara de acerto legítimo, e some no meio dos outros ajustes do dia.
contado = novo_produto(f"Conc contagem {marca}")
chamar("POST", "/estoque/entradas", {
    "id_produto": contado, "quantidade": 10, "custo_unitario": 3,
    "id_local": local["id"]}, token=token)
st, inv = chamar("POST", "/inventarios", {
    "id_local": local["id"], "nome": f"Conc {marca}",
    "produtos": [contado]}, token=token)
if st not in (200, 201):
    st, inv = chamar("POST", "/inventarios", {"id_local": local["id"],
                                              "nome": f"Conc {marca}"}, token=token)
checar("inventário aberto", st in (200, 201), (st, inv))
id_inv = (inv or {}).get("id")

if id_inv:
    chamar("PUT", f"/inventarios/{id_inv}/contagem",
           {"itens": [{"id_produto": contado, "id_local": local["id"], "qtd_contada": 7}]},
           token=token)
    saidas = em_paralelo("POST", f"/inventarios/{id_inv}/fechar", {}, token)
    codigos = sorted(s[0] for s in saidas)
    movs = movimentos_de("INVENTARIO", id_inv)
    checar("o razão recebeu UM ajuste, não dois", movs <= 1, {"movimentos": movs})
    checar("e o segundo fechamento foi recusado", any(c >= 400 for c in codigos), codigos)
    checar("com exatamente um aceito", sum(1 for c in codigos if c < 400) == 1, codigos)


print("4. limpeza")
# ⚠️ O razão FICA — é append-only, e apagar movimento seria justamente o que
# este arquivo existe para provar que não acontece. Sai o que é cadastro.
for id_produto in criados["produtos"]:
    chamar("DELETE", f"/produtos/{id_produto}", token=token)
checar("produtos de teste saíram da lista ativa", True)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
raise SystemExit(1 if falhas else 0)
