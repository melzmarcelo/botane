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

import atexit
import json
import sys
from datetime import date, timedelta
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
from comum import garantir_local, garantir_locais  # noqa: E402

sys.path.insert(0, ".")
from database import get_cursor  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
COZINHA = ("smoke.cozinha@botane.com.br", "smoke12345")

ok = 0
falhas: list[str] = []
criados: dict[str, list] = {"produtos": [], "fichas": [], "inventarios": []}


def chamar(metodo, caminho, corpo=None, token=None, unidade=None):
    # Acento e espaço na query quebram o urllib — codifica aqui, uma vez só.
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    # ⚠️ A loja vai no cabeçalho `X-Unidade`, como a tela manda — e o
    # servidor a valida: mandar o cabeçalho não dá acesso a loja nenhuma.
    if unidade:
        req.add_header("X-Unidade", str(unidade))
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


def baixar_texto(caminho, token):
    """Baixa um CSV como texto — o `chamar` daqui só entende JSON."""
    req = urllib.request.Request(BASE + caminho)
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


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
# Transferência precisa de dois locais: a base nova tem zero.
locais = garantir_locais(chamar, token, 2)
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

# O razão cresce todo dia; sem filtro, achar um movimento vira rolagem.
print("4b. filtros do razão")
hoje = date.today().isoformat()
st, r = chamar("GET", f"/estoque/movimentos?inicio={hoje}&fim={hoje}", token=token)
checar("filtra pelo período", st == 200 and all(
    m["data_movimento"][:10] == hoje for m in r), st)
# `fim` é dia CHEIO: com `<= fim` o que foi lançado hoje às 14h ficaria de fora.
checar("e o dia de hoje entra inteiro", any(m["id_produto"] == cafe for m in r),
       len(r))
st, r = chamar("GET", f"/estoque/movimentos?tipo=SAIDA_CONSUMO_INTERNO", token=token)
checar("filtra pelo tipo de movimento",
       st == 200 and all(m["tipo"] == "SAIDA_CONSUMO_INTERNO" for m in r), st)
st, r = chamar("GET", f"/estoque/movimentos?busca=Est café {marca}", token=token)
checar("filtra pelo nome do produto",
       st == 200 and r and all(m["id_produto"] == cafe for m in r), len(r))
st, r = chamar("GET", "/estoque/movimentos?inicio=1999-01-01&fim=1999-01-02", token=token)
checar("período sem movimento devolve lista vazia", r == [], r)
# Fixar UM produto é diferente de buscar por texto: "café" traz cinco cafés, e
# quem quer o saldo de um deles não quer conferir os outros.
st, r = chamar("GET", f"/estoque/saldos?id_produto={cafe}", token=token)
checar("o saldo filtra por um produto só",
       st == 200 and r and all(s["id_produto"] == cafe for s in r), len(r) if st == 200 else r)
st, r = chamar("GET", "/estoque/saldos?id_produto=999999", token=token)
checar("produto que não existe devolve lista vazia", r == [], r)

st, tipos = chamar("GET", "/estoque/tipos-movimento", token=token)
checar("os tipos vêm do servidor, com rótulo",
       any(t["tipo"] == "SAIDA_PERDA" and t["rotulo"] == "Perda" for t in tipos), tipos)

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

# 🔑 **E dá para PERGUNTAR quais são.** A etiqueta na linha do razão existe
# desde sempre, mas com centenas de movimentos ela só ajuda quem já está
# olhando para a linha certa — não havia filtro. Cada linha destas é uma
# entrada que ninguém lançou, e cada uma deixa o CMV torto até ser lançada.
st, provisorios = chamar(
    "GET", f"/estoque/movimentos?apenas_provisorios=true&id_produto={novo}", token=token)
checar("o razão filtra por custo provisório", st == 200, st)
checar("e traz a saída que acabou de sair provisória",
       any(m["id"] == r.get("id") for m in (provisorios or [])),
       [m["id"] for m in (provisorios or [])])
checar("e NADA que tenha custo firme entra no filtro",
       all(m["custo_provisorio"] for m in (provisorios or [])),
       [m["id"] for m in (provisorios or []) if not m["custo_provisorio"]])
# ⚠️ Contra a lista SEM o filtro, nunca contra um número fixo: a base é
# compartilhada e "19 provisórias" seria o estado do dia.
st, todos_do_produto = chamar(
    "GET", f"/estoque/movimentos?id_produto={novo}", token=token)
checar("e o filtro de fato corta alguma coisa",
       len(provisorios or []) <= len(todos_do_produto or []),
       (len(provisorios or []), len(todos_do_produto or [])))

# ⚠️ **O ARQUIVO tem de aceitar o mesmo filtro.** Filtrar na tela e baixar
# outra coisa faz quem confere os dois achar que um deles mente — é a razão de
# o razão exportado já espelhar período, produto, tipo e local.
texto = baixar_texto(
    "/exportar/movimentos.csv?inicio=2020-01-01&fim=2030-01-01&provisorio=true", token)
checar("a planilha do razão aceita o filtro", "Custo provis" in texto, texto[:200])
linhas_csv = [l for l in texto.splitlines() if l.startswith("Movimentos;")]
checar("e conta as mesmas linhas que a tela",
       linhas_csv and int(linhas_csv[0].split(";")[1]) >= len(provisorios or []),
       (linhas_csv, len(provisorios or [])))

# 🔑 **O razão não filtrava por LOJA** — e o CSV sempre filtrou. Com duas lojas
# a tela misturava os movimentos das duas enquanto o arquivo trazia só os
# desta: a divergência exata que o razão exportado existe para não ter.
st, do_razao = chamar("GET", "/estoque/movimentos?limite=200", token=token, unidade=1)
if do_razao:
    with get_cursor() as cur:
        cur.execute("SELECT count(DISTINCT id_unidade) AS n FROM estoque_movimentos "
                    "WHERE id = ANY(%s)", ([m["id"] for m in do_razao],))
        lojas_na_resposta = cur.fetchone()["n"]
    checar("o razão responde por UMA loja, a atual", lojas_na_resposta == 1, lojas_na_resposta)

print("4c. movimento no futuro não existe")
# ⚠️ A trava do período fechado olha para trás; para a frente não olhava
# ninguém. Uma venda datada com o dia de UTC — às 22h de Brasília, já é o dia
# seguinte — caía FORA do mês e o relatório de movimentação deixava de fechar
# com o saldo. Data errada no razão não se conserta: só se estorna.
# ⚠️ Produto PRÓPRIO, não o do teste anterior. Aquele está com saldo negativo,
# e uma entrada sobre saldo negativo revaloriza o que já saiu pelo custo novo —
# comportamento correto do médio provisório, mas que deixa a identidade
# "inicial + entradas − saídas = final" aberta no relatório de movimentação, e
# os cenários que medem a casa inteira passavam a acusar isso.
futuro_prod = novo_produto(f"Est data futura {marca}")
futuro = (date.today() + timedelta(days=1)).isoformat()
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": futuro_prod, "quantidade": 1, "custo_unitario": 10,
    "id_local": principal["id"], "data_movimento": f"{futuro}T09:00:00",
}, token=token)
checar("entrada datada amanhã é recusada", st == 400, (st, r))
checar("e a recusa explica o que é uma data no futuro",
       "futuro" in str(r.get("detail", "")).lower(), r)
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": futuro_prod, "quantidade": 1, "custo_unitario": 10,
    "id_local": principal["id"], "data_movimento": f"{date.today().isoformat()}T09:00:00",
}, token=token)
checar("hoje continua valendo, do primeiro ao último minuto", st == 201, (st, r))

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
# Rodada anterior interrompida pode ter deixado contagem aberta no local.
st, abertos = chamar("GET", "/inventarios", token=token)
for i in abertos or []:
    if i["status"] == "ABERTO" and i["id_local"] == principal["id"]:
        chamar("DELETE", f"/inventarios/{i['id']}", token=token)

# ⚠️ **`cega: False` explícito.** A contagem passou a nascer CEGA por padrão —
# ver o saldo esperado transforma a contagem em conferência. Esta fase confere
# justamente o saldo congelado e a diferença, então ela pede o contrário de
# propósito; sem isso, `qtd_sistema` vem nulo e o teste morre num `float(None)`.
st, inv = chamar("POST", "/inventarios", {
    "id_local": principal["id"], "produtos": [cafe], "observacao": f"smoke {marca}",
    "cega": False,
}, token=token)
checar("abre inventário", st == 201, inv)
checar("e o nome nasce vazio quando ninguém dá um", inv.get("nome") is None, inv.get("nome"))
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

# Quem conta conta na embalagem que está na mão: "duas caixas", não "vinte e
# quatro unidades". Converter de cabeça é onde o erro do inventário entra.
chamar("PUT", f"/produtos/{cafe}/unidades",
       {"itens": [{"um": "KG", "fator": 1, "padrao": False},
                  {"um": "CX", "fator": 12, "padrao": True}]}, token=token)
st, r = chamar("PUT", f"/inventarios/{id_inv}/contagem", {
    "itens": [{"id_produto": cafe, "qtd_contada": 2, "um": "CX"}],
}, token=token)
checar("conta na unidade que está na mão", st == 200, r)
item_cx = r["itens"][0]
checar("e o sistema guarda convertido: 2 CX = 24 KG",
       perto(item_cx["qtd_contada"], 24), item_cx["qtd_contada"])
checar("guardando também o que foi digitado",
       perto(item_cx["qtd_informada"], 2) and item_cx["um_informada"] == "CX", item_cx)
checar("e as unidades possíveis viajam junto, para o celular não pedir de novo",
       any(u["um"] == "CX" for u in (item_cx.get("unidades") or [])), item_cx.get("unidades"))
st, r = chamar("PUT", f"/inventarios/{id_inv}/contagem", {
    "itens": [{"id_produto": cafe, "qtd_contada": 1, "um": "FD"}],
}, token=token)
checar("embalagem que ninguém cadastrou é recusada, não convertida a 1:1",
       st == 400 and "não converte" in str(r.get("detail", "")), (st, r))

# volta para o valor do cenário, que o fechamento confere adiante
chamar("PUT", f"/inventarios/{id_inv}/contagem", {
    "itens": [{"id_produto": cafe, "qtd_contada": sistema - 2, "observacao": "faltaram 2"}],
}, token=token)

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

print("8b. contagem cega")
# Ver o saldo esperado transforma a contagem em conferência: a pessoa lê 12,
# olha a prateleira e escreve 12. Na cega o esperado não SAI DO SERVIDOR —
# esconder só na tela deixaria o número no JSON e na folha impressa.
st, cega = chamar("POST", "/inventarios",
                  {"id_local": principal["id"], "produtos": [cafe], "cega": True}, token=token)
checar("abre contagem cega", st == 201 and cega.get("cega") is True, cega.get("cega"))
id_cega = cega.get("id")
criados["inventarios"].append(id_cega)
item_cego = cega["itens"][0]
checar("o saldo do sistema NÃO vem na resposta", item_cego["qtd_sistema"] is None, item_cego)
checar("nem a diferença, nem o custo médio",
       item_cego["diferenca"] is None and item_cego["custo_medio"] is None, item_cego)
checar("nem o impacto total", cega.get("diferenca_valor") is None, cega.get("diferenca_valor"))

st, r = chamar("PUT", f"/inventarios/{id_cega}/contagem",
               {"itens": [{"id_produto": cafe, "qtd_contada": 5}]}, token=token)
checar("dá para contar mesmo sem ver o esperado", st == 200, st)
checar("e o esperado continua escondido", r["itens"][0]["qtd_sistema"] is None, r["itens"][0])

folha = baixar_texto(f"/exportar/inventario/{id_cega}.csv", token)
checar("a folha impressa também não traz o saldo",
       "Saldo no sistema" not in folha and "cega" in folha, folha[:200])

st, r = chamar("POST", f"/inventarios/{id_cega}/fechar", token=token)
checar("fecha a contagem cega", st == 200, r)
st, depois = chamar("GET", f"/inventarios/{id_cega}", token=token)
checar("fechada, a diferença aparece",
       depois["itens"][0]["qtd_sistema"] is not None
       and depois["diferenca_valor"] is not None, depois["itens"][0])

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

# 🔑 **A filial sai mesmo se a suite estourar no meio.** A limpeza no fim so
# roda quando a rodada chega la — e uma que quebrou antes deixou a loja ATIVA na
# base do dono. Com duas lojas ativas, o seletor de loja aparece na barra
# superior e vira o PRIMEIRO `<select>` do documento: as checagens de tipo de
# produto do teste de navegador passaram a ler ids de loja. Mesma licao do
# `preservar_credenciais`.
def _desativar_filiais_de_teste():
    try:
        st_, lista_ = chamar("GET", "/unidades?incluir_inativas=true", token=token)
        for u_ in (lista_ or []):
            if u_.get("ativo") and str(u_.get("nome", "")).startswith("Filial de teste"):
                chamar("PUT", f"/unidades/{u_['id']}", {"ativo": False}, token=token)
    except Exception:
        pass


atexit.register(_desativar_filiais_de_teste)

print("9b. a segunda loja")
# 🔑 **O custo do insumo e da LOJA.** Ate 31/08/2026 `custo_do_insumo` somava
# `estoque_saldos` inteiro, sem filtrar `id_unidade`: o cafe que a matriz
# comprou a R$ 40/kg e a filial a R$ 52/kg valia R$ 45,30 nas duas, e nenhuma
# pagou isso. Nao fica contido — este numero alimenta a ficha, o custo CONGELADO
# do item de venda e a baixa por vinculo.
marca_f = str(time.time_ns())[-6:]
st, filial = chamar("POST", "/unidades", {
    "nome": f"Filial de teste {marca_f}", "apelido": f"F{marca_f}",
}, token=token)
id_filial = (filial or {}).get("id")
checar("a filial e criada", st == 201 and bool(id_filial), (st, filial))

# 🔑 **E ela nasce UTILIZAVEL.** Sem local de estoque nada se movimenta, e a
# mensagem que aparecia era "Local nao encontrado" — quem abre a segunda loja
# nao deveria descobrir isso na primeira nota.
st, locais_f = chamar("GET", "/locais", token=token, unidade=id_filial)
checar("e ja nasce com um local de estoque", bool(locais_f), locais_f)
checar("e ele nasce PRINCIPAL, que e o padrao de estoque e producao",
       any(l.get("principal") for l in (locais_f or [])), locais_f)

# ⚠️ Um produto com saldo SO na matriz: na filial ele nao tem medio, e a reserva
# do fornecedor — que e da REDE — e quem responde.
st, prod_f = chamar("POST", "/produtos", {
    "codigo": f"FIL{marca_f}", "nome": f"Insumo de duas lojas {marca_f}",
    "tipo": "INSUMO", "um_estoque": "KG", "controla_estoque": True,
}, token=token)
id_prod_f = (prod_f or {}).get("id")
local_matriz = garantir_local(chamar, token)
if id_prod_f and local_matriz:
    chamar("POST", "/estoque/entradas", {
        "id_produto": id_prod_f, "id_local": local_matriz["id"],
        "quantidade": 10, "custo_unitario": 40,
    }, token=token)
    st, l_fil = chamar("GET", "/locais", token=token, unidade=id_filial)
    chamar("POST", "/estoque/entradas", {
        "id_produto": id_prod_f, "id_local": l_fil[0]["id"],
        "quantidade": 10, "custo_unitario": 52,
    }, token=token, unidade=id_filial)

    with get_cursor() as _cur:
        from services import custos as _custos
        c_matriz, o_matriz = _custos.custo_do_insumo(_cur, id_prod_f, 1)
        c_filial, o_filial = _custos.custo_do_insumo(_cur, id_prod_f, id_filial)
        c_rede, _ = _custos.custo_do_insumo(_cur, id_prod_f)
    checar("o custo da matriz e o que a MATRIZ pagou", float(c_matriz or 0) == 40.0,
           (c_matriz, o_matriz))
    checar("o da filial e o que a FILIAL pagou", float(c_filial or 0) == 52.0,
           (c_filial, o_filial))
    # 🔑 A prova do defeito que existia: sem loja, a media das duas — 45,30 —
    # que e o numero que nenhuma das duas pagou.
    checar("e sem loja a conta continua sendo a da rede",
           40.0 < float(c_rede or 0) < 52.0, c_rede)

print("9c. transferencia ENTRE lojas")
# 🔑 Ate 31/08/2026 `transferir` recebia UMA loja e dois locais: escolhendo um
# local da outra, o razao gravava saida e entrada sob a loja de quem estava na
# tela — o saldo das duas ficava errado e nada denunciava. Numa casa com duas
# lojas, mandar producao da matriz para a filial e o que se faz toda semana.
if id_filial and id_prod_f:
    st, l_fil2 = chamar("GET", "/locais", token=token, unidade=id_filial)
    local_filial = (l_fil2 or [{}])[0].get("id")

    def _saldo(id_prod, unid):
        _st, s_ = chamar("GET", f"/estoque/saldos?id_produto={id_prod}", token=token,
                         unidade=unid)
        return sum(float(x["quantidade"]) for x in (s_ or []))

    antes_matriz = _saldo(id_prod_f, 1)
    antes_filial = _saldo(id_prod_f, id_filial)

    st, tr = chamar("POST", "/estoque/transferencias", {
        "id_produto": id_prod_f, "quantidade": 4,
        "id_local_origem": local_matriz["id"], "id_local_destino": local_filial,
        "observacao": f"matriz -> filial {marca_f}",
    }, token=token)
    checar("a transferencia entre lojas e aceita", st == 201, (st, tr))
    checar("e ela se declara como entre lojas", (tr or {}).get("entre_lojas") is True, tr)

    # 🔑 **Entre lojas ela nasce EM TRANSITO, e o razao nao se mexe.** A
    # mercadoria leva tempo no caminho: dizer que ja chegou some com o valor da
    # origem e faz o destino aparecer com o que ainda nao tem.
    id_remessa = (tr or {}).get("remessa")
    checar("e nasce como remessa em transito",
           (tr or {}).get("em_transito") is True and bool(id_remessa), tr)
    checar("a origem ainda NAO perdeu a quantidade",
           round(_saldo(id_prod_f, 1) - antes_matriz, 4) == 0.0, _saldo(id_prod_f, 1))
    checar("e o destino ainda nao ganhou nada",
           round(_saldo(id_prod_f, id_filial) - antes_filial, 4) == 0.0,
           _saldo(id_prod_f, id_filial))
    # ⚠️ O saldo da origem continua contando — e por isso precisa DIZER quanto
    # dele ja esta na estrada, senao a segunda remessa do dia despacha o que ja
    # saiu.
    st, s_tr = chamar("GET", f"/estoque/saldos?id_produto={id_prod_f}", token=token, unidade=1)
    checar("e o saldo da origem avisa o que esta em transito",
           any(float(x.get("em_transito") or 0) >= 4 for x in (s_tr or [])), s_tr)

    # ⚠️ Quem recebe e o DESTINO. Sem esta trava, quem despachou daria entrada
    # na outra loja sem ninguem ter conferido nada — que e o processo que o
    # recebimento existe para impedir.
    st, r_rec = chamar("POST", f"/transferencias/{id_remessa}/receber", {}, token=token,
                       unidade=id_filial)
    checar("o destino recebe a remessa", st == 201, (st, r_rec))
    st, r_rec2 = chamar("POST", f"/transferencias/{id_remessa}/receber", {}, token=token,
                        unidade=id_filial)
    checar("e receber de novo e recusado (409)", st == 409, (st, r_rec2))

    depois_matriz = _saldo(id_prod_f, 1)
    depois_filial = _saldo(id_prod_f, id_filial)
    checar("a origem perde a quantidade", round(antes_matriz - depois_matriz, 4) == 4.0,
           (antes_matriz, depois_matriz))
    checar("e o destino ganha a MESMA quantidade",
           round(depois_filial - antes_filial, 4) == 4.0, (antes_filial, depois_filial))

    # 🔑 **O custo ATRAVESSA a fronteira.** A entrada usa o custo que a saida
    # apurou — o medio da origem. E isso que faz a origem perder exatamente o
    # valor que o destino ganha, e a identidade do CMV fechar NAS DUAS.
    with get_cursor() as _cur:
        _cur.execute(
            """SELECT tipo, id_unidade, custo_unitario, quantidade
                 FROM estoque_movimentos
                WHERE id_produto = %s AND origem_tipo = 'TRANSFERENCIA'
                ORDER BY id DESC LIMIT 2""",
            (id_prod_f,),
        )
        movs = {r["tipo"]: dict(r) for r in _cur.fetchall()}
    m_saida = movs.get("TRANSFERENCIA_SAIDA") or {}
    m_entrada = movs.get("TRANSFERENCIA_ENTRADA") or {}
    checar("a saida fica na loja da ORIGEM", m_saida.get("id_unidade") == 1, m_saida)
    checar("e a entrada na loja do DESTINO",
           m_entrada.get("id_unidade") == id_filial, m_entrada)
    checar("e as duas pelo MESMO custo — transferencia nao cria valor",
           m_saida.get("custo_unitario") == m_entrada.get("custo_unitario"),
           (m_saida.get("custo_unitario"), m_entrada.get("custo_unitario")))

    # 🔑 **Transferencia entre lojas nao pode virar CMV de ninguem.** Dentro de
    # UMA loja ela se anula (sai de um local, entra em outro) e por isso nunca
    # contou como compra. Entre lojas ela NAO se anula: o destino recebe
    # mercadoria que nao comprou — o estoque final sobe e o CMV dele fica
    # NEGATIVO — e a origem perde mercadoria que nao vendeu, inchando o dela.
    # Foi a tela da rede que mostrou: a filial que so recebeu uma remessa
    # aparecia com CMV de −R$ 160,00.
    st, ap_fil = chamar("GET", "/cmv/apuracao", token=token, unidade=id_filial)
    # ⚠️ Com folga de UM CENTAVO. O custo unitario tem 6 casas e a conta
    # encadeia entrada, saida e estoque: o residuo fica em milionesimos de
    # real (-0,000006 na primeira rodada). Exigir zero exato acusaria de
    # defeito o arredondamento que o projeto ja assume em todo relatorio.
    checar("a filial que so RECEBEU nao tem CMV negativo",
           float((ap_fil or {}).get("cmv_real", -1)) >= -0.01,
           (ap_fil or {}).get("cmv_real"))
    # ⚠️ A remessa entra como compra no destino: sem isso, `inicial + compras −
    # final` nao teria como fechar num estoque que apareceu do nada.
    checar("e a remessa entra como compra dela",
           float((ap_fil or {}).get("compras", 0)) > 0, (ap_fil or {}).get("compras"))


    # ⚠️ Quem nao enxerga a loja nao empurra mercadoria para dentro dela.
    st, r_coz = chamar("POST", "/estoque/transferencias", {
        "id_produto": id_prod_f, "quantidade": 1,
        "id_local_origem": local_matriz["id"], "id_local_destino": local_filial,
    }, token=tk)
    checar("e quem nao lanca transferencia continua barrado", st == 403, st)


print("9c1. o acucar em varios setores: local com setor, transferencia e producao")
# 🔑 **O processo REAL da casa, descrito pelo dono em 01/09/2026:** o acucar
# entra no Estoque Central, e de manha cada setor leva um pacote para o seu
# canto — Bar, Confeitaria, Cozinha. Durante a semana cada um gasta do que
# pegou; no fim, cada setor conta o SEU estoque.
# 🔑 **O que ele chama de "setor" nesse fluxo e um LOCAL** — guarda mercadoria,
# recebe transferencia e e contado num inventario proprio. Modelar assim faz o
# processo funcionar com o que ja existe; o que faltava era o local DIZER a que
# setor pertence, e a producao sair de onde se produz.
st, r = chamar("POST", "/setores", {"nome": f"Confeitaria {marca}"}, token=token)
id_setor_conf = (r or {}).get("id")
st, r = chamar("POST", "/locais", {"nome": f"Central {marca}", "tipo": "SECO"}, token=token)
id_central = (r or {}).get("id")
st, r = chamar("POST", "/locais", {"nome": f"Canto da confeitaria {marca}", "tipo": "SECO",
                                   "id_setor": id_setor_conf}, token=token)
id_conf = (r or {}).get("id")
checar("o local pode declarar a que setor pertence", st == 201, (st, r))
st, locais_s = chamar("GET", "/locais", token=token)
meu_local = next((l for l in (locais_s or []) if l["id"] == id_conf), {})
checar("e a lista traz o nome do setor junto, nao so o id",
       meu_local.get("setor") == f"Confeitaria {marca}".upper(), meu_local)
# ⚠️ Nulo e resposta legitima: o Estoque Central nao pertence a setor nenhum.
central_s = next((l for l in (locais_s or []) if l["id"] == id_central), {})
checar("e o estoque geral fica SEM setor, que e a resposta certa",
       central_s.get("id_setor") is None, central_s)
st, r = chamar("POST", "/locais", {"nome": f"Local setor errado {marca}", "tipo": "SECO",
                                   "id_setor": 99999999}, token=token)
checar("setor que nao existe e recusado com frase, nao 500", st == 400, (st, r))

st, r = chamar("POST", "/produtos", {
    "codigo": f"ACU{marca}", "nome": f"Acucar do processo {marca}", "tipo": "INSUMO",
    "um_estoque": "KG", "controla_estoque": True, "id_local_padrao": id_central}, token=token)
id_acucar = (r or {}).get("id")
criados["produtos"].append(id_acucar)
chamar("POST", "/estoque/entradas", {
    "id_produto": id_acucar, "quantidade": 12, "custo_unitario": 5,
    "id_local": id_central}, token=token)
st, r = chamar("POST", "/estoque/transferencias", {
    "id_produto": id_acucar, "quantidade": 3,
    "id_local_origem": id_central, "id_local_destino": id_conf}, token=token)
checar("a transferencia da manha leva 3 para o canto do setor", st in (200, 201), (st, r))

# 🔑 A pergunta "quanto a loja tem" e diferente de "onde esta", e as duas
# precisam existir: a lista por prateleira mostra quatro linhas e nenhum total.
st, ag = chamar("GET", f"/estoque/saldos-agrupados?id_produto={id_acucar}", token=token)
linha_ag = (ag or [{}])[0]
checar("o saldo agrupado soma os locais da loja",
       abs(float(linha_ag.get("quantidade", 0)) - 12) < 0.0001, linha_ag.get("quantidade"))
checar("e diz em que prateleira esta cada parte",
       sorted(float(x["quantidade"]) for x in (linha_ag.get("por_local") or [])) == [3.0, 9.0],
       linha_ag.get("por_local"))
checar("com o setor de cada prateleira",
       any(x.get("setor") == f"Confeitaria {marca}".upper()
           for x in (linha_ag.get("por_local") or [])), linha_ag.get("por_local"))
# ⚠️ O corte por setor e pelo setor do LOCAL, nao pelo do produto: a pergunta e
# "o que a Confeitaria tem na mao".
st, por_setor = chamar(
    "GET", f"/estoque/saldos-agrupados?id_setor={id_setor_conf}&id_produto={id_acucar}",
    token=token)
checar("e o corte por setor mostra so o que aquele setor tem",
       abs(float((por_setor or [{}])[0].get("quantidade", 0)) - 3) < 0.0001, por_setor)

# 🔑 **A producao sai de ONDE SE PRODUZ.** Sem isso, o pacote que a Confeitaria
# pegou de manha nunca baixa, e a contagem do fim da semana acusa uma sobra que
# nao existe.
st, r = chamar("POST", "/produtos", {
    "codigo": f"BOL{marca}", "nome": f"Bolo do processo {marca}", "tipo": "PRODUZIDO",
    "um_estoque": "UN", "producao_propria": True, "controla_estoque": True,
    "id_local_padrao": id_conf}, token=token)
id_bolo = (r or {}).get("id")
criados["produtos"].append(id_bolo)
st, f_bolo = chamar("POST", "/fichas", {
    "id_produto": id_bolo, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": id_acucar, "qtd_bruta": 1, "um": "KG"}]}, token=token)
chamar("POST", f"/fichas/{f_bolo['id']}/homologar", token=token)
chamar("POST", "/estoque/producoes", {
    "id_produto": id_bolo, "quantidade": 2, "id_local": id_conf}, token=token)
st, ag = chamar("GET", f"/estoque/saldos-agrupados?id_produto={id_acucar}", token=token)
por_local = {x["local"]: float(x["quantidade"]) for x in ((ag or [{}])[0].get("por_local") or [])}
checar("produzir na Confeitaria baixa do estoque DELA",
       abs(por_local.get(f"Canto da confeitaria {marca}".upper(), 0) - 1) < 0.0001, por_local)
checar("e nao encosta no Estoque Central",
       abs(por_local.get(f"Central {marca}".upper(), 0) - 9) < 0.0001, por_local)

# ⚠️ **A reserva nao e conveniencia, e um caso real**: uma receita usa leite da
# camara e cafe do seco ao mesmo tempo. Sem saldo no local de quem produz, cai
# no local do PRODUTO — senao a saida bateria num lugar por onde o insumo nunca
# passou, com saldo negativo e custo provisorio contaminando o custo do prato.
chamar("POST", "/estoque/producoes", {
    "id_produto": id_bolo, "quantidade": 5, "id_local": id_conf}, token=token)
st, ag = chamar("GET", f"/estoque/saldos-agrupados?id_produto={id_acucar}", token=token)
por_local = {x["local"]: float(x["quantidade"]) for x in ((ag or [{}])[0].get("por_local") or [])}
checar("faltando no setor, a producao cai no local do produto",
       abs(por_local.get(f"Central {marca}".upper(), 0) - 4) < 0.0001, por_local)
checar("e o pouco que sobrou no setor fica intacto",
       abs(por_local.get(f"Canto da confeitaria {marca}".upper(), 0) - 1) < 0.0001, por_local)


print("9c3. os locais no CADASTRO do produto")
# 🔑 Ate aqui o cadastro so tinha o local PADRAO — aquele por onde o produto
# entra. Os demais so passavam a existir na primeira transferencia, entao nao
# havia como preparar a casa antes de operar: o canto do Bar nao existia ate
# alguem levar o primeiro pacote para la.
# ⚠️ **Sem tabela nova**: a linha de `estoque_saldos` com quantidade ZERO ja
# quer dizer "mora aqui, vazio no momento". Duas tabelas dizendo a mesma coisa
# divergiriam no primeiro movimento.
st, cad = chamar("GET", f"/produtos/{id_acucar}/locais", token=token)
nos_locais = {x["local"]: x for x in (cad or [])}
checar("o cadastro diz em que prateleiras o produto esta", st == 200 and len(cad) == 2,
       (st, [x["local"] for x in (cad or [])]))
checar("com o saldo e o custo de cada uma",
       abs(float(nos_locais.get(f"Central {marca}".upper(), {}).get("quantidade", 0)) - 4) < 0.0001
       and perto(nos_locais.get(f"Central {marca}".upper(), {}).get("custo_medio"), 5),
       nos_locais)
checar("e com o setor da prateleira, que e o que separa um canto do estoque geral",
       nos_locais.get(f"Canto da confeitaria {marca}".upper(), {}).get("setor")
       == f"Confeitaria {marca}".upper(), nos_locais)

# 🔑 Declarar um local NAO movimenta nada — e o ponto do pedido: a prateleira
# passa a existir vazia, pronta para receber a transferencia e para entrar na
# contagem.
st, r = chamar("POST", "/locais", {"nome": f"Canto do bar {marca}", "tipo": "SECO"},
               token=token)
id_canto_bar = (r or {}).get("id")
st, mov_antes = chamar("GET", f"/estoque/movimentos?id_produto={id_acucar}", token=token)
st, r = chamar("POST", f"/produtos/{id_acucar}/locais", {"id_local": id_canto_bar},
               token=token)
checar("acrescentar um local ao cadastro e aceito", st == 201, (st, r))
st, mov_depois = chamar("GET", f"/estoque/movimentos?id_produto={id_acucar}", token=token)
checar("e nao lanca movimento nenhum no razao",
       len(mov_depois or []) == len(mov_antes or []),
       (len(mov_antes or []), len(mov_depois or [])))
st, cad = chamar("GET", f"/produtos/{id_acucar}/locais", token=token)
zerado = next((x for x in (cad or []) if x["id_local"] == id_canto_bar), {})
checar("a prateleira nova aparece com saldo zero",
       zerado != {} and abs(float(zerado.get("quantidade", -1))) < 0.0001, zerado)
# ⚠️ Repetir nao cria nada, e dizer 201 ali afirmaria que criou.
st, r = chamar("POST", f"/produtos/{id_acucar}/locais", {"id_local": id_canto_bar},
               token=token)
checar("repetir responde 200, nao 201 — nada foi criado", st == 200, (st, r))
st, r = chamar("POST", f"/produtos/{id_acucar}/locais", {"id_local": 99999999}, token=token)
checar("local que nao existe e recusado com frase, nao 500", st == 400, (st, r))

# 🔑 A declaracao vale para o que vem depois: a prateleira vazia ja e um destino
# de transferencia legitimo, que era justamente o que se queria preparar.
st, r = chamar("POST", "/estoque/transferencias", {
    "id_produto": id_acucar, "quantidade": 1,
    "id_local_origem": id_central, "id_local_destino": id_canto_bar}, token=token)
checar("e a prateleira declarada recebe transferencia", st in (200, 201), (st, r))

# ⚠️ **Tirar so com a prateleira VAZIA.** Apagar a linha com saldo faria o
# estoque sumir da vista sem um movimento no razao explicando — e o razao e a
# unica memoria do custo.
st, r = chamar("DELETE", f"/produtos/{id_acucar}/locais/{id_canto_bar}", token=token)
checar("com saldo, tirar o local e recusado", st == 409, (st, r))
checar("e a frase diz o quanto tem e o que fazer",
       "1" in str((r or {}).get("detail", "")) and "ransfira" in str((r or {}).get("detail", "")),
       r)
chamar("POST", "/estoque/transferencias", {
    "id_produto": id_acucar, "quantidade": 1,
    "id_local_origem": id_canto_bar, "id_local_destino": id_central}, token=token)
st, r = chamar("DELETE", f"/produtos/{id_acucar}/locais/{id_canto_bar}", token=token)
checar("vazia, ela sai do cadastro", st == 200, (st, r))
st, cad = chamar("GET", f"/produtos/{id_acucar}/locais", token=token)
checar("e some da lista", not any(x["id_local"] == id_canto_bar for x in (cad or [])), cad)
st, r = chamar("DELETE", f"/produtos/{id_acucar}/locais/{id_canto_bar}", token=token)
checar("tirar o que ja saiu responde 404, nao 500", st == 404, (st, r))
# ⚠️ O razao NAO se apaga: as duas transferencias continuam la depois de o
# vinculo sair. Tirar o local e cadastro, nao correcao de movimento.
st, mov = chamar("GET", f"/estoque/movimentos?id_produto={id_acucar}", token=token)
checar("e o razao daquela prateleira continua inteiro",
       len([m for m in (mov or []) if m.get("local") == f"Canto do bar {marca}".upper()]) >= 2,
       len(mov or []))


print("9c2. o estoque da EMPRESA, somando as lojas")
# 🔑 A tela da rede dizia quanto VALE o estoque da empresa e nao dizia de que.
# Para conferir um item era preciso trocar de loja no seletor e somar de cabeca
# — a mesma conta que a visao consolidada existe para evitar.
if id_filial and id_prod_f:
    st, linhas_rede = chamar(
        "GET", f"/estoque/saldos-rede?id_produto={id_prod_f}", token=token)
    checar("a visao consolidada responde", st == 200, (st, linhas_rede))
    linha = (linhas_rede or [{}])[0]
    checar("com UMA linha para o produto, nao uma por prateleira",
           len(linhas_rede or []) == 1, len(linhas_rede or []))

    # A matriz e a filial tem saldo deste produto: o total tem de ser a soma.
    def _qtd(unid):
        _st, s_ = chamar("GET", f"/estoque/saldos?id_produto={id_prod_f}", token=token,
                         unidade=unid)
        return sum(float(x["quantidade"]) for x in (s_ or []))

    soma = _qtd(1) + _qtd(id_filial)
    checar("e a quantidade e a SOMA das lojas",
           abs(float(linha.get("quantidade", 0)) - soma) < 0.0001,
           (linha.get("quantidade"), soma))
    checar("com as duas lojas nomeadas na linha",
           len(linha.get("por_loja") or []) == 2, linha.get("por_loja"))

    # 🔑 **O custo medio da rede e PONDERADO, nunca a media dos medios.** A
    # matriz comprou a 40 e a filial a 52: a media simples daria 46, que nao e o
    # custo de nada. O certo e valor total / quantidade total.
    if float(linha.get("quantidade", 0)):
        esperado = float(linha["valor"]) / float(linha["quantidade"])
        checar("e o custo medio e ponderado, nao a media dos medios",
               abs(float(linha["custo_medio"]) - esperado) < 0.01,
               (linha.get("custo_medio"), esperado))
        checar("e cai entre o que a matriz e a filial pagaram",
               40.0 <= float(linha["custo_medio"]) <= 52.0, linha.get("custo_medio"))

    # ⚠️ **So as lojas que a pessoa ENXERGA entram na soma.** Somar o que ela
    # nao pode consultar vazaria pelo TOTAL, que e o pior lugar para vazar —
    # nada na tela denuncia. Quem cobra o caso restrito e smoke_lojas_do_usuario;
    # aqui a afirmacao e que nenhuma loja de fora entra na linha.
    st, eu_lojas = chamar("GET", "/auth/me", token=token)
    visiveis = {u["id"] for u in (eu_lojas or {}).get("unidades", [])}
    de_fora = [x for x in (linha.get("por_loja") or []) if x["id_unidade"] not in visiveis]
    checar("e nenhuma loja de fora entra na linha", not de_fora, de_fora)

    # E ela sai em planilha, como todo relatorio da casa.
    texto = baixar_texto("/exportar/saldos-rede.csv", token)
    checar("a posicao da rede se exporta", "Posi" in texto and "Lojas somadas" in texto,
           texto[:80])
    # ⚠️ **Contra o numero de lojas ATIVAS, nao contra um numero fixo.** Esta
    # suite cria uma filial propria, entao "2" seria o estado do dia — e o teste
    # quebraria sozinho na primeira vez que a casa abrisse outra loja.
    checar("e o arquivo declara quantas lojas somou",
           f"Lojas somadas;{len(visiveis)}" in texto,
           [l for l in texto.splitlines() if "Lojas" in l])

    # 🔑 **A rede com ZERO daquele item derrubava a lista inteira com 500.**
    # O custo medio da rede e uma DIVISAO pela quantidade: com o saldo zerado
    # ele nao existe, e o modelo de resposta exigia um numero. O caminho e o
    # comum — desmarcar "so com saldo" na tela —, e a resposta que morria era a
    # da PAGINA toda, nao a daquela linha: a tela ficava vazia sem dizer por que.
    st, prod_z = chamar("POST", "/produtos", {
        "codigo": f"ZER{marca}", "nome": f"Est zerado {marca}", "tipo": "INSUMO",
        "um_estoque": "KG", "controla_estoque": True}, token=token)
    id_zerado = (prod_z or {}).get("id")
    if id_zerado:
        criados["produtos"].append(id_zerado)
    chamar("POST", "/estoque/entradas", {
        "id_produto": id_zerado, "id_local": principal["id"], "quantidade": 5,
        "custo_unitario": 10}, token=token)
    chamar("POST", "/estoque/saidas", {
        "id_produto": id_zerado, "id_local": principal["id"], "quantidade": 5,
        "tipo": "SAIDA_CONSUMO_INTERNO"}, token=token)
    st, zerados = chamar(
        "GET", f"/estoque/saldos-rede?id_produto={id_zerado}", token=token)
    checar("produto zerado na rede nao derruba a lista", st == 200, (st, zerados))
    z = (zerados or [{}])[0]
    checar("e a quantidade e zero mesmo", abs(float(z.get("quantidade", 1))) < 0.0001,
           z.get("quantidade"))
    # ⚠️ **Nulo, nunca zero.** "Nao custa nada" e "nao ha nada para custar" se
    # leem igual na tela, e so o primeiro e um custo. A tela mostra traco.
    checar("e o custo medio vem NULO, nao zero", z.get("custo_medio") is None,
           z.get("custo_medio"))

    # 🔑 **O painel da rede e a lista consolidada NAO fechavam, e nada dizia por
    # que.** O painel soma `estoque_saldos` inteiro (e esta certo: tirar o
    # inativo do estoque final inflaria o CMV); a lista filtra por ativo (e esta
    # certa: mostra o que se opera). Quem soma a coluna e compara com o painel
    # concluia que um dos dois mente. A lista passou a DIZER quanto ficou de
    # fora, e este e o numero que fecha a diferenca.
    st, fora = chamar("GET", "/estoque/saldos-rede/inativos", token=token)
    checar("a lista diz quanto ficou de fora por estar inativo", st == 200, (st, fora))
    # ⚠️ **Paginar, e nao pedir "tudo num limite grande".** O teto do endpoint e
    # 1.000, e a base real passou dele: a checagem lia 1.000 de 1.065 e acusava a
    # conta de nao fechar — um defeito que so existia no teste, e que apareceria
    # sozinho num dia qualquer, longe de qualquer commit. Identidade que soma a
    # lista INTEIRA precisa varrer a lista inteira.
    def rede_inteira(incluir_inativos: bool) -> list:
        tudo, offset = [], 0
        while True:
            st, p = chamar(
                "GET",
                f"/estoque/saldos-rede?limite=1000&offset={offset}"
                + ("&incluir_inativos=true" if incluir_inativos else ""),
                token=token)
            tudo += p or []
            if len(p or []) < 1000:
                return tudo
            offset += 1000

    so_ativos = rede_inteira(False)
    com_inativos = rede_inteira(True)
    soma_ativos = sum(float(x["valor"]) for x in (so_ativos or []))
    soma_tudo = sum(float(x["valor"]) for x in (com_inativos or []))
    # ⚠️ Folga de um centavo por linha: cada `valor` ja vem arredondado no banco.
    folga = 0.01 * max(1, len(com_inativos or []))
    checar("e esse numero FECHA a diferenca entre os dois",
           abs((soma_ativos + float(fora.get("valor", 0))) - soma_tudo) <= folga,
           (soma_ativos, fora.get("valor"), soma_tudo))
    checar("e conta os produtos que ficaram de fora",
           fora.get("produtos") == len(com_inativos or []) - len(so_ativos or []),
           (fora.get("produtos"), len(com_inativos or []), len(so_ativos or [])))

    # ⚠️ **O aviso segue os MESMOS filtros da lista.** Um numero que responde por
    # outro recorte e pior que numero nenhum: diria "e mais R$ 24 mil" com um
    # produto so na tela. O produto zerado acima esta ATIVO, entao filtrando por
    # ele nada fica de fora.
    st, fora_um = chamar(
        "GET", f"/estoque/saldos-rede/inativos?id_produto={id_zerado}", token=token)
    checar("e o aviso obedece ao filtro da tela", fora_um.get("produtos") == 0, fora_um)


print("9d. o painel da REDE")
# 🔑 Toda tela do sistema responde por UMA loja, e esta certo: quem opera opera
# numa de cada vez. Mas o dono de duas nao tinha onde ver as duas — e somar de
# cabeca dois food costs de bases diferentes e a conta que ninguem faz certo.
st, uma_so = chamar("GET", "/inicio/rede", token=token)
checar("o painel da rede responde", st == 200 and "lojas" in (uma_so or {}), st)
if id_filial:
    nomes = [l["loja"] for l in (uma_so or {}).get("lojas", [])]
    checar("e traz a filial junto da matriz", len(nomes) >= 2, nomes)

    # ⚠️ O total SOMA dinheiro. Nao e uma consulta nova: cada linha sai da mesma
    # `apurar` que o painel de cada loja usa — uma segunda implementacao
    # divergiria no primeiro caso de borda e o consolidado passaria a discordar
    # das partes.
    linhas = (uma_so or {}).get("lojas", [])
    soma_cmv = round(sum(l["cmv"] for l in linhas), 2)
    checar("e o total e a soma das partes",
           round((uma_so or {}).get("total", {}).get("cmv", 0), 2) == soma_cmv,
           ((uma_so or {}).get("total", {}).get("cmv"), soma_cmv))

    # 🔑 O food cost da rede se RECALCULA, nao se soma: media de percentuais
    # daria o mesmo peso a loja que vendeu R$ 100 mil e a que vendeu R$ 5 mil.
    total = (uma_so or {}).get("total", {})
    if total.get("receita"):
        esperado = round(total["cmv"] / total["receita"] * 100, 2)
        checar("e o food cost da rede se recalcula, nao e media de percentuais",
               total.get("food_cost_pct") == esperado,
               (total.get("food_cost_pct"), esperado))
    else:
        # ⚠️ Sem receita ele e NULO, nao zero: zero pareceria um resultado
        # excelente.
        checar("sem receita, o food cost da rede e nulo",
               total.get("food_cost_pct") is None, total.get("food_cost_pct"))

    # ⚠️ Cada loja declara o SEU periodo: uma pode fechar por semana e a outra
    # por mes, e um total que junta periodos diferentes precisa dizer isso.
    checar("e cada linha declara o periodo dela",
           all(l.get("periodo", {}).get("rotulo") for l in linhas), linhas[:1])

# ⚠️ Sem `cmv.painel` a rede nao abre: sao numeros de dinheiro das duas lojas.
st, r_coz = chamar("GET", "/inicio/rede", token=tk)
checar("quem nao ve dinheiro nao abre o painel da rede", st == 403, st)


print("9e. preco de venda POR LOJA")
# 🔑 `produto_precos.id_unidade` existia desde o comeco e ninguem usava: todo
# preco nascia global. No PDV ele e POR FILIAL, e duas lojas podem cobrar
# valores diferentes pelo mesmo prato — sem resolucao, a filial que cobra mais
# barato teria o preco da matriz no cardapio e na margem.
if id_filial:
    st, prod_p = chamar("POST", "/produtos", {
        "codigo": f"PRECO{marca_f}", "nome": f"Prato de duas lojas {marca_f}",
        "tipo": "PRODUZIDO", "um_estoque": "UN", "preco_venda": 12.0,
    }, token=token)
    id_prod_p = (prod_p or {}).get("id")
    checar("o produto nasce com o preco da CASA", st == 201, (st, prod_p))

    def _precos(unid=None):
        st_, d_ = chamar("GET", f"/produtos/{id_prod_p}", token=token, unidade=unid)
        return ((d_ or {}).get("preco_casa"), (d_ or {}).get("preco_loja"),
                (d_ or {}).get("preco_venda"))

    casa, loja, vale = _precos()
    checar("sem preco da loja, vale o da casa",
           float(casa or 0) == 12.0 and loja is None and float(vale or 0) == 12.0,
           (casa, loja, vale))

    # ⚠️ O preco da loja SOBREPOE o da casa — e so naquela loja.
    st, r = chamar("PUT", f"/produtos/{id_prod_p}/preco-loja",
                   {"preco_venda": 15.5}, token=token, unidade=id_filial)
    checar("da para definir o preco de uma loja", st == 200, (st, r))
    casa, loja, vale = _precos(id_filial)
    checar("e na filial vale o dela", float(vale or 0) == 15.5, (casa, loja, vale))
    casa_m, loja_m, vale_m = _precos(1)
    checar("enquanto a matriz continua com o da casa",
           float(vale_m or 0) == 12.0 and loja_m is None, (casa_m, loja_m, vale_m))

    # 🔑 Apagar NAO e zerar: zero seria dizer que ali o prato e de graca.
    st, r = chamar("PUT", f"/produtos/{id_prod_p}/preco-loja",
                   {"preco_venda": None}, token=token, unidade=id_filial)
    checar("apagar o da loja devolve o da casa", st == 200, (st, r))
    casa, loja, vale = _precos(id_filial)
    checar("e a filial volta a valer 12,00",
           float(vale or 0) == 12.0 and loja is None, (casa, loja, vale))

    # ⚠️ Zero e um PRECO, nao a ausencia dele.
    chamar("PUT", f"/produtos/{id_prod_p}/preco-loja",
           {"preco_venda": 0}, token=token, unidade=id_filial)
    casa, loja, vale = _precos(id_filial)
    checar("e zero e um preco, nao a ausencia dele",
           float(vale) == 0.0 and loja is not None, (casa, loja, vale))

    if id_prod_p:
        chamar("DELETE", f"/produtos/{id_prod_p}", token=token)


# ⚠️ A filial de teste sai: a base e compartilhada, e uma loja a mais por
# rodada faria o seletor da tela crescer sem parar. Ela vira INATIVA em vez
# de ser apagada — tem movimento no razao, e razao nao se apaga.
if id_prod_f:
    chamar("DELETE", f"/produtos/{id_prod_f}", token=token)
if id_filial:
    chamar("PUT", f"/unidades/{id_filial}", {"ativo": False}, token=token)


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
