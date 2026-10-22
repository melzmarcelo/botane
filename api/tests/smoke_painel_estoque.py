"""Teste de fumaça do painel de estoque (22/10/2026, pedido do dono).

O cenário, conferido na mão (produto A, mínimo 10, tudo hoje):

    entrada 6 UN a 2,00            → saldo 6
    consumo interno 3              → saldo 3
    perda 1 (motivo Quebra)        → saldo 2      perda R$ 2,00
    consumo dos 30 dias = 3 + 1 = 4 → 0,1333/dia → acaba em 2 ÷ 0,1333 = 15 dias
    faltam 10 − 2 = 8 → repor 8 × 2,00 = R$ 16,00
    estornar a perda               → perda R$ 0 (líquida), saldo 3

Prova também a regra que mais importa na tela: **o número do cartão é o tamanho da lista**
para onde ele leva (negativos por prateleira, abaixo do mínimo por produto), e o alerta da
tela inicial conta o mesmo.

    python tests/smoke_painel_estoque.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
from comum import garantir_locais  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None, total=False):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=60) as r:
            corpo_r = json.loads(r.read() or b"null")
            if total:
                return r.status, corpo_r, int(r.headers.get("X-Total") or -1)
            return r.status, corpo_r
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            corpo_r = json.loads(bruto or b"null")
        except json.JSONDecodeError:
            corpo_r = {"detail": bruto.decode(errors="replace")}
        return (e.code, corpo_r, None) if total else (e.code, corpo_r)


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


def perto(a, b, tol=0.01):
    return a is not None and abs(float(a) - float(b)) < tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
marca = str(time.time_ns() // 100)[-6:]
locais = garantir_locais(chamar, token, 1)
principal = next((l for l in locais if l["principal"]), locais[0])

print("1. o cenário")
st, r = chamar("POST", "/produtos", {
    "codigo": f"PE-A-{marca}", "nome": f"Painel estoque A {marca}", "tipo": "INSUMO",
    "um_estoque": "UN", "controla_estoque": True, "status": "ATIVO", "estoque_minimo": 10,
}, token=token)
prod_a = r.get("id")
checar("produto A criado, com mínimo 10", st == 201, (st, r))

st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": prod_a, "quantidade": 6, "custo_unitario": 2,
    "id_local": principal["id"], "documento": f"PE-{marca}"}, token=token)
checar("entrada de 6 a 2,00", st == 201, (st, r))
st, r = chamar("POST", "/estoque/saidas", {
    "id_produto": prod_a, "quantidade": 3, "tipo": "SAIDA_CONSUMO_INTERNO",
    "id_local": principal["id"]}, token=token)
checar("consumo interno de 3", st == 201, (st, r))

st, motivos = chamar("GET", "/estoque/motivos-perda", token=token)
quebra = next((m for m in motivos or [] if m["nome"].lower() == "quebra"), (motivos or [{}])[0])
st, r = chamar("POST", "/estoque/saidas", {
    "id_produto": prod_a, "quantidade": 1, "tipo": "SAIDA_PERDA",
    "id_motivo_perda": quebra.get("id"), "observacao": f"caiu no chão {marca}",
    "id_local": principal["id"]}, token=token)
checar("perda de 1, com motivo", st == 201, (st, r))
id_perda = r.get("id_movimento") or r.get("id")

print("\n2. o número do cartão é o tamanho da lista")
st, g = chamar("GET", "/estoque/painel?limite=100", token=token)
checar("o painel responde", st == 200, (st, g))
st, _, total_abaixo = chamar("GET", "/estoque/saldos-agrupados?abaixo_do_minimo=true&limite=1",
                             token=token, total=True)
checar("abaixo do mínimo: cartão == lista por produto",
       g["abaixo_do_minimo"]["produtos"] == total_abaixo,
       (g["abaixo_do_minimo"]["produtos"], total_abaixo))
st, _, total_neg = chamar("GET", "/estoque/saldos?negativos=true&limite=1", token=token,
                          total=True)
checar("negativos: cartão == lista por prateleira",
       g["negativos"]["prateleiras"] == total_neg, (g["negativos"]["prateleiras"], total_neg))
st, alertas = chamar("GET", "/alertas", token=token)
por_chave = {a["chave"]: a for a in alertas or []}
checar("o alerta de mínimo conta o mesmo, e leva à lista filtrada",
       por_chave.get("estoque.minimo", {}).get("quantidade") == total_abaixo
       and "situacao=minimo" in por_chave.get("estoque.minimo", {}).get("href", ""),
       por_chave.get("estoque.minimo"))
st, lista_a = chamar("GET", f"/estoque/saldos-agrupados?abaixo_do_minimo=true&id_produto={prod_a}",
                     token=token)
checar("A está na lista dos abaixo do mínimo", len(lista_a or []) == 1, lista_a)

linha = next((a for a in g["abaixo_do_minimo"]["lista"] if a["id_produto"] == prod_a), None)
checar("e na lista do painel", linha is not None)
if linha:
    checar("faltam 8", perto(linha["faltam"], 8), linha)
    checar("consumo por dia = 4 ÷ 30", perto(linha["consumo_dia"], 4 / 30, 0.001), linha)
    checar("acaba em 15 dias", perto(linha["cobertura_dias"], 15, 0.11), linha)
    checar("repor custa R$ 16,00", perto(linha["valor_repor"], 16), linha)
    checar("e é de comprar (insumo)", linha["acao"] == "comprar", linha)

print("\n3. o produto")
st, d = chamar("GET", f"/estoque/painel/produto/{prod_a}", token=token)
checar("o detalhe responde", st == 200, (st, d))
ind = d.get("indicadores", {})
checar("saldo de hoje 2", perto(d["atual"]["saldo"], 2), d.get("atual"))
checar("e abaixo do mínimo", d["atual"]["abaixo_do_minimo"] is True)
checar("o último ponto da série é o saldo de hoje", perto(d["serie"][-1]["saldo"], 2),
       d["serie"][-1])
checar("comprado 6", perto(ind.get("compras"), 6), ind)
checar("consumo 4 (consumo interno + perda)", perto(ind.get("consumo"), 4), ind)
checar("perdido 1, R$ 2,00", perto(ind.get("perda"), 1) and perto(ind.get("perda_valor"), 2),
       ind)
checar("por tipo traz a perda", any(t["tipo"] == "SAIDA_PERDA" and perto(t["quantidade"], 1)
                                    for t in d.get("por_tipo", [])), d.get("por_tipo"))
checar("as barras do período: entrou 6, saiu 4",
       perto(sum(s["entradas"] for s in d["serie"]), 6)
       and perto(sum(s["saidas"] for s in d["serie"]), 4), d["serie"][-2:])
st, _ = chamar("GET", "/estoque/painel/produto/999999999", token=token)
checar("produto que não existe é 404", st == 404, st)

print("\n4. as perdas")
st, p = chamar("GET", f"/estoque/painel/perdas?id_produto={prod_a}", token=token)
checar("o painel de perdas responde", st == 200, (st, p))
checar("R$ 2,00 em 1 registro", perto(p["totais"]["valor"], 2)
       and p["totais"]["ocorrencias"] == 1, p.get("totais"))
checar("pelo motivo escolhido", [m["nome"] for m in p["por_motivo"]] == [quebra.get("nome")],
       p.get("por_motivo"))
# Saiu R$ 8,00 (consumo interno 3 × 2,00 + perda 1 × 2,00): a perda é 25% disso.
checar("a perda é 25% do que saiu, em valor",
       perto(p["totais"]["pct_do_consumo"], 25, 0.2), p["totais"])
checar("e a observação aparece no registro",
       any(f"caiu no chão {marca}" in (x.get("observacao") or "") for x in p["recentes"]),
       p.get("recentes"))
st, p_outro = chamar("GET", f"/estoque/painel/perdas?id_produto={prod_a}&id_motivo=0",
                     token=token)
checar("o recorte 'sem motivo' não traz a perda com motivo",
       perto(p_outro["totais"]["valor"], 0), p_outro.get("totais"))

st, mov = chamar("GET", f"/estoque/movimentos?id_produto={prod_a}", token=token)
perda = next((m for m in mov or [] if m["tipo"] == "SAIDA_PERDA"), {})
st, r = chamar("POST", f"/estoque/movimentos/{perda.get('id')}/estornar",
               {"motivo": "lançada por engano"}, token=token)
checar("a perda é estornada", st in (200, 201), (st, r))
st, p = chamar("GET", f"/estoque/painel/perdas?id_produto={prod_a}", token=token)
# ⚠️ Líquida de estorno, como no CMV: perda desfeita não é perda.
checar("perda estornada não conta: R$ 0 e zero registro",
       perto(p["totais"]["valor"], 0) and p["totais"]["ocorrencias"] == 0, p.get("totais"))
checar("nem o produto aparece entre os que se perdem", p["produtos_total"] == 0, p["produtos"])
st, d = chamar("GET", f"/estoque/painel/produto/{prod_a}", token=token)
checar("no produto também: perdido 0 e saldo 3",
       perto(d["indicadores"]["perda"], 0) and perto(d["atual"]["saldo"], 3), d["indicadores"])
checar("e as barras descontam o estorno: saiu 3",
       perto(sum(s["saidas"] for s in d["serie"]), 3), d["serie"][-2:])

print("\n5. o negativo leva à prateleira")
st, r = chamar("POST", "/produtos", {
    "codigo": f"PE-B-{marca}", "nome": f"Painel estoque B {marca}", "tipo": "INSUMO",
    "um_estoque": "UN", "controla_estoque": True, "status": "ATIVO"}, token=token)
prod_b = r.get("id")
antes = g["negativos"]["prateleiras"]
st, r = chamar("POST", "/estoque/saidas", {
    "id_produto": prod_b, "quantidade": 2, "tipo": "SAIDA_CONSUMO_INTERNO",
    "id_local": principal["id"]}, token=token)
checar("saída sem saldo deixa B negativo", st == 201, (st, r))
st, g2 = chamar("GET", "/estoque/painel", token=token)
checar("o cartão ganha uma prateleira", g2["negativos"]["prateleiras"] == antes + 1,
       (antes, g2["negativos"]["prateleiras"]))
st, lista_b = chamar("GET", f"/estoque/saldos?negativos=true&id_produto={prod_b}", token=token)
checar("e B está na lista dos negativos", len(lista_b or []) == 1, lista_b)
st, lista_b2 = chamar("GET", f"/estoque/saldos-agrupados?negativos=true&id_produto={prod_b}",
                      token=token)
checar("também na visão por produto", len(lista_b2 or []) == 1, lista_b2)

print("\n6. o recorte")
st, _ = chamar("GET", "/estoque/painel/perdas?inicio=2026-10-10&fim=2026-10-01", token=token)
checar("período invertido é recusado", st == 400, st)
st, _ = chamar("GET", "/estoque/painel/perdas?inicio=2020-01-01&fim=2026-01-01", token=token)
checar("mais de dois anos é recusado", st == 400, st)
st, p = chamar("GET", "/estoque/painel/perdas?agrupar=semana&inicio=2026-09-01&fim=2026-09-30",
               token=token)
checar("por semana, a série cobre o mês em semanas que começam na segunda",
       st == 200 and p["serie"][0]["periodo"] == "2026-08-31", p.get("serie", [])[:1])

# Sai das listas da operação: o B negativo não pode virar trabalho para ninguém, e o A
# abaixo do mínimo também não. Desativar tira os dois das contagens (só ativos contam).
for pid in (prod_a, prod_b):
    if pid:
        chamar("DELETE", f"/produtos/{pid}", token=token)
st, g3 = chamar("GET", "/estoque/painel", token=token)
checar("desativados, saem do cartão de negativos",
       g3["negativos"]["prateleiras"] == antes, (antes, g3["negativos"]["prateleiras"]))

print()
print(f"{ok} passaram, {len(falhas)} falharam")
if falhas:
    for f in falhas:
        print("  -", f)
    sys.exit(1)
