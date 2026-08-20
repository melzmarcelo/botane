"""Teste de fumaça dos relatórios do dono.

Dois relatórios, duas provas:

**CMV por setor / categoria.** O cenário monta dois setores com valores
diferentes e confere que cada um aparece com o seu, que a soma dos grupos
**fecha com o CMV total** do período (se não fechar, algum real sumiu no
caminho) e que produto sem setor aparece como "Sem setor" em vez de evaporar.

**Evolução de preço.** Compra o mesmo insumo três vezes, com preço subindo, e
confere que o relatório enxerga a alta, calcula o **impacto em reais** sobre o
volume comprado e diz de qual fornecedor veio o mais barato. A ordenação é por
impacto, não por percentual: item que subiu muito e se compra pouco não pode
passar na frente do que subiu pouco e entra toda semana.

    python tests/smoke_relatorios.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
from comum import garantir_local, garantir_setores  # noqa: E402
from datetime import date, timedelta

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
COZINHA = ("smoke.cozinha@botane.com.br", "smoke12345")

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
        with urllib.request.urlopen(req, dados, timeout=60) as r:
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


def perto(a, b, tol=0.02):
    return a is not None and abs(float(a) - float(b)) < tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
marca = str(time.time_ns())[-6:]

# O período começa hoje: o teste mede o DELTA que ele mesmo cria, porque o
# banco local já tem movimento de outras rodadas.
hoje = date.today()
periodo = f"?inicio={hoje}&fim={hoje}"

local = garantir_local(chamar, token)
# O relatório por grupo só prova o que promete com mais de um setor.
setores = garantir_setores(chamar, token, 2)
setor_a, setor_b = setores[0], setores[1] if len(setores) > 1 else setores[0]

print("0. dois setores, valores diferentes")
st, antes_grupo = chamar("GET", f"/cmv/por-grupo{periodo}&agrupar=setor", token=token)
checar("o relatório por setor responde", st == 200, antes_grupo)
base = {g["grupo"]: float(g["cmv"]) for g in (antes_grupo or [])}

produtos = {}
for rotulo, setor, custo in (("cozinha", setor_a, 10), ("bar", setor_b, 4)):
    st, p = chamar("POST", "/produtos", {
        "nome": f"Rel {rotulo} {marca}", "tipo": "INSUMO", "um_estoque": "KG",
        "id_setor": setor["id"],
    }, token=token)
    produtos[rotulo] = p.get("id")
    checar(f"produto de {rotulo} criado", st == 201, p)
    # Entra 10 e sai 6: o CMV do produto é 6 x custo.
    chamar("POST", "/estoque/entradas", {
        "id_produto": p["id"], "quantidade": 10, "custo_unitario": custo,
        "id_local": local["id"],
    }, token=token)
    chamar("POST", "/estoque/saidas", {
        "tipo": "SAIDA_PERDA", "id_produto": p["id"], "quantidade": 6,
        "id_local": local["id"], "id_motivo_perda": 1,
    }, token=token)

# Um produto sem setor nenhum: ele não pode sumir do relatório.
st, sem_setor = chamar("POST", "/produtos", {
    "nome": f"Rel sem setor {marca}", "tipo": "INSUMO", "um_estoque": "KG",
}, token=token)
chamar("POST", "/estoque/entradas", {
    "id_produto": sem_setor["id"], "quantidade": 5, "custo_unitario": 2,
    "id_local": local["id"],
}, token=token)
chamar("POST", "/estoque/saidas", {
    "tipo": "SAIDA_PERDA", "id_produto": sem_setor["id"], "quantidade": 5,
    "id_local": local["id"], "id_motivo_perda": 1,
}, token=token)

print("1. cada setor com o seu")
st, grupos = chamar("GET", f"/cmv/por-grupo{periodo}&agrupar=setor", token=token)
depois = {g["grupo"]: float(g["cmv"]) for g in grupos}
checar(f"o setor {setor_a['nome']} subiu 60,00 (6 x 10)",
       perto(depois.get(setor_a["nome"], 0) - base.get(setor_a["nome"], 0),
             60 if setor_a["id"] != setor_b["id"] else 84), depois)
if setor_a["id"] != setor_b["id"]:
    checar(f"o setor {setor_b['nome']} subiu 24,00 (6 x 4)",
           perto(depois.get(setor_b["nome"], 0) - base.get(setor_b["nome"], 0), 24), depois)
checar("produto sem setor aparece como 'Sem setor'",
       perto(depois.get("Sem setor", 0) - base.get("Sem setor", 0), 10), depois)

print("2. a soma dos grupos fecha com o CMV total")
st, apuracao = chamar("GET", f"/cmv/apuracao{periodo}", token=token)
soma = sum(float(g["cmv"]) for g in grupos)
checar("a apuração responde", st == 200, apuracao)
checar("a soma dos grupos é o CMV do período",
       perto(soma, apuracao.get("cmv_real"), 0.05), (soma, apuracao.get("cmv_real")))
checar("e as participações somam 100%",
       perto(sum(float(g["participacao_pct"]) for g in grupos), 100, 0.5),
       sum(float(g["participacao_pct"]) for g in grupos))

print("3. o mesmo por categoria")
st, cats = chamar("GET", f"/cmv/por-grupo{periodo}&agrupar=categoria", token=token)
checar("o relatório por categoria responde", st == 200, cats)
checar("e fecha com o mesmo total",
       perto(sum(float(g["cmv"]) for g in cats), apuracao.get("cmv_real"), 0.05),
       sum(float(g["cmv"]) for g in cats))
st, r = chamar("GET", f"/cmv/por-grupo{periodo}&agrupar=fornecedor", token=token)
checar("agrupamento inventado é recusado (422)", st == 422, st)

print("4. evolução de preço: o que subiu, e quanto custa")
st, fornecedores = chamar("GET", "/fornecedores", token=token)
caro, barato = fornecedores[0], fornecedores[1] if len(fornecedores) > 1 else fornecedores[0]
st, insumo = chamar("POST", "/produtos", {
    "nome": f"Rel azeite {marca}", "tipo": "INSUMO", "um_estoque": "UN",
}, token=token)
# Três compras do mesmo item, subindo: 10,00 -> 12,00 -> 15,00, 10 un cada.
for i, (preco, fornecedor) in enumerate(((10, barato), (12, caro), (15, caro))):
    st, nota = chamar("POST", "/notas", {
        "id_fornecedor": fornecedor["id"], "numero": f"R{marca}{i}",
        "data_emissao": str(hoje - timedelta(days=2 - i)),
        "id_local": local["id"],
        "itens": [{"id_produto": insumo["id"], "quantidade": 10, "valor_unitario": preco}],
    }, token=token)
    checar(f"nota {i + 1} de {preco},00 registrada", st == 200, nota)
    st, r = chamar("POST", f"/notas/{nota['id']}/lancar", {"id_local": local["id"]}, token=token)
    checar(f"nota {i + 1} lançada no estoque", st == 200, r)

st, precos = chamar("GET", f"/cmv/precos?inicio={hoje - timedelta(days=3)}&fim={hoje}",
                    token=token)
linha = next((x for x in precos if x["id_produto"] == insumo["id"]), None)
checar("o insumo aparece no relatório de preços", linha is not None,
       [x["produto"] for x in precos[:5]])
checar("três compras contadas", linha and linha["compras"] == 3, linha)
checar("primeiro preço 10,00", linha and perto(linha["primeiro"], 10), linha)
checar("último preço 15,00", linha and perto(linha["ultimo"], 15), linha)
checar("alta de 50%", linha and perto(linha["variacao_pct"], 50, 0.1), linha)
# 30 unidades compradas x 5,00 de alta = 150,00. É o número da conversa.
checar("impacto de 150,00 no volume comprado", linha and perto(linha["impacto"], 150), linha)
checar("e diz de quem veio o mais barato",
       linha and linha["fornecedor_mais_barato"] == barato["nome"], linha)
if caro["id"] != barato["id"]:
    checar("e de quem veio a última compra",
           linha and linha["fornecedor_ultimo"] == caro["nome"], linha)

print("5. o detalhe por trás da variação")
st, serie = chamar("GET", f"/cmv/precos/{insumo['id']}", token=token)
checar("a série de compras responde", st == 200 and len(serie) == 3, serie)
checar("da mais recente para a mais antiga",
       serie and perto(serie[0]["preco"], 15) and perto(serie[-1]["preco"], 10), serie)
checar("com o fornecedor de cada compra", all(s.get("fornecedor") for s in serie), serie)

print("6. item comprado uma vez só não vira ruído")
st, unico = chamar("POST", "/produtos", {
    "nome": f"Rel unico {marca}", "tipo": "INSUMO", "um_estoque": "UN"}, token=token)
st, nota = chamar("POST", "/notas", {
    "id_fornecedor": caro["id"], "numero": f"U{marca}", "data_emissao": str(hoje),
    "id_local": local["id"],
    "itens": [{"id_produto": unico["id"], "quantidade": 1, "valor_unitario": 99}],
}, token=token)
chamar("POST", f"/notas/{nota['id']}/lancar", {"id_local": local["id"]}, token=token)
st, precos = chamar("GET", f"/cmv/precos?inicio={hoje - timedelta(days=3)}&fim={hoje}",
                    token=token)
checar("uma compra só não entra (não há variação a mostrar)",
       not any(x["id_produto"] == unico["id"] for x in precos))

print("7. a planilha do fornecedor")
import urllib.request as _u
req = _u.Request(BASE + f"/exportar/precos.csv?inicio={hoje - timedelta(days=3)}&fim={hoje}")
req.add_header("Authorization", f"Bearer {token}")
with _u.urlopen(req, timeout=60) as resp:
    csv = resp.read().decode("utf-8")
checar("o CSV sai", "Evolução de preço" in csv, csv[:80])
checar("com o insumo do teste", f"Rel azeite {marca}" in csv)
checar("e traz o quadro por setor no mesmo arquivo", "Onde o custo pesa" in csv)
checar("com o impacto somado no resumo", "Impacto somado" in csv)

print("8. permissão")
st, r = chamar("POST", "/auth/login", {"email": COZINHA[0], "senha": COZINHA[1]})
tk = r.get("access_token")
if tk:
    checar("cozinha não vê o CMV por setor",
           chamar("GET", f"/cmv/por-grupo{periodo}", token=tk)[0] == 403)
    checar("cozinha não vê o relatório de preços",
           chamar("GET", "/cmv/precos", token=tk)[0] == 403)
else:
    checar("usuário de cozinha disponível para o teste de permissão", False, r)

print("9. limpeza")
for p in list(produtos.values()) + [sem_setor.get("id"), insumo.get("id"), unico.get("id")]:
    chamar("DELETE", f"/produtos/{p}", token=token)
checar("limpeza concluída", True)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
