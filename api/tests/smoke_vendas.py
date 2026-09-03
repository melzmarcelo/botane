"""Teste de fumaça das telas de venda: a lista, o detalhe e o lançamento.

`/vendas` era uma tela só: dois formulários no topo e as vendas embaixo. Com
1.375 vendas num mês isso deixou de servir — quem precisa achar uma venda não a
acha, e quem precisa saber o que ela tinha dentro não tem para onde ir.

O que este arquivo cobra:

1. a lista **filtra pela loja atual**, e não somava as de todas as lojas
2. busca e filtro de origem vão ao SERVIDOR, não à página carregada
3. `/vendas/{id}` devolve cabeçalho, itens e os movimentos de estoque
4. o custo do detalhe é o **congelado**, não o de hoje
5. item sem ficha é contado, para a tela poder dizer "parcial" em vez de mentir
6. **`/vendas/sem-vinculo` continua respondendo** — a rota com parâmetro não a
   engoliu (é o erro clássico de ordem de declaração no FastAPI)
7. cancelar devolve o estoque, e o detalhe mostra o estorno

⚠️ **A suíte procura os registros DELA.** A base é compartilhada e tem vendas
reais importadas do PDV; contar linhas ou pegar "a primeira venda" acusaria bug
onde não há.

    python tests/smoke_vendas.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, "tests")
sys.path.insert(0, ".")
from comum import garantir_cozinha, garantir_locais  # noqa: E402

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
        with urllib.request.urlopen(req, dados, timeout=90) as r:
            return r.status, json.loads(r.read() or b"null")
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


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
assert st == 200, r
token = r["access_token"]

marca = str(time.time_ns())[-6:]
hoje = date.today().isoformat()

print("1. um prato com ficha, para o detalhe ter custo de verdade")
garantir_locais(chamar, token)

st, r = chamar("POST", "/produtos", {
    "codigo": f"VD-INS-{marca}", "nome": f"Insumo venda {marca}", "tipo": "INSUMO",
    "um_estoque": "KG", "controla_estoque": True, "status": "ATIVO",
}, token=token)
insumo = r.get("id")
checar("insumo criado", st == 201, (st, r))

# ⚠️ `controla_estoque` LIGADO, e é isso que faz a venda mexer no razão. Vender
# é sair do estoque: sem esta caixinha o prato continuaria na prateleira do
# sistema depois de vendido, o CMV real sairia subestimado, e a primeira
# contagem cobriria o buraco como "ajuste de inventário" — que é onde a
# diferença some sem nome.
st, r = chamar("POST", "/produtos", {
    "codigo": f"VD-PRT-{marca}", "nome": f"Prato venda {marca}", "tipo": "PRODUZIDO",
    "um_estoque": "UN", "producao_propria": True, "controla_estoque": True,
    "modo_producao": "NA_HORA", "status": "ATIVO",
}, token=token)
prato = r.get("id")
checar("prato criado", st == 201, (st, r))

# Uma entrada dá custo médio ao insumo; sem ela a ficha nasce sem custo e o
# detalhe não teria o que congelar.
st, locais = chamar("GET", "/locais", token=token)
principal = next((x for x in locais if x.get("principal")), locais[0])
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": insumo, "quantidade": 10, "custo_unitario": 20,
    "id_local": principal["id"], "documento": f"VD-{marca}",
}, token=token)
checar("entrada dá custo médio de 20,00 ao insumo", st == 201, (st, r))

st, r = chamar("POST", "/fichas", {
    "id_produto": prato, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": insumo, "qtd_bruta": 0.5, "um": "KG"}],
}, token=token)
ficha = r.get("id")
checar("ficha criada", st == 201, (st, r))
st, r = chamar("POST", f"/fichas/{ficha}/homologar", token=token)
checar("ficha homologada", st == 200, (st, r))

print("\n2. a venda")
documento = f"VENDA-{marca}"
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    # 🔑 A HORA do cupom. A coluna existia desde o comeco e o mapeador do PDV ja
    # a lia — ela so nunca chegava ao INSERT, e o dado morria no caminho. Sem
    # ela, todas as vendas de um dia sao a mesma coisa para quem procura uma.
    "data": hoje, "hora": "14:37:05",
    "documento": documento, "origem": "MANUAL", "canal": "BALCAO",
    "itens": [
        {"id_produto": prato, "quantidade": 3, "valor_unitario": 30},
        # ⚠️ Item sem produto de propósito: é ele que faz o detalhe ter de dizer
        # "parcial" em vez de mostrar uma margem que não é a da venda.
        {"codigo": f"NAO-EXISTE-{marca}", "descricao": f"Fantasma {marca}",
         "quantidade": 1, "valor_unitario": 10},
    ],
}]}, token=token)
checar("venda importada", st == 201 and r.get("importadas") == 1, (st, r))
checar("um item ficou sem vínculo", r.get("itens_sem_vinculo") == 1, r)

# ⚠️ Ida e volta: gravada na importacao, devolvida na LISTA e no DETALHE. A do
# detalhe ja aparecia na tela; a da lista nao existia.
st, _lista = chamar("GET", f"/vendas?busca={documento}", token=token)
checar("a hora do cupom volta na lista",
       (_lista or [{}])[0].get("hora", "")[:5] == "14:37", _lista)

st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": hoje, "documento": documento, "origem": "MANUAL",
    "itens": [{"id_produto": prato, "quantidade": 1, "valor_unitario": 30}],
}]}, token=token)
checar("mesmo documento não duplica", r.get("repetidas") == 1, r)

# 🔑 **O DESCONTO do cupom** (pedido do dono, 03/09/2026). O Botane gravava a
# soma dos ITENS (bruto) e o PDV informa o valor cobrado (liquido) — medido na
# conta real, 02/09 diferia 26,50, 29/08 diferia 13,50 e 28/08 diferia 722,00,
# em todos exatamente o desconto do dia.
# ⚠️ Receita e o DENOMINADOR do food cost: inflada, ela faz o food cost parecer
# melhor do que e. E o mesmo erro silencioso do custo zero.
doc_desc = f"DESC-{marca}"
st, rd = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": hoje, "documento": doc_desc, "origem": "PLANILHA", "desconto": 7.5,
    "itens": [{"id_produto": prato, "quantidade": 2, "valor_unitario": 25}],
}]}, token=token)
# ⚠️ 201, nao 200: importar CRIA venda.
checar("a importacao aceita desconto", st == 201, (st, rd))
st, lista_d = chamar("GET", f"/vendas?busca={doc_desc}", token=token)
vd = (lista_d or [{}])[0]
# 2 x 25 = 50 de itens, menos 7,50 = 42,50 cobrados.
checar("e o total gravado e o LIQUIDO, como o PDV informa",
       abs(float(vd.get("valor_total") or 0) - 42.5) < 0.01, vd.get("valor_total"))

print("\n3. a lista")
st, lista = chamar("GET", f"/vendas?busca={documento}", token=token)
checar("a busca vai ao servidor", st == 200 and len(lista) == 1, (st, len(lista or [])))
minha = lista[0] if lista else {}
id_venda = minha.get("id")
checar("e traz a venda desta rodada", minha.get("documento") == documento, minha)
checar("com a contagem de itens", minha.get("itens") == 2, minha)
checar("e o aviso de item sem custo", minha.get("sem_custo") == 1, minha)

st, lista = chamar("GET", f"/vendas?busca={documento}&origem=PDV_LEGAL", token=token)
checar("o filtro de origem exclui", st == 200 and not lista, (st, lista))

st, lista = chamar("GET", f"/vendas?busca=NAOEXISTE{marca}", token=token)
checar("busca sem resultado devolve lista vazia, não tudo",
       st == 200 and not lista, (st, len(lista or [])))

st, lista = chamar("GET", f"/vendas?busca={documento}&inicio=2000-01-01&fim=2000-01-02",
                   token=token)
checar("o período filtra", st == 200 and not lista, (st, lista))

print("\n4. a rota do detalhe não engoliu a fila de de-para")
# ⚠️ O FastAPI casa rotas na ordem de declaração: com `/{id_venda}` na frente,
# "sem-vinculo" viraria um id e o pedido morreria em 422.
st, fila = chamar("GET", "/vendas/sem-vinculo", token=token)
# ⚠️ **Pergunta pelo item DESTA rodada.** A fila e cortada nos 100 de maior
# receita, e o fantasma de R$ 10 saiu do topo assim que a base ganhou venda
# de verdade — a checagem acusava a fila de perder um item que estava la.
st_f, so_meu = chamar("GET", f"/vendas/sem-vinculo?busca=NAO-EXISTE-{marca}",
                      token=token)
checar("/vendas/sem-vinculo continua respondendo", st == 200 and isinstance(fila, list), st)
checar("e a fila tem o fantasma desta rodada",
       any(f"NAO-EXISTE-{marca}" == (x.get("codigo_pdv") or "") for x in (so_meu or [])),
       (st_f, len(so_meu or []), len(fila)))

print("\n5. o detalhe")
st, d = chamar("GET", f"/vendas/{id_venda}", token=token)
checar("o detalhe responde", st == 200, (st, d))
checar("com o cabeçalho", d.get("documento") == documento, d.get("documento"))
checar("o canal veio junto", d.get("canal") == "BALCAO", d.get("canal"))
checar("os dois itens", len(d.get("itens") or []) == 2, len(d.get("itens") or []))

item = next((i for i in d["itens"] if i["id_produto"] == prato), None)
# ⚠️ `.upper()`: o nome do produto é normalizado pelo banco (migração
# 036), e a suíte afirma sobre o que foi GRAVADO, não sobre o que mandou.
checar("o item vinculado traz o nome do produto",
       item and item["produto"] == f"Prato venda {marca}".upper(), item)
# 🔑 **No cupom vale o nome do PDV** (pedido do dono, 03/09/2026): e o que o
# caixa e o cliente viram. O detalhe manda os DOIS, e a tela escolhe — mandar so
# um deixaria quem confere o cupom contra o cadastro sem saber em que produto a
# linha caiu.
# ⚠️ Este produto foi cadastrado a mao e nunca teve nome de PDV, entao o curto
# vem NULO — e a tela cai no nome do cadastro. E o caminho de reserva, e ele
# precisa estar coberto tanto quanto o outro.
checar("o detalhe manda o nome curto junto", item and "produto_curto" in item, item)
# ⚠️ `.get`, nao `[]`: campo ausente tem de virar uma FALHA com nome, nao um
# KeyError que derruba a suite e esconde as checagens seguintes.
checar("nulo para quem nunca teve nome de PDV", item and item.get("produto_curto") is None,
       item and item.get("produto_curto"))

# 0,5 kg × 20/kg = 10,00 por unidade — o custo CONGELADO, não o de hoje.
checar("e o custo congelado da ficha (10,00)",
       item and abs(float(item["custo_ficha_unitario"]) - 10) < 0.01, item)
checar("dizendo que veio da ficha", item and item["origem_custo"] == "ficha", item)

fantasma = next((i for i in d["itens"] if i["id_produto"] is None), None)
checar("o item sem produto aparece com a descrição do PDV",
       fantasma and fantasma["descricao_pdv"] == f"Fantasma {marca}", fantasma)
checar("e sem custo", fantasma and fantasma["custo_ficha_unitario"] is None, fantasma)

checar("a receita soma os dois itens (100,00)", abs(float(d["receita"]) - 100) < 0.01, d["receita"])
checar("o custo teórico é só o do que tem ficha (30,00)",
       abs(float(d["custo_teorico"]) - 30) < 0.01, d["custo_teorico"])
# ⚠️ Sem esta contagem a tela mostraria margem de 70% como se fosse o resultado
# da venda — quando um dos itens simplesmente não tem custo conhecido.
checar("e a tela sabe que é parcial", d.get("itens_sem_custo") == 1, d)
checar("e que há item sem vínculo", d.get("itens_sem_vinculo") == 1, d)

print("\n6. o movimento de estoque, e o estorno do cancelamento")
# O prato é NA_HORA: a venda produz e baixa no mesmo lançamento, e o saldo dele
# volta a zero. A prova é o razão apontando para esta venda.
movimentos = d.get("movimentos") or []
checar("a venda deixou rastro no razão", len(movimentos) >= 1, len(movimentos))
checar("nenhum deles é estorno ainda",
       all(not m["id_estorno_de"] for m in movimentos), movimentos)

st, r = chamar("DELETE", f"/vendas/{id_venda}", token=token)
checar("cancelar responde", st == 200, (st, r))
checar("e devolve o que tinha saído", (r.get("estornados") or 0) >= 1, r)

st, d2 = chamar("GET", f"/vendas/{id_venda}", token=token)
checar("a venda continua existindo, cancelada", d2.get("cancelada") is True, d2.get("cancelada"))
checar("e o estorno aparece no detalhe",
       any(m["id_estorno_de"] for m in d2.get("movimentos") or []), d2.get("movimentos"))

st, r = chamar("DELETE", f"/vendas/{id_venda}", token=token)
checar("cancelar de novo é recusado", st == 400, st)

st, r = chamar("GET", "/vendas/99999999", token=token)
checar("venda inexistente é 404", st == 404, st)

print("\n7. a ficha em RASCUNHO custeia a venda, e a origem diz isso")
# 🔑 **Pedido do dono (02/09/2026):** o prato com ficha ainda nao homologada
# entrava na venda com custo ZERO. O CMV teorico saia subestimado, a margem alta
# demais e o food cost bom demais — e nada denunciava. A cozinha escreve a
# receita muito antes de alguem homologa-la, e o prato ja esta sendo vendido
# nesse meio tempo, que e exatamente quando o numero importa.
st, r = chamar("POST", "/produtos", {
    "codigo": f"VD-RAS-{marca}", "nome": f"Prato rascunho {marca}", "tipo": "PRODUZIDO",
    "um_estoque": "UN", "producao_propria": True, "controla_estoque": False,
    "modo_producao": "NA_HORA", "status": "ATIVO",
}, token=token)
prato_r = r.get("id")
checar("prato do rascunho criado", st == 201, (st, r))
st, r = chamar("POST", "/fichas", {
    "id_produto": prato_r, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": insumo, "qtd_bruta": 0.25, "um": "KG"}],
}, token=token)
ficha_r = r.get("id")
checar("e a ficha fica em RASCUNHO, sem homologar", st == 201, (st, r))
st, fr = chamar("GET", f"/fichas/{ficha_r}", token=token)
checar("a ficha esta mesmo em rascunho", fr.get("status") == "RASCUNHO", fr.get("status"))

doc_r = f"VENDA-RAS-{marca}"
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "documento": doc_r, "data": str(date.today()), "origem": "MANUAL",
    "itens": [{"id_produto": prato_r, "quantidade": 2,
               "valor_unitario": 30, "descricao": f"Prato rascunho {marca}"}],
}]}, token=token)
checar("a venda do prato em rascunho entra", st in (200, 201), (st, r))
# ⚠️ Antes este numero era 1: o item entrava sem custo nenhum.
checar("e ela NAO conta como item sem custo", (r or {}).get("itens_sem_custo") == 0, r)
checar("a resposta diz quantos vieram de ficha em rascunho",
       (r or {}).get("itens_ficha_rascunho") == 1, r)
checar("e a frase avisa", "RASCUNHO" in ((r or {}).get("message") or ""), r)

st, lista_r = chamar("GET", f"/vendas?busca={doc_r}", token=token)
id_venda_r = (lista_r or [{}])[0].get("id")
st, dr = chamar("GET", f"/vendas/{id_venda_r}", token=token)
item_r = (dr.get("itens") or [{}])[0]
# 0,25 kg x 20,00/kg = 5,00 por unidade.
checar("o custo saiu da ficha em rascunho (5,00)",
       abs(float(item_r.get("custo_ficha_unitario") or 0) - 5) < 0.01, item_r)
checar("e a origem NOMEIA o rascunho",
       item_r.get("origem_custo") == "ficha_rascunho", item_r.get("origem_custo"))
checar("o detalhe conta os itens de rascunho para a tela avisar",
       dr.get("itens_ficha_rascunho") == 1, dr)
checar("e o custo teorico da venda deixa de ser zero",
       abs(float(dr.get("custo_teorico") or 0) - 10) < 0.01, dr.get("custo_teorico"))

# 🔑 **A homologada vem PRIMEIRO, sempre.** O rascunho e a reserva e so responde
# quando nao ha versao aprovada vigente — senao homologar uma receita nao mudaria
# o custo de nada.
st, r = chamar("POST", f"/fichas/{ficha_r}/homologar", token=token)
checar("homologar a ficha responde", st == 200, (st, r))
doc_h = f"VENDA-HOM-{marca}"
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "documento": doc_h, "data": str(date.today()), "origem": "MANUAL",
    "itens": [{"id_produto": prato_r, "quantidade": 1,
               "valor_unitario": 30, "descricao": f"Prato rascunho {marca}"}],
}]}, token=token)
checar("depois de homologada, nenhum item e de rascunho",
       (r or {}).get("itens_ficha_rascunho") == 0, r)
st, lista_h = chamar("GET", f"/vendas?busca={doc_h}", token=token)
st, dh = chamar("GET", f"/vendas/{(lista_h or [{}])[0].get('id')}", token=token)
checar("e a origem volta a ser a ficha, sem ressalva",
       (dh.get("itens") or [{}])[0].get("origem_custo") == "ficha",
       (dh.get("itens") or [{}])[0].get("origem_custo"))
# ⚠️ O custo do item JA GRAVADO nao muda: ele e congelado no momento da venda.
st, dr2 = chamar("GET", f"/vendas/{id_venda_r}", token=token)
checar("e a venda anterior guarda o custo que tinha na hora dela",
       abs(float((dr2.get("itens") or [{}])[0].get("custo_ficha_unitario") or 0) - 5) < 0.01,
       dr2.get("itens"))

for _lista in (lista_r, lista_h):
    for _v in (_lista or []):
        chamar("DELETE", f"/vendas/{_v['id']}", token=token)
chamar("DELETE", f"/produtos/{prato_r}", token=token)


print("\n8. o painel abre no dia da ultima venda, e as setas andam entre dias com venda")
# 🔑 **Pedido do dono (03/09/2026).** O painel respondia pelo mes inteiro e nao
# dizia como foi o ultimo dia — que e a primeira coisa que se olha de manha.
# ⚠️ Abre no dia da ULTIMA venda, nao em hoje: de manha, ou num dia em que a
# busca no PDV ainda nao rodou, "hoje" e um dia sem venda nenhuma, e um cartao
# zerado se le como "a casa nao vendeu" — que e diferente de "ainda nao importou".
st, painel = chamar("GET", "/inicio", token=token)
checar("o painel responde", st == 200, st)
# ⚠️ **No MESMO pacote**, nao numa segunda chamada: painel que faz seis
# requisicoes pisca seis vezes.
checar("e traz o dia junto, sem segunda requisicao", "dia" in (painel or {}), list(painel or {}))
dia = (painel or {}).get("dia") or {}
checar("o dia tem as tres informacoes pedidas",
       {"vendas", "receita", "ticket_medio"} <= set(dia), sorted(dia))

st, ultimo = chamar("GET", "/inicio/dia", token=token)
checar("e a rota do dia, sem data, responde o mesmo dia",
       (ultimo or {}).get("dia", {}).get("data") == dia.get("data"),
       (dia.get("data"), (ultimo or {}).get("dia", {}).get("data")))
# 🔑 O dia mais recente NAO tem para onde avancar — e e isso que desliga a seta.
checar("no dia mais recente nao ha proximo", dia.get("proximo") is None, dia.get("proximo"))

# ⚠️ **Ticket medio e receita ÷ numero de VENDAS**, nao ÷ itens: e o quanto cada
# cliente gastou.
if dia.get("vendas"):
    checar("o ticket medio e a receita dividida pelas vendas",
           abs(float(dia["ticket_medio"]) - float(dia["receita"]) / dia["vendas"]) < 0.0001,
           (dia.get("ticket_medio"), dia.get("receita"), dia.get("vendas")))

# 🔑 **As setas andam entre dias que TEM venda, nao entre dias do calendario.**
# Avancar um dia cairia num domingo fechado e mostraria zero — o mesmo engano
# pela outra porta.
if dia.get("anterior"):
    st, r = chamar("GET", f"/inicio/dia?data={dia['anterior']}", token=token)
    d2 = (r or {}).get("dia") or {}
    checar("o dia anterior existe e TEM venda", d2.get("vendas", 0) > 0, d2)
    checar("e o proximo dele aponta de volta para o que estava na tela",
           d2.get("proximo") == dia.get("data"), (d2.get("proximo"), dia.get("data")))

# ⚠️ **Venda CANCELADA nao conta** — aqui como em todo lugar.
doc_c = f"VENDA-DIA-{marca}"
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "documento": doc_c, "data": str(date.today()), "origem": "MANUAL",
    "itens": [{"id_produto": prato, "quantidade": 1, "valor_unitario": 999,
               "descricao": f"Prato venda {marca}"}]}]}, token=token)
st, r = chamar("GET", f"/inicio/dia?data={date.today()}", token=token)
com_ela = (r or {}).get("dia") or {}
st, lista_c = chamar("GET", f"/vendas?busca={doc_c}", token=token)
if lista_c:
    chamar("DELETE", f"/vendas/{lista_c[0]['id']}", token=token)
    st, r = chamar("GET", f"/inicio/dia?data={date.today()}", token=token)
    sem_ela = (r or {}).get("dia") or {}
    checar("cancelar a venda tira ela da contagem do dia",
           sem_ela.get("vendas") == com_ela.get("vendas") - 1,
           (com_ela.get("vendas"), sem_ela.get("vendas")))
    checar("e tira o valor dela junto",
           abs(float(com_ela["receita"]) - float(sem_ela["receita"]) - 999) < 0.01,
           (com_ela.get("receita"), sem_ela.get("receita")))

# ⚠️ **Dia sem venda devolve ticket NULO, nao zero**: um ticket de zero real e
# uma afirmacao, e nao a ausencia de uma.
st, r = chamar("GET", "/inicio/dia?data=2020-01-01", token=token)
vazio = (r or {}).get("dia") or {}
checar("dia sem venda vem com zero venda", vazio.get("vendas") == 0, vazio)
checar("e com ticket medio NULO, nao zero", vazio.get("ticket_medio") is None, vazio)
# ⚠️ E ele ainda diz para onde da para ir: e assim que se volta de um dia vazio.
checar("mas ainda aponta o proximo dia com venda",
       vazio.get("proximo") is not None, vazio)

# ⚠️ **Dinheiro obedece a permissao**, como o resto do painel: quem nao tem
# `cmv.painel` recebe `dia: null`, nao um cartao com o valor zerado.
tk_coz = garantir_cozinha(chamar, token)
if tk_coz:
    st, p_coz = chamar("GET", "/inicio", token=tk_coz)
    checar("quem nao ve dinheiro recebe o dia NULO, nao zerado",
           (p_coz or {}).get("dia") is None, (p_coz or {}).get("dia"))
    st, _ = chamar("GET", "/inicio/dia", token=tk_coz)
    checar("e a rota do dia recusa para ele", st == 403, st)


print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
