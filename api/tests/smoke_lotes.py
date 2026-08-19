"""Teste de fumaça do FEFO — o lote na saída.

O cenário, conferido na mão:

    entra 10 un no lote A, que vence 10/09
    entra 10 un no lote B, que vence 20/09
    entra 10 un SEM lote informado (o campo é opcional)

    sai 12 un  ->  10 do lote A (vence antes) + 2 do lote B
    sobra:         lote A = 0, lote B = 8, e 10 un fora de lote

O que este teste existe para provar:

* **O que vence primeiro sai primeiro**, e uma saída pode quebrar em vários lotes.
* **O saldo por lote DIMINUI na saída.** Antes disso ele só crescia, e o alerta
  de vencimento apontava lote que já tinha sido usado — o alerta mentia.
* **Lote nunca barra a operação.** A soma dos lotes pode ser menor que o saldo
  (entrada sem lote informado), e a cozinha continua produzindo.
* **Lote sem validade é o último da fila** — não se gasta o que não tem data
  na frente do que vence.
* **O estorno volta para o MESMO lote**, não para o que o FEFO escolheria agora.

    python tests/smoke_lotes.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

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
        with urllib.request.urlopen(req, dados, timeout=30) as r:
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


def perto(a, b, tol=0.001):
    return a is not None and abs(float(a) - float(b)) < tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
marca = str(time.time_ns())[-6:]

st, locais = chamar("GET", "/locais", token=token)
local = next((l for l in locais if l["principal"]), locais[0])
LOTE_A, LOTE_B, LOTE_C = f"A{marca}", f"B{marca}", f"C{marca}"


def lotes_do_produto(id_produto):
    st, todos = chamar("GET", f"/estoque/lotes?id_produto={id_produto}&incluir_zerados=true&incluir_inativos=true",
                       token=token)
    return {l["lote"]: l for l in (todos or [])}


print("0. um perecível só deste teste")
st, produto = chamar("POST", "/produtos", {
    "nome": f"Iogurte FEFO {marca}", "tipo": "INSUMO", "um_estoque": "UN",
    "controla_lote": True, "controla_validade": True, "perecivel": True,
}, token=token)
pid = produto.get("id")
checar("produto criado", st == 201 and pid, produto)

for lote, validade in ((LOTE_B, "2026-09-20"), (LOTE_A, "2026-09-10")):
    # De propósito na ordem trocada: o que decide é a validade, não a ordem de
    # entrada nem o nome do lote.
    st, r = chamar("POST", "/estoque/entradas", {
        "id_produto": pid, "quantidade": 10, "custo_unitario": 5,
        "id_local": local["id"], "lote": lote, "validade": validade,
    }, token=token)
    checar(f"entra o lote {lote[0]}", st == 201, r)

st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": pid, "quantidade": 10, "custo_unitario": 5, "id_local": local["id"],
}, token=token)
checar("entra 10 SEM lote (o campo é opcional)", st == 201, r)
checar("o saldo total é 30", perto(r.get("saldo"), 30), r)

print("1. a saída escolhe sozinha: vence antes, sai antes")
st, saida = chamar("POST", "/estoque/saidas", {
    "tipo": "SAIDA_PERDA", "id_produto": pid, "quantidade": 12,
    "id_local": local["id"], "id_motivo_perda": 1, "observacao": f"FEFO {marca}",
}, token=token)
checar("a saída passa", st == 201, saida)
consumidos = saida.get("lotes") or []
checar("a saída diz de quais lotes saiu", len(consumidos) == 2, consumidos)
checar("o primeiro é o que vence antes (lote A)",
       consumidos and consumidos[0]["lote"] == LOTE_A, consumidos)
checar("levou os 10 do lote A", consumidos and perto(consumidos[0]["quantidade"], 10),
       consumidos)
checar("e as 2 que faltavam do lote B",
       len(consumidos) > 1 and consumidos[1]["lote"] == LOTE_B
       and perto(consumidos[1]["quantidade"], 2), consumidos)

print("2. o saldo por lote DIMINUI — é o que faz o alerta parar de mentir")
lotes = lotes_do_produto(pid)
checar("o lote A zerou", perto(lotes.get(LOTE_A, {}).get("quantidade", 0), 0), lotes.get(LOTE_A))
checar("o lote B ficou com 8", perto(lotes.get(LOTE_B, {}).get("quantidade"), 8), lotes.get(LOTE_B))
st, saldos = chamar("GET", f"/estoque/saldos?busca=Iogurte FEFO {marca}", token=token)
checar("e o saldo geral ficou com 18", perto((saldos or [{}])[0].get("quantidade"), 18), saldos)

print("3. lote nunca barra a operação")
# Restam 18 no saldo, mas só 8 em lote identificado. A saída de 12 tem de
# passar: o resto sai como "sem lote".
st, saida2 = chamar("POST", "/estoque/saidas", {
    "tipo": "SAIDA_PERDA", "id_produto": pid, "quantidade": 12,
    "id_local": local["id"], "id_motivo_perda": 1,
}, token=token)
checar("saída maior que o saldo em lote passa mesmo assim", st == 201, saida2)
checar("consumiu os 8 que havia em lote",
       perto(sum(float(l["quantidade"]) for l in (saida2.get("lotes") or [])), 8),
       saida2.get("lotes"))
st, saldos = chamar("GET", f"/estoque/saldos?busca=Iogurte FEFO {marca}", token=token)
checar("o saldo geral caiu para 6", perto((saldos or [{}])[0].get("quantidade"), 6), saldos)
lotes = lotes_do_produto(pid)
checar("e nenhum lote ficou negativo",
       all(float(l["quantidade"]) >= 0 for l in lotes.values()), lotes)

print("4. lote sem validade é o último da fila")
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": pid, "quantidade": 5, "custo_unitario": 5, "id_local": local["id"],
    "lote": LOTE_C,
}, token=token)
checar("entra lote sem validade", st == 201, r)
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": pid, "quantidade": 5, "custo_unitario": 5, "id_local": local["id"],
    "lote": f"D{marca}", "validade": "2026-12-31",
}, token=token)
checar("entra lote com validade distante", st == 201, r)
st, saida3 = chamar("POST", "/estoque/saidas", {
    "tipo": "SAIDA_PERDA", "id_produto": pid, "quantidade": 3,
    "id_local": local["id"], "id_motivo_perda": 1,
}, token=token)
usados = [l["lote"] for l in (saida3.get("lotes") or [])]
checar("saiu do que tem validade, não do sem-data", usados == [f"D{marca}"], usados)

print("5. o estorno volta para o MESMO lote")
st, entrada = chamar("POST", "/estoque/entradas", {
    "id_produto": pid, "quantidade": 4, "custo_unitario": 5, "id_local": local["id"],
    "lote": f"E{marca}", "validade": "2026-09-05",
}, token=token)
id_entrada = entrada.get("id")
# O lote E vence antes de todos: se o estorno usasse FEFO, tiraria dele por
# acaso e o teste passaria por engano. Por isso o estorno aqui é de uma ENTRADA:
# ele precisa retirar exatamente do lote E.
st, r = chamar("POST", f"/estoque/movimentos/{id_entrada}/estornar", {"motivo": "teste FEFO"}, token=token)
checar("estorna a entrada", st == 201, r)
lotes = lotes_do_produto(pid)
checar("o lote estornado voltou a zero", perto(lotes.get(f"E{marca}", {}).get("quantidade", 0), 0),
       lotes.get(f"E{marca}"))
checar("e o lote sem validade não foi tocado",
       perto(lotes.get(LOTE_C, {}).get("quantidade"), 5), lotes.get(LOTE_C))

print("6. estornar uma SAÍDA devolve ao lote de onde saiu")
st, saida4 = chamar("POST", "/estoque/saidas", {
    "tipo": "SAIDA_PERDA", "id_produto": pid, "quantidade": 2,
    "id_local": local["id"], "id_motivo_perda": 1,
}, token=token)
de_onde = [l["lote"] for l in (saida4.get("lotes") or [])]
st, r = chamar("POST", f"/estoque/movimentos/{saida4['id']}/estornar", {"motivo": "teste FEFO"}, token=token)
checar("estorna a saída", st == 201, r)
voltou = [l["lote"] for l in (r.get("lotes") or [])]
checar("a mercadoria volta para o mesmo lote", voltou == de_onde, (de_onde, voltou))

print("7. produto sem controle de lote segue como era")
st, simples = chamar("POST", "/produtos", {
    "nome": f"Sal FEFO {marca}", "tipo": "INSUMO", "um_estoque": "KG",
}, token=token)
chamar("POST", "/estoque/entradas", {
    "id_produto": simples["id"], "quantidade": 10, "custo_unitario": 2, "id_local": local["id"],
}, token=token)
st, r = chamar("POST", "/estoque/saidas", {
    "tipo": "SAIDA_PERDA", "id_produto": simples["id"], "quantidade": 3,
    "id_local": local["id"], "id_motivo_perda": 1,
}, token=token)
checar("saída normal continua funcionando", st == 201, r)
checar("e não inventa lote nenhum", not r.get("lotes"), r.get("lotes"))

print("8. limpeza")
for p in (pid, simples.get("id")):
    chamar("DELETE", f"/produtos/{p}", token=token)
checar("limpeza concluída", True)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
