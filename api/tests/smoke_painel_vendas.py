"""Teste de fumaça do painel de vendas (`GET /vendas/painel`) e do relatório dele.

🔑 Pedido do dono (21/10/2026): o estudo das vendas por dia, semana, mês ou
período — totais, comparação, evolução, dia da semana, hora, grupos e os mais
vendidos — e o mesmo recorte em arquivo.

O que este arquivo cobra:

1. a conta do cabeçalho: cupons, receita LÍQUIDA (itens − desconto), ticket e
   itens; cancelado e consumo interno fora, os cancelados contados à parte
2. a comparação: um dia contra o mesmo dia da semana anterior; um período contra
   o de mesmo tamanho logo antes
3. a soma da evolução bate com o total do cabeçalho (o painel não discorda de si)
4. a hora: cupom digitado sem hora vai para `sem_hora`, nunca para a meia-noite
5. os mais vendidos nas duas ordens, e a participação
6. o recorte por categoria: receita BRUTA dos itens, desconto nulo
7. a rota vem antes de `/{id_venda}` (não 422), recusa período invertido e quem
   não vê dinheiro
8. o relatório `vendas` sai da MESMA conta

⚠️ **A suíte trabalha num trecho do calendário SEM venda nenhuma** (anos 80,
escolhido pela marca) e confere que ele está vazio antes de lançar: a base tem
vendas reais do PDV, e qualquer total sobre ela seria um número que muda sozinho.

    python tests/smoke_painel_vendas.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, "tests")
sys.path.insert(0, ".")
from comum import garantir_categorias, garantir_ciclo_de_consumo, garantir_cozinha  # noqa: E402

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
            return r.status, (bruto.decode("utf-8-sig") if cru else json.loads(bruto or b"null"))
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


def perto(a, b):
    return a is not None and abs(float(a) - float(b)) < 0.006


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
assert st == 200, r
token = r["access_token"]
marca = str(time.time_ns() // 100)[-6:]

# Uma SEGUNDA-feira nos anos 80, escolhida pela marca: cada rodada cai noutra semana.
d1 = date(1980, 1, 7) + timedelta(weeks=int(marca) % 500)
d2 = d1 + timedelta(days=1)


def painel(q):
    return chamar("GET", f"/vendas/painel?{q}", token=token)


print("0. o trecho do calendario esta vazio")
st, vazio = painel(f"inicio={d1 - timedelta(days=14)}&fim={d2 + timedelta(days=7)}")
checar("a rota responde (e nao foi engolida por /{id_venda})", st == 200, (st, vazio))
checar("o trecho escolhido nao tem venda nenhuma", (vazio or {}).get("totais", {}).get("cupons") == 0,
       (vazio or {}).get("totais"))

print("1. os produtos e as vendas")
cats = garantir_categorias(chamar, token, 2)
cat_a, cat_b = cats[0]["id"], cats[1]["id"]
ids = []
for i, cat in enumerate((cat_a, cat_b)):
    st, p = chamar("POST", "/produtos", {
        "codigo": f"PV-{i}-{marca}", "nome": f"Prato painel {i} {marca}", "tipo": "PRODUZIDO",
        "um_estoque": "UN", "controla_estoque": False, "status": "ATIVO", "id_categoria": cat,
    }, token=token)
    checar(f"prato {i} criado", st == 201, (st, p))
    ids.append(p.get("id"))
p1, p2 = ids


def cupom(doc, dia, itens, **extra):
    return {"data": dia, "documento": f"PV-{doc}-{marca}", "origem": "MANUAL", **extra,
            "itens": [{"id_produto": pid, "quantidade": q, "valor_unitario": v} for pid, q, v in itens]}


st, r = chamar("POST", "/vendas/importar", {"vendas": [
    # d1: dois cupons com hora, um com desconto de 3
    cupom("A", d1, [(p1, 2, 10), (p2, 1, 5)], hora="12:10:00", desconto=3),
    cupom("B", d1, [(p1, 1, 10)], hora="13:05:00"),
    # d2: um cupom DIGITADO, sem hora
    cupom("C", d2, [(p2, 4, 5)]),
    # fora das somas: cancelado e consumo interno
    cupom("X", d1, [(p1, 1, 10)], hora="12:30:00", cancelada=True),
    # o periodo anterior de mesmo tamanho (d1-2, d1-1) e o mesmo dia da semana anterior
    cupom("E", d1 - timedelta(days=2), [(p1, 1, 10)], hora="10:00:00"),
    cupom("F", d1 - timedelta(days=7), [(p2, 2, 5)], hora="10:00:00"),
]}, token=token)
checar("as vendas entraram", st in (200, 201) and not (r or {}).get("erros"), (st, r))
# Consumo interno pede a pessoa e um periodo de consumo aberto.
# ⚠️ **Uma pessoa PROPRIA da suite, nunca "a primeira da lista"** (21/10/2026): a
# primeira era o fornecedor que a bateria do navegador abre, e a ficha dele ganhou
# uma segunda tabela (o consumo no ciclo) — a checagem "dez linhas por pagina"
# passou a contar as duas e acusou a ficha.
garantir_ciclo_de_consumo(chamar, token)
NOME_PESSOA = "Smoke painel de vendas"
st, achadas = chamar("GET", f"/fornecedores?incluir_inativos=true&busca={NOME_PESSOA}", token=token)
pessoa = next((x["id"] for x in (achadas or []) if x.get("nome", "").lower() == NOME_PESSOA.lower()),
              None)
if pessoa is None:
    st, nova = chamar("POST", "/fornecedores", {"nome": NOME_PESSOA, "fornecedor": False}, token=token)
    pessoa = (nova or {}).get("id")
checar("a pessoa da suite existe", pessoa is not None, achadas)
st, r = chamar("POST", "/vendas/importar", {"vendas": [
    cupom("Y", d1, [(p1, 5, 10)], hora="14:00:00", consumo_interno=True, id_pessoa=pessoa)]},
    token=token)
checar("e o consumo interno tambem", st in (200, 201), (st, r))

print("2. o cabecalho do periodo (d1 a d2)")
st, pv = painel(f"inicio={d1}&fim={d2}")
t = pv.get("totais", {})
checar("3 cupons (cancelado e consumo interno fora)", t.get("cupons") == 3, t)
checar("receita bruta 55", perto(t.get("bruta"), 55), t)
checar("desconto 3", perto(t.get("desconto"), 3), t)
checar("receita LIQUIDA 52", perto(t.get("receita"), 52), t)
checar("ticket 52/3", perto(t.get("ticket_medio"), 52 / 3), t)
checar("8 itens e 2 dias", t.get("itens") == 8 and t.get("dias") == 2, t)
checar("media por dia 26", perto(t.get("media_por_dia"), 26), t)
checar("o cancelado aparece contado, com o valor",
       pv.get("canceladas") == {"cupons": 1, "valor": 10.0}, pv.get("canceladas"))

c = pv.get("comparacao", {})
checar("compara com os 2 dias anteriores",
       c.get("inicio") == str(d1 - timedelta(days=2)) and c.get("fim") == str(d1 - timedelta(days=1)), c)
checar("e a variacao e +420%", c.get("pct_receita") == 420.0 and c.get("cupons") == 1, c)

print("3. a evolucao bate com o cabecalho")
serie = pv.get("serie", [])
checar("dois pontos, um por dia", [s["periodo"] for s in serie] == [str(d1), str(d2)], serie)
checar("d1 liquido 32 e d2 20", perto(serie[0]["receita"], 32) and perto(serie[1]["receita"], 20), serie)
checar("a soma dos pontos e o total", perto(sum(s["receita"] for s in serie), t.get("receita")), serie)
st, ps = painel(f"inicio={d1}&fim={d2}&agrupar=semana")
checar("por semana, um ponto na segunda", [s["periodo"] for s in ps.get("serie", [])] == [str(d1)],
       ps.get("serie"))

print("4. dia da semana e hora")
dows = {d["dia_semana"]: d for d in pv.get("por_dia_semana", [])}
checar("segunda e terca, um dia cada", set(dows) == {1, 2} and dows[1]["dias"] == 1, dows)
# ⚠️ Sem recorte, dia da semana e hora também são LÍQUIDOS: a soma deles é o cabeçalho.
checar("segunda liquida 32, terca 20",
       perto(dows.get(1, {}).get("receita"), 32) and perto(dows.get(2, {}).get("receita"), 20), dows)
horas = {h["hora"]: h for h in pv.get("por_hora", [])}
checar("12h tem o cupom A (25 - 3 de desconto) e 13h o B (10)",
       perto(horas.get(12, {}).get("receita"), 22) and perto(horas.get(13, {}).get("receita"), 10), horas)
checar("horas + sem hora = o total",
       perto(sum(h["receita"] for h in horas.values()) + (pv.get("sem_hora") or {}).get("receita", 0),
             t.get("receita")), (horas, pv.get("sem_hora")))
checar("o cupom digitado vai para 'sem hora', nao para a meia-noite",
       0 not in horas and (pv.get("sem_hora") or {}).get("cupons") == 1, (horas, pv.get("sem_hora")))

print("5. os mais vendidos")
prods = pv.get("produtos", [])
checar("por faturado, o prato 1 primeiro (30 contra 25)",
       [x["id_produto"] for x in prods] == [p1, p2] and perto(prods[0]["receita"], 30), prods)
checar("participacao sobre a bruta: 30/55", prods and prods[0]["participacao_pct"] == 54.5, prods)
checar("preco medio 10", prods and perto(prods[0]["preco_medio"], 10), prods)
st, pq = painel(f"inicio={d1}&fim={d2}&ordem=quantidade")
checar("por quantidade, o prato 2 primeiro (5 contra 3)",
       [x["id_produto"] for x in pq.get("produtos", [])] == [p2, p1], pq.get("produtos"))
st, pl = painel(f"inicio={d1}&fim={d2}&limite=1")
checar("o limite corta e o total diz quantos ha", len(pl.get("produtos", [])) == 1
       and pl.get("produtos_total") == 2, (pl.get("produtos"), pl.get("produtos_total")))

print("6. o recorte por categoria")
st, pc = painel(f"inicio={d1}&fim={d2}&categorias={cat_b}")
tc = pc.get("totais", {})
checar("so os cupons com item da categoria (A e C)", tc.get("cupons") == 2, tc)
checar("receita BRUTA dos itens: 25", perto(tc.get("receita"), 25) and pc.get("bruta") is True, tc)
checar("desconto nulo com recorte", tc.get("desconto") is None, tc)
checar("e sem a contagem de cancelados", pc.get("canceladas") is None, pc.get("canceladas"))
cats_resp = {g["id"]: g for g in pv.get("por_categoria", [])}
checar("a quebra por categoria soma a bruta",
       perto(cats_resp.get(cat_a, {}).get("receita"), 30) and perto(cats_resp.get(cat_b, {}).get("receita"), 25),
       cats_resp)

print("7. um dia so")
st, pd = painel(f"inicio={d1}&fim={d1}")
cd = pd.get("comparacao", {})
checar("um dia compara com o mesmo dia da semana anterior",
       cd.get("inicio") == str(d1 - timedelta(days=7)) and cd.get("rotulo", "").startswith("o mesmo dia"), cd)
checar("32 contra 10: +220%", cd.get("pct_receita") == 220.0, cd)

print("8. bordas e permissao")
st, r = painel(f"inicio={d2}&fim={d1}")
checar("periodo invertido e recusado (400)", st == 400, (st, r))
st, r = painel("inicio=2020-01-01&fim=2026-01-01")
checar("mais de dois anos e recusado (400)", st == 400, (st, r))
st, r = painel("")
checar("sem datas, abre num dia so (o da ultima venda)", st == 200 and r.get("inicio") == r.get("fim"), r)
tk = garantir_cozinha(chamar, token)
st, r = chamar("GET", f"/vendas/painel?inicio={d1}&fim={d2}", token=tk)
checar("quem nao ve dinheiro recebe 403", st == 403, (st, r))

print("9. o relatorio sai da mesma conta")
st, cat = chamar("GET", "/exportar/catalogo", token=token)
rel = next((x for x in (cat or []) if x["chave"] == "vendas"), None)
checar("o relatorio esta no catalogo, com os filtros do painel",
       rel and [f["nome"] for f in rel["filtros"]] == ["periodo", "agrupar", "categorias", "setores", "produtos"],
       rel)
st, csv = chamar("GET", f"/exportar/vendas.csv?inicio={d1}&fim={d2}&agrupar=dia", token=token, cru=True)
checar("a planilha sai", st == 200 and isinstance(csv, str), (st, str(csv)[:200]))
csv = csv if isinstance(csv, str) else ""
checar("com a receita liquida do painel", "Receita líquida;52" in csv, csv[:600])
checar("com os produtos e os quadros atras",
       f"PRATO PAINEL 0 {marca}" in csv.upper() and "Por hora do cupom" in csv and "Por dia da semana" in csv,
       csv[:900])
st, csv_c = chamar("GET", f"/exportar/vendas.csv?inicio={d1}&fim={d2}&categorias={cat_b}",
                   token=token, cru=True)
checar("com recorte, o arquivo diz que a receita e bruta",
       isinstance(csv_c, str) and "receita bruta dos itens" in csv_c, str(csv_c)[:300])
st, pdf = chamar("GET", f"/exportar/vendas/previa?inicio={d1}&fim={d2}", token=token)
checar("a previa conta as linhas", st == 200, (st, pdf))

print("10. limpeza")
# O consumo interno da suite sai do ciclo aberto: cancelado, ele nao pesa na conta da pessoa.
st, docs_y = chamar("GET", f"/vendas?busca=PV-Y-{marca}", token=token)
for v in docs_y or []:
    if v.get("documento") == f"PV-Y-{marca}":
        chamar("DELETE", f"/vendas/{v['id']}", token=token)
st, docs_y = chamar("GET", f"/vendas?busca=PV-Y-{marca}", token=token)
checar("o consumo interno da suite foi cancelado",
       all(v.get("cancelada") for v in (docs_y or []) if v.get("documento") == f"PV-Y-{marca}"),
       docs_y)

print(f"\n{ok} passaram, {len(falhas)} falharam")
sys.exit(1 if falhas else 0)
