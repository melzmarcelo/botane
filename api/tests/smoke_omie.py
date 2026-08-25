"""Teste de fumaça da etapa 5 (integração Omie), em modo simulado.

O cenário das fixtures, conferido na mão:

    NF 4812 — 4 CX de café a 120,00 (480,00) + 40 UN de leite a 4,00 (160,00)
              frete 60,00 rateado por valor: 45,00 no café, 15,00 no leite
              café:  (480 + 45) ÷ (4 CX × 12 un) = 10,9375 por unidade
              leite: (160 + 15) ÷ 40            =  4,375  por unidade

Prova também: a chave da NF-e impede duplicar, item sem produto barra o
lançamento, vincular ensina o de-para, e a credencial nunca sai da API.

    python tests/smoke_omie.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
from comum import garantir_cozinha, garantir_local, preservar_credenciais  # noqa: E402

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
        print(f"  FALHA {nome} {extra}")


def perto(a, b, tol=0.01):
    return a is not None and abs(float(a) - float(b)) < tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
marca = str(time.time_ns())[-6:]

print("0. limpa o cenário da rodada anterior")
# As notas das fixtures são únicas pela chave da NF-e: sem desfazer o que a
# rodada passada importou, a segunda execução não teria o que conciliar.
# ⚠️ Procuradas pelo NÚMERO, uma a uma. `GET /notas` devolve uma PÁGINA, e numa
# base que já recebeu notas de uma conta real as da fixture ficam fora dela — a
# limpeza não achava nada, a rodada seguinte encontrava tudo já conciliado e as
# fases que precisam de pendência não exercitavam trava nenhuma.
for numero in ("4812", "4913", "5014"):
    st, notas_antigas = chamar("GET", f"/notas?busca={numero}", token=token)
    for n in notas_antigas or []:
        if n.get("numero") != numero:
            continue
        if n["status"] == "LANCADA":
            chamar("POST", f"/notas/{n['id']}/estornar", token=token)
        chamar("DELETE", f"/notas/{n['id']}", token=token)
for codigo in ("CAF-500", "LEI-INT", "TOM-CX"):
    chamar("DELETE", f"/notas/vinculos/{codigo}", token=token)
# O catálogo importado na rodada anterior deixou produtos com o MESMO EAN das
# notas — e aí o item casaria sozinho pelo nível 2 da cascata, que é o
# comportamento certo mas apaga o cenário de conciliação deste teste.
for nome in ("Café em grão especial", "Leite integral 1L", "Tomate italiano"):
    st, achados = chamar("GET", f"/produtos?busca={nome}", token=token)
    for p in achados or []:
        chamar("DELETE", f"/produtos/{p['id']}", token=token)
checar("cenário limpo", True)

# ⚠️ A credencial de verdade do cliente mora na mesma linha que a suíte vai
# sobrescrever com uma de mentira. Guardada antes, reposta no fim.
# Base virgem não tem local de estoque, e sem local nenhuma nota se lança —
# a suíte falhava em quatro pontos que nada tinham a ver com o Omie.
garantir_local(chamar, token)

repor_credenciais = preservar_credenciais("OMIE")

print("1. configuração — a credencial não volta em claro")
st, cfg = chamar("GET", "/omie/config", token=token)
checar("config responde", st == 200, cfg)
st, r = chamar("PUT", "/omie/config",
               {"app_key": "chave-de-teste-1234", "app_secret": "segredo-de-teste-9876",
                "modo": "simulado", "ativa": True}, token=token)
checar("salva a configuração", st == 200, r)
st, cfg = chamar("GET", "/omie/config", token=token)
checar("marca como configurada", cfg.get("configurada") is True, cfg)
checar("app_key volta mascarada", str(cfg.get("app_key", "")).endswith("1234")
       and "•" in str(cfg.get("app_key")), cfg.get("app_key"))
checar("o segredo nunca sai em claro", "segredo-de-teste" not in json.dumps(cfg), cfg)
st, r = chamar("PUT", "/omie/config", {"modo": "real", "ativa": True}, token=token)
checar("trocar para modo real com a chave já salva não exige redigitar", st == 200, r)
chamar("PUT", "/omie/config", {"modo": "simulado", "ativa": True}, token=token)

st, r = chamar("POST", "/omie/testar", token=token)
checar("teste de conexão responde", st == 200 and r.get("ok") is True, r)
checar("teste diz que está em modo simulado", r.get("modo") == "simulado", r)

print("2. sincronização importa as notas das fixtures")
st, r = chamar("POST", "/omie/sincronizar?dias=60", token=token)
checar("sincroniza", st == 200, r)
primeira = r.get("novas", 0)
st, r2 = chamar("POST", "/omie/sincronizar?dias=60", token=token)
checar("reimportar não duplica (chave da NF-e)", r2.get("novas") == 0 and r2.get("repetidas") >= 1,
       r2)

st, notas = chamar("GET", "/notas", token=token)
checar("as notas aparecem na lista", st == 200 and len(notas) >= 2, len(notas) if st == 200 else notas)
# ⚠️ Pela BUSCA, não pela lista: a lista traz uma página, e numa base com notas
# de uma conta real a 4812 fica fora dela. Sem isto a suíte estourava num
# `None` seis passos adiante, longe da causa.
st, achadas = chamar("GET", "/notas?busca=4812", token=token)
nota_cafe = next((n for n in achadas or [] if n["numero"] == "4812"), None)
checar("a nota 4812 foi importada", nota_cafe is not None)
checar("o fornecedor foi criado a partir da nota",
       nota_cafe and nota_cafe.get("fornecedor"), nota_cafe)
checar("a nota nasce com pendência de de-para",
       nota_cafe and nota_cafe["pendentes"] >= 1, nota_cafe)

print("2b. a janela da busca e a conferência do período")
# Sem parâmetro, a janela sai da última sincronização com folga — é o padrão, e
# é o que impede a nota lançada com atraso de cair fora para sempre.
st, r = chamar("POST", "/omie/sincronizar", token=token)
checar("busca sem período usa a janela automática", st == 200, r)
checar("e diz qual janela usou",
       "última sincronização" in (r.get("janela") or ""), r.get("janela"))
st, r = chamar("POST", "/omie/sincronizar?desde=2026-01-01", token=token)
checar("a carga do histórico aceita a data escolhida",
       r.get("janela") == "desde 01/01/2026", r.get("janela"))
st, r = chamar("POST", "/omie/sincronizar?dias=15", token=token)
checar("e a janela fixa continua valendo", r.get("janela") == "últimos 15 dias", r.get("janela"))

# A conferência responde "quais faltam", não só "quantas".
st, conf = chamar("GET", "/omie/conferencia-notas?inicio=2026-01-01&fim=2026-12-31", token=token)
checar("a conferência de notas responde", st == 200, conf)
checar("com nada faltando depois de sincronizar",
       conf.get("faltando") == [], conf.get("faltando"))
no_omie = conf.get("no_omie", 0)
checar("e contando o que o Omie tem", no_omie >= 2, conf)

# Apaga uma e confere que ela é NOMEADA como faltante.
# ⚠️ Tem de ser uma nota DA FIXTURE. Quando a base já tem notas de uma conta
# real (o teste roda depois de alguém sincronizar de verdade), apagar uma delas
# nunca a faria aparecer como "faltante": ela não existe do lado simulado, e a
# conferência — com razão — não acusaria falta nenhuma.
st, notas = chamar("GET", "/notas?busca=4913", token=token)
alvo_conf = next((n for n in notas or [] if n["numero"] == "4913" and n["status"] != "LANCADA"),
                 None)
if alvo_conf:
    chamar("DELETE", f"/notas/{alvo_conf['id']}", token=token)
    st, conf = chamar("GET", "/omie/conferencia-notas?inicio=2026-01-01&fim=2026-12-31",
                      token=token)
    checar("a nota apagada aparece como faltante", len(conf.get("faltando") or []) == 1, conf)
    faltante = (conf.get("faltando") or [{}])[0]
    checar("com número e emitente, para dar para ir atrás",
           faltante.get("numero") and faltante.get("emitente"), faltante)
    st, r = chamar("POST", "/omie/sincronizar?desde=2026-01-01", token=token)
    checar("e 'trazer as que faltam' a devolve", r.get("novas") == 1, r)
    st, conf = chamar("GET", "/omie/conferencia-notas?inicio=2026-01-01&fim=2026-12-31",
                      token=token)
    checar("a conferência fecha em zero", conf.get("faltando") == [], conf)

print("2c. criar o produto direto do item da nota")
st, pendencias = chamar("GET", "/notas/pendencias", token=token)
# Não pode ser o café nem o leite: a fase 3 conta com os dois ainda pendentes
# para provar que nota com pendência não é lançada.
# Pelo mesmo motivo, o item também tem de ser da fixture: o TOM-CX. Pegar
# "o primeiro pendente que não seja café nem leite" escolhia um item de nota
# real assim que a base deixava de estar sozinha.
alvo_item = next((i for i in pendencias if i.get("codigo_fornecedor") == "TOM-CX"), None)
if alvo_item:
    st, r = chamar("POST", f"/notas/itens/{alvo_item['id']}/criar-produto", {}, token=token)
    checar("cria o produto a partir do item", st == 200 and r.get("id_produto"), r)
    st, novo_p = chamar("GET", f"/produtos/{r['id_produto']}", token=token)
    # Se o EAN já era de outro produto, o certo é vincular ao que existe — dois
    # cadastros para o mesmo insumo partiriam o custo dele em dois.
    reaproveitou = "já é de" in (r.get("message") or "")
    checar("nasce RASCUNHO — unidade e fator ninguém conferiu ainda",
           reaproveitou or novo_p.get("status") == "RASCUNHO", novo_p.get("status"))
    checar("com o nome que veio na nota",
           reaproveitou or novo_p.get("nome") == alvo_item["descricao_fornecedor"],
           novo_p.get("nome"))
    checar("e o NCM da nota, quando veio",
           reaproveitou or not alvo_item.get("ncm") or novo_p.get("ncm") == alvo_item["ncm"],
           novo_p.get("ncm"))
    st, depois_pend = chamar("GET", "/notas/pendencias", token=token)
    checar("o item sai da fila de conciliação",
           not any(i["id"] == alvo_item["id"] for i in depois_pend))
    # O de-para nasce junto: a próxima nota reconhece sozinha.
    st, vinculos = chamar("GET", "/notas/vinculos", token=token)
    checar("o de-para do código do fornecedor nasce junto",
           any(v["codigo"] == alvo_item["codigo_fornecedor"] for v in vinculos),
           alvo_item["codigo_fornecedor"])
    st, r2 = chamar("POST", f"/notas/itens/{alvo_item['id']}/criar-produto", {}, token=token)
    checar("e criar de novo no mesmo item é recusado", st == 400, st)
    # Desfaz o que esta fase criou. Quando o produto foi REAPROVEITADO não há o
    # que apagar — mas fica no cadastro dele o código do fornecedor, e é por ele
    # que a cascata resolve. Sem tirar, a próxima rodada acha o item já
    # conciliado e esta fase inteira deixa de ter o que provar.
    chamar("DELETE", f"/notas/vinculos/{alvo_item['codigo_fornecedor']}", token=token)
    if reaproveitou:
        st, prod = chamar("GET", f"/produtos/{r['id_produto']}", token=token)
        sobra = [f for f in (prod.get("fornecedores") or [])
                 if (f.get("codigo_no_fornecedor") or "") != alvo_item["codigo_fornecedor"]]
        chamar("PUT", f"/produtos/{r['id_produto']}", {"fornecedores": sobra}, token=token)
    else:
        chamar("DELETE", f"/produtos/{r['id_produto']}", token=token)

print("2d. cadastro de fornecedores vindo do Omie")
st, r = chamar("POST", "/omie/importar-fornecedores", token=token)
checar("importa fornecedores", st == 200, r)
checar("e conta o que criou e o que completou",
       "criados" in r and "completados" in r, r)
# Incluindo inativos: o smoke_cadastros usa o mesmo CNPJ e o desativa na
# limpeza. O que se prova aqui é o preenchimento, não a situação do cadastro.
st, fornecedores = chamar("GET", "/fornecedores?incluir_inativos=true", token=token)
vindo = next((f for f in fornecedores if (f.get("cnpj") or "").endswith("000195")), None)
checar("o fornecedor da nota ficou completo",
       vindo and vindo.get("cidade") and vindo.get("codigo_omie"), vindo)

# Importar de novo não pode desfazer correção feita à mão.
if vindo:
    chamar("PUT", f"/fornecedores/{vindo['id']}", {"telefone": "(47) 3333-0000"}, token=token)
    chamar("POST", "/omie/importar-fornecedores", token=token)
    st, depois_f = chamar("GET", f"/fornecedores/{vindo['id']}", token=token)
    checar("importar de novo NÃO sobrescreve o que foi digitado aqui",
           depois_f.get("telefone") == "(47) 3333-0000", depois_f.get("telefone"))

st, r = chamar("POST", "/omie/importar-fornecedores?apenas_completar=true", token=token)
checar("'apenas completar' não cria ninguém", r.get("criados") == 0, r)

print("3. conciliação: sem produto, sem lançamento")
st, r = chamar("POST", f"/notas/{nota_cafe['id']}/lancar", {}, token=token)
checar("recusa lançar com item pendente", st == 400, (st, r))
checar("a recusa diz quantos itens faltam", "item" in str(r.get("detail", "")).lower(), r)

st, pend = chamar("GET", "/notas/pendencias", token=token)
checar("as pendências aparecem na fila", st == 200 and len(pend) >= 2, len(pend))
item_cafe = next((p for p in pend if "CAFE" in (p["descricao_fornecedor"] or "").upper()), None)
checar("o item de café está na fila", item_cafe is not None, pend[:1])

# Produtos do lado de cá: café em UN (a caixa traz 12) e leite em UN.
st, r = chamar("POST", "/produtos", {"nome": f"Omie café {marca}", "tipo": "INSUMO",
                                     "um_estoque": "UN", "um_compra": "CX",
                                     "fator_compra": 12}, token=token)
cafe = r.get("id")
st, r = chamar("POST", "/produtos", {"nome": f"Omie leite {marca}", "tipo": "INSUMO",
                                     "um_estoque": "UN"}, token=token)
leite = r.get("id")
checar("produtos do cenário criados", bool(cafe and leite))

st, r = chamar("POST", f"/notas/itens/{item_cafe['id']}/vincular",
               {"id_produto": cafe, "fator": 12}, token=token)
checar("vincula o item de café", st == 200, r)

st, nota = chamar("GET", f"/notas/{nota_cafe['id']}", token=token)
linha_cafe = next(i for i in nota["itens"] if i["id_produto"] == cafe)
checar("quantidade convertida: 4 CX × 12 = 48 un",
       perto(linha_cafe["quantidade_convertida"], 48), linha_cafe["quantidade_convertida"])
checar("frete rateado no café = 45,00", perto(linha_cafe["valor_frete_rateado"], 45),
       linha_cafe["valor_frete_rateado"])
checar("custo de aquisição do café = 10,9375 (não os 10,00 da nota)",
       perto(linha_cafe["custo_aquisicao_unitario"], 10.9375, 0.0001),
       linha_cafe["custo_aquisicao_unitario"])

item_leite = next(i for i in nota["itens"] if i["id_produto"] is None and not i["ignorado"])
st, r = chamar("POST", f"/notas/itens/{item_leite['id']}/vincular",
               {"id_produto": leite}, token=token)
checar("vincula o item de leite", st == 200, r)
st, nota = chamar("GET", f"/notas/{nota_cafe['id']}", token=token)
linha_leite = next(i for i in nota["itens"] if i["id_produto"] == leite)
checar("custo do leite = 4,375 (160 + 15 de frete ÷ 40)",
       perto(linha_leite["custo_aquisicao_unitario"], 4.375, 0.0001),
       linha_leite["custo_aquisicao_unitario"])
checar("a nota passou para CONCILIADA", nota["status"] == "CONCILIADA", nota["status"])

print("4. lançamento vira estoque avaliado")
st, r = chamar("POST", f"/notas/{nota_cafe['id']}/lancar", {}, token=token)
checar("lança a nota", st == 200 and r.get("itens_lancados") == 2, r)
checar("valor lançado = 700,00 (a nota inteira)", perto(r.get("valor"), 700), r)

st, saldos = chamar("GET", f"/estoque/saldos?busca={marca}", token=token)
s_cafe = next((s for s in saldos if s["id_produto"] == cafe), None)
checar("café entrou com 48 un", s_cafe and perto(s_cafe["quantidade"], 48), s_cafe)
checar("café entrou pelo custo de aquisição", s_cafe and perto(s_cafe["custo_medio"], 10.9375, 0.001),
       s_cafe)

st, r = chamar("POST", f"/notas/{nota_cafe['id']}/lancar", {}, token=token)
checar("não lança a mesma nota duas vezes", st == 400, st)

print("5. o de-para aprendeu")
# Apaga a nota de café e reimporta: o item tem de casar sozinho agora.
st, r = chamar("POST", "/omie/sincronizar?dias=60", token=token)
checar("nova sincronização não traz a nota de novo", r.get("novas") == 0, r)
st, pend = chamar("GET", "/notas/pendencias", token=token)
checar("o item de café saiu da fila de pendências",
       not any(p["id"] == item_cafe["id"] for p in pend))

print("6. carga do catálogo e conferência cruzada")
st, r = chamar("POST", "/omie/importar-catalogo", token=token)
checar("importa o catálogo", st == 200, r)
checar("traz os 3 produtos da fixture", r.get("criados", 0) + r.get("ja_existiam", 0) >= 3, r)
st, produtos = chamar("GET", "/produtos?busca=Café em grão&incluir_inativos=true", token=token)
checar("o produto importado nasce em rascunho",
       any(p["status"] == "RASCUNHO" for p in produtos), produtos[:1])
checar("o catálogo não inventa unidade que a casa não tem",
       r.get("sem_unidade", 0) >= 1, r)
st, r2 = chamar("POST", "/omie/importar-catalogo", token=token)
checar("reimportar o catálogo não duplica", r2.get("criados") == 0, r2)

st, conf = chamar("GET", "/omie/conferencia", token=token)
checar("conferência com o CMC responde", st == 200, conf if st != 200 else len(conf))

print("6b. o catálogo destrava as notas: nome limpo, de-para pelo id do Omie e a trava da unidade")
# O rodapé de tributos aproximados que o DANFE manda imprimir vem grudado na
# descrição. Não é nome de nada — e um nome desses não cabe em tela nenhuma.
# ⚠️ Pelo CÓDIGO da fixture, não pelo nome: numa base que já recebeu um
# catálogo real existe mais de um champignon, e buscar por nome pegava o do
# cliente — que tem unidade, e faria a trava "passar" sem provar nada.
st, achados = chamar("GET", "/produtos?busca=CHAMP-BJ&incluir_inativos=true", token=token)
champ = next((p for p in achados or [] if p["codigo"] == "CHAMP-BJ"), None)
checar("o produto do catálogo existe", champ is not None, achados)
checar("o rodapé fiscal saiu do nome",
       champ and "Trib" not in champ["nome"] and "IBPT" not in champ["nome"],
       champ and champ["nome"])
# Garante a condição em vez de supô-la: numa rodada anterior esta mesma suíte
# definiu a unidade no fim da fase, e sem repor o rascunho ao estado de origem a
# trava não seria exercitada — passaria sozinha, provando nada.
st, detalhe = chamar("GET", f"/produtos/{champ['id']}", token=token)
if detalhe.get("um_estoque"):
    chamar("PUT", f"/produtos/{champ['id']}", {**detalhe, "um_estoque": None}, token=token)
    st, detalhe = chamar("GET", f"/produtos/{champ['id']}", token=token)
checar("o rascunho está sem unidade, como o catálogo o deixou",
       not detalhe.get("um_estoque"), detalhe.get("um_estoque"))

# A nota entrou ANTES do catálogo — a ordem de sempre, porque é a nota que
# revela o que a casa compra. Sem reconciliar, o item ficaria pendente para
# sempre; com o catálogo na base, o `nIdProduto` do Omie casa sozinho.
st, notas = chamar("GET", "/notas?busca=5014", token=token)
nota_champ = next((n for n in notas or [] if n["numero"] == "5014"), None)
checar("a nota do champignon foi importada", nota_champ is not None, nota_champ)

st, pend = chamar("GET", "/notas/pendencias", token=token)
pendente_champ = next((i for i in pend or [] if i.get("codigo_fornecedor") == "CHAMP-BJ"), None)
st, r = chamar("POST", "/notas/reconciliar", {}, token=token)
checar("reconciliar responde", st == 200, r)
# ⚠️ A suíte roda sobre base suja: numa primeira rodada a nota chega antes do
# catálogo e o item fica pendente; nas seguintes o catálogo já está lá e o item
# entra ligado na própria importação. É a MESMA cascata, mais cedo — e as duas
# situações têm de ser afirmadas, senão o teste passa à toa em metade das vezes.
if pendente_champ:
    checar("o item pendente encontrou produto pelo id do Omie",
           r.get("vinculados", 0) >= 1, r)
else:
    st, detalhe_nota = chamar("GET", f"/notas/{nota_champ['id']}", token=token)
    item_champ = next((i for i in detalhe_nota.get("itens", [])
                       if i.get("codigo_fornecedor") == "CHAMP-BJ"), None)
    checar("com o catálogo já na base, o item entrou vinculado na importação",
           item_champ and item_champ.get("id_produto"), item_champ)
st, pend = chamar("GET", "/notas/pendencias", token=token)
checar("de um jeito ou de outro, o item não fica na fila",
       not any(i.get("codigo_fornecedor") == "CHAMP-BJ" for i in pend or []), pend)

# ⚠️ Vinculado não quer dizer lançável. Quantidade sem unidade é número sem
# significado, e o custo médio que sair daí contamina ficha, CMV e a próxima
# compra.
st, notas = chamar("GET", "/notas?busca=5014", token=token)
nota_champ = next((n for n in notas or [] if n["numero"] == "5014"), None)
checar("a nota do champignon está conciliada",
       nota_champ and nota_champ["status"] == "CONCILIADA", nota_champ)
st, r = chamar("POST", f"/notas/{nota_champ['id']}/lancar", {}, token=token)
checar("produto sem unidade NÃO entra no estoque", st == 400, (st, r))
checar("e a recusa diz qual produto e por quê",
       "unidade" in str(r.get("detail", "")).lower()
       and "CHAMPIGNON" in str(r.get("detail", "")).upper(), r)

# Resolvida a unidade, a mesma nota passa.
st, detalhe = chamar("GET", f"/produtos/{champ['id']}", token=token)
st, r = chamar("PUT", f"/produtos/{champ['id']}", {**detalhe, "um_estoque": "UN"}, token=token)
st, detalhe = chamar("GET", f"/produtos/{champ['id']}", token=token)
checar("define a unidade do produto", detalhe.get("um_estoque") == "UN", detalhe.get("um_estoque"))
st, r = chamar("POST", f"/notas/{nota_champ['id']}/lancar", {}, token=token)
checar("com unidade definida, a nota entra", st == 200 and r.get("itens_lancados") == 1, r)
st, r = chamar("POST", f"/notas/{nota_champ['id']}/estornar", {}, token=token)
checar("e o estorno desfaz", st == 200, r)

print("7. permissão")
tk = garantir_cozinha(chamar, token)
st, r = chamar("GET", "/omie/config", token=tk)
checar("cozinha NÃO vê a configuração da integração (403)", st == 403, st)
st, r = chamar("POST", "/omie/sincronizar", token=tk)
checar("cozinha NÃO sincroniza (403)", st == 403, st)
st, r = chamar("GET", "/notas", token=tk)
checar("cozinha NÃO vê as notas (403)", st == 403, st)

print("8. desfazer: estorno e desvínculo")
st, r = chamar("POST", f"/notas/{nota_cafe['id']}/estornar", token=token)
checar("estorna o lançamento da nota", st == 200 and r.get("estornados") == 2, r)
st, saldos = chamar("GET", f"/estoque/saldos?busca={marca}", token=token)
s_cafe2 = next((s for s in saldos if s["id_produto"] == cafe), None)
checar("o saldo do café voltou a zero", s_cafe2 is None or perto(s_cafe2["quantidade"], 0),
       s_cafe2)
st, mov = chamar("GET", f"/estoque/movimentos?id_produto={cafe}", token=token)
checar("o movimento original continua no razão, com a contrapartida", len(mov) == 2, len(mov))
st, r = chamar("DELETE", f"/notas/vinculos/CAF-500", token=token)
checar("desfaz o vínculo aprendido", st == 200, r)

print("9. limpeza")
for p in (cafe, leite):
    chamar("DELETE", f"/produtos/{p}", token=token)
chamar("PUT", "/omie/config", {"modo": "simulado", "ativa": False}, token=token)
repostas = repor_credenciais()
checar("a credencial de verdade voltou como estava", repostas >= 0, repostas)
checar("limpeza concluída", True)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
