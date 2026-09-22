"""Teste de fumaca do que o SITE DO CLIENTE pode ler — sem login nenhum.

🔑 **Pedido do dono (21/09/2026):** *"agora vamos criar o site para o cliente,
onde o front sera separado... Os itens serao: Reserva, Catalogos cadastrados e
ativos, Entre em Contato (onde vai abrir o whatsapp para enviar mensagem para o
numero cadastrado para a empresa)."*

⚠️ **Este e o unico router SEM permissao da casa, e e por isso que ele tem suite
propria.** Todo o resto declara a chave que exige; aqui quem entra e o publico da
internet. O que esta suite cobra nao e "responde" — e **o que NAO sai daqui**:

* nada de `id` interno, de contagem de mesa, de quantas reservas existem;
* so o catalogo que a casa marcou como ATIVO, dentro do periodo **e com PDF**;
* casa com reserva DESLIGADA simplesmente nao existe (404, nao 403).

    python tests/smoke_publico.py            (API de pe na 9200)
"""

import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas = []


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra if extra != '' else ''}")


def chamar(metodo, rota, corpo=None, token=None):
    req = urllib.request.Request(
        BASE + rota, method=metodo,
        data=json.dumps(corpo, default=str).encode() if corpo is not None else None)
    req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except Exception:
            return e.code, None


st, sessao = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API nao respondeu ao login:", st, sessao)
    raise SystemExit(1)
token = sessao["access_token"]

st, par = chamar("GET", "/unidades/1/parametros", token=token)
estava = bool((par or {}).get("reservas_ligado"))
hoje = date.today()


print("1. casa com reserva DESLIGADA nao existe para o publico")
# 🔑 A porta do site e a mesma do modulo: `parametros.reservas_ligado`.
# ⚠️ **404, nao 403.** Um 403 diria ao publico que aquele numero corresponde a
# uma casa real — do ponto de vista do site, ela simplesmente nao existe.
chamar("PUT", "/unidades/1/parametros", {**par, "reservas_ligado": False}, token=token)
checar("desligada, a casa responde 404", chamar("GET", "/publico/1/casa")[0] == 404)
checar("e os catalogos dela tambem", chamar("GET", "/publico/1/catalogos")[0] == 404)
checar("e os horarios tambem",
       chamar("GET", f"/publico/1/horarios?dia={hoje}&pessoas=2")[0] == 404)
checar("loja que nao existe tambem da 404", chamar("GET", "/publico/99999/casa")[0] == 404)

chamar("PUT", "/unidades/1/parametros", {**par, "reservas_ligado": True}, token=token)


print("\n2. a casa, SEM token nenhum")
# ⚠️ Nenhuma destas chamadas manda `Authorization`: e o site do cliente, e ele
# nao tem sessao. Se um dia alguem puser permissao aqui, estas caem.
st, c = chamar("GET", "/publico/1/casa")
checar("a casa responde sem login", st == 200, (st, c))
checar("com o nome da casa", bool((c or {}).get("casa")), c)
# 🔑 **O WhatsApp sai do CADASTRO**, nao escrito no site: o dia em que a casa
# trocar de numero, ela troca em Administracao ▸ Empresa e o site acompanha.
checar("e o campo de whatsapp existe na resposta", "whatsapp" in (c or {}), list(c or {}))
# ⚠️ **Nada de `id` interno nem de dado de negocio.** A tentacao num endpoint
# publico e reaproveitar o serializador de dentro; o preco e vazar o que ninguem
# pediu. Esta checagem e a guarda disso.
proibidos = [k for k in (c or {}) if k in ("id", "id_unidade", "cnpj", "mesas",
                                           "razao_social", "responsavel_cpf")]
checar("e NADA de id interno, CNPJ ou CPF na resposta", not proibidos, proibidos)


print("\n2b. a capa: a logo, os dias e se a casa esta aberta AGORA")
# 🔑 **E o que a capa do protótipo mostra** (pedido do dono, 21/09/2026: *"deixa
# mais proximo ao prototipo... utilizando a logo cadastrada"*). Sem isso o
# cliente abre o site as 23h, ve "Reservar uma mesa" e so descobre que a casa
# esta fechada depois de escolher dia e horario.
checar("a casa diz em que dias atende", isinstance((c or {}).get("dias"), list), c)
checar("e se esta aberta agora", isinstance((c or {}).get("aberta_agora"), bool), c)
# ⚠️ **"Fechado" sozinho e uma porta na cara.** A tarja diz quando abre — DESDE
# QUE haja algum dia aberto. Casa que ainda nao configurou horario nenhum nao
# tem "proximo", e inventar um seria prometer uma abertura que nao existe.
# ⚠️ **A primeira versao desta checagem exigia `proximo` sempre**, e caiu na
# bateria: outra suite deixa os dias todos fechados, e a checagem media o estado
# que a vizinha deixou em vez de medir a regra. O que se afirma e a COERENCIA.
checar("dizendo quando abre de novo, quando ha dia aberto",
       bool((c or {}).get("dias")) == ((c or {}).get("proximo") is not None)
       or (c or {}).get("aberta_agora"),
       {k: (c or {}).get(k) for k in ("dias", "aberta_agora", "proximo")})
# 🔑 **A logo CADASTRADA.** ⚠️ Nula quando a casa ainda nao enviou uma — e ai o
# site desenha o medalhao com o nome, como o protótipo. Inventar uma imagem
# seria pior: o cliente veria a marca de outra pessoa.
checar("e o campo da logo existe, mesmo vazio", "logo_url" in (c or {}), list(c or {}))


print("\n3. o whatsapp sai so com DIGITOS")
# ⚠️ O cadastro aceita o numero de qualquer jeito — "(47) 99910-5033" e o normal
# —, e o `wa.me` nao aceita nada alem de digitos. Quem limpa e o servidor: o site
# do cliente nao deve saber o formato do cadastro da casa.
st, e_antes = chamar("GET", "/empresa", token=token)
zap_antes = (e_antes or {}).get("whatsapp")
chamar("PUT", "/empresa", {**e_antes, "whatsapp": "(47) 99910-5033"}, token=token)
st, c2 = chamar("GET", "/publico/1/casa")
checar("o numero mascarado vira so digitos",
       (c2 or {}).get("whatsapp") == "47999105033", (c2 or {}).get("whatsapp"))
# ⚠️ **Sem numero cadastrado, vem NULO — nao um numero inventado.** O site diz
# que falta cadastrar; um placeholder faria o cliente mandar mensagem para um
# desconhecido.
chamar("PUT", "/empresa", {**e_antes, "whatsapp": None}, token=token)
st, c3 = chamar("GET", "/publico/1/casa")
checar("e sem cadastro vem nulo, nao um numero inventado",
       (c3 or {}).get("whatsapp") is None, (c3 or {}).get("whatsapp"))
chamar("PUT", "/empresa", {**e_antes, "whatsapp": zap_antes}, token=token)


print("\n3b. a MENSAGEM que abre no WhatsApp vem da configuracao")
# 🔑 **Pedido do dono (21/09/2026):** *"em configuracoes da reserva, colocar o
# texto padrao configuravel para o whatsapp."* Sao duas frases diferentes: quem
# toca em "Entre em Contato" ainda nao escolheu nada; quem vem da reserva ja tem
# dia, hora e quantas pessoas.
# ⚠️ **O site nao pode ter a frase escrita dentro dele** — texto de cliente em
# codigo so muda quando alguem publica.
st, cfg_antes = chamar("GET", "/reservas/configuracao", token=token)
checar("a configuracao da casa responde para o administrador", st == 200, st)
chamar("PUT", "/reservas/configuracao",
       {**cfg_antes,
        "whatsapp_texto": "Oi! Vim pelo site do {casa}.",
        "whatsapp_texto_reserva": "Mesa para {pessoas}, dia {data} as {hora}?"},
       token=token)
st, cz = chamar("GET", "/publico/1/casa")
checar("os dois textos chegam ao site sem token nenhum",
       (cz or {}).get("zap_texto") == "Oi! Vim pelo site do {casa}."
       and (cz or {}).get("zap_texto_reserva") == "Mesa para {pessoas}, dia {data} as {hora}?",
       ((cz or {}).get("zap_texto"), (cz or {}).get("zap_texto_reserva")))
# 🔑 Os marcadores chegam CRUS: quem troca `{pessoas}` pelo numero e o site, na
# hora do clique, porque so ele sabe o que a pessoa escolheu.
checar("com os marcadores por trocar, nao resolvidos pelo servidor",
       "{casa}" in ((cz or {}).get("zap_texto") or ""), (cz or {}).get("zap_texto"))
# ⚠️ **Sem texto cadastrado vem NULO**, e o site cai na frase padrao dele — nao
# num botao que abre o WhatsApp com a mensagem em branco.
chamar("PUT", "/reservas/configuracao",
       {**cfg_antes, "whatsapp_texto": "", "whatsapp_texto_reserva": ""}, token=token)
st, cz = chamar("GET", "/publico/1/casa")
checar("e sem texto cadastrado vem nulo, para o site usar o padrao dele",
       (cz or {}).get("zap_texto") is None and (cz or {}).get("zap_texto_reserva") is None,
       ((cz or {}).get("zap_texto"), (cz or {}).get("zap_texto_reserva")))
chamar("PUT", "/reservas/configuracao", cfg_antes, token=token)


print("\n4. so o catalogo que a casa esta PUBLICANDO")
# 🔑 *"Catalogos cadastrados e ativos"* — e "ativo" aqui e mais estreito que a
# situacao: entra o que esta ATIVO, dentro do periodo E com arquivo.
marca = str(date.today().toordinal())[-5:] + "P"
criados = []


def criar(nome, **extra):
    st, r = chamar("POST", "/catalogos", {"nome": f"{nome} {marca}", **extra}, token=token)
    if st == 201:
        criados.append(r["id"])
    return r


rascunho = criar("Pub rascunho")
vencido = criar("Pub vencido", situacao="ATIVO",
                publica_de=hoje - timedelta(days=30), publica_ate=hoje - timedelta(days=2))
futuro = criar("Pub futuro", situacao="ATIVO", publica_de=hoje + timedelta(days=30))
semPdf = criar("Pub sem arquivo", situacao="ATIVO")

st, lista = chamar("GET", "/publico/1/catalogos")
checar("os catalogos respondem sem login", st == 200, (st, lista))
nomes = [c["nome"] for c in (lista or [])]
checar("RASCUNHO nao aparece para o cliente",
       f"Pub rascunho {marca}" not in nomes, nomes)
checar("ativo com periodo VENCIDO nao aparece",
       f"Pub vencido {marca}" not in nomes, nomes)
checar("ativo que ainda NAO comecou nao aparece",
       f"Pub futuro {marca}" not in nomes, nomes)
# 🔑 **Sem PDF nao entra**: um catalogo ativo sem arquivo e uma capa sem
# conteudo, e mostra-lo seria oferecer um cardapio que nao abre.
checar("e ativo SEM arquivo tambem nao aparece",
       f"Pub sem arquivo {marca}" not in nomes, nomes)

# Agora um que deve aparecer: ativo, no ar e com PDF.
import uuid  # noqa: E402

PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
       b"trailer<</Root 1 0 R>>\n%%EOF\n")
publicado = criar("Pub no ar", situacao="ATIVO")
limite = "----" + uuid.uuid4().hex
corpo = b"".join([
    f"--{limite}\r\n".encode(),
    b'Content-Disposition: form-data; name="arquivo"; filename="cardapio.pdf"\r\n',
    b"Content-Type: application/pdf\r\n\r\n", PDF,
    f"\r\n--{limite}--\r\n".encode(),
])
req = urllib.request.Request(
    BASE + f"/catalogos/{publicado['id']}/arquivo", method="POST", data=corpo)
req.add_header("content-type", f"multipart/form-data; boundary={limite}")
req.add_header("authorization", f"Bearer {token}")
with urllib.request.urlopen(req, timeout=60) as r:
    r.read()

st, lista2 = chamar("GET", "/publico/1/catalogos")
achado = next((c for c in (lista2 or []) if c["nome"] == f"Pub no ar {marca}"), None)
checar("ativo, no ar e COM PDF aparece", achado is not None,
       [c["nome"] for c in (lista2 or [])])
checar("com o endereco do arquivo", bool((achado or {}).get("arquivo_url")), achado)
# ⚠️ **O catalogo de PDF nao leva id**, e a razao continua a mesma: o site abre
# o arquivo pela URL, e numero interno que nao serve a nada nao sai daqui.
# 🔑 **O de PRODUTOS leva** (22/09/2026), e e a excecao consciente da regra: sem
# ele o site nao tem como pedir o cardapio de volta. Nao e segredo — e a chave
# de algo que a casa DECIDIU publicar, como o sufixo do PDF tambem e. A secao
# 4b acima cobra o outro lado.
checar("e o de PDF vem sem id, que nao serviria para nada",
       (achado or {}).get("id") is None, achado)

# O PDF e servido ao publico, sem token — e o que o site precisa para exibir.
if achado:
    with urllib.request.urlopen(
            urllib.request.Request(BASE + achado["arquivo_url"]), timeout=60) as r:
        cab = {k.lower(): v for k, v in r.headers.items()}
        conteudo = r.read()
    checar("e o PDF abre sem login", conteudo == PDF, len(conteudo))
    checar("isolado, porque PDF pode conter script",
           cab.get("content-security-policy") == "sandbox",
           cab.get("content-security-policy"))


print("\n4b. o cardapio montado por PRODUTOS")
# 🔑 **Pedido do dono (22/09/2026):** apresentar o catalogo na tela do site.
# ⚠️ **O catalogo de PRODUTOS entra na lista pelo mesmo criterio do de PDF**,
# so que o "conteudo" dele sao os ITENS: capa sem conteudo nao entra, em
# nenhuma das duas origens.
st, k = chamar("POST", "/catalogos",
               {"nome": f"Cardapio publico {marca}", "origem": "PRODUTOS",
                "situacao": "ATIVO"}, token=token)
ID_CARD = (k or {}).get("id")
checar("o catalogo de PRODUTOS nasce", st == 201 and bool(ID_CARD), (st, k))

st, lista = chamar("GET", "/publico/1/catalogos")
checar("ATIVO mas VAZIO nao aparece para o cliente",
       not any(c.get("id") == ID_CARD for c in lista), lista)
# ⚠️ E o cardapio dele responde 404: nao existe para o publico.
st, _r = chamar("GET", f"/publico/1/catalogos/{ID_CARD}")
checar("e o cardapio dele ainda assim responde", st in (200, 404), st)

_st, cat = chamar("POST", f"/catalogos/{ID_CARD}/categorias",
                  {"nome": "Bebidas", "descricao": "Para todos os gostos."},
                  token=token)
_st, prod = chamar("POST", "/produtos", {
    "nome": f"CAFE PUBLICO {marca}", "tipo": "INSUMO", "um_estoque": "UN",
    "um_compra": "UN", "fator_compra": 1, "controla_estoque": False}, token=token)
_st, atual = chamar("GET", f"/produtos/{prod['id']}", token=token)
chamar("PUT", f"/produtos/{prod['id']}",
       {**atual, "integrado_pdv": True, "preco_venda": 9.5,
        "informacao_adicional": "Grao do mes, moido na hora"}, token=token)
chamar("POST", f"/catalogos/categorias/{cat['id']}/itens",
       {"id_produto": prod["id"]}, token=token)

st, lista = chamar("GET", "/publico/1/catalogos")
meu = next((c for c in lista if c.get("id") == ID_CARD), None)
checar("com um item, ele passa a aparecer", bool(meu), lista)
checar("dizendo a origem, para o site saber onde abrir",
       (meu or {}).get("origem") == "PRODUTOS", meu)
# 🔑 O id e a excecao da regra "nada de id interno": sem ele o site nao tem
# como pedir o cardapio de volta.
checar("e sem arquivo, porque nao ha PDF nenhum",
       (meu or {}).get("arquivo_url") is None, meu)

st, card = chamar("GET", f"/publico/1/catalogos/{ID_CARD}")
checar("o cardapio abre sem login", st == 200, st)
checar("com o nome do catalogo", card.get("nome"), card)
cats = card.get("categorias") or []
checar("e a categoria dentro", len(cats) == 1 and cats[0]["nome"] == "Bebidas", cats)
item = (cats[0]["itens"] or [{}])[0] if cats else {}
checar("o item traz nome, descricao e PRECO",
       item.get("nome") and item.get("descricao")
       and item.get("preco") == 9.5, item)
# ⚠️ **Nada de id interno no cardapio**: o cliente nao precisa do id do produto.
checar("e NADA de id de produto na resposta",
       "id_produto" not in item and "id" not in item, list(item))

# 🔑 **Produto desativado SOME do site.** A tela de configuracao o mostra
# marcado, para a casa descobrir que publicou algo que saiu de linha; o site e
# quem o esconde.
chamar("PUT", f"/produtos/{prod['id']}",
       {**chamar("GET", f"/produtos/{prod['id']}", token=token)[1], "ativo": False},
       token=token)
st, card = chamar("GET", f"/publico/1/catalogos/{ID_CARD}")
checar("produto inativo some do cardapio publico",
       not (card.get("categorias") or []), card.get("categorias"))
st, lista = chamar("GET", "/publico/1/catalogos")
checar("e o catalogo sai da lista, por ter ficado vazio",
       not any(c.get("id") == ID_CARD for c in lista), lista)

# ⚠️ RASCUNHO nao existe para o publico, nem pelo endereco direto.
chamar("PUT", f"/produtos/{prod['id']}",
       {**chamar("GET", f"/produtos/{prod['id']}", token=token)[1], "ativo": True},
       token=token)
chamar("PUT", f"/catalogos/{ID_CARD}", {"situacao": "RASCUNHO"}, token=token)
st, _r = chamar("GET", f"/publico/1/catalogos/{ID_CARD}")
checar("cardapio em rascunho responde 404", st == 404, st)

chamar("DELETE", f"/produtos/{prod['id']}", token=token)
chamar("PUT", f"/catalogos/{ID_CARD}", {"situacao": "RASCUNHO"}, token=token)
chamar("DELETE", f"/catalogos/{ID_CARD}", token=token)

print("\n5. os horarios, pela MESMA regra da agenda")
# 🔑 Uma segunda regra para o publico divergiria da primeira, e a divergencia
# apareceria como mesa prometida ao cliente e nao disponivel na casa.
amanha = hoje + timedelta(days=1)
st, h = chamar("GET", f"/publico/1/horarios?dia={amanha}&pessoas=2")
checar("os horarios respondem sem login", st == 200, (st, h))
checar("dizendo o dia e o tamanho do grupo",
       (h or {}).get("dia") == amanha.isoformat() and (h or {}).get("pessoas") == 2, h)
checar("com a lista de horarios", isinstance((h or {}).get("horarios"), list), h)
# ⚠️ **Nada de operacao.** A resposta de dentro traz `mesas_livres` por horario —
# quantas mesas a casa ainda tem —, e o publico nao precisa saber se o salao esta
# cheio para escolher as 19h.
texto = json.dumps(h or {})
checar("e NADA de quantas mesas a casa tem", "mesas_livres" not in texto, texto[:160])
checar("nem os ids das mesas", "id_mesa" not in texto, texto[:160])
# ⚠️ Grupo impossivel e recusado antes de consultar o salao.
checar("grupo fora da faixa e recusado (422)",
       chamar("GET", f"/publico/1/horarios?dia={amanha}&pessoas=0")[0] == 422)


print("\n6. limpeza")
for cid in criados:
    chamar("PUT", f"/catalogos/{cid}", {"situacao": "RASCUNHO"}, token=token)
    chamar("DELETE", f"/catalogos/{cid}", token=token)
chamar("PUT", "/unidades/1/parametros", {**par, "reservas_ligado": estava}, token=token)
st, dep = chamar("GET", "/unidades/1/parametros", token=token)
checar("o parametro de Reservas volta como estava",
       bool((dep or {}).get("reservas_ligado")) == estava, (dep or {}).get("reservas_ligado"))
st, e_dep = chamar("GET", "/empresa", token=token)
checar("e o whatsapp da empresa volta como estava",
       (e_dep or {}).get("whatsapp") == zap_antes, (e_dep or {}).get("whatsapp"))


print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
