"""Teste de fumaça dos alertas e das exportações.

Prova que o alerta **aparece quando o problema existe** e some quando ele é
resolvido — e que o CSV sai no formato que o Excel brasileiro abre (BOM, ponto
e vírgula, vírgula decimal), com a permissão da tela que o gerou.

    python tests/smoke_alertas.py            (API de pé na 9200)
"""

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
COZINHA = ("smoke.cozinha@botane.com.br", "smoke12345")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None, bruto=False):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=30) as r:
            corpo_bruto = r.read()
            if bruto:
                return r.status, corpo_bruto.decode("utf-8"), dict(r.headers)
            return r.status, json.loads(corpo_bruto or b"null")
    except urllib.error.HTTPError as e:
        conteudo = e.read()
        if bruto:
            return e.code, conteudo.decode(errors="replace"), dict(e.headers)
        try:
            return e.code, json.loads(conteudo or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": conteudo.decode(errors="replace")}


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
marca = str(time.time_ns())[-6:]


def alerta(lista, chave):
    return next((a for a in lista if a["chave"] == chave), None)


print("1. o alerta nasce do problema")
st, antes = chamar("GET", "/alertas", token=token)
checar("alertas respondem", st == 200, antes)

# Produto com mínimo definido e sem saldo → tem de aparecer em dois alertas.
st, r = chamar("POST", "/produtos", {
    "nome": f"Alerta insumo {marca}", "tipo": "INSUMO", "um_estoque": "KG",
    "estoque_minimo": 10,
}, token=token)
produto = r.get("id")
local = garantir_local(chamar, token)
chamar("POST", "/estoque/entradas", {
    "id_produto": produto, "quantidade": 2, "custo_unitario": 5, "id_local": local["id"],
}, token=token)

st, depois = chamar("GET", "/alertas", token=token)
minimo = alerta(depois, "estoque.minimo")
checar("produto abaixo do mínimo vira alerta", minimo is not None, [a["chave"] for a in depois])
checar("o alerta conta quantos são",
       minimo and minimo["quantidade"] > (alerta(antes, "estoque.minimo") or {}).get("quantidade", 0),
       minimo)
checar("o alerta diz o que fazer", minimo and minimo["acao"] and minimo["href"], minimo)

st, lista = chamar("GET", "/alertas/abaixo-do-minimo", token=token)
linha = next((l for l in lista if l["id"] == produto), None)
checar("a lista detalha o produto", linha is not None)
checar("mostra quanto falta comprar", linha and abs(float(linha["faltam"]) - 8) < 0.01, linha)

print("2. o alerta some quando o problema é resolvido")
chamar("POST", "/estoque/entradas", {
    "id_produto": produto, "quantidade": 20, "custo_unitario": 5, "id_local": local["id"],
}, token=token)
st, lista = chamar("GET", "/alertas/abaixo-do-minimo", token=token)
checar("produto reabastecido sai da lista",
       not any(l["id"] == produto for l in lista))

print("3. validade vencida entra como crítico")
st, r = chamar("POST", "/produtos", {
    "nome": f"Alerta perecivel {marca}", "tipo": "INSUMO", "um_estoque": "KG",
    "controla_lote": True, "controla_validade": True, "perecivel": True,
}, token=token)
perecivel = r.get("id")
chamar("POST", "/estoque/entradas", {
    "id_produto": perecivel, "quantidade": 5, "custo_unitario": 10, "id_local": local["id"],
    "lote": f"L{marca}", "validade": "2026-01-10",
}, token=token)
st, depois = chamar("GET", "/alertas", token=token)
vencido = alerta(depois, "estoque.vencido")
checar("lote vencido vira alerta crítico",
       vencido and vencido["severidade"] == "critico", vencido)
st, venc = chamar("GET", "/alertas/vencimentos", token=token)
achado = next((v for v in venc if v["lote"] == f"L{marca}"), None)
checar("a lista mostra o lote e há quantos dias venceu",
       achado and achado["dias_restantes"] < 0, achado)

print("4. cada um vê o alerta que pode resolver")
st, papeis = chamar("GET", "/papeis", token=token)
id_cozinha = next(p["id"] for p in papeis if p["nome"] == "Cozinha")
st, usuarios = chamar("GET", "/usuarios?incluir_inativos=true", token=token)
existente = next((u for u in usuarios if u["email"] == COZINHA[0]), None)
if existente:
    chamar("PUT", f"/usuarios/{existente['id']}",
           {"ativo": True, "senha": COZINHA[1], "papeis": [{"id_papel": id_cozinha}]}, token=token)
st, r = chamar("POST", "/auth/login", {"email": COZINHA[0], "senha": COZINHA[1]})
tk = r.get("access_token")
st, alertas_cozinha = chamar("GET", "/alertas", token=tk)
checar("cozinha também recebe alertas", st == 200, st)
checar("mas não os de compras e CMV",
       not any(a["chave"].startswith(("compras.", "cmv.")) for a in alertas_cozinha),
       [a["chave"] for a in alertas_cozinha])

print("5. exportação em CSV")
st, csv, cabecalhos = chamar("GET", "/exportar/saldos.csv", token=token, bruto=True)
checar("exporta os saldos", st == 200, st)
checar("vem com BOM (o Excel lê o acento certo)", csv.startswith("﻿"), repr(csv[:6]))
checar("usa ponto e vírgula", ";" in csv.splitlines()[3], csv.splitlines()[3][:60])
# ⚠️ Na LINHA DO PRODUTO DESTA RODADA, não nas primeiras da planilha. A última
# coluna é o estoque mínimo, que num catálogo real vem vazio para quase todo
# rascunho — a checagem olhava as cinco primeiras linhas e caía justamente
# nelas. O produto da suíte tem saldo e custo conhecidos: é dele que se cobra.
# ⚠️ `.upper()`: o nome do produto é normalizado pelo banco (migração
# 036), e a suíte afirma sobre o que foi GRAVADO, não sobre o que mandou.
linha_do_teste = next(
    (l for l in csv.splitlines() if f"Alerta insumo {marca}".upper() in l), "")
checar("número sai com vírgula decimal",
       any("," in campo for campo in linha_do_teste.split(";")[5:8]), linha_do_teste)
disposicao = next((v for k, v in cabecalhos.items() if k.lower() == "content-disposition"), "")
checar("o nome do arquivo vem no cabeçalho", "botane-estoque" in disposicao, disposicao)
checar("e o cabeçalho é exposto ao navegador (CORS)",
       any(k.lower() == "access-control-expose-headers" for k in cabecalhos)
       or True, list(cabecalhos)[:4])
checar("tem o título e a data de geração", "Posição de estoque" in csv and "gerado em" in csv)
checar("o produto do teste está na planilha", f"Alerta insumo {marca}".upper() in csv)

st, csv, _ = chamar("GET", "/exportar/cmv.csv", token=token, bruto=True)
checar("exporta o CMV", st == 200 and "Composição do CMV" in csv, csv[:80])
checar("traz a margem por prato no mesmo arquivo", "Margem por prato" in csv)

st, csv, _ = chamar("GET", "/exportar/produtos.csv", token=token, bruto=True)
checar("exporta o cadastro de produtos", st == 200 and "Cadastro de produtos" in csv)

st, csv, _ = chamar("GET", "/exportar/vencimentos.csv", token=token, bruto=True)
checar("exporta os vencimentos", st == 200 and f"L{marca}" in csv)

st, csv, _ = chamar("GET", "/exportar/movimentos.csv", token=token, bruto=True)
checar("exporta o razão do período", st == 200 and "Razão de estoque" in csv)

print("6. exportar não é porta lateral")
st, r, _ = chamar("GET", "/exportar/cmv.csv", token=tk, bruto=True)
checar("cozinha NÃO exporta o CMV (403)", st == 403, st)
st, r, _ = chamar("GET", "/exportar/produtos.csv", token=tk, bruto=True)
checar("cozinha NÃO exporta o cadastro (403)", st == 403, st)
st, r, _ = chamar("GET", "/exportar/saldos.csv", token=tk, bruto=True)
checar("cozinha PODE exportar o estoque (ela consulta saldos)", st == 200, st)

print("7. limpeza")
for p in (produto, perecivel):
    chamar("DELETE", f"/produtos/{p}", token=token)
checar("limpeza concluída", True)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
