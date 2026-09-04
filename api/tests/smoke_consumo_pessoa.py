"""O CUPOM DA PESSOA: a prévia, o valor cheio guardado e o relatório da cobrança.

Os três pedidos do dono em 04/09/2026, numa suíte só porque são a mesma
mecânica vista de três lugares:

1. **"gostaria que o valor fosse ajustado ao digitar para ter esta percepção
   visual"** → `POST /vendas/previa`, que calcula pelo MESMO código do
   lançamento
2. **"ao acessar este cupom, ver o valor cheio e o valor do desconto"** →
   `venda_itens.valor_unitario_cheio`, que antes era perdido
3. **"gera um relatorio para demostrar o que foi consumido e o que teve de
   desconto, podendo ser sintetico ou analitico"** → `GET /vendas/por-pessoa`

⚠️ **O que esta suíte protege acima de tudo é a prévia NÃO virar a segunda
implementação da regra.** Ela cobra que prévia e lançamento cheguem ao mesmo
número — no dia em que alguém "otimizar" a prévia calculando no front, a
checagem 3 cai.

    python tests/smoke_consumo_pessoa.py     (API de pé na 9200)

⚠️ Cria produto, pessoas e vendas com marca de tempo, e limpa no `atexit`.
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, ".")

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None, cru=False):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=90) as r:
            bruto = r.read()
            return r.status, bruto if cru else json.loads(bruto or b"null")
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


def perto(a, b, tol=0.005):
    try:
        return abs(float(a) - float(b)) < tol
    except (TypeError, ValueError):
        return False


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API nao respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]

marca = str(time.time_ns())[-6:]
criados: dict = {"produtos": [], "vendas": []}


def _limpar():
    for v in criados["vendas"]:
        if v:
            chamar("DELETE", f"/vendas/{v}", token=token)
    for p in criados["produtos"]:
        if p:
            chamar("DELETE", f"/produtos/{p}", token=token)


atexit.register(_limpar)


print("1. o cenario: um prato de 50 e um funcionario com 20% de desconto")
st, prod = chamar("POST", "/produtos", {
    "codigo": f"CUP-{marca}", "nome": f"PRATO CUPOM {marca}",
    "tipo": "PRODUZIDO", "um_estoque": "UN", "controla_estoque": False,
    "status": "ATIVO", "preco_venda": 50,
}, token=token)
produto = (prod or {}).get("id")
criados["produtos"].append(produto)

st, pes = chamar("POST", "/fornecedores", {
    "nome": f"FUNCIONARIO {marca}", "fornecedor": False,
    "cupom_base": "VENDA", "cupom_desconto_pct": 20,
}, token=token)
funcionario = (pes or {}).get("id")
checar("o prato e o funcionario nascem", bool(produto and funcionario), (produto, funcionario))


print("\n2. a PREVIA diz quanto vai sair, antes de gravar")
st, pv = chamar("POST", "/vendas/previa", {
    "id_pessoa": funcionario,
    "itens": [{"id_produto": produto, "quantidade": 2, "valor_unitario": 50}],
}, token=token)
checar("a previa responde", st == 200, (st, pv))
checar("e diz a politica em portugues",
       "20% de desconto" in (pv.get("politica") or ""), pv.get("politica"))
# 🔑 O numero exato: 50 menos 20% = 40.
checar("50 com 20% de desconto sai por 40",
       perto(pv["itens"][0]["valor_unitario"], 40), pv["itens"][0])
# 🔑 **O preco CHEIO volta junto** — e e ele que continua no campo editavel da
# tela. Devolver so o ajustado faria o envio seguinte trazer o valor ja
# descontado, e o servidor descontaria de novo: 20% viraria 36%, calado.
checar("e o preco cheio volta junto, para a tela mostrar os dois",
       perto(pv["itens"][0]["valor_unitario_cheio"], 50), pv["itens"][0])
checar("os totais fecham: 100 cheio, 20 de desconto, 80 a pagar",
       perto(pv["total_cheio"], 100) and perto(pv["desconto"], 20) and perto(pv["total"], 80),
       (pv.get("total_cheio"), pv.get("desconto"), pv.get("total")))

st, pv0 = chamar("POST", "/vendas/previa", {
    "itens": [{"id_produto": produto, "quantidade": 2, "valor_unitario": 50}],
}, token=token)
# ⚠️ Politica que nao muda nada nao e anunciada: dizer "pelo preco de venda,
# sem desconto" faria a tela avisar de um ajuste que nao houve.
checar("sem pessoa, a previa nao anuncia politica nenhuma",
       pv0.get("politica") is None and perto(pv0["total"], 100), pv0)


print("\n3. o LANCAMENTO chega ao mesmo numero que a previa")
st, imp = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": "2026-09-04", "documento": f"CUPOM{marca}", "origem": "MANUAL",
    "id_pessoa": funcionario,
    "itens": [{"id_produto": produto, "quantidade": 2, "valor_unitario": 50}],
}]}, token=token)
checar("a venda entra", st == 201, (st, imp))
st, lista = chamar("GET", f"/vendas?busca=CUPOM{marca}", token=token)
venda = (lista or [{}])[0].get("id")
criados["vendas"].append(venda)
st, det = chamar("GET", f"/vendas/{venda}", token=token)
# 🔑 **A checagem que impede a prevIa de virar a segunda implementacao da
# regra.** No dia em que alguem calcular a previa no front, os dois numeros
# divergem e esta linha cai.
checar("o valor gravado e O MESMO que a previa prometeu",
       perto(det["valor_total"], pv["total"]), (det.get("valor_total"), pv.get("total")))


print("\n4. o CUPOM guarda o cheio, o cobrado e a politica do dia")
item = (det.get("itens") or [{}])[0]
# 🔑 Antes disto o preco de tabela era PERDIDO: a politica reescrevia o valor e
# nao sobrava de onde tirar o desconto.
checar("o item guarda o preco cheio de 50",
       perto(item.get("valor_unitario_cheio"), 50), item.get("valor_unitario_cheio"))
checar("e o cobrado de 40", perto(item.get("valor_unitario"), 40),
       item.get("valor_unitario"))
checar("o cupom diz para quem foi", det.get("pessoa") and marca in det["pessoa"],
       det.get("pessoa"))
# ⚠️ **CONGELADA**, como o custo da ficha: a politica muda no cadastro, e sem
# isto o cupom de marco passaria a se explicar por uma regra de setembro.
checar("e a politica que valia NO DIA, congelada",
       det.get("cupom_base") == "VENDA" and perto(det.get("cupom_desconto_pct"), 20),
       (det.get("cupom_base"), det.get("cupom_desconto_pct")))

st, r = chamar("PUT", f"/fornecedores/{funcionario}", {
    "nome": f"FUNCIONARIO {marca}", "fornecedor": False,
    "cupom_base": "VENDA", "cupom_desconto_pct": 50,
}, token=token)
st, det2 = chamar("GET", f"/vendas/{venda}", token=token)
checar("mudar a politica no cadastro NAO reescreve o cupom antigo",
       perto(det2.get("cupom_desconto_pct"), 20), det2.get("cupom_desconto_pct"))


print("\n5. o RELATORIO sintetico — o documento da cobranca")
st, rel = chamar(
    "GET", f"/vendas/por-pessoa?inicio=2026-09-04&fim=2026-09-04&id_pessoa={funcionario}",
    token=token)
checar("o sintetico responde", st == 200, (st, rel))
linha = (rel.get("linhas") or [{}])[0]
checar("uma linha, um cupom", linha.get("cupons") == 1, linha)
checar("com o valor cheio de 100", perto(linha.get("total_cheio"), 100), linha.get("total_cheio"))
checar("o desconto de 20", perto(linha.get("desconto"), 20), linha.get("desconto"))
checar("e 80 a cobrar", perto(linha.get("total"), 80), linha.get("total"))


print("\n6. o RELATORIO analitico — item a item")
st, rea = chamar(
    "GET",
    f"/vendas/por-pessoa?inicio=2026-09-04&fim=2026-09-04&id_pessoa={funcionario}"
    "&detalhe=analitico",
    token=token)
la = (rea.get("linhas") or [{}])[0]
checar("o analitico traz a linha do item", perto(la.get("quantidade"), 2), la.get("quantidade"))
checar("com os dois precos lado a lado",
       perto(la.get("unitario_cheio"), 50) and perto(la.get("unitario"), 40),
       (la.get("unitario_cheio"), la.get("unitario")))
# ⚠️ Os dois formatos respondem perguntas diferentes, mas sobre o MESMO dinheiro:
# discordarem seria o defeito que este relatorio existe para nao ter.
checar("e os dois formatos somam o mesmo total",
       perto(rea.get("total"), rel.get("total")), (rea.get("total"), rel.get("total")))


print("\n7. o cupom CANCELADO nao entra na cobranca")
st, imp = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": "2026-09-04", "documento": f"CANC{marca}", "origem": "MANUAL",
    "id_pessoa": funcionario, "cancelada": True,
    "itens": [{"id_produto": produto, "quantidade": 5, "valor_unitario": 50}],
}]}, token=token)
st, lc = chamar("GET", f"/vendas?busca=CANC{marca}", token=token)
criados["vendas"].append((lc or [{}])[0].get("id"))
st, rel2 = chamar(
    "GET", f"/vendas/por-pessoa?inicio=2026-09-04&fim=2026-09-04&id_pessoa={funcionario}",
    token=token)
# 🔑 Ele existe na base para a conferencia com o PDV fechar — mas cobrar alguem
# por um cupom cancelado seria cobrar o que nao foi consumido.
checar("o cancelado nao muda o total a cobrar",
       perto((rel2.get("linhas") or [{}])[0].get("total"), 80),
       (rel2.get("linhas") or [{}])[0].get("total"))


print("\n8. a exportacao sai do MESMO lugar que a tela")
st, cat = chamar("GET", "/exportar/catalogo", token=token)
alvo = next((c for c in (cat or []) if c["chave"] == "consumo-pessoa"), None)
checar("o relatorio esta no catalogo", alvo is not None,
       [c["chave"] for c in (cat or [])])
checar("com periodo, pessoas e detalhe",
       alvo and {f["nome"] for f in alvo["filtros"]} == {"periodo", "pessoas", "detalhe"},
       alvo and [f["nome"] for f in alvo["filtros"]])
st, csv = chamar("GET", "/exportar/consumo-pessoa.csv?inicio=2026-09-04&fim=2026-09-04",
                 token=token, cru=True)
checar("a planilha sai", st == 200 and isinstance(csv, bytes) and len(csv) > 100, st)
# ⚠️ **O arquivo e a tela nao podem discordar**: a diferenca apareceria numa
# discussao sobre dinheiro com quem esta sendo cobrado. Os dois vem da mesma
# funcao (`services.consumo_pessoa`), e esta linha cobra isso pelo numero.
texto = csv.decode("utf-8-sig", "replace") if isinstance(csv, bytes) else ""
checar("e o arquivo traz o mesmo total que a tela", "80" in texto, texto[:200])
st, pdf = chamar("GET", "/exportar/consumo-pessoa.pdf?inicio=2026-09-04&fim=2026-09-04"
                        "&detalhe=analitico", token=token, cru=True)
checar("e o PDF tambem, no analitico",
       st == 200 and isinstance(pdf, bytes) and pdf[:4] == b"%PDF", st)


print("\n9. o preco cheio nao se aceita de fora")
# ⚠️ Se o cliente pudesse declarar o cheio, qualquer chamador inventaria um
# desconto que nunca houve — e o relatorio de cobranca somaria dinheiro que
# ninguem deixou de pagar.
st, imp = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": "2026-09-04", "documento": f"FALSO{marca}", "origem": "MANUAL",
    "itens": [{"id_produto": produto, "quantidade": 1, "valor_unitario": 50,
               "valor_unitario_cheio": 999}],
}]}, token=token)
st, lf = chamar("GET", f"/vendas?busca=FALSO{marca}", token=token)
vf = (lf or [{}])[0].get("id")
criados["vendas"].append(vf)
st, df = chamar("GET", f"/vendas/{vf}", token=token)
checar("o cheio mandado pelo cliente e descartado",
       (df.get("itens") or [{}])[0].get("valor_unitario_cheio") is None,
       (df.get("itens") or [{}])[0].get("valor_unitario_cheio"))


_limpar()
print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
