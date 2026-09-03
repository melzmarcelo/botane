"""Teste de fumaça do vínculo entre cadastros: o botão Vincular e a fusão.

O sistema recebe produto por três portas — o catálogo do **Omie** (o que a casa
compra), o cardápio do **PDV Legal** (o que a casa vende) e a mão de quem
cadastra. Nenhuma chave impede o mesmo produto de existir duas vezes.

⚠️ **Nada aqui adivinha, e o par que motivou isso está no teste.** Existiu um
detector que cruzava os nomes por semelhança, e ele errava nos dois sentidos:
não achava "BEB CERV HEINEKEN 350ML" contra "CERVEJA HEINEKEN PILSEN" — o mesmo
produto, **63,8%** de semelhança — e juntava "CAKE BOARD N19" com "CAKE BOARD
N21", que são tamanhos diferentes. Nenhum piso separa os dois casos, porque a
diferença não está no texto.

O que este arquivo cobra:

1. `codigo_pdv` é campo do produto, espelho do `codigo_omie`, e **único**
2. a prévia mostra o resultado ANTES — fusão não tem desfazer
3. **a descrição vem do lado do Omie e a curta do lado do PDV**
4. os campos em branco se completam; os preenchidos NÃO são sobrescritos
5. os códigos das duas integrações migram para o mesmo cadastro
6. **dois códigos do PDV viram principal + apelido**, porque o caso é real
7. quem tem história não é absorvido, e a recusa nomeia o que trava
8. os itens de venda mudam de dono e o que estava sem custo ganha custo
9. o absorvido vira **inativo**, nunca apagado

    python tests/smoke_vinculo.py            (API de pé na 9200)
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
from comum import garantir_locais  # noqa: E402

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
        with urllib.request.urlopen(req, dados, timeout=120) as r:
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
garantir_locais(chamar, token)

print("1. o mesmo produto entrando por duas portas")
# ⚠️ Os nomes REAIS do caso do cliente. Nenhum detector honesto os junta.
st, r = chamar("POST", "/produtos", {
    "codigo": f"OM-{marca}", "nome": f"BEB CERV HEINEKEN 350ML {marca}",
    "tipo": "REVENDA", "um_estoque": "UN", "controla_estoque": True, "status": "ATIVO",
    "codigo_omie": f"77{marca}", "ncm": "22030000",
}, token=token)
do_omie = r.get("id")
checar("o cadastro do lado do Omie", st == 201, (st, r))

st, r = chamar("POST", "/produtos", {
    "codigo": f"PDV-{marca}", "nome": f"CERVEJA HEINEKEN PILSEN {marca}",
    "tipo": "PRODUZIDO", "producao_propria": True, "controla_estoque": False,
    "status": "RASCUNHO", "codigo_pdv": f"99{marca}", "marca": "Heineken",
    "cest": "0300100",
}, token=token)
do_pdv = r.get("id")
checar("o cadastro do lado do cardápio", st == 201, (st, r))

st, p = chamar("GET", f"/produtos/{do_pdv}", token=token)
checar("`codigo_pdv` é campo do produto, como o `codigo_omie`",
       p.get("codigo_pdv") == f"99{marca}", p.get("codigo_pdv"))

# ⚠️ Único, como `ux_produto_omie`: dois cadastros com o mesmo código do PDV
# fariam a venda escolher um deles ao acaso.
st, r = chamar("POST", "/produtos", {
    "codigo": f"XX-{marca}", "nome": f"Colidente {marca}", "tipo": "REVENDA",
    "um_estoque": "UN", "status": "ATIVO", "codigo_pdv": f"99{marca}",
}, token=token)
checar("e é ÚNICO — o mesmo código não entra duas vezes", st >= 400, (st, r))

print("\n2. uma venda pelo cadastro do cardápio, sem custo")
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": hoje, "documento": f"VINC-{marca}", "origem": "MANUAL",
    "itens": [{"id_produto": do_pdv, "quantidade": 4, "valor_unitario": 12}],
}]}, token=token)
checar("venda gravada", st == 201 and r.get("importadas") == 1, (st, r))
checar("e o item entrou SEM custo", r.get("itens_sem_custo") == 1, r)
# ⚠️ O cadastro do cardápio não controla estoque: é assim que o saldo do outro
# nunca desce, e a sobra vira "ajuste de inventário" na contagem.
checar("e sem baixar estoque", (r.get("itens_baixados") or 0) == 0, r)

print("\n3. a prévia — fusão não tem desfazer")
st, prev = chamar("GET", f"/produtos/{do_omie}/vincular/previa?id_sai={do_pdv}", token=token)
checar("a prévia responde", st == 200, (st, prev))
checar("e diz que pode", prev.get("pode") is True, prev.get("impedimentos"))
res = prev.get("resultado") or {}
# ⚠️ A afirmação central: os dois nomes têm funções diferentes. O do Omie é o
# fiscal, o que aparece na nota; o do PDV é o que sai no cupom.
checar("a descrição vem do lado do OMIE",
       res.get("nome") == f"BEB CERV HEINEKEN 350ML {marca}", res.get("nome"))
checar("e a descrição curta do lado do PDV",
       res.get("nome_curto") == f"CERVEJA HEINEKEN PILSEN {marca}", res.get("nome_curto"))
checar("a prévia diz de onde veio cada uma",
       (res.get("de_onde") or {}).get("nome") == "omie"
       and (res.get("de_onde") or {}).get("nome_curto") == "pdv", res.get("de_onde"))
checar("os dois códigos ficam no mesmo cadastro",
       res.get("codigo_omie") == f"77{marca}" and res.get("codigo_pdv") == f"99{marca}", res)
checar("e lista os campos que vão ser completados",
       set(prev.get("completa") or []) >= {"marca", "cest"}, prev.get("completa"))
checar("dizendo quantos itens de venda mudam de dono",
       prev.get("itens_de_venda") == 1, prev.get("itens_de_venda"))

st, r = chamar("GET", f"/produtos/{do_omie}/vincular/previa?id_sai={do_omie}", token=token)
checar("conferir consigo mesmo é recusado", st == 400, st)
st, r = chamar("GET", f"/produtos/{do_omie}/vincular/previa?id_sai=99999999", token=token)
checar("cadastro inexistente é 404", st == 404, st)

print("\n4. a recusa: história não muda de cadastro")
st, locais = chamar("GET", "/locais", token=token)
principal = next((x for x in locais if x.get("principal")), locais[0])
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": do_omie, "quantidade": 6, "custo_unitario": 5,
    "id_local": principal["id"], "documento": f"VINC-{marca}",
}, token=token)
checar("o lado do Omie ganha movimento no razão", st == 201, (st, r))

# ⚠️ **A direção é resolvida pelos FATOS, não pela tela.** Antes isto era uma
# recusa: "não pode ser absorvido… faça a fusão a partir dele" — uma resposta que
# já sabia o certo e ainda exigia refazer o caminho noutra tela. Se só um lado tem
# história, não há escolha a fazer: o sistema inverte e DIZ por quê.
st, prev = chamar("GET", f"/produtos/{do_pdv}/vincular/previa?id_sai={do_omie}", token=token)
checar("da tela do que NÃO tem história, a direção inverte",
       prev.get("invertido") is True, prev.get("invertido"))
checar("e o que tem movimento é que fica",
       prev["fica"]["id"] == do_omie, (prev["fica"]["id"], do_omie))
checar("com o motivo dito", "história" in (prev.get("motivo_da_direcao") or ""),
       prev.get("motivo_da_direcao"))
checar("e sem impedimento, porque agora dá", prev.get("pode") is True, prev.get("impedimentos"))

print("\n4b. sem história dos dois lados, quem CONTROLA ESTOQUE fica")
# ⚠️ **O caso real que motivou isto.** "AGUA MINERAL C/GAS 600ML PLATINA" (Omie)
# tinha nota de entrada e fornecedor, mas ZERO movimento no razão — nada que o
# impedisse de ser absorvido. Sem este critério, fundir da tela do cardápio
# deixaria vivo o rascunho do PDV, que nasce SEM controlar estoque: a compra
# deixaria de entrar no razão, calada, e o saldo pararia de existir para o item.
st, r = chamar("POST", "/produtos", {
    "codigo": f"CE-OMIE-{marca}", "nome": f"Agua omie {marca}", "tipo": "REVENDA",
    "um_estoque": "UN", "controla_estoque": True, "status": "ATIVO",
}, token=token)
ce_omie = r.get("id")
checar("um cadastro que controla estoque, sem movimento", st == 201, (st, r))

st, r = chamar("POST", "/produtos", {
    "codigo": f"CE-PDV-{marca}", "nome": f"Agua pdv {marca}", "tipo": "PRODUZIDO",
    "producao_propria": True, "controla_estoque": False, "status": "RASCUNHO",
}, token=token)
ce_pdv = r.get("id")
checar("e o rascunho do cardápio, que não controla", st == 201, (st, r))

st, prev = chamar("GET", f"/produtos/{ce_pdv}/vincular/previa?id_sai={ce_omie}", token=token)
checar("nenhum dos dois tem impedimento", prev.get("pode") is True, prev.get("impedimentos"))
checar("mas a direção inverte mesmo assim", prev.get("invertido") is True, prev)
checar("e quem fica é o que controla estoque",
       prev["fica"]["id"] == ce_omie and prev["fica"]["controla_estoque"] is True, prev["fica"])
checar("com o motivo dito", "controla estoque" in (prev.get("motivo_da_direcao") or ""),
       prev.get("motivo_da_direcao"))

print("\n4c. nota de entrada e fornecedor NÃO travam — são ponteiros")
# ⚠️ A primeira versão barrava os dois, e estava errado: um item de nota diz
# "esta linha é deste produto"; se os dois cadastros são o mesmo produto, a linha
# muda de dono. O caso real foi recusado por uma nota NÃO lançada.
st, forn = chamar("GET", "/fornecedores?limite=1", token=token)
if forn:
    st, r = chamar("PUT", f"/produtos/{ce_omie}", {
        "nome": f"Agua omie {marca}", "tipo": "REVENDA", "um_estoque": "UN",
        "controla_estoque": True, "status": "ATIVO",
        "fornecedores": [{"id_fornecedor": forn[0]["id"], "fator": 1, "preferencial": True}],
    }, token=token)
    checar("o cadastro ganha um fornecedor vinculado", st == 200, (st, r))
    st, prev = chamar("GET", f"/produtos/{ce_pdv}/vincular/previa?id_sai={ce_omie}", token=token)
    checar("e continua podendo ser fundido", prev.get("pode") is True, prev.get("impedimentos"))

print("\n4d. fundir A PARTIR do lado que NAO fica — a direcao invertida")
# 🔑 **O defeito que a tela teve (03/09/2026, achado pelo dono).** Vincular dois
# cadastros do Omie funcionava; um do PDV com um do Omie devolvia "Escolha dois
# cadastros diferentes" — com dois cadastros diferentes escolhidos.
#
# A causa: a PRÉVIA resolve a direção e devolve `id_sai`. Quando ela inverte,
# `id_sai` É o cadastro em que a pessoa está — e a tela mandava esse `id_sai` de
# volta como "o que sai", chegando ao servidor com o mesmo id dos dois lados.
# Entre dois do Omie não há inversão (nenhum controla estoque a mais que o
# outro), e por isso aquele caminho passava.
#
# O que se cobra aqui é a PROPRIEDADE que faltava: **fundir a partir de
# QUALQUER um dos dois lados chega no mesmo resultado**. A suíte já provava que
# a prévia inverte; nunca provava que a fusão acontece a partir do lado
# invertido, que era justamente o caminho quebrado.
st, r = chamar("POST", f"/produtos/{ce_pdv}/vincular", {"id_sai": ce_omie}, token=token)
checar("fundir estando no cadastro que SAI e aceito", st == 200, (st, r))
checar("e o servidor diz que inverteu", (r or {}).get("invertido") is True, r)
# ⚠️ Quem fica e o que CONTROLA ESTOQUE, mesmo tendo sido o "escolhido": sem
# isso o rascunho do PDV sobreviveria e a compra deixaria de entrar no razao.
checar("quem ficou foi o que controla estoque",
       (r or {}).get("fica", {}).get("id") == ce_omie, r.get("fica"))
checar("e quem saiu foi o cadastro em que a pessoa estava",
       (r or {}).get("saiu", {}).get("id") == ce_pdv, r.get("saiu"))
st, sobrou = chamar("GET", f"/produtos/{ce_omie}", token=token)
checar("o sobrevivente continua ativo e controlando estoque",
       sobrou.get("ativo") is True and sobrou.get("controla_estoque") is True, sobrou)
st, foi = chamar("GET", f"/produtos/{ce_pdv}", token=token)
checar("e o outro virou arquivado", foi.get("status") == "ARQUIVADO", foi.get("status"))
# ⚠️ **Mandar o mesmo id dos dois lados continua sendo recusado** — a trava e
# certa, e era a tela que a acionava sem querer. Tirar a trava esconderia o
# defeito em vez de corrige-lo.
st, r = chamar("POST", f"/produtos/{ce_omie}/vincular", {"id_sai": ce_omie}, token=token)
checar("mandar o mesmo cadastro dos dois lados continua recusado", st == 400, (st, r))


print("\n4e. os cadastros com o MESMO NOME, em lote — o ABACATE")
# 🔑 **Pedido do dono (03/09/2026).** O catálogo do Omie cria um cadastro por
# CÓDIGO, e o mesmo abacate aparece uma vez para cada fornecedor que já o vendeu.
# Juntar de dois em dois pela tela resolve, mas com centenas ninguém percorre a
# lista — e o trabalho não é feito.
#
# ⚠️ **Isto DETECTA, e quem decide é gente.** O projeto já removeu uma cascata
# que vinculava sozinha por semelhança de nome. Nome IDÊNTICO é um sinal muito
# mais forte — mas continua sendo um sinal, e a fusão não tem desfazer.
abac = []
for i in range(3):
    st, r = chamar("POST", "/produtos", {
        # ⚠️ Prefixo PRÓPRIO: `ABA1-`/`ABA2-` já são da fase 7, e o 409 do código
        # repetido aparecia como "o abacate principal falhou" doze checagens
        # adiante. Cada fase procura (e cria) os registros DELA.
        "codigo": f"LOTE{i}-{marca}", "nome": f"ABACATE LOTE {marca}", "tipo": "INSUMO",
        "um_estoque": "KG", "controla_estoque": True, "status": "ATIVO",
        "codigo_omie": f"6{i}{marca}",
    }, token=token)
    abac.append((r or {}).get("id"))
checar("tres cadastros com o mesmo nome, codigos diferentes", all(abac), abac)

st, grupos = chamar("GET", "/produtos/duplicados?so_do_omie=true&limite=200", token=token)
meu = next((g for g in (grupos or []) if g["nome"] == f"ABACATE LOTE {marca}"), None)
checar("a lista de duplicados acha o grupo", meu is not None, len(grupos or []))
if meu:
    checar("com os tres juntos", meu["quantos"] == 3, meu["quantos"])
    checar("e diz que da para juntar", meu["pode"] is True, meu)
    # ⚠️ O principal e resolvido pelos MESMOS criterios da tela; sem historia
    # nem diferenca de controle de estoque, o desempate e o menor id — o mais
    # antigo —, que e o unico criterio estavel num grupo sem "a tela".
    checar("o principal e o cadastro mais antigo do grupo",
           meu["id_principal"] == min(abac), (meu["id_principal"], abac))
    # ⚠️ Cada linha traz o CODIGO de cada cadastro: e o que permite reconhecer
    # que "VALE-PRESENTE" sao tres valores diferentes ANTES de juntar.
    checar("e cada linha mostra o codigo externo de cada um",
           all(i.get("codigo_omie") for i in meu["itens"]), meu["itens"])

st, r = chamar("POST", "/produtos/duplicados/fundir", {
    "id_principal": abac[0], "ids_que_saem": abac[1:], "baixar_vendas": True}, token=token)
checar("juntar o grupo inteiro responde", st == 200, (st, r))
checar("e diz quantos foram absorvidos", len((r or {}).get("juntados") or []) == 2, r)

st, fica = chamar("GET", f"/produtos/{abac[0]}", token=token)
checar("o principal continua ativo", fica.get("ativo") is True, fica.get("ativo"))
# 🔑 **A razao de existir: os codigos dos absorvidos viram APELIDOS.** Sem isso a
# proxima nota que trouxesse o codigo de um deles nao acharia o principal, o item
# cairia na fila de pendentes, e quem clicasse em "criar produto" recriaria o
# duplicado — o trabalho de juntar se desfazendo sozinho.
apelidos = {c["codigo"] for c in (fica.get("codigos_externos") or [])}
checar("e os codigos dos absorvidos passam a cair nele",
       {f"6{i}{marca}" for i in (1, 2)} <= apelidos, sorted(apelidos))
for i in abac[1:]:
    st, saiu = chamar("GET", f"/produtos/{i}", token=token)
    checar(f"o cadastro {i} virou arquivado", saiu.get("status") == "ARQUIVADO",
           saiu.get("status"))
    # ⚠️ A coluna e zerada junto: ela e unica, e deixa-la la manteria o codigo
    # preso a um cadastro arquivado.
    checar(f"e o codigo_omie de {i} foi zerado", saiu.get("codigo_omie") is None,
           saiu.get("codigo_omie"))

# ⚠️ **O grupo some da lista depois de junto**, porque so ATIVOS entram: sem
# isso a lista nunca esvaziaria, propondo de novo o que ja foi feito.
st, grupos = chamar("GET", "/produtos/duplicados?so_do_omie=true&limite=200", token=token)
checar("e o grupo sai da lista depois de junto",
       not any(g["nome"] == f"ABACATE LOTE {marca}" for g in (grupos or [])), grupos)

# ⚠️ Mandar o principal na lista dos que saem seria o mesmo id dos dois lados —
# o defeito que a tela do Vincular teve.
st, r = chamar("POST", "/produtos/duplicados/fundir",
               {"id_principal": abac[0], "ids_que_saem": [abac[0]]}, token=token)
checar("o principal na lista dos que saem e recusado", st == 400, (st, r))
st, r = chamar("POST", "/produtos/duplicados/fundir",
               {"id_principal": abac[0], "ids_que_saem": []}, token=token)
checar("e lista vazia tambem", st == 400, (st, r))

# 🔑 **Grupo com DOIS que tem historia nao se junta**, e a lista DIZ isso em vez
# de omitir: unir dois razoes exigiria reescrever movimento, e o custo medio
# resultante seria invencao.
st, locais_d = chamar("GET", "/locais", token=token)
local_d = next((x for x in locais_d if x.get("principal")), locais_d[0])
hist = []
for i in range(2):
    st, r = chamar("POST", "/produtos", {
        "codigo": f"HIST{i}-{marca}", "nome": f"COM HISTORIA {marca}", "tipo": "INSUMO",
        "um_estoque": "KG", "controla_estoque": True, "status": "ATIVO"}, token=token)
    hist.append((r or {}).get("id"))
    chamar("POST", "/estoque/entradas", {
        "id_produto": hist[i], "quantidade": 1, "custo_unitario": 5,
        "id_local": local_d["id"]}, token=token)
st, grupos = chamar("GET", "/produtos/duplicados?limite=300", token=token)
com_hist = next((g for g in (grupos or []) if g["nome"] == f"COM HISTORIA {marca}"), None)
checar("o grupo com dois historicos aparece na lista", com_hist is not None, com_hist)
if com_hist:
    checar("mas marcado como NAO podendo ser junto", com_hist["pode"] is False, com_hist)
    checar("e nomeando quem impede", len(com_hist["impedidos"]) >= 1, com_hist["impedidos"])
st, r = chamar("POST", "/produtos/duplicados/fundir",
               {"id_principal": hist[0], "ids_que_saem": [hist[1]]}, token=token)
checar("e juntar assim mesmo e recusado, com a frase", st == 400, (st, r))
checar("dizendo que tem historia", "história" in str((r or {}).get("detail", "")), r)
for i in hist:
    chamar("DELETE", f"/produtos/{i}", token=token)


print("\n5. a fusão, na direção certa")
st, r = chamar("POST", f"/produtos/{do_omie}/vincular", {"id_sai": do_pdv}, token=token)
checar("vincular responde", st == 200, (st, r))
checar("moveu o item de venda", r.get("itens_de_venda") == 1, r)
checar("e ele ganhou custo (o do Omie tem custo médio)",
       r.get("itens_que_ganharam_custo") == 1, r)
checar("completou marca e cest", set(r.get("completados") or []) >= {"marca", "cest"}, r)

st, fica = chamar("GET", f"/produtos/{do_omie}", token=token)
checar("a descrição ficou a do Omie",
       fica.get("nome") == f"BEB CERV HEINEKEN 350ML {marca}", fica.get("nome"))
checar("a curta ficou a do PDV",
       fica.get("nome_curto") == f"CERVEJA HEINEKEN PILSEN {marca}", fica.get("nome_curto"))
checar("o código do PDV migrou", fica.get("codigo_pdv") == f"99{marca}", fica.get("codigo_pdv"))
checar("o do Omie continua", fica.get("codigo_omie") == f"77{marca}", fica.get("codigo_omie"))
# ⚠️ Não sobrescreve: o NCM era do cadastro que fica e continua sendo dele.
checar("o que já estava preenchido NÃO foi sobrescrito",
       fica.get("ncm") == "22030000", fica.get("ncm"))
checar("marca veio do que saiu", fica.get("marca") == "Heineken", fica.get("marca"))

st, saiu = chamar("GET", f"/produtos/{do_pdv}", token=token)
checar("o absorvido virou inativo, não sumiu",
       saiu.get("ativo") is False and saiu.get("status") == "ARQUIVADO",
       (saiu.get("ativo"), saiu.get("status")))
checar("e a observação diz para onde ele foi",
       "Fundido em" in (saiu.get("observacao") or ""), saiu.get("observacao"))
checar("e ele perdeu o código do PDV, que agora é do outro",
       saiu.get("codigo_pdv") is None, saiu.get("codigo_pdv"))

print("\n5b. o que foi vendido e nunca saiu do estoque BAIXA na fusão")
# ⚠️ **O cenário que o dono descreveu, e é a razão de a fusão existir:**
#
#     PRODUTO PDV    estoque  0   vendas 10
#     PRODUTO OMIE   estoque 15   vendas  0
#     ao vincular →  estoque  5   vendas 10
#
# O item do cardápio vendia sem baixar estoque (nasce sem controlar). Sem esta
# saída, o resultado seria "comprou 15, vendeu 10, saldo 15" — e as 10 faltando
# apareceriam na primeira contagem como AJUSTE DE INVENTÁRIO, que é exatamente
# onde a diferença some sem nome.
st, r = chamar("POST", "/produtos", {
    "codigo": f"BX-OMIE-{marca}", "nome": f"Baixa omie {marca}", "tipo": "REVENDA",
    "um_estoque": "UN", "controla_estoque": True, "status": "ATIVO",
    "codigo_omie": f"55{marca}",
}, token=token)
bx_omie = r.get("id")
checar("o lado das compras", st == 201, (st, r))

st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": bx_omie, "quantidade": 15, "custo_unitario": 8,
    "id_local": principal["id"], "documento": f"BX-{marca}",
}, token=token)
checar("entra 15 no estoque", st == 201, (st, r))

st, r = chamar("POST", "/produtos", {
    "codigo": f"BX-PDV-{marca}", "nome": f"Baixa pdv {marca}", "tipo": "PRODUZIDO",
    "producao_propria": True, "controla_estoque": False, "status": "RASCUNHO",
    "codigo_pdv": f"66{marca}",
}, token=token)
bx_pdv = r.get("id")
checar("o lado das vendas, sem controlar estoque", st == 201, (st, r))

st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": hoje, "documento": f"BXV-{marca}", "origem": "PDV_LEGAL",
    "itens": [{"id_produto": bx_pdv, "quantidade": 10, "valor_unitario": 20}],
}]}, token=token)
checar("vende 10 pelo cadastro do cardápio", st == 201, (st, r))
# ⚠️ A venda NÃO baixou nada: é assim que o buraco nasce.
checar("e nada baixou do estoque", (r.get("itens_baixados") or 0) == 0, r)


def _saldo(id_produto):
    st, s = chamar("GET", f"/estoque/saldos?id_produto={id_produto}", token=token)
    return sum(float(x["quantidade"]) for x in (s or []))


checar("antes: o lado das compras tem 15", _saldo(bx_omie) == 15, _saldo(bx_omie))

st, prev = chamar("GET", f"/produtos/{bx_omie}/vincular/previa?id_sai={bx_pdv}", token=token)
baixa = prev.get("baixa") or {}
# ⚠️ O número aparece ANTES do botão: é movimento de estoque, não pode ser
# surpresa. E o saldo resultante vem junto, porque é o que a pessoa confere.
checar("a prévia diz quanto vai baixar", baixa.get("quantidade") == 10, baixa)
checar("e qual saldo vai sobrar", baixa.get("saldo_depois") == 5, baixa)
checar("dizendo que não fica negativo", baixa.get("fica_negativo") is False, baixa)
checar("e de qual prateleira sai", baixa.get("local") is not None, baixa)

st, r = chamar("POST", f"/produtos/{bx_omie}/vincular", {"id_sai": bx_pdv}, token=token)
checar("a fusão responde", st == 200, (st, r))
checar("e conta a baixa", r.get("baixa_de_estoque") == 10, r)
# 15 comprados − 10 vendidos = 5. É a conta que o dono descreveu.
checar("DEPOIS: estoque 5, que é 15 menos os 10 vendidos", _saldo(bx_omie) == 5, _saldo(bx_omie))

st, mg = chamar("GET", f"/cmv/margem?id_produto={bx_omie}", token=token)
checar("e as 10 vendas passaram para o cadastro que ficou",
       sum(float(x["quantidade"]) for x in (mg or [])) == 10, mg)

# ⚠️ O tipo é SAIDA_VENDA, não ajuste: aquelas unidades foram vendidas mesmo.
# Como ajuste, engordariam a linha do CMV que quer dizer "não sabemos o que houve".
st, movs = chamar("GET", f"/estoque/movimentos?id_produto={bx_omie}", token=token)
a_baixa = next((x for x in (movs or []) if (x.get("documento") or "").startswith("vinculo-")), None)
checar("o movimento existe e é do tipo SAIDA_VENDA",
       a_baixa and a_baixa["tipo"] == "SAIDA_VENDA", a_baixa)
checar("com a observação dizendo de onde veio",
       a_baixa and "nunca baixaram estoque" in (a_baixa.get("observacao") or ""), a_baixa)

print("\n5c. e dá para NÃO baixar, sabendo do que se abre mão")
st, r = chamar("POST", "/produtos", {
    "codigo": f"BX2-OMIE-{marca}", "nome": f"Sem baixa omie {marca}", "tipo": "REVENDA",
    "um_estoque": "UN", "controla_estoque": True, "status": "ATIVO",
}, token=token)
sb_omie = r.get("id")
chamar("POST", "/estoque/entradas", {
    "id_produto": sb_omie, "quantidade": 8, "custo_unitario": 4,
    "id_local": principal["id"], "documento": f"BX2-{marca}",
}, token=token)
st, r = chamar("POST", "/produtos", {
    "codigo": f"BX2-PDV-{marca}", "nome": f"Sem baixa pdv {marca}", "tipo": "PRODUZIDO",
    "producao_propria": True, "controla_estoque": False, "status": "RASCUNHO",
}, token=token)
sb_pdv = r.get("id")
chamar("POST", "/vendas/importar", {"vendas": [{
    "data": hoje, "documento": f"BX2V-{marca}", "origem": "MANUAL",
    "itens": [{"id_produto": sb_pdv, "quantidade": 3, "valor_unitario": 9}],
}]}, token=token)

st, r = chamar("POST", f"/produtos/{sb_omie}/vincular",
               {"id_sai": sb_pdv, "baixar_vendas": False}, token=token)
checar("com `baixar_vendas: false` a fusão acontece", st == 200, (st, r))
checar("e NÃO baixa nada", r.get("baixa_de_estoque") is None, r)
checar("o saldo fica como estava", _saldo(sb_omie) == 8, _saldo(sb_omie))


print("\n6. dois códigos do PDV: principal e apelido")
# ⚠️ **O caso é REAL**: "ENTREGA" tem QUATRO códigos de cardápio distintos na
# conta do cliente. Uma coluna sozinha guardaria um, e os outros voltariam a
# virar rascunho na importação seguinte — o duplicado renascendo sozinho.
st, r = chamar("POST", "/produtos", {
    "codigo": f"PDV2-{marca}", "nome": f"HEINEKEN LONG NECK {marca}",
    "tipo": "PRODUZIDO", "producao_propria": True, "controla_estoque": False,
    "status": "RASCUNHO", "codigo_pdv": f"88{marca}",
}, token=token)
outro_pdv = r.get("id")
checar("um segundo cadastro do cardápio", st == 201, (st, r))

st, r = chamar("POST", f"/produtos/{do_omie}/vincular", {"id_sai": outro_pdv}, token=token)
checar("a fusão aceita, mesmo com os dois tendo código do PDV", st == 200, (st, r))
checar("e o segundo código virou APELIDO", r.get("apelido_pdv") == f"88{marca}", r)

st, fica = chamar("GET", f"/produtos/{do_omie}", token=token)
checar("o principal continua sendo o primeiro",
       fica.get("codigo_pdv") == f"99{marca}", fica.get("codigo_pdv"))
checar("e o apelido aparece na tela do produto",
       f"88{marca}" in (fica.get("apelidos_pdv") or []), fica.get("apelidos_pdv"))

# ⚠️ O que importa de verdade: a venda que chegar com o APELIDO acha o produto.
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": hoje, "documento": f"VINC2-{marca}", "origem": "PDV_LEGAL",
    "itens": [{"codigo": f"88{marca}", "descricao": "Long neck",
               "quantidade": 2, "valor_unitario": 14}],
}]}, token=token)
# O importador de vendas resolve por `codigo` da casa e por nome; o de-para do
# PDV é aplicado pelo importador do PDV. Aqui a checagem é a da fila:
st, fila = chamar("GET", "/vendas/sem-vinculo", token=token)
st, rec = chamar("POST", "/pdv/reconciliar", token=token)
checar("a reconciliação acha o produto pelo apelido",
       (rec.get("vinculados") or 0) >= 1, rec)

print()
print("7. dois códigos do OMIE: o de sair virava LIXO")
# 🔑 **O caso do ABACATE.** O catálogo do Omie cria um cadastro por código, e o
# mesmo abacate aparece uma vez por fornecedor. A fusão DESCARTAVA o
# `codigo_omie` do absorvido — enquanto o do PDV virava apelido, na mesma
# função. O efeito: na primeira nota que trouxesse o código do absorvido, o
# sistema não achava o principal (a cascata filtra `AND ativo`, e ele está
# arquivado), o item caía na fila de pendentes e quem clicasse em "criar
# produto" recriava o duplicado. O trabalho de juntar se desfazia sozinho.
st, r = chamar("POST", "/produtos", {
    "codigo": f"ABA1-{marca}", "nome": f"ABACATE PRINCIPAL {marca}",
    "tipo": "INSUMO", "um_estoque": "KG", "controla_estoque": True,
    "codigo_omie": f"OM1{marca}",
}, token=token)
abacate = r.get("id")
checar("o abacate principal", st == 201, (st, r))
st, r = chamar("POST", "/produtos", {
    "codigo": f"ABA2-{marca}", "nome": f"ABACATE DO OUTRO FORNECEDOR {marca}",
    "tipo": "INSUMO", "um_estoque": "KG", "controla_estoque": True,
    "codigo_omie": f"OM2{marca}",
}, token=token)
abacate_dup = r.get("id")
checar("e o duplicado que o catálogo criou", st == 201, (st, r))

st, r = chamar("POST", f"/produtos/{abacate}/vincular", {"id_sai": abacate_dup}, token=token)
checar("a fusão aceita os dois com código do Omie", st == 200, (st, r))
checar("e o do absorvido virou APELIDO, não lixo",
       r.get("apelido_omie") == f"OM2{marca}", r)

st, fica = chamar("GET", f"/produtos/{abacate}", token=token)
codigos = {(c["sistema"], c["codigo"]) for c in (fica.get("codigos_externos") or [])}
checar("o principal continua com o código dele",
       fica.get("codigo_omie") == f"OM1{marca}", fica.get("codigo_omie"))
checar("e o outro aparece na lista de códigos do produto",
       ("OMIE_PRODUTO", f"OM2{marca}") in codigos, codigos)
# ⚠️ A coluna do absorvido é zerada: ela é única, e deixá-la lá manteria o
# código preso a um cadastro arquivado.
st, saiu = chamar("GET", f"/produtos/{abacate_dup}", token=token)
checar("e o absorvido não guarda mais o código", saiu.get("codigo_omie") is None,
       saiu.get("codigo_omie"))

# 🔑 **A PROMESSA INTEIRA: a nota com o código do absorvido cai no principal.**
# Tudo o mais neste bloco é meio do caminho — o que importa é onde o estoque
# entra. A checagem chama a própria cascata, que é quem decide o dono do item:
# pela HTTP só se chegaria aqui com uma nota do Omie inteira, e o que se quer
# provar é a decisão, não o transporte.
sys.path.insert(0, ".")
from database import get_cursor as _cursor                    # noqa: E402
from services.omie.importador import conciliar_item           # noqa: E402
with _cursor() as _cur:
    _antes = conciliar_item(_cur, {"codigo_omie": f"OM2{marca}"}, None)
checar("a nota com o código do ABSORVIDO cai no principal",
       _antes[0] == abacate, (_antes[0], abacate))
checar("e o caminho é o do código do Omie, não um palpite",
       _antes[3] == "codigo_omie", _antes[3])
# 🔑 **E o CATÁLOGO tem de achar o mesmo — senão o duplicado renasce por outra
# porta.** A importação procurava só pela COLUNA `codigo_omie`; ao juntar, a do
# absorvido é zerada e o código só existe como apelido: a consulta não achava
# nada e um rascunho novo era criado, desfazendo o trabalho de juntar. Mesmo
# defeito da cascata da nota, pela porta do lado.
with _cursor() as _cur:
    _cur.execute("SELECT id FROM produtos WHERE codigo_omie = %s", (f"OM2{marca}",))
    _pela_coluna = _cur.fetchone()
    _cur.execute("""SELECT id_produto FROM codigos_externos
                     WHERE sistema = 'OMIE_PRODUTO' AND codigo = %s""", (f"OM2{marca}",))
    _pelo_apelido = _cur.fetchone()
checar("a coluna do absorvido foi zerada — o catálogo não o acha por ela",
       _pela_coluna is None, _pela_coluna)
checar("mas o apelido responde, e é ele que evita o rascunho duplicado",
       (_pelo_apelido or {}).get("id_produto") == abacate, _pelo_apelido)

print()
print("7b. a prévia MOSTRA por quais códigos o cadastro vai responder")
# 🔑 **É o que faz a fusão em lote ser confiável.** Juntar os cinco abacates só
# se decide vendo, ANTES de confirmar, que o principal passa a responder pelos
# cinco códigos de lá — senão a pessoa confirma no escuro e descobre depois, na
# nota que não achou dono.
st, r = chamar("POST", "/produtos", {
    "codigo": f"ABA3-{marca}", "nome": f"ABACATE TERCEIRO {marca}",
    "tipo": "INSUMO", "um_estoque": "KG", "controla_estoque": True,
    "codigo_omie": f"OM3{marca}",
}, token=token)
terceiro = r.get("id")
st, prev = chamar("GET", f"/produtos/{abacate}/vincular/previa?id_sai={terceiro}", token=token)
linhas = prev.get("codigos_externos") or []
por_codigo = {l["codigo"]: l for l in linhas}
checar("a prévia traz as linhas de código do resultado", st == 200 and linhas, (st, linhas))
checar("o código do que FICA aparece como principal",
       por_codigo.get(f"OM1{marca}", {}).get("origem") == "principal", por_codigo)
checar("e o do que SAI aparece como apelido — não some",
       por_codigo.get(f"OM3{marca}", {}).get("origem") == "vira apelido", por_codigo)
# ⚠️ O apelido que a fusão anterior criou continua na lista: ele JÁ aponta.
checar("e o que já apontava continua listado",
       por_codigo.get(f"OM2{marca}", {}).get("origem") == "já aponta", por_codigo)

# ⚠️ Sem código do lado que fica, o do absorvido sobe a PRINCIPAL em vez de
# virar apelido — a prévia tem de dizer o mesmo que `_absorver` faz.
st, r = chamar("POST", "/produtos", {
    "codigo": f"ABA4-{marca}", "nome": f"ABACATE SEM CODIGO {marca}",
    "tipo": "INSUMO", "um_estoque": "KG", "controla_estoque": True}, token=token)
sem_codigo = r.get("id")
st, prev = chamar("GET", f"/produtos/{sem_codigo}/vincular/previa?id_sai={terceiro}",
                  token=token)
linhas = {l["codigo"]: l for l in (prev.get("codigos_externos") or [])}
checar("com o lado que fica vazio, o código do absorvido vira o PRINCIPAL",
       linhas.get(f"OM3{marca}", {}).get("origem") == "principal", linhas)

for _p in (abacate, terceiro, sem_codigo):
    chamar("DELETE", f"/produtos/{_p}", token=token)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
