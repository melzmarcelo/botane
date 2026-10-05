"""Teste de fumaça: a fila de fichas pela receita e o alerta de rascunho EM USO.

Duas ideias da mesma família — trocar uma lista do cadastro inteiro pelo que a
operação está tocando agora:

    1-2. `GET /fichas/fila`: produto vendido sem custo entra na fila, ordenada
         pela receita, com a cobertura acumulada; com custo, sai dela.
    3-4. O alerta "rascunho em uso" e o filtro `em_uso` da lista de produtos
         contam a MESMA coisa: rascunho parado fica de fora, rascunho que
         aparece em nota aberta entra.

⚠️ **Mede por DELTA e por presença**: a base local tem vendas e rascunhos de
verdade, então a suíte não supõe fila vazia nem alerta zerado.

    python tests/smoke_fila_e_rascunhos.py      (API de pé na 9200)
"""

import datetime
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
from comum import garantir_cozinha, garantir_local  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []
marca = str(int(time.time()))[-6:]
HOJE = datetime.date.today().isoformat()


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


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


def alerta(token, chave):
    st, lista = chamar("GET", "/alertas", token=token)
    return next((a for a in (lista or []) if a.get("chave") == chave), {"quantidade": 0})


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
local = garantir_local(chamar, token)
produtos, notas = [], []

print("1. produto VENDIDO sem custo entra na fila de fichas")
# Um preço alto de propósito: a fila mostra os que mais pesam, e a base local tem
# vendas de verdade — o produto desta rodada precisa caber no topo.
st, p = chamar("POST", "/produtos", {
    "codigo": f"FILA-{marca}", "nome": f"PRATO DA FILA {marca}", "tipo": "PRODUZIDO",
    "um_estoque": "UN", "controla_estoque": False, "producao_propria": True,
    "status": "ATIVO", "preco_venda": 999999}, token=token)
id_prato = (p or {}).get("id")
produtos.append(id_prato)
checar("o prato de teste nasce", bool(id_prato), (st, p))
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": HOJE, "documento": f"FILA-{marca}", "origem": "MANUAL",
    "itens": [{"id_produto": id_prato, "quantidade": 2, "valor_unitario": 999999}]}]},
    token=token)
checar("a venda entra", st in (200, 201), (st, r))

st, fila = chamar("GET", "/fichas/fila?dias=30&limite=200", token=token)
checar("a fila responde", st == 200, (st, fila))
linha = next((i for i in (fila or {}).get("itens", []) if i["id_produto"] == id_prato), None)
checar("o prato vendido sem custo está nela", linha is not None, [i["nome"] for i in fila["itens"]][:5])
checar("dizendo o que falta: a ficha", (linha or {}).get("falta") == "sem_ficha", linha)
checar("o administrador vê a receita: 2 x 999.999",
       abs(((linha or {}).get("receita") or 0) - 1999998) < 0.01, linha)
pesos = [i["participacao_pct"] for i in fila["itens"]]
checar("a ordem é a da receita, do maior para o menor", pesos == sorted(pesos, reverse=True),
       pesos[:6])
acumulada = [i["cobertura_acumulada_pct"] for i in fila["itens"]]
checar("a cobertura acumulada só cresce", acumulada == sorted(acumulada), acumulada[:6])
checar("e nunca passa de 100%", all(c <= 100.01 for c in acumulada), acumulada[-3:])
checar("a primeira linha parte da cobertura de hoje",
       acumulada[0] >= (fila.get("cobertura_pct") or 0), (acumulada[0], fila.get("cobertura_pct")))
checar("conta a fila inteira, não só a página", fila.get("produtos", 0) >= len(fila["itens"]),
       fila.get("produtos"))

print("\n2. quem não vê custo recebe a ordem, não o dinheiro")
cozinha = garantir_cozinha(chamar, token)
st, fila_c = chamar("GET", "/fichas/fila?limite=200", token=cozinha)
if st == 200:
    linha_c = next((i for i in fila_c["itens"] if i["id_produto"] == id_prato), {})
    checar("a cozinha vê a fila", True)
    checar("sem a receita em reais", fila_c.get("receita") is None and linha_c.get("receita") is None,
           (fila_c.get("receita"), linha_c))
    checar("mas com o peso em percentual", (linha_c.get("participacao_pct") or 0) > 0, linha_c)
else:
    # A Cozinha desta base pode não ter `fichas.visualizar`: aí a rota recusa, e é só isso.
    checar("sem permissão de ficha, a fila recusa", st == 403, st)
st, _ = chamar("GET", "/fichas/fila?dias=0", token=token)
checar("recorte de zero dias é recusado", st == 422, st)

print("\n3. rascunho PARADO fica fora do alerta e do filtro")
antes = alerta(token, "cadastro.rascunho")["quantidade"]
st, rasc = chamar("POST", "/produtos", {
    "codigo": f"RASC-{marca}", "nome": f"RASCUNHO {marca}", "tipo": "INSUMO",
    "um_estoque": "UN", "controla_estoque": True, "status": "RASCUNHO"}, token=token)
id_rasc = (rasc or {}).get("id")
produtos.append(id_rasc)
checar("o rascunho nasce", bool(id_rasc), (st, rasc))
checar("parado, não muda o alerta",
       alerta(token, "cadastro.rascunho")["quantidade"] == antes,
       (antes, alerta(token, "cadastro.rascunho")))
st, todos = chamar("GET", f"/produtos?status=RASCUNHO&busca=RASC-{marca}", token=token)
checar("ele existe na lista de rascunhos", any(x["id"] == id_rasc for x in (todos or [])), todos)
st, usados = chamar("GET", f"/produtos?status=RASCUNHO&em_uso=true&busca=RASC-{marca}",
                    token=token)
checar("mas não na de rascunhos em uso", not any(x["id"] == id_rasc for x in (usados or [])),
       usados)

print("\n4. em nota ABERTA, ele entra nos dois — e os dois contam igual")
st, fornecedores = chamar("GET", "/fornecedores?limite=1", token=token)
st, nota = chamar("POST", "/notas", {
    "id_fornecedor": fornecedores[0]["id"], "numero": f"RS{marca}", "serie": "1",
    "data_emissao": HOJE, "id_local": local["id"],
    "itens": [{"id_produto": id_rasc, "quantidade": 1, "valor_unitario": 5}]}, token=token)
notas.append((nota or {}).get("id"))
checar("a nota com o rascunho é digitada", st == 200, (st, nota))
depois = alerta(token, "cadastro.rascunho")
checar("o alerta sobe um", depois["quantidade"] == antes + 1, (antes, depois))
checar("e leva para a lista já filtrada",
       depois.get("href") == "/produtos?situacao=RASCUNHO_EM_USO", depois.get("href"))
st, usados = chamar("GET", f"/produtos?status=RASCUNHO&em_uso=true&busca=RASC-{marca}",
                    token=token)
checar("o filtro em uso passa a trazê-lo", any(x["id"] == id_rasc for x in (usados or [])),
       usados)
st, _pagina = chamar("GET", "/produtos?status=RASCUNHO&em_uso=true&limite=1000", token=token)
checar("alerta e lista contam a MESMA coisa", len(_pagina or []) == depois["quantidade"]
       or len(_pagina or []) == 1000, (len(_pagina or []), depois["quantidade"]))

print("\n5. limpeza")
# ⚠️ A venda de teste é CANCELADA: ela vale R$ 2 milhões de propósito (para caber
# no topo da fila), e deixada viva inflaria a receita do dia em toda tela e em
# toda suíte que vier depois.
st, vendas_teste = chamar("GET", "/vendas?busca=FILA-", token=token)
for v in (vendas_teste or []):
    if not v.get("cancelada"):
        chamar("DELETE", f"/vendas/{v['id']}", token=token)
st, sobrou = chamar("GET", "/vendas?busca=FILA-", token=token)
checar("nenhuma venda de teste fica valendo na base",
       not [v for v in (sobrou or []) if not v.get("cancelada")], sobrou)
for id_nota in notas:
    if id_nota:
        chamar("DELETE", f"/notas/{id_nota}", token=token)
checar("sem a nota, o alerta volta ao que era",
       alerta(token, "cadastro.rascunho")["quantidade"] == antes,
       alerta(token, "cadastro.rascunho"))
for id_produto in produtos:
    if id_produto:
        chamar("DELETE", f"/produtos/{id_produto}", token=token)
st, fila = chamar("GET", "/fichas/fila?limite=200", token=token)
checar("produto desativado sai da fila",
       not any(i["id_produto"] == id_prato for i in (fila or {}).get("itens", [])))

print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
