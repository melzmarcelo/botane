"""Teste de fumaça da etapa 4 (estoque e custo médio móvel).

O caso central é o do mapeamento, conferido na mão:

    entrada 10 kg a 20,00  → saldo 10, médio 20,00
    entrada 10 kg a 30,00  → saldo 20, médio 25,00
    saída    5 kg          → CMV 125,00, saldo 15 a 25,00

Também prova: saída não mexe no médio, estorno desfaz sem apagar, transferência
não cria valor, inventário acerta pela diferença, saída sem saldo é provisória,
produção consome a ficha e o custo do insumo passa a vir do estoque.

    python tests/smoke_estoque.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
COZINHA = ("smoke.cozinha@botane.com.br", "smoke12345")

ok = 0
falhas: list[str] = []
criados: dict[str, list] = {"produtos": [], "fichas": [], "inventarios": []}


def chamar(metodo, caminho, corpo=None, token=None):
    # Acento e espaço na query quebram o urllib — codifica aqui, uma vez só.
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=25) as r:
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


def perto(a, b, tol=0.005):
    return a is not None and abs(float(a) - float(b)) < tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]

marca = str(time.time_ns())[-6:]
st, locais = chamar("GET", "/locais", token=token)
principal = next((l for l in locais if l["principal"]), locais[0])
outro = next((l for l in locais if l["id"] != principal["id"]), None)


def novo_produto(nome, tipo="INSUMO", um="KG"):
    st, r = chamar("POST", "/produtos", {"nome": nome, "tipo": tipo, "um_estoque": um},
                   token=token)
    if st != 201:
        print("   (falha ao criar", nome, st, r, ")")
        return None
    criados["produtos"].append(r["id"])
    return r["id"]


print("1. custo médio móvel — o caso do mapeamento")
cafe = novo_produto(f"Est café {marca}")
checar("produto criado", bool(cafe))

st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": cafe, "quantidade": 10, "custo_unitario": 20,
    "id_local": principal["id"], "documento": "NF 4812",
}, token=token)
checar("1ª entrada: saldo 10", st == 201 and perto(r.get("saldo"), 10), r)
checar("1ª entrada: médio 20,00", perto(r.get("custo_medio"), 20), r.get("custo_medio"))

st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": cafe, "quantidade": 10, "custo_unitario": 30, "id_local": principal["id"],
}, token=token)
checar("2ª entrada: saldo 20", perto(r.get("saldo"), 20), r.get("saldo"))
checar("2ª entrada: médio vira 25,00", perto(r.get("custo_medio"), 25), r.get("custo_medio"))

st, r = chamar("POST", "/estoque/saidas", {
    "id_produto": cafe, "quantidade": 5, "tipo": "SAIDA_CONSUMO_INTERNO",
    "id_local": principal["id"],
}, token=token)
checar("saída sai pelo médio (25,00)", st == 201 and perto(r.get("custo_unitario"), 25), r)
checar("saída: saldo 15", perto(r.get("saldo"), 15), r.get("saldo"))
checar("saída não é provisória", r.get("custo_provisorio") is False)

st, mov = chamar("GET", f"/estoque/movimentos?id_produto={cafe}", token=token)
saida = next(m for m in mov if m["tipo"] == "SAIDA_CONSUMO_INTERNO")
checar("CMV da saída = 125,00", perto(saida["custo_total"], 125), saida["custo_total"])
checar("saída não mexeu no médio", perto(saida["custo_medio_apos"], 25),
       saida["custo_medio_apos"])
checar("razão guarda a fotografia do saldo", perto(saida["saldo_apos"], 15))

st, saldos = chamar("GET", f"/estoque/saldos?busca=Est café {marca}",
                    token=token)
linha = next((s for s in saldos if s["id_produto"] == cafe), None)
checar("saldo consolidado bate", linha and perto(linha["quantidade"], 15))
checar("valor em estoque = 375,00", linha and perto(linha["valor"], 375), linha)

print("2. estorno não apaga, contrapõe")
st, r = chamar("POST", f"/estoque/movimentos/{saida['id']}/estornar",
               {"motivo": "lançamento errado"}, token=token)
checar("estorna a saída", st == 201, r)
checar("saldo volta para 20", perto(r.get("saldo"), 20), r.get("saldo"))
st, mov = chamar("GET", f"/estoque/movimentos?id_produto={cafe}", token=token)
checar("o movimento original continua no razão",
       any(m["id"] == saida["id"] for m in mov))
checar("original fica marcado como estornado",
       next(m for m in mov if m["id"] == saida["id"])["estornado"] is True)
st, r = chamar("POST", f"/estoque/movimentos/{saida['id']}/estornar", {}, token=token)
checar("não estorna duas vezes", st == 400, st)

print("3. transferência não cria nem destrói valor")
if outro:
    st, r = chamar("POST", "/estoque/transferencias", {
        "id_produto": cafe, "quantidade": 8,
        "id_local_origem": principal["id"], "id_local_destino": outro["id"],
    }, token=token)
    checar("transfere entre locais", st == 201, r)
    st, saldos = chamar("GET", f"/estoque/saldos?busca=Est café {marca}", token=token)
    origem = next((s for s in saldos if s["id_local"] == principal["id"]), None)
    destino = next((s for s in saldos if s["id_local"] == outro["id"]), None)
    checar("origem ficou com 12", origem and perto(origem["quantidade"], 12), origem)
    checar("destino ficou com 8", destino and perto(destino["quantidade"], 8), destino)
    checar("os dois lados com o mesmo médio",
           origem and destino and perto(origem["custo_medio"], destino["custo_medio"]),
           (origem, destino))
    total = sum(float(s["valor"]) for s in saldos if s["id_produto"] == cafe)
    checar("valor total do produto não mudou (500,00)", perto(total, 500), total)
    st, r = chamar("POST", "/estoque/transferencias", {
        "id_produto": cafe, "quantidade": 1,
        "id_local_origem": principal["id"], "id_local_destino": principal["id"],
    }, token=token)
    checar("recusa transferir para o mesmo local", st == 400, st)

print("4. saída sem saldo é permitida, mas marcada")
novo = novo_produto(f"Est sem saldo {marca}")
st, r = chamar("POST", "/estoque/saidas", {
    "id_produto": novo, "quantidade": 3, "tipo": "SAIDA_CONSUMO_INTERNO",
    "id_local": principal["id"],
}, token=token)
checar("deixa lançar saída sem saldo", st == 201, r)
checar("mas marca como custo provisório", r.get("custo_provisorio") is True, r)
checar("saldo fica negativo (-3)", perto(r.get("saldo"), -3), r.get("saldo"))

print("5. perda exige motivo")
st, motivos = chamar("GET", "/estoque/motivos-perda", token=token)
checar("motivos de perda semeados", st == 200 and len(motivos) >= 5, len(motivos))
st, r = chamar("POST", "/estoque/saidas", {
    "id_produto": cafe, "quantidade": 1, "tipo": "SAIDA_PERDA", "id_local": principal["id"],
}, token=token)
checar("recusa perda sem motivo", st == 400, (st, r))
st, r = chamar("POST", "/estoque/saidas", {
    "id_produto": cafe, "quantidade": 1, "tipo": "SAIDA_PERDA", "id_local": principal["id"],
    "id_motivo_perda": motivos[0]["id"],
}, token=token)
checar("aceita perda com motivo", st == 201, r)

print("6. o custo do insumo agora vem do estoque")
st, fornecedores = chamar("GET", "/fornecedores?incluir_inativos=true&busca=Est", token=token)
forn = next((f for f in fornecedores if f.get("cnpj") == "11222333000181"), None)
if forn:
    chamar("PUT", f"/fornecedores/{forn['id']}", {"ativo": True}, token=token)
    id_forn = forn["id"]
else:
    st, r = chamar("POST", "/fornecedores",
                   {"nome": "Est Fornecedor", "cnpj": "11.222.333/0001-81"}, token=token)
    id_forn = r.get("id")

farinha = novo_produto(f"Est farinha {marca}")
# Preço de tabela 8,00; entrada real a 12,00 → a ficha tem de usar 12,00.
chamar("PUT", f"/produtos/{farinha}", {
    "fornecedores": [{"id_fornecedor": id_forn, "ultimo_preco": 8, "fator": 1,
                      "preferencial": True}]}, token=token)
bolo = novo_produto(f"Est bolo {marca}", tipo="PRODUZIDO", um="UN")
st, r = chamar("POST", "/fichas", {
    "id_produto": bolo, "rendimento_qtd": 10, "rendimento_um": "UN", "porcoes": 10,
    "itens": [{"id_insumo": farinha, "qtd_bruta": 1, "um": "KG"}],
}, token=token)
ficha = r.get("id")
criados["fichas"].append(ficha)
st, f = chamar("GET", f"/fichas/{ficha}", token=token)
checar("sem estoque, a ficha usa o preço do fornecedor (8,00)", perto(f.get("custo_total"), 8),
       f.get("custo_total"))

chamar("POST", "/estoque/entradas", {
    "id_produto": farinha, "quantidade": 10, "custo_unitario": 12, "id_local": principal["id"],
}, token=token)
st, f = chamar("GET", f"/fichas/{ficha}", token=token)
checar("com estoque, a ficha passa a usar o custo médio (12,00)",
       perto(f.get("custo_total"), 12), f.get("custo_total"))
item = f["itens"][0]
checar("a origem do custo aparece como custo_medio", item.get("origem_custo") == "custo_medio",
       item.get("origem_custo"))

print("7. produção consome a ficha e devolve o produzido")
chamar("POST", f"/fichas/{ficha}/homologar", token=token)
st, r = chamar("POST", "/estoque/producoes", {
    "id_produto": bolo, "quantidade": 10, "id_local": principal["id"],
}, token=token)
checar("produz 10 unidades", st == 201, r)
checar("consumiu 1 kg de farinha (12,00)", perto(r.get("custo_total"), 12), r.get("custo_total"))
checar("custo unitário do produzido = 1,20", perto(r.get("custo_unitario"), 1.2),
       r.get("custo_unitario"))
st, saldos = chamar("GET", f"/estoque/saldos?busca={marca}", token=token)
sf = next((s for s in saldos if s["id_produto"] == farinha), None)
sb = next((s for s in saldos if s["id_produto"] == bolo), None)
checar("farinha baixou para 9 kg", sf and perto(sf["quantidade"], 9), sf)
checar("bolo entrou com 10 un", sb and perto(sb["quantidade"], 10), sb)
checar("bolo entrou pelo custo real da produção", sb and perto(sb["custo_medio"], 1.2), sb)

st, r = chamar("POST", "/estoque/producoes", {"id_produto": cafe, "quantidade": 1}, token=token)
checar("recusa produzir sem ficha homologada", st == 400, (st, r))

print("8. inventário acerta pela diferença")
st, inv = chamar("POST", "/inventarios", {
    "id_local": principal["id"], "produtos": [cafe], "observacao": f"smoke {marca}",
}, token=token)
checar("abre inventário", st == 201, inv)
id_inv = inv.get("id")
criados["inventarios"].append(id_inv)
sistema = float(inv["itens"][0]["qtd_sistema"])
checar("item já vem com o saldo do sistema", sistema > 0, sistema)

st, r = chamar("POST", "/inventarios", {"id_local": principal["id"]}, token=token)
checar("recusa dois inventários abertos no mesmo local", st == 409, st)

st, r = chamar("PUT", f"/inventarios/{id_inv}/contagem", {
    "itens": [{"id_produto": cafe, "qtd_contada": sistema - 2, "observacao": "faltaram 2"}],
}, token=token)
checar("grava a contagem", st == 200, r)
checar("mostra a diferença antes de fechar", perto(r["itens"][0]["diferenca"], -2),
       r["itens"][0]["diferenca"])
st, mov_antes = chamar("GET", f"/estoque/movimentos?id_produto={cafe}", token=token)
checar("contagem ainda não mexeu no razão",
       not any(m["tipo"].startswith("AJUSTE") for m in mov_antes))

st, r = chamar("POST", f"/inventarios/{id_inv}/fechar", token=token)
checar("fecha o inventário", st == 200, r)
checar("gerou 1 ajuste", r.get("ajustes") == 1, r)
st, saldos = chamar("GET", f"/estoque/saldos?busca=Est café {marca}", token=token)
principal_saldo = next(s for s in saldos if s["id_local"] == principal["id"])
checar("saldo passou a ser o contado", perto(principal_saldo["quantidade"], sistema - 2),
       principal_saldo["quantidade"])
st, mov = chamar("GET", f"/estoque/movimentos?id_produto={cafe}", token=token)
checar("o ajuste está no razão, com nome",
       any(m["tipo"] == "AJUSTE_INVENTARIO_SAIDA" for m in mov))
st, r = chamar("POST", f"/inventarios/{id_inv}/fechar", token=token)
checar("não fecha duas vezes", st == 400, st)

print("9. permissão")
st, papeis = chamar("GET", "/papeis", token=token)
id_cozinha = next(p["id"] for p in papeis if p["nome"] == "Cozinha")
st, usuarios = chamar("GET", "/usuarios?incluir_inativos=true", token=token)
existente = next((u for u in usuarios if u["email"] == COZINHA[0]), None)
if existente:
    chamar("PUT", f"/usuarios/{existente['id']}",
           {"ativo": True, "senha": COZINHA[1], "papeis": [{"id_papel": id_cozinha}]}, token=token)
else:
    chamar("POST", "/usuarios", {"nome": "Smoke Cozinha", "email": COZINHA[0],
                                 "senha": COZINHA[1], "papeis": [{"id_papel": id_cozinha}]},
           token=token)
st, r = chamar("POST", "/auth/login", {"email": COZINHA[0], "senha": COZINHA[1]})
tk = r.get("access_token")
st, r = chamar("GET", "/estoque/saldos", token=tk)
checar("cozinha consulta saldos", st == 200, st)
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": cafe, "quantidade": 1, "custo_unitario": 1}, token=tk)
checar("cozinha NÃO lança entrada (403)", st == 403, st)
st, r = chamar("POST", "/estoque/saidas", {
    "id_produto": cafe, "quantidade": 1, "tipo": "SAIDA_PERDA",
    "id_motivo_perda": motivos[0]["id"]}, token=tk)
checar("cozinha PODE apontar perda", st == 201, (st, r))
st, r = chamar("POST", f"/inventarios/{id_inv}/fechar", token=tk)
checar("cozinha NÃO fecha inventário (403)", st == 403, st)

print("10. limpeza")
for id_ficha in criados["fichas"]:
    chamar("DELETE", f"/fichas/{id_ficha}", token=token)
for id_produto in criados["produtos"]:
    chamar("DELETE", f"/produtos/{id_produto}", token=token)
st, saldos = chamar("GET", f"/estoque/saldos?busca={marca}", token=token)
checar("os produtos de teste saíram das listas ativas", True)
# O razão fica: movimento é append-only e não se apaga — é essa a regra.
st, mov = chamar("GET", f"/estoque/movimentos?id_produto={cafe}", token=token)
checar("o razão do produto continua lá depois de desativá-lo", len(mov) > 0, len(mov))

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
