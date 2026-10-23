"""Os quatro relatórios de 23/10/2026: compras, perdas e ajustes, margem dos pratos e
recebimentos do consumo.

🔑 Pedido do dono: *"Gostaria de mais relatorios e planilhas"* — escolhidos 1, 2, 3 e 6
da lista proposta. Cada um é cobrado pelo que AFIRMA: a soma que fecha, a linha que
aparece, o filtro que corta e a permissão que barra.

    python tests/smoke_relatorios_gestao.py      (API de pé na 9200)
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import garantir_cozinha, garantir_local  # noqa: E402

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
        with urllib.request.urlopen(req, dados, timeout=180) as r:
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


def numero(texto: str) -> float:
    """"1234,5" (o CSV da casa) → 1234.5; vazio → 0."""
    texto = (texto or "").strip()
    return float(texto.replace(",", ".")) if texto else 0.0


def csv(caminho: str) -> tuple[int, list[list[str]]]:
    """O CSV em linhas de células; o título, o resumo e o cabeçalho vêm junto."""
    st, bruto = chamar("GET", caminho, token=token, cru=True)
    if st != 200 or not isinstance(bruto, bytes):
        return st, []
    texto = bruto.decode("utf-8-sig")
    return st, [l.split(";") for l in texto.splitlines()]


def linha_com(linhas, trecho: str) -> list[str] | None:
    return next((l for l in linhas if any(trecho in c for c in l)), None)


def coluna(linhas, cabecalho: str, linha: list[str]) -> str:
    """A célula de `linha` na coluna cujo cabeçalho é `cabecalho`."""
    for l in linhas:
        if cabecalho in l and len(l) == len(linha):
            return linha[l.index(cabecalho)]
    return ""


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API nao respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
marca = str(time.time_ns() // 100)[-6:]
hoje = date.today().isoformat()
criados: dict = {"produtos": [], "vendas": [], "lotes": [], "pessoas": [], "movimentos": []}


def _limpar():
    for lid in criados["lotes"]:
        chamar("POST", f"/receber/lotes/{lid}/estornar-baixa", None, token=token)
        chamar("POST", f"/receber/lotes/{lid}/cancelar", None, token=token)
    for v in criados["vendas"]:
        if v:
            chamar("DELETE", f"/vendas/{v}", token=token)
    for m in criados["movimentos"]:
        chamar("POST", f"/estoque/movimentos/{m}/estornar", {"motivo": "limpeza da suite"},
               token=token)
    for p in criados["produtos"]:
        if p:
            chamar("DELETE", f"/produtos/{p}", token=token)
    for f in criados["pessoas"]:
        chamar("DELETE", f"/fornecedores/{f}", token=token)
    for k in criados:
        criados[k].clear()


atexit.register(_limpar)


print("1. os quatro entram no catalogo de quem pode")
st, cat = chamar("GET", "/exportar/catalogo", token=token)
chaves = {c["chave"] for c in cat or []}
checar("compras, perdas, margem e recebimentos aparecem para o admin",
       {"compras", "perdas", "margem", "recebimentos"} <= chaves, sorted(chaves))
filtros = {c["chave"]: {x["nome"] for x in c["filtros"]} for c in cat or []}
checar("com os filtros declarados",
       {"detalhe_compras", "situacao_nota", "busca_fornecedor"} <= filtros.get("compras", set())
       and {"detalhe_perdas", "motivos"} <= filtros.get("perdas", set())
       and {"formas", "pessoas"} <= filtros.get("recebimentos", set()), filtros)


print("\n2. o cenario: um insumo com entrada, perda e uma venda; uma pessoa com lote")
local = garantir_local(chamar, token)
st, prod = chamar("POST", "/produtos", {
    "codigo": f"REL-{marca}", "nome": f"INSUMO RELATORIO {marca}", "tipo": "REVENDA",
    "um_estoque": "UN", "controla_estoque": True, "status": "ATIVO", "preco_venda": 25,
}, token=token)
PROD = (prod or {}).get("id")
criados["produtos"].append(PROD)
st, ent = chamar("POST", "/estoque/entradas", {
    "id_produto": PROD, "quantidade": 10, "custo_unitario": 10, "id_local": local["id"],
    "documento": f"REL {marca}"}, token=token)
if (ent or {}).get("id"):
    criados["movimentos"].append(ent["id"])
_st, motivos = chamar("GET", "/estoque/motivos-perda", token=token)
MOTIVO = (motivos or [{}])[0]
st, perda = chamar("POST", "/estoque/saidas", {
    "id_produto": PROD, "quantidade": 3, "tipo": "SAIDA_PERDA", "id_local": local["id"],
    "id_motivo_perda": MOTIVO.get("id"), "observacao": f"perda {marca}"}, token=token)
PERDA = (perda or {}).get("id")
checar("a entrada e a perda entram", ent.get("id") and PERDA, (ent, perda))

st, v = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": hoje, "documento": f"REL{marca}", "origem": "MANUAL",
    "itens": [{"id_produto": PROD, "quantidade": 2, "valor_unitario": 25}]}]}, token=token)
st, lista = chamar("GET", f"/vendas?busca=REL{marca}", token=token)
criados["vendas"].append((lista or [{}])[0].get("id"))

st, pessoa = chamar("POST", "/fornecedores", {"nome": f"REL PESSOA {marca}",
                                              "fornecedor": False}, token=token)
PESSOA = (pessoa or {}).get("id")
criados["pessoas"].append(PESSOA)
st, v = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": hoje, "documento": f"RELP{marca}", "origem": "MANUAL", "id_pessoa": PESSOA,
    "itens": [{"id_produto": PROD, "quantidade": 1, "valor_unitario": 30}]}]}, token=token)
st, lista = chamar("GET", f"/vendas?busca=RELP{marca}", token=token)
criados["vendas"].append((lista or [{}])[0].get("id"))
st, g = chamar("POST", "/receber/lotes", {"ate": hoje, "ids_pessoa": [PESSOA]}, token=token)
LOTE = ((g or {}).get("lotes") or [{}])[0].get("id")
criados["lotes"].append(LOTE)
st, b = chamar("POST", f"/receber/lotes/{LOTE}/receber",
               {"recebido_em": hoje, "forma_pagamento": "PERMUTA"}, token=token)
checar("a venda, o lote e a baixa por permuta entram", st == 200 and LOTE, (st, b))


print("\n3. perdas e ajustes: a perda aparece com o motivo, e o estorno a zera")
q = f"inicio={hoje}&fim={hoje}"
st, linhas = csv(f"/exportar/perdas.csv?{q}&detalhe_perdas=movimento")
minha = linha_com(linhas, f"INSUMO RELATORIO {marca}")
checar("movimento a movimento: a perda de 3 a 10,00 vale 30",
       st == 200 and minha and abs(numero(coluna(linhas, "Valor", minha)) - 30) < 0.01,
       (st, minha))
checar("com o motivo do cadastro", minha and coluna(linhas, "Motivo", minha) == MOTIVO.get("nome"),
       (minha, MOTIVO))
st, linhas = csv(f"/exportar/perdas.csv?{q}&detalhe_perdas=motivo&motivos=m{MOTIVO.get('id')}")
checar("por motivo, filtrado pelo motivo: so ele sai",
       st == 200 and linha_com(linhas, MOTIVO.get("nome", "?"))
       and not linha_com(linhas, "Diferença de inventário"), linhas[:8])
st, linhas = csv(f"/exportar/perdas.csv?{q}&detalhe_perdas=produto&motivos=inventario")
checar("o filtro por origem corta: em 'inventario' o insumo nao aparece",
       st == 200 and not linha_com(linhas, f"INSUMO RELATORIO {marca}"), linhas[:6])
chamar("POST", f"/estoque/movimentos/{PERDA}/estornar", {"motivo": "teste"}, token=token)
st, linhas = csv(f"/exportar/perdas.csv?{q}&detalhe_perdas=produto")
minha = linha_com(linhas, f"INSUMO RELATORIO {marca}")
checar("estornada, a perda liquida do produto vai a zero",
       minha and abs(numero(coluna(linhas, "Valor perdido", minha))) < 0.01, minha)
st, pdf = chamar("GET", f"/exportar/perdas.pdf?{q}", token=token, cru=True)
checar("e o PDF sai", st == 200 and pdf[:5] == b"%PDF-", st)


print("\n4. compras: as visoes somam o mesmo, e o filtro de situacao corta")
q = "inicio=2026-01-01&fim=2026-12-31"
totais = {}
for det, cab, rotulo in (("nota", "Total das notas", "Total das notas"),
                         ("fornecedor", "Total das notas", "Total das notas"),
                         ("produto", "Custo total dos itens", "Custo total dos itens"),
                         ("item", "Custo total dos itens", "Custo total dos itens")):
    st, linhas = csv(f"/exportar/compras.csv?{q}&detalhe_compras={det}")
    resumo = linha_com(linhas, rotulo)
    totais[det] = numero(resumo[1]) if resumo and len(resumo) > 1 else None
    checar(f"a visao '{det}' sai", st == 200 and totais[det] is not None, (st, linhas[:6]))
checar("por nota e por fornecedor fecham no mesmo total",
       totais["nota"] is not None and abs(totais["nota"] - (totais["fornecedor"] or -1)) < 0.01,
       totais)
checar("por produto e item a item fecham no mesmo custo",
       totais["produto"] is not None and abs(totais["produto"] - (totais["item"] or -1)) < 0.01,
       totais)
st, linhas = csv(f"/exportar/compras.csv?{q}&detalhe_compras=nota&situacao_nota=cancelada")
situacoes = {l[4] for l in linhas if len(l) == 11 and l[4] in
             ("lançada", "importada", "conciliada", "cancelada")}
checar("so canceladas: nenhuma lancada no arquivo", st == 200 and situacoes <= {"cancelada"},
       situacoes)
st, pdf = chamar("GET", f"/exportar/compras.pdf?{q}&detalhe_compras=fornecedor", token=token,
                 cru=True)
checar("e o PDF sai", st == 200 and pdf[:5] == b"%PDF-", st)


print("\n5. margem dos pratos: o vendido no periodo, com o custo e o CMV %")
st, linhas = csv(f"/exportar/margem.csv?inicio={hoje}&fim={hoje}")
minha = linha_com(linhas, f"INSUMO RELATORIO {marca}")
checar("o produto vendido hoje aparece", st == 200 and minha, (st, linhas[:6]))
checar("com o preco de 25 e as 3 unidades vendidas (2 + 1 da pessoa)",
       minha and abs(numero(coluna(linhas, "Preço", minha)) - 25) < 0.01
       and abs(numero(coluna(linhas, "Vendido", minha)) - 3) < 0.01, minha)
cmv_pct = numero(coluna(linhas, "CMV %", minha)) if minha else 0
checar("e o CMV % de pelo menos 40 (custo 10 sobre 25, mais o que a loja somar por unidade)",
       cmv_pct >= 39.99, cmv_pct)
st, linhas = csv("/exportar/margem.csv?inicio=2001-01-01&fim=2001-01-31")
checar("periodo sem venda: o produto nao aparece",
       st == 200 and not linha_com(linhas, f"INSUMO RELATORIO {marca}"), st)


print("\n6. recebimentos: o lote baixado no periodo, e o quadro por forma")
st, linhas = csv(f"/exportar/recebimentos.csv?inicio={hoje}&fim={hoje}")
minha = linha_com(linhas, f"REL PESSOA {marca}")
checar("o lote recebido hoje aparece com a forma",
       st == 200 and minha and coluna(linhas, "Forma", minha) == "Permuta", minha)
checar("e o quadro por forma de pagamento vem junto",
       linha_com(linhas, "Por forma de pagamento") is not None, linhas[-6:])
st, linhas = csv(f"/exportar/recebimentos.csv?inicio={hoje}&fim={hoje}&formas=DINHEIRO")
checar("filtrado por dinheiro, o lote da permuta some",
       st == 200 and not linha_com(linhas, f"REL PESSOA {marca}"), st)
st, pdf = chamar("GET", f"/exportar/recebimentos.pdf?inicio={hoje}&fim={hoje}", token=token,
                 cru=True)
checar("e o PDF sai", st == 200 and pdf[:5] == b"%PDF-", st)


print("\n7. quem nao tem a chave nao baixa")
tk = garantir_cozinha(chamar, token)
st_c, cat_c = chamar("GET", "/exportar/catalogo", token=tk)
chaves_c = {c["chave"] for c in cat_c or []}
for chave in ("compras", "margem", "recebimentos"):
    if chave not in chaves_c:
        st, r = chamar("GET", f"/exportar/{chave}.csv", token=tk)
        checar(f"{chave} sem a chave: 403", st == 403, (st, r))
checar("e o catalogo da cozinha so oferece o que ela pode baixar",
       all(chamar("GET", f"/exportar/{c}.csv?inicio={hoje}&fim={hoje}", token=tk,
                  cru=True)[0] == 200
           for c in chaves_c & {"compras", "perdas", "margem", "recebimentos"}), chaves_c)


_limpar()
print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
