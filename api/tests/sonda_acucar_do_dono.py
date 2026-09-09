"""O caso EXATO que o dono pediu para conferir (09/09/2026).

    Açúcar 1 kg (principal, estoque em KG)
      vinculado ao Açúcar 500 g, com fator de conversão 0,5

    Nota de entrada do Açúcar 500 g: 4 unidades a R$ 2,50

    Esperado:  o Açúcar 1 kg recebe 2 KG no estoque
               e o custo passa a 5,00 por KG

A conta: 4 x 0,5 = 2 KG. 4 x 2,50 = R$ 10,00. 10,00 / 2 = R$ 5,00/KG.

⚠️ Isto é uma SONDA, não uma suíte da bateria: ela monta o cenário, mede e
apaga o que criou. Roda com a API de pé na 9200.

    python tests/sonda_acucar_do_dono.py
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import garantir_fornecedor, garantir_local  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
marca = uuid.uuid4().hex[:6].upper()
criados: list[int] = []
notas: list[int] = []
ok, falhas = 0, []


def chamar(metodo, caminho, corpo=None, token=None):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=60) as r:
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
        print(f"  FALHA {nome}  ->  {detalhe}")


def perto(a, b, casas=4):
    return abs(float(a or 0) - float(b)) < 10 ** -casas


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = r["access_token"]
init_pool()
local = garantir_local(chamar, token)
fornecedor = garantir_fornecedor(chamar, token, f"ACUCAREIRA {marca}", "77888999000155")

print("1. o cenario do dono")
_st, p1 = chamar("POST", "/produtos", {
    "codigo": f"ACU1KG-{marca}", "nome": f"ACUCAR 1KG {marca}",
    "tipo": "INSUMO", "um_estoque": "KG", "controla_estoque": True,
    "status": "ATIVO", "id_local_padrao": local["id"]}, token=token)
principal = p1["id"]
criados.append(principal)

_st, p2 = chamar("POST", "/produtos", {
    "codigo": f"ACU500-{marca}", "nome": f"ACUCAR 500G {marca}",
    "tipo": "INSUMO", "um_estoque": "KG", "controla_estoque": True,
    "status": "ATIVO"}, token=token)
meio = p2["id"]
criados.append(meio)
print(f"   Acucar 1kg = {principal} | Acucar 500g = {meio}")

# O vinculo: o de 500 g e o mesmo produto, e some dentro do principal.
st, r = chamar("POST", f"/produtos/{principal}/vincular",
               {"id_sai": meio}, token=token)
checar("os dois cadastros se vinculam", st == 200, (st, r))

# ⚠️ **O de-para se ensina pelo caminho de quem usa, nao por SQL.** A
# primeira versao desta sonda gravou `codigos_externos` com
# `sistema='FORNECEDOR'` -- e a cascata do fator consulta `'OMIE'`. O fator nao
# foi achado, os 4 UN entraram como 4 KG e a sonda "provou" um defeito que era
# dela. Agora ela faz o que a pessoa faz: lanca a nota com o codigo do
# fornecedor, vincula o item ao principal informando o fator e marca `aprender`.
codigo_externo = f"AC500-{marca}"


print("\n2. a nota: 4 unidades de Acucar 500g a R$ 2,50")
st, nota = chamar("POST", "/notas", {
    "id_fornecedor": fornecedor, "numero": f"AC{marca}", "serie": "1",
    "data_emissao": "2026-09-09", "id_local": local["id"],
    "itens": [{"id_produto": principal, "quantidade": 4, "um": "UN",
               "valor_unitario": 2.50,
               "codigo_fornecedor": codigo_externo}],
}, token=token)
checar("a nota entra", st == 200, (st, nota))
id_nota = nota.get("id")
if id_nota:
    notas.append(id_nota)

st, n = chamar("GET", f"/notas/{id_nota}", token=token)
item = (n.get("itens") or [{}])[0]

# 🔑 **A conversao se DITA aqui**, vinculando o item e informando quanto vale
# uma unidade daquele codigo. `aprender` grava o de-para: a proxima nota do
# mesmo fornecedor entra sozinha, ja convertida.
st, v = chamar("POST", f"/notas/itens/{item['id']}/vincular",
               {"id_produto": principal, "fator": 0.5, "aprender": True}, token=token)
checar("o item se vincula ao principal com fator 0,5", st == 200, (st, v))

st, n = chamar("GET", f"/notas/{id_nota}", token=token)
item = (n.get("itens") or [{}])[0]
print(f"   item: {item.get('quantidade')} {item.get('um_nota')} "
      f"x {item.get('valor_unitario')}  ->  convertida "
      f"{item.get('quantidade_convertida')} | custo "
      f"{item.get('custo_aquisicao_unitario')}")

checar("4 UN viram 2 KG", perto(item.get("quantidade_convertida"), 2),
       item.get("quantidade_convertida"))
checar("e o custo de aquisicao e 5,00 por KG",
       perto(item.get("custo_aquisicao_unitario"), 5),
       item.get("custo_aquisicao_unitario"))


print("\n3. o razao e o custo do PRINCIPAL, depois de lancar")
st, r = chamar("POST", f"/notas/{id_nota}/lancar", {"id_local": local["id"]}, token=token)
checar("a nota lanca", st == 200, (st, r))

st, movs = chamar("GET", f"/estoque/movimentos?id_produto={principal}", token=token)
lista = movs.get("itens", movs) if isinstance(movs, dict) else movs
entrada = next((m for m in (lista or []) if m["tipo"] == "ENTRADA_NF"), None)
print("   movimento:", {k: entrada.get(k) for k in
                        ("tipo", "quantidade", "custo_unitario")} if entrada else None)
checar("o Acucar 1kg recebe 2 KG no razao",
       entrada and perto(entrada["quantidade"], 2),
       entrada and entrada.get("quantidade"))
checar("com custo unitario de 5,00",
       entrada and perto(entrada["custo_unitario"], 5),
       entrada and entrada.get("custo_unitario"))

st, saldos = chamar("GET", f"/estoque/saldos?id_produto={principal}", token=token)
linhas = saldos.get("itens", saldos) if isinstance(saldos, dict) else saldos
saldo = (linhas or [None])[0]
print("   saldo:", {k: saldo.get(k) for k in
                    ("quantidade", "custo_medio")} if saldo else None)
checar("o saldo do principal e 2 KG", saldo and perto(saldo["quantidade"], 2),
       saldo and saldo.get("quantidade"))
checar("e o custo medio e 5,00 por KG", saldo and perto(saldo["custo_medio"], 5),
       saldo and saldo.get("custo_medio"))

st, custo = chamar("GET", f"/produtos/{principal}/custo", token=token)
print("   o que a tela do produto mostra:",
      {k: custo.get(k) for k in list(custo)[:6]} if isinstance(custo, dict) else custo)


print("\n4. limpando o que a sonda criou")
for nid in notas:
    chamar("POST", f"/notas/{nid}/estornar", {}, token=token)
    chamar("DELETE", f"/notas/{nid}", token=token)
with get_cursor() as cur:
    cur.execute("DELETE FROM codigos_externos WHERE codigo = %s", (codigo_externo,))
for pid in criados:
    chamar("DELETE", f"/produtos/{pid}", token=token)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
raise SystemExit(1 if falhas else 0)
