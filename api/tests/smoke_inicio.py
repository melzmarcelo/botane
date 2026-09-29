"""A tela inicial nova (protótipo aprovado em 29/09/2026): o que `GET /inicio` passou a trazer.

- a META de food cost da loja (migração 102), que a régua marca;
- a comparação do dia com o MESMO dia da semana anterior;
- as etiquetas do dia (vencidas e vencendo hoje) e as pessoas das mesas de hoje.

    python tests/smoke_inicio.py        (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

BASE = "http://127.0.0.1:9200"
ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


_st, r = chamar("POST", "/auth/login", {"email": "admin@botane.com.br", "senha": "botane123"})
token = r["access_token"]
_st, par = chamar("GET", "/unidades/1/parametros", token=token)
antes = par.get("meta_food_cost_pct")

print("1. a meta de food cost é parâmetro da loja")
st, r = chamar("PUT", "/unidades/1/parametros", {"meta_food_cost_pct": 32.5}, token)
checar("grava a meta", st == 200, (st, r))
st, r = chamar("PUT", "/unidades/1/parametros", {"meta_food_cost_pct": 150}, token)
checar("meta acima de 100% é recusada", st == 422, st)
_st, p = chamar("GET", "/inicio", token=token)
checar("o Início traz a meta junto do dinheiro",
       (p.get("dinheiro") or {}).get("meta_food_cost_pct") == 32.5, p.get("dinheiro"))
st, r = chamar("PUT", "/unidades/1/parametros", {"meta_food_cost_pct": None}, token)
_st, p = chamar("GET", "/inicio", token=token)
checar("sem meta, vem nula (a régua fica sem marca)",
       st == 200 and (p.get("dinheiro") or {}).get("meta_food_cost_pct") is None, p.get("dinheiro"))

print("\n2. a comparação do dia e os blocos novos")
dia = p.get("dia")
if dia:
    c = dia.get("comparacao")
    checar("o dia traz a comparação (ou nulo, sem venda na semana anterior)",
           "comparacao" in dia and (c is None or {"data", "receita", "pct"} <= set(c)), c)
    if c:
        from datetime import date, timedelta
        checar("contra o MESMO dia da semana anterior",
               c["data"] == (date.fromisoformat(dia["data"]) - timedelta(days=7)).isoformat(), c)
else:
    checar("sem venda nenhuma, o dia vem nulo", dia is None)
etq = p.get("etiquetas")
checar("o Início traz as etiquetas do dia para quem imprime etiqueta",
       etq is not None and {"vencidas", "hoje"} <= set(etq), etq)
if p.get("reservas"):
    checar("e as pessoas das mesas de hoje", "pessoas_hoje" in p["reservas"], p["reservas"])
if p.get("pedidos"):
    checar("e os pedidos em aberto", "abertos" in p["pedidos"], p["pedidos"])

chamar("PUT", "/unidades/1/parametros", {"meta_food_cost_pct": antes}, token)
print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
