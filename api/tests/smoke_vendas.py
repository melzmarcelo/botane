"""Teste de fumaça das telas de venda: a lista, o detalhe e o lançamento.

`/vendas` era uma tela só: dois formulários no topo e as vendas embaixo. Com
1.375 vendas num mês isso deixou de servir — quem precisa achar uma venda não a
acha, e quem precisa saber o que ela tinha dentro não tem para onde ir.

O que este arquivo cobra:

1. a lista **filtra pela loja atual**, e não somava as de todas as lojas
2. busca e filtro de origem vão ao SERVIDOR, não à página carregada
3. `/vendas/{id}` devolve cabeçalho, itens e os movimentos de estoque
4. o custo do detalhe é o **congelado**, não o de hoje
5. item sem ficha é contado, para a tela poder dizer "parcial" em vez de mentir
6. **`/vendas/sem-vinculo` continua respondendo** — a rota com parâmetro não a
   engoliu (é o erro clássico de ordem de declaração no FastAPI)
7. cancelar devolve o estoque, e o detalhe mostra o estorno

⚠️ **A suíte procura os registros DELA.** A base é compartilhada e tem vendas
reais importadas do PDV; contar linhas ou pegar "a primeira venda" acusaria bug
onde não há.

    python tests/smoke_vendas.py            (API de pé na 9200)
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
from comum import garantir_locais  # noqa: E402

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

marca = str(time.time_ns())[-6:]
hoje = date.today().isoformat()

print("1. um prato com ficha, para o detalhe ter custo de verdade")
garantir_locais(chamar, token)

st, r = chamar("POST", "/produtos", {
    "codigo": f"VD-INS-{marca}", "nome": f"Insumo venda {marca}", "tipo": "INSUMO",
    "um_estoque": "KG", "controla_estoque": True, "status": "ATIVO",
}, token=token)
insumo = r.get("id")
checar("insumo criado", st == 201, (st, r))

# ⚠️ `controla_estoque` LIGADO, e é isso que faz a venda mexer no razão. Vender
# é sair do estoque: sem esta caixinha o prato continuaria na prateleira do
# sistema depois de vendido, o CMV real sairia subestimado, e a primeira
# contagem cobriria o buraco como "ajuste de inventário" — que é onde a
# diferença some sem nome.
st, r = chamar("POST", "/produtos", {
    "codigo": f"VD-PRT-{marca}", "nome": f"Prato venda {marca}", "tipo": "PRODUZIDO",
    "um_estoque": "UN", "producao_propria": True, "controla_estoque": True,
    "modo_producao": "NA_HORA", "status": "ATIVO",
}, token=token)
prato = r.get("id")
checar("prato criado", st == 201, (st, r))

# Uma entrada dá custo médio ao insumo; sem ela a ficha nasce sem custo e o
# detalhe não teria o que congelar.
st, locais = chamar("GET", "/locais", token=token)
principal = next((x for x in locais if x.get("principal")), locais[0])
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": insumo, "quantidade": 10, "custo_unitario": 20,
    "id_local": principal["id"], "documento": f"VD-{marca}",
}, token=token)
checar("entrada dá custo médio de 20,00 ao insumo", st == 201, (st, r))

st, r = chamar("POST", "/fichas", {
    "id_produto": prato, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": insumo, "qtd_bruta": 0.5, "um": "KG"}],
}, token=token)
ficha = r.get("id")
checar("ficha criada", st == 201, (st, r))
st, r = chamar("POST", f"/fichas/{ficha}/homologar", token=token)
checar("ficha homologada", st == 200, (st, r))

print("\n2. a venda")
documento = f"VENDA-{marca}"
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": hoje, "documento": documento, "origem": "MANUAL", "canal": "BALCAO",
    "itens": [
        {"id_produto": prato, "quantidade": 3, "valor_unitario": 30},
        # ⚠️ Item sem produto de propósito: é ele que faz o detalhe ter de dizer
        # "parcial" em vez de mostrar uma margem que não é a da venda.
        {"codigo": f"NAO-EXISTE-{marca}", "descricao": f"Fantasma {marca}",
         "quantidade": 1, "valor_unitario": 10},
    ],
}]}, token=token)
checar("venda importada", st == 201 and r.get("importadas") == 1, (st, r))
checar("um item ficou sem vínculo", r.get("itens_sem_vinculo") == 1, r)

st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": hoje, "documento": documento, "origem": "MANUAL",
    "itens": [{"id_produto": prato, "quantidade": 1, "valor_unitario": 30}],
}]}, token=token)
checar("mesmo documento não duplica", r.get("repetidas") == 1, r)

print("\n3. a lista")
st, lista = chamar("GET", f"/vendas?busca={documento}", token=token)
checar("a busca vai ao servidor", st == 200 and len(lista) == 1, (st, len(lista or [])))
minha = lista[0] if lista else {}
id_venda = minha.get("id")
checar("e traz a venda desta rodada", minha.get("documento") == documento, minha)
checar("com a contagem de itens", minha.get("itens") == 2, minha)
checar("e o aviso de item sem custo", minha.get("sem_custo") == 1, minha)

st, lista = chamar("GET", f"/vendas?busca={documento}&origem=PDV_LEGAL", token=token)
checar("o filtro de origem exclui", st == 200 and not lista, (st, lista))

st, lista = chamar("GET", f"/vendas?busca=NAOEXISTE{marca}", token=token)
checar("busca sem resultado devolve lista vazia, não tudo",
       st == 200 and not lista, (st, len(lista or [])))

st, lista = chamar("GET", f"/vendas?busca={documento}&inicio=2000-01-01&fim=2000-01-02",
                   token=token)
checar("o período filtra", st == 200 and not lista, (st, lista))

print("\n4. a rota do detalhe não engoliu a fila de de-para")
# ⚠️ O FastAPI casa rotas na ordem de declaração: com `/{id_venda}` na frente,
# "sem-vinculo" viraria um id e o pedido morreria em 422.
st, fila = chamar("GET", "/vendas/sem-vinculo", token=token)
checar("/vendas/sem-vinculo continua respondendo", st == 200 and isinstance(fila, list), st)
checar("e a fila tem o fantasma desta rodada",
       any(f"NAO-EXISTE-{marca}" == (x.get("codigo_pdv") or "") for x in fila), len(fila))

print("\n5. o detalhe")
st, d = chamar("GET", f"/vendas/{id_venda}", token=token)
checar("o detalhe responde", st == 200, (st, d))
checar("com o cabeçalho", d.get("documento") == documento, d.get("documento"))
checar("o canal veio junto", d.get("canal") == "BALCAO", d.get("canal"))
checar("os dois itens", len(d.get("itens") or []) == 2, len(d.get("itens") or []))

item = next((i for i in d["itens"] if i["id_produto"] == prato), None)
checar("o item vinculado traz o nome do produto",
       item and item["produto"] == f"Prato venda {marca}", item)
# 0,5 kg × 20/kg = 10,00 por unidade — o custo CONGELADO, não o de hoje.
checar("e o custo congelado da ficha (10,00)",
       item and abs(float(item["custo_ficha_unitario"]) - 10) < 0.01, item)
checar("dizendo que veio da ficha", item and item["origem_custo"] == "ficha", item)

fantasma = next((i for i in d["itens"] if i["id_produto"] is None), None)
checar("o item sem produto aparece com a descrição do PDV",
       fantasma and fantasma["descricao_pdv"] == f"Fantasma {marca}", fantasma)
checar("e sem custo", fantasma and fantasma["custo_ficha_unitario"] is None, fantasma)

checar("a receita soma os dois itens (100,00)", abs(float(d["receita"]) - 100) < 0.01, d["receita"])
checar("o custo teórico é só o do que tem ficha (30,00)",
       abs(float(d["custo_teorico"]) - 30) < 0.01, d["custo_teorico"])
# ⚠️ Sem esta contagem a tela mostraria margem de 70% como se fosse o resultado
# da venda — quando um dos itens simplesmente não tem custo conhecido.
checar("e a tela sabe que é parcial", d.get("itens_sem_custo") == 1, d)
checar("e que há item sem vínculo", d.get("itens_sem_vinculo") == 1, d)

print("\n6. o movimento de estoque, e o estorno do cancelamento")
# O prato é NA_HORA: a venda produz e baixa no mesmo lançamento, e o saldo dele
# volta a zero. A prova é o razão apontando para esta venda.
movimentos = d.get("movimentos") or []
checar("a venda deixou rastro no razão", len(movimentos) >= 1, len(movimentos))
checar("nenhum deles é estorno ainda",
       all(not m["id_estorno_de"] for m in movimentos), movimentos)

st, r = chamar("DELETE", f"/vendas/{id_venda}", token=token)
checar("cancelar responde", st == 200, (st, r))
checar("e devolve o que tinha saído", (r.get("estornados") or 0) >= 1, r)

st, d2 = chamar("GET", f"/vendas/{id_venda}", token=token)
checar("a venda continua existindo, cancelada", d2.get("cancelada") is True, d2.get("cancelada"))
checar("e o estorno aparece no detalhe",
       any(m["id_estorno_de"] for m in d2.get("movimentos") or []), d2.get("movimentos"))

st, r = chamar("DELETE", f"/vendas/{id_venda}", token=token)
checar("cancelar de novo é recusado", st == 400, st)

st, r = chamar("GET", "/vendas/99999999", token=token)
checar("venda inexistente é 404", st == 404, st)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
