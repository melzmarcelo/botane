"""Agenda de produção e os dois modos de produzir.

Duas coisas que o sistema tratava igual e não são:

* **Massa de pizza** (PARA_ESTOQUE): produz, guarda, sai depois. Tem estoque,
  tem mínimo, e alguém precisa decidir produzir antes que falte — é o que a
  agenda serve. A agenda é PLANO: não mexe no estoque até ser cumprida.

* **Café passado** (NA_HORA): não fica em estoque. A venda e a produção são o
  mesmo instante — a venda produz e baixa junto, e o saldo volta a zero. Sem
  isso, a casa venderia mil cafés e o pó continuaria inteiro no razão.

    python tests/smoke_producao.py            (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date, timedelta

sys.path.insert(0, "tests")
from comum import garantir_local  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []
SUF = uuid.uuid4().hex[:5]


def chamar(metodo, caminho, corpo=None, token=None):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=40) as r:
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
        print(f"  FALHA {nome} -> {extra}")


def perto(a, b, tol=0.001):
    return a is not None and abs(float(a) - float(b)) < tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = r["access_token"]
local = garantir_local(chamar, token)
amanha = date.today() + timedelta(days=1)
ontem = date.today() - timedelta(days=1)


def novo_produto(nome, um, **extra):
    st, r = chamar("POST", "/produtos", {"nome": nome, "um_estoque": um, **extra}, token=token)
    return r.get("id")


print("1. o cenário: farinha, massa (para estoque) e café (na hora)")
farinha = novo_produto(f"Prod farinha {SUF}", "KG", tipo="INSUMO")
po = novo_produto(f"Prod pó de café {SUF}", "KG", tipo="INSUMO")
massa = novo_produto(f"Prod massa {SUF}", "UN", tipo="PRODUZIDO", producao_propria=True,
                     estoque_minimo=10, estoque_maximo=30)
cafe = novo_produto(f"Prod café passado {SUF}", "UN", tipo="PRODUZIDO",
                    producao_propria=True, modo_producao="NA_HORA")
st, p = chamar("GET", f"/produtos/{cafe}", token=token)
checar("o café é NA_HORA", p.get("modo_producao") == "NA_HORA", p.get("modo_producao"))
st, p = chamar("GET", f"/produtos/{massa}", token=token)
checar("a massa é PARA_ESTOQUE (o padrão)", p.get("modo_producao") == "PARA_ESTOQUE",
       p.get("modo_producao"))
st, r = chamar("PUT", f"/produtos/{cafe}", {"modo_producao": "INVENTADO"}, token=token)
checar("modo inventado é recusado", st == 400, (st, r))

for insumo, custo in ((farinha, 5.00), (po, 40.00)):
    chamar("POST", "/estoque/entradas",
           {"id_produto": insumo, "quantidade": 100, "custo_unitario": custo,
            "id_local": local["id"]}, token=token)

# 1 massa = 0,2 KG de farinha = 1,00 | 1 café = 0,01 KG de pó = 0,40
st, r = chamar("POST", "/fichas", {
    "id_produto": massa, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": farinha, "qtd_bruta": 0.2, "um": "KG"}]}, token=token)
ficha_massa = r.get("id")
chamar("POST", f"/fichas/{ficha_massa}/homologar", {}, token=token)
st, r = chamar("POST", "/fichas", {
    "id_produto": cafe, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": po, "qtd_bruta": 0.01, "um": "KG"}]}, token=token)
ficha_cafe = r.get("id")
chamar("POST", f"/fichas/{ficha_cafe}/homologar", {}, token=token)

print("\n2. a agenda é plano: não mexe no estoque")
st, r = chamar("POST", "/producao-agenda",
               {"id_produto": massa, "data_prevista": str(amanha), "quantidade": 20},
               token=token)
checar("agenda 20 massas para amanhã", st == 201, r)
id_linha = r.get("id")
st, saldos = chamar("GET", "/estoque/saldos", token=token)
checar("o estoque NÃO se mexeu ao agendar",
       not any(s["id_produto"] == massa for s in saldos), saldos[:2])
st, saldo_farinha = chamar("GET", f"/estoque/saldos?id_produto={farinha}", token=token)
checar("nem o da farinha", perto(saldo_farinha[0]["quantidade"], 100),
       saldo_farinha[0]["quantidade"])

st, r = chamar("POST", "/producao-agenda",
               {"id_produto": massa, "data_prevista": str(amanha), "quantidade": 5},
               token=token)
checar("agendar de novo no mesmo dia SOMA, não duplica", perto(r.get("quantidade"), 25), r)

st, r = chamar("POST", "/producao-agenda",
               {"id_produto": cafe, "data_prevista": str(amanha), "quantidade": 10},
               token=token)
checar("o que é feito na hora não se agenda", st == 400, (st, r))
checar("e a recusa explica por quê", "na hora" in str(r.get("detail", "")).lower(), r)

print("\n3. cumprir a linha é que mexe no estoque")
st, r = chamar("POST", f"/producao-agenda/{id_linha}/produzir", {"quantidade": 22},
               token=token)
checar("produz 22 (a cozinha rendeu diferente do plano)", st == 200, r)
checar("guarda o planejado e o produzido",
       perto(r.get("planejado"), 25) and perto(r.get("produzido"), 22), r)
checar("consumindo 4,4 KG de farinha",
       perto((r.get("consumos") or [{}])[0].get("quantidade"), 4.4), r.get("consumos"))
checar("a 22,00 (4,4 × 5,00)", perto(r.get("custo_total"), 22.00, 0.01), r.get("custo_total"))
st, saldos = chamar("GET", f"/estoque/saldos?id_produto={massa}", token=token)
checar("22 massas em estoque", perto(saldos[0]["quantidade"], 22), saldos)
checar("a 1,00 cada", perto(saldos[0]["custo_medio"], 1.00), saldos)

st, r = chamar("POST", f"/producao-agenda/{id_linha}/produzir", {}, token=token)
checar("não produz a mesma linha duas vezes", st == 400, (st, r))

# Agenda é lista de TAREFA: cumprida, sai dela. O que já foi produzido tem
# lugar próprio ("Produções recentes"); misturar faria a agenda crescer para
# sempre e esconder o que falta fazer no meio do que já foi feito.
st, agenda = chamar("GET", "/producao-agenda", token=token)
checar("a linha produzida sai da agenda",
       not any(l["id"] == id_linha for l in agenda["linhas"]),
       [(l["id"], l["status"]) for l in agenda["linhas"]])
st, historico = chamar("GET", "/producao-agenda?status=PRODUZIDA", token=token)
checar("mas continua no histórico, para conferir plano contra realizado",
       any(l["id"] == id_linha for l in historico["linhas"]),
       [(l["id"], l["status"]) for l in historico["linhas"]])

print("\n3b. a folha da produção: o que vai ser preciso")
st, r = chamar("POST", "/producao-agenda",
               {"id_produto": massa, "data_prevista": str(amanha), "quantidade": 10},
               token=token)
linha_folha = r.get("id")
st, det = chamar("GET", f"/producao-agenda/{linha_folha}", token=token)
checar("a linha traz a previsão junto", st == 200 and "previsao" in det, st)
prev = det.get("previsao") or {}
item = (prev.get("itens") or [{}])[0]
checar("com o insumo da ficha", item.get("id_produto") == farinha, item)
checar("por unidade: 0,2 KG", perto(item.get("por_unidade"), 0.2), item.get("por_unidade"))
checar("no total: 2 KG para 10 massas", perto(item.get("necessario"), 2),
       item.get("necessario"))
checar("dizendo quanto existe no local", item.get("saldo_no_local") is not None, item)
checar("e que não falta nada", prev.get("itens_faltando") == 0, prev.get("itens_faltando"))
checar("com o custo da produção (2 × 5,00)", perto(prev.get("custo_total"), 10.00, 0.01),
       prev.get("custo_total"))

# A previsão avulsa é a mesma conta, para simular outra quantidade.
st, prev2 = chamar("GET", f"/producao-agenda/necessario?id_produto={massa}&quantidade=20",
                   token=token)
checar("dobrar a quantidade dobra o necessário",
       perto((prev2.get("itens") or [{}])[0].get("necessario"), 4),
       (prev2.get("itens") or [{}])[0].get("necessario"))
st, prev3 = chamar("GET", f"/producao-agenda/necessario?id_produto={massa}&quantidade=10000",
                   token=token)
checar("pedir mais do que existe acusa a falta", prev3.get("itens_faltando") == 1, prev3)
checar("dizendo QUANTO falta", (prev3.get("itens") or [{}])[0].get("falta", 0) > 0,
       (prev3.get("itens") or [{}])[0].get("falta"))
chamar("DELETE", f"/producao-agenda/{linha_folha}", token=token)

print("\n4. o café passado: a venda produz e baixa")
st, antes = chamar("GET", f"/estoque/saldos?id_produto={po}", token=token)
po_antes = float(antes[0]["quantidade"])
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": str(date.today()), "documento": f"CUPOM-{SUF}",
    "itens": [{"id_produto": cafe, "quantidade": 30, "valor_unitario": 6.00}]}]},
    token=token)
checar("importa a venda de 30 cafés", st == 201, r)
checar("e diz que produziu na hora", r.get("produzidos_na_hora") == 1, r)

st, depois = chamar("GET", f"/estoque/saldos?id_produto={po}", token=token)
checar("o pó baixou 0,3 KG (30 × 0,01)", perto(float(depois[0]["quantidade"]), po_antes - 0.3),
       (po_antes, depois[0]["quantidade"]))
st, saldos = chamar("GET", f"/estoque/saldos?id_produto={cafe}", token=token)
checar("e o café passado NÃO fica em estoque",
       not saldos or perto(saldos[0]["quantidade"], 0), saldos)

st, mov = chamar("GET", f"/estoque/movimentos?id_produto={cafe}", token=token)
tipos = {m["tipo"] for m in mov}
checar("o razão mostra os dois lados: produção e venda",
       {"ENTRADA_PRODUCAO", "SAIDA_VENDA"} <= tipos, tipos)

# A massa é do outro tipo: vender não produz nada sozinho.
st, antes = chamar("GET", f"/estoque/saldos?id_produto={massa}", token=token)
chamar("POST", "/vendas/importar", {"vendas": [{
    "data": str(date.today()), "documento": f"CUPOM-M-{SUF}",
    "itens": [{"id_produto": massa, "quantidade": 2, "valor_unitario": 12.00}]}]},
    token=token)
st, depois = chamar("GET", f"/estoque/saldos?id_produto={massa}", token=token)
# Vender massa BAIXA o estoque (ela existe na prateleira), mas NÃO produz nada:
# é o contrário do café, que nasce na venda. As duas metades importam.
checar("vender massa baixa o estoque, sem produzir",
       perto(depois[0]["quantidade"], float(antes[0]["quantidade"]) - 2),
       (antes[0]["quantidade"], depois[0]["quantidade"]))
st, mov_massa = chamar("GET", f"/estoque/movimentos?id_produto={massa}&tipo=ENTRADA_PRODUCAO",
                       token=token)
checar("e a venda não gerou produção nenhuma", len(mov_massa) == 1, len(mov_massa))

print("\n5. o mínimo vira agenda")
st, r = chamar("POST", "/estoque/saidas",
               {"id_produto": massa, "quantidade": 15, "id_local": local["id"],
                "tipo": "SAIDA_CONSUMO_INTERNO"}, token=token)
checar("consome 15 massas, ficando abaixo do mínimo", st == 201, r)
st, agenda = chamar("GET", "/producao-agenda", token=token)
sugerida = next((s for s in agenda["sugestoes"] if s["id_produto"] == massa), None)
checar("a massa aparece como sugestão", sugerida is not None,
       [s["produto"] for s in agenda["sugestoes"]])
if sugerida:
    # 22 produzidas − 2 vendidas − 15 consumidas = 5; o máximo é 30.
    checar("sugerindo repor até o MÁXIMO (30 − 5 = 25)", perto(sugerida["sugerido"], 25),
           sugerida)

st, alertas = chamar("GET", "/alertas", token=token)
chaves = {a["chave"] for a in alertas}
checar("o alerta separa 'produzir' de 'comprar'", "producao.agendar" in chaves, chaves)

st, r = chamar("POST", "/producao-agenda/das-sugestoes", token=token)
checar("um botão põe todas na agenda", st == 201 and r.get("criadas", 0) >= 1, r)
st, agenda = chamar("GET", "/producao-agenda", token=token)
checar("e a sugestão some depois de agendada",
       not any(s["id_produto"] == massa for s in agenda["sugestoes"]),
       [s["produto"] for s in agenda["sugestoes"]])

print("\n6. o que ficou para trás")
st, r = chamar("POST", "/producao-agenda",
               {"id_produto": massa, "data_prevista": str(ontem), "quantidade": 3},
               token=token)
atrasada = r.get("id")
st, agenda = chamar("GET", "/producao-agenda", token=token)
linha = next((l for l in agenda["linhas"] if l["id"] == atrasada), None)
checar("a linha de ontem aparece como atrasada", linha and linha["atrasada"] is True, linha)
checar("e o resumo conta as atrasadas", agenda["resumo"]["atrasadas"] >= 1, agenda["resumo"])

st, r = chamar("DELETE", f"/producao-agenda/{atrasada}", token=token)
checar("dá para cancelar o que não vai ser feito", st == 200, r)
st, r = chamar("DELETE", f"/producao-agenda/{id_linha}", token=token)
checar("mas não se cancela o que já virou produção", st == 400, (st, r))

print("\n7. limpeza")
st, agenda = chamar("GET", "/producao-agenda", token=token)
for l in agenda["linhas"]:
    if l["status"] == "PLANEJADA":
        chamar("DELETE", f"/producao-agenda/{l['id']}", token=token)
for pid in (farinha, po, massa, cafe):
    chamar("DELETE", f"/produtos/{pid}", token=token)
checar("limpeza concluída", True)

print("")
print("9. a receita que rende em KG um produto contado em UN")
# 🔑 **Relatado pelo dono (15/09/2026):** *"a ficha do COOKIES FLAT produz 65
# porções, coloquei para produzir 2 e no estoque só entraram 2 UN"*. O que ele
# viu é verdade — e o que ninguém via é que a conta por trás estava errada.
# ⚠️ **As duas pontas falam unidades diferentes**: a quantidade está na unidade
# de ESTOQUE (UN de cookie) e o rendimento, na da RECEITA (KG de massa).
# `qtd / rendimento` dividia unidade por quilo: 2 / 8,535 = **0,234 receita**,
# 23% dos ingredientes para fazer dois cookies, quando o certo é 2/65 = 3,08%.
# Sete vezes e meia de manteiga, farinha e chocolate a mais saindo do estoque —
# e o custo do cookie inflado na mesma medida.
biscoito = novo_produto(f"Prod cookie {SUF}", "UN", tipo="PRODUZIDO", producao_propria=True)
manteiga = novo_produto(f"Prod manteiga {SUF}", "KG", tipo="INSUMO")
chamar("POST", "/estoque/entradas",
       {"id_produto": manteiga, "quantidade": 50, "custo_unitario": 10,
        "id_local": local["id"]}, token=token)
# A receita rende 8,535 KG de massa = 65 cookies, e leva 1,3 KG de manteiga.
st, r = chamar("POST", "/fichas", {
    "id_produto": biscoito, "rendimento_qtd": 8.535, "rendimento_um": "KG", "porcoes": 65,
    "itens": [{"id_insumo": manteiga, "qtd_bruta": 1.3, "um": "KG"}]}, token=token)
ficha_biscoito = r.get("id")
chamar("POST", f"/fichas/{ficha_biscoito}/homologar", {}, token=token)

st, prev = chamar("GET", f"/producao-agenda/necessario?id_produto={biscoito}&quantidade=2",
                  token=token)
checar("a previsao responde", st == 200, (st, prev))
# 🔑 A afirmação central: 2 cookies são 2/65 da receita, não 2/8,535.
checar("2 unidades sao 2/65 da receita, e nao 2/8,535",
       perto(prev.get("lotes"), 2 / 65, 0.0001), prev.get("lotes"))
manteiga_prevista = next((i for i in prev.get("itens", []) if i["id_produto"] == manteiga), {})
checar("e a manteiga necessaria acompanha",
       perto(manteiga_prevista.get("necessario"), 1.3 * 2 / 65, 0.0001), manteiga_prevista)

# ⚠️ E a RECEITA INTEIRA continua sendo a receita inteira: 65 unidades = 1 lote.
st, cheia = chamar("GET", f"/producao-agenda/necessario?id_produto={biscoito}&quantidade=65",
                   token=token)
checar("65 unidades dao exatamente uma receita", perto(cheia.get("lotes"), 1), cheia.get("lotes"))

st, r = chamar("POST", "/estoque/producoes", {
    "id_produto": biscoito, "quantidade": 2, "id_local": local["id"]}, token=token)
checar("produzir 2 cookies grava", st == 201, (st, r))
st, mov = chamar(
    "GET", f"/estoque/movimentos?id_produto={manteiga}&por_pagina=10", token=token)
saida = next((m for m in (mov or []) if m["tipo"] == "SAIDA_PRODUCAO"), None)
checar("e tira do estoque a manteiga de DOIS cookies, nao a de quinze",
       perto(abs(float((saida or {}).get("quantidade") or 0)), 1.3 * 2 / 65, 0.0001), saida)
# 🔑 O custo do cookie sai do que REALMENTE saiu: 0,04 KG de manteiga a R$ 10,00
# dão R$ 0,40 para dois cookies — R$ 0,20 cada.
st, produzido = chamar("GET", f"/estoque/saldos?id_produto={biscoito}", token=token)
checar("e o custo do cookie e o do ingrediente que ele levou",
       perto(float((produzido or [{}])[0].get("custo_medio") or 0), 0.2, 0.01), produzido)


print()
print("10. pedir em RECEITAS, e nao em porcoes")
# 🔑 **Pedido do dono (15/09/2026):** *"na producao podemos ter como informar
# se vamos produzir X porcoes ou X rendimentos -- a ficha tem rendimento de 10 KG
# sendo 60 porcoes; informar 2 rendimento gera 120 porcoes"*. As duas contas
# sempre existiram (uma e o inverso da outra); o que faltava era a pessoa poder
# dizer QUAL das duas ela esta digitando. Sem isso, "2" era ambiguo -- e foi
# essa ambiguidade que fez dois cookies entrarem onde se esperavam cento e
# trinta.
st, duas = chamar(
    "GET",
    f"/producao-agenda/necessario?id_produto={biscoito}&quantidade=2&medida=RECEITAS",
    token=token)
checar("a previsao aceita o pedido em receitas", st == 200, (st, duas))
checar("duas receitas sao duas voltas da ficha", perto(duas.get("lotes"), 2), duas.get("lotes"))
# ⚠️ A afirmacao central: o que ENTRA e sempre na unidade de estoque.
checar("e viram 130 unidades de estoque", perto(duas.get("quantidade"), 130),
       duas.get("quantidade"))
checar("a tela sabe quantas unidades UMA receita rende",
       perto(duas.get("porcoes_por_receita"), 65), duas.get("porcoes_por_receita"))
st, cento = chamar(
    "GET", f"/producao-agenda/necessario?id_produto={biscoito}&quantidade=130",
    token=token)
# 🔑 Os dois caminhos tem de chegar ao MESMO lugar: sao a mesma conta, lida
# de dois lados. Se um dia divergirem, a tela passa a mentir em um dos dois.
checar("e pedir 130 porcoes da exatamente o mesmo",
       perto(cento.get("lotes"), duas.get("lotes"))
       and perto(cento.get("custo_total"), duas.get("custo_total")), (cento, duas))

st, antes_saldo = chamar("GET", f"/estoque/saldos?id_produto={manteiga}", token=token)
tinha = float((antes_saldo or [{}])[0].get("quantidade") or 0)
st, r = chamar("POST", "/estoque/producoes", {
    "id_produto": biscoito, "quantidade": 2, "medida": "RECEITAS",
    "id_local": local["id"]}, token=token)
checar("produzir DUAS RECEITAS grava", st == 201, (st, r))
checar("e o que entrou no estoque sao 130 unidades", perto((r or {}).get("quantidade"), 130), r)
checar("a resposta diz que foram 2 receitas", perto((r or {}).get("lotes"), 2), r)
st, depois_saldo = chamar("GET", f"/estoque/saldos?id_produto={manteiga}", token=token)
ficou = float((depois_saldo or [{}])[0].get("quantidade") or 0)
# 2 receitas x 1,3 KG = 2,6 KG de manteiga -- a receita inteira, duas vezes.
checar("e saiu a manteiga de duas receitas inteiras", perto(tinha - ficou, 2.6, 0.0001),
       (tinha, ficou))

# A agenda tambem aceita o pedido em receitas -- e traduz NA PORTA. Ela guarda
# sempre a unidade de estoque: de dentro para la (resumo do dia, folha da
# bancada, producao que fecha a linha) ninguem precisa lembrar de traduzir, e a
# primeira consulta que esquecesse produziria dois cookies.
st, r = chamar("POST", "/producao-agenda", {
    "id_produto": biscoito, "quantidade": 2, "medida": "RECEITAS",
    "data_prevista": str(amanha), "id_local": local["id"]}, token=token)
checar("agendar em receitas responde", st == 201, (st, r))
checar("e a agenda guarda 130, nao 2", perto((r or {}).get("quantidade"), 130), r)

# ⚠️ **O padrao continua sendo PORCOES.** Quem nao manda nada pede na
# unidade do produto, que e como sempre foi -- mudar o padrao reescreveria o
# significado de toda tela e todo script que ja chama esta rota.
st, r = chamar("POST", "/estoque/producoes", {
    "id_produto": biscoito, "quantidade": 65, "id_local": local["id"]}, token=token)
checar("sem medida, 65 continua querendo dizer 65 unidades",
       st == 201 and perto((r or {}).get("quantidade"), 65) and perto((r or {}).get("lotes"), 1),
       (st, r))


print()
print("11. o que REALMENTE foi usado")
# 🔑 **Pedido do dono (16/09/2026):** *"na lista de insumos, ter uma nova
# coluna com o que realmente foi usado. Por padrao e a mesma quantidade, mas o
# usuario pode alterar, inclusive a unidade -- por exemplo, na receita vao 5
# ovos, mas por um acaso usei 6."*
# 🔑 O razao SEMPRE foi capaz disso; o que faltava era a porta. Quem usava
# seis ovos lancava cinco, e o sexto sumia do controle ate aparecer semanas
# depois no inventario, como falta sem causa.
ovo = novo_produto(f"Prod ovo {SUF}", "UN", tipo="INSUMO")
chamar("POST", "/estoque/entradas",
       {"id_produto": ovo, "quantidade": 200, "custo_unitario": 1,
        "id_local": local["id"]}, token=token)
bolo = novo_produto(f"Prod bolo {SUF}", "UN", tipo="PRODUZIDO", producao_propria=True)
st, r = chamar("POST", "/fichas", {
    "id_produto": bolo, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": ovo, "qtd_bruta": 5, "um": "UN"}]}, token=token)
ficha_bolo = r.get("id")
chamar("POST", f"/fichas/{ficha_bolo}/homologar", {}, token=token)

st, prev = chamar("GET", f"/producao-agenda/necessario?id_produto={bolo}&quantidade=1",
                  token=token)
item = (prev.get("itens") or [{}])[0]
# ⚠️ A correcao viaja pela LINHA da receita, nao pelo produto: a mesma ficha
# pode listar o mesmo insumo duas vezes.
checar("a folha traz o id da linha da receita", bool(item.get("id_item")), item)
checar("e as unidades que o insumo aceita", "UN" in (item.get("unidades") or []), item)

st, antes = chamar("GET", f"/estoque/saldos?id_produto={ovo}", token=token)
tinha = sum(float(x["quantidade"]) for x in (antes or []))
st, r = chamar("POST", "/estoque/producoes", {
    "id_produto": bolo, "quantidade": 1, "id_local": local["id"],
    "consumos": [{"id_item": item["id_item"], "quantidade": 6, "um": "UN"}]}, token=token)
checar("produzir com a correcao grava", st == 201, (st, r))
st, depois = chamar("GET", f"/estoque/saldos?id_produto={ovo}", token=token)
ficou = sum(float(x["quantidade"]) for x in (depois or []))
# A afirmacao central: sairam SEIS, nao os cinco da receita.
checar("e sairam os 6 ovos usados, nao os 5 da receita", perto(tinha - ficou, 6),
       (tinha, ficou))
checar("a producao fica marcada como corrigida",
       (r or {}).get("consumo_ajustado") is True, r)
linha_ovo = next((c for c in (r or {}).get("consumos", []) if c["id_produto"] == ovo), None)
checar("e a resposta diz o que a receita pedia, ao lado do que saiu",
       linha_ovo and perto(linha_ovo.get("pedida"), 5) and perto(linha_ovo.get("quantidade"), 6),
       linha_ovo)

# ⚠️ Sem correcao, nada muda: linha nao tocada e a receita.
st, r = chamar("POST", "/estoque/producoes", {
    "id_produto": bolo, "quantidade": 1, "id_local": local["id"]}, token=token)
checar("sem correcao, a producao segue a receita",
       st == 201 and (r or {}).get("consumo_ajustado") is False, (st, r))

# 🔑 **Zero e aceito e NAO vira movimento.** "Nao usei" e resposta legitima --
# acabou, substitui -- e uma linha de quantidade zero no razao diria que algo se
# moveu.
st, antes2 = chamar("GET", f"/estoque/saldos?id_produto={ovo}", token=token)
tinha2 = sum(float(x["quantidade"]) for x in (antes2 or []))
st, r = chamar("POST", "/estoque/producoes", {
    "id_produto": bolo, "quantidade": 1, "id_local": local["id"],
    "consumos": [{"id_item": item["id_item"], "quantidade": 0}]}, token=token)
checar("produzir sem usar o insumo e aceito", st == 201, (st, r))
st, depois2 = chamar("GET", f"/estoque/saldos?id_produto={ovo}", token=token)
checar("e o saldo do insumo nao se mexe",
       perto(tinha2, sum(float(x["quantidade"]) for x in (depois2 or []))), (tinha2, depois2))

# ⚠️ Unidade sem caminho de conversao e RECUSA: aceitar 1:1 faria "usei 2 CX"
# baixar duas unidades.
st, r = chamar("POST", "/estoque/producoes", {
    "id_produto": bolo, "quantidade": 1, "id_local": local["id"],
    "consumos": [{"id_item": item["id_item"], "quantidade": 2, "um": "CX"}]}, token=token)
checar("unidade que nao converte e recusada", st == 400, (st, r))
checar("e a frase diz o que cadastrar", "converte" in str((r or {}).get("detail", "")), r)

# ⚠️ Correcao de linha que esta ficha nao tem: a receita mudou desde que a
# folha foi aberta, e gravar seria gravar uma producao que ninguem viu.
st, r = chamar("POST", "/estoque/producoes", {
    "id_produto": bolo, "quantidade": 1, "id_local": local["id"],
    "consumos": [{"id_item": 99999999, "quantidade": 1}]}, token=token)
checar("correcao de linha que nao e desta ficha e recusada", st == 400, (st, r))


print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
