"""Conferência do caixa e taxas por forma de pagamento (migração 161).

O que este arquivo cobra:

1. o esperado do dia é dinheiro recebido − troco, das finalizadoras, e a venda cancelada fica fora
2. venda sem forma de pagamento é contada (esperado incompleto)
3. gravar o contado dá a diferença (sobra positiva); corrigir troca, não duplica
4. dia futuro e contado negativo são recusados; quem não tem `vendas.caixa` recebe 403
5. as taxas por forma: gravar, ler, apagar com nulo, a taxa média real pelo peso das formas
6. o painel de vendas estima o custo das taxas
7. o relatório "Conferência do caixa" responde

⚠️ **Mede diferenças no dia de hoje** (há venda real e de outras suítes) e devolve as taxas e o
contado de hoje como estavam.

    python tests/smoke_caixa.py      (API de pé na 9200)
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Unidade", "1")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=120) as r:
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


def igual(a, b):
    return a is not None and abs(float(a) - float(b)) < 0.005


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
marca = str(time.time_ns() // 1000)[-8:]
hoje = date.today().isoformat()
criadas: list[int] = []

_s, taxas_antes = chamar("GET", "/caixa/taxas", token=token)
_s, caixa_antes = chamar("GET", f"/caixa/conferencia?inicio={hoje}&fim={hoje}", token=token)
dia_antes = next((d for d in caixa_antes["dias"] if d["data"] == hoje), None)


def _devolver():
    try:
        chamar("PUT", "/caixa/taxas", {"itens": [{"grupo": l["grupo"], "taxa_pct": l["taxa_pct"]}
                                                 for l in taxas_antes["linhas"]]}, token=token)
        if dia_antes and dia_antes["contado"] is not None:
            chamar("PUT", f"/caixa/conferencia/{hoje}",
                   {"contado": dia_antes["contado"], "observacao": dia_antes["observacao"]}, token=token)
        for i in criadas:
            chamar("DELETE", f"/vendas/{i}", token=token)
    except Exception:
        pass


atexit.register(_devolver)


def dia():
    _s, c = chamar("GET", f"/caixa/conferencia?inicio={hoje}&fim={hoje}", token=token)
    return next((d for d in c["dias"] if d["data"] == hoje), None) or \
        {"recebido": 0, "troco": 0, "esperado": 0, "sem_forma": 0, "contado": None}


def lancar(documento, total, pagamentos, cancelada=False):
    chamar("POST", "/vendas/importar", {"vendas": [{
        "data": hoje, "hora": "11:00:00", "documento": documento, "origem": "TESTE_CAIXA",
        "cancelada": cancelada, "pagamentos": pagamentos,
        "itens": [{"descricao": f"Item caixa {marca}", "quantidade": 1, "valor_unitario": total}]}]},
        token=token)
    _s, l = chamar("GET", f"/vendas?busca={documento}&limite=5", token=token)
    lista = l["itens"] if isinstance(l, dict) and "itens" in l else (l or [])
    i = next((v["id"] for v in lista if v.get("documento") == documento), None)
    if i:
        criadas.append(i)


print("1. o esperado")
s, c = chamar("GET", "/caixa/conferencia", token=token)
checar("sem datas, responde os últimos 14 dias", s == 200 and "totais" in c, (s, c))
antes = dia()
lancar(f"CX{marca}A", 40, [{"grupo": "DINHEIRO", "valor": 50}, {"grupo": "TROCO", "valor": 10}])
lancar(f"CX{marca}B", 30, [{"grupo": "CREDITO", "valor": 30}])
lancar(f"CX{marca}C", 70, [{"grupo": "DINHEIRO", "valor": 70}], cancelada=True)
lancar(f"CX{marca}D", 12, [])
depois = dia()
checar("recebido andou 50 e troco 10 (o crédito não conta na gaveta)",
       igual(depois["recebido"] - antes["recebido"], 50) and igual(depois["troco"] - antes["troco"], 10),
       (antes, depois))
checar("o esperado andou 40, e a venda cancelada ficou fora",
       igual(depois["esperado"] - antes["esperado"], 40), (antes["esperado"], depois["esperado"]))
checar("a venda sem forma conta como esperado incompleto", depois["sem_forma"] - antes["sem_forma"] == 1,
       (antes["sem_forma"], depois["sem_forma"]))

print("2. contar")
contado = round(depois["esperado"] + 5, 2)
s, r = chamar("PUT", f"/caixa/conferencia/{hoje}", {"contado": contado, "observacao": f"teste {marca}"},
              token=token)
checar("gravar o contado", s == 200, (s, r))
d = dia()
checar("sobrou 5: diferença positiva", igual(d["diferenca"], 5) and d["conferido_por"], d)
s, r = chamar("PUT", f"/caixa/conferencia/{hoje}", {"contado": depois["esperado"]}, token=token)
d = dia()
checar("corrigir troca o contado e zera a diferença", igual(d["diferenca"], 0) and d["observacao"] is None, d)
amanha = (date.today() + timedelta(days=1)).isoformat()
s, _ = chamar("PUT", f"/caixa/conferencia/{amanha}", {"contado": 1}, token=token)
checar("dia que não chegou: 422", s == 422, s)
s, _ = chamar("PUT", f"/caixa/conferencia/{hoje}", {"contado": -1}, token=token)
checar("contado negativo: 422", s == 422, s)

_s, papeis = chamar("GET", "/papeis", token=token)
cozinha = next(p for p in papeis if p["nome"] == "Cozinha")
_s, unidades = chamar("GET", "/unidades", token=token)
matriz = next(u["id"] for u in unidades if u.get("matriz"))
email = f"caixa{marca}@teste.botane"
chamar("POST", "/usuarios", {"nome": f"Caixa {marca}", "email": email, "senha": "Teste#12345",
                             "papeis": [{"id_papel": cozinha["id"], "id_unidade": matriz}]}, token=token)
_s, lg = chamar("POST", "/auth/login", {"email": email, "senha": "Teste#12345"})
tk = (lg or {}).get("access_token")
s, _ = chamar("GET", "/caixa/conferencia", token=tk)
checar("a cozinha não confere o caixa: 403", s == 403, s)
s, _ = chamar("PUT", "/caixa/taxas", {"itens": [{"grupo": "PIX", "taxa_pct": 1}]}, token=tk)
checar("nem muda as taxas: 403", s == 403, s)

print("3. taxas")
s, r = chamar("PUT", "/caixa/taxas", {"itens": [{"grupo": "CREDITO", "taxa_pct": 3},
                                                {"grupo": "DEBITO", "taxa_pct": 1.5},
                                                {"grupo": "PIX", "taxa_pct": 0},
                                                {"grupo": "DINHEIRO", "taxa_pct": 0},
                                                {"grupo": "VALE", "taxa_pct": None}]}, token=token)
checar("gravar as taxas", s == 200, (s, r))
taxas = {l["grupo"]: l["taxa_pct"] for l in r["linhas"]}
checar("crédito 3, débito 1,5, Pix 0 e vale sem taxa (nulo, não zero)",
       igual(taxas["CREDITO"], 3) and igual(taxas["DEBITO"], 1.5) and igual(taxas["PIX"], 0)
       and taxas["VALE"] is None, taxas)
checar("a taxa média real existe e fica entre 0 e 3%",
       r["taxa_media_real"] is not None and 0 <= r["taxa_media_real"] <= 3, r.get("taxa_media_real"))
s, _ = chamar("PUT", "/caixa/taxas", {"itens": [{"grupo": "CREDITO", "taxa_pct": 120}]}, token=token)
checar("taxa de 100% ou mais: 422", s == 422, s)

_s, p = chamar("GET", f"/vendas/painel?inicio={hoje}&fim={hoje}", token=token)
q = p.get("por_pagamento") or {}
credito = next((l for l in q.get("linhas", []) if l["grupo"] == "CREDITO"), None)
checar("o painel estima o custo das taxas", q.get("custo_taxas") is not None and credito
       and igual(credito["taxa_pct"], 3) and igual(credito["custo_taxa"], round(credito["valor"] * 0.03, 2)),
       (q.get("custo_taxas"), credito))

print("4. relatório")
s, rel = chamar("GET", f"/exportar/caixa/dados?inicio={hoje}&fim={hoje}", token=token)
checar("o relatório do caixa responde", s == 200, (s, rel))
texto = json.dumps(rel, ensure_ascii=False, default=str)
checar("com esperado, contado e diferença", all(c in texto for c in ("Esperado na gaveta", "Contado", "Diferença")),
       texto[:300])

print(f"\n{ok} passaram, {len(falhas)} falharam")
if falhas:
    for x in falhas:
        print("  -", x)
    sys.exit(1)
