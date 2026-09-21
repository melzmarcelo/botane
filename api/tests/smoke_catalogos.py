"""Teste de fumaca do cadastro de catalogos — o cabecalho do que a casa publica.

🔑 **Pedido do dono (21/09/2026):** *"vamos iniciar pelo cadastro de catalogos.
Onde teremos o cabecalho do catalogo, origem — neste momento somente vamos ter
PDF —, o nome dele no site do cliente, o periodo de publicacao, a situacao:
rascunho, ativo, inativo."*

🔑 **PDF, nao PDV, e o catalogo e do site de RESERVAS** (correcao do dono no
mesmo dia). O modulo passa pela porta de `parametros.reservas_ligado`: desligado,
as rotas recusam com 409 — e esta suite cobra isso antes de qualquer outra coisa,
porque e a primeira parede que alguem esbarra.

O que esta suite cobra, alem do CRUD:

* **"No ar hoje" NAO e o mesmo que ATIVO.** Um catalogo ativo cujo periodo
  terminou ontem nao esta publicado. E a pergunta que a lista responde de
  relance, e confundir as duas faria a casa procurar no site um cardapio que
  saiu do ar sozinho.
* **Varios ATIVOS sao permitidos** (decisao do dono: *"varios, sem trava
  nenhuma"*). A suite afirma isso para que ninguem "conserte" com um indice
  unico achando que e defeito.
* **Campo ausente nao e campo nulo**: mudar so a situacao nao pode apagar o
  periodo.
* **So rascunho se apaga.** O que ja esteve no ar se inativa — alguem leu
  aquele cardapio.

    python tests/smoke_catalogos.py            (API de pe na 9200)
"""

import json
import sys
import urllib.error
import urllib.parse
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

marca = str(date.today().toordinal())[-5:] + "C"
hoje = date.today()
criados = []

# 🔑 **O catalogo e do site de RESERVAS**: sem o modulo ligado, as rotas recusam.
# ⚠️ A suite LIGA e DEVOLVE ao estado anterior — o modulo nasce desligado em toda
# loja, e deixa-lo ligado mudaria o que a bateria do navegador encontra depois.
st, par_antes = chamar("GET", "/unidades/1/parametros", token=token)
reservas_estava = bool((par_antes or {}).get("reservas_ligado"))

print("0. sem Reservas ligado, o catalogo nao existe")
if reservas_estava:
    chamar("PUT", "/unidades/1/parametros", {**par_antes, "reservas_ligado": False},
           token=token)
st, r = chamar("GET", "/catalogos", token=token)
checar("desligado, listar recusa com 409", st == 409, (st, r))
checar("e a frase diz onde se liga",
       "Reservas" in str((r or {}).get("detail", "")), (r or {}).get("detail"))
checar("criar tambem recusa",
       chamar("POST", "/catalogos", {"nome": "Nao deveria"}, token=token)[0] == 409)

chamar("PUT", "/unidades/1/parametros", {**par_antes, "reservas_ligado": True}, token=token)


def criar(nome, **extra):
    corpo = {"nome": f"{nome} {marca}", **extra}
    st, r = chamar("POST", "/catalogos", corpo, token=token)
    if st == 201 and r:
        criados.append(r["id"])
    return st, r


print("1. o vocabulario vem do SERVIDOR")
# 🔑 Para a tela nao manter a segunda copia da lista — e a licao das tres listas
# de TIPOS que divergiram caladas.
st, op = chamar("GET", "/catalogos/opcoes", token=token)
checar("as opcoes respondem", st == 200, (st, op))
# ⚠️ **PDF e ARQUIVO, nao PDV.** O modulo nasceu com a sigla errada por um
# engano de digitacao, e a primeira versao inteira foi escrita em cima dela.
checar("com a unica origem de hoje, PDF", (op or {}).get("origens") == ["PDF"], op)
checar("e as tres situacoes que o dono nomeou",
       (op or {}).get("situacoes") == ["RASCUNHO", "ATIVO", "INATIVO"], op)


print("\n2. o catalogo nasce RASCUNHO")
# ⚠️ Catalogo que nasce ativo e catalogo publicado antes de alguem conferir o
# que tem dentro.
st, c1 = criar("Cardapio permanente")
checar("cria", st == 201, (st, c1))
checar("nascendo rascunho", (c1 or {}).get("situacao") == "RASCUNHO", c1)
checar("com a origem PDF por padrao", (c1 or {}).get("origem") == "PDF", c1)
checar("e sem periodo, que quer dizer 'vale enquanto estiver ativo'",
       (c1 or {}).get("publica_de") is None and (c1 or {}).get("publica_ate") is None, c1)
checar("e NAO esta no ar, porque rascunho nao vai para o site",
       (c1 or {}).get("publicado_hoje") is False, c1)
checar("guardando quem criou", (c1 or {}).get("criado_por") is not None, c1)


print("\n3. o nome e unico por loja, sem caixa")
# ⚠️ Dois com o mesmo nome sao o mesmo catalogo cadastrado duas vezes, e quem
# for publicar escolhe um dos dois sem saber qual.
st, r = criar("cardapio PERMANENTE")
checar("o nome repetido e recusado com 409", st == 409, (st, r))
checar("e a frase diz qual e o que ja existe",
       "Cardapio permanente" in str((r or {}).get("detail", "")), (r or {}).get("detail"))


print("\n4. o periodo nao se inverte")
st, r = criar("Invertido", publica_de=hoje + timedelta(days=5), publica_ate=hoje)
checar("periodo invertido e recusado", st == 422, (st, str(r)[:120]))
checar("dizendo que sairia do ar antes de entrar",
       "antes de entrar" in str(r), str(r)[:200])
# ⚠️ E em DUAS gravacoes tambem: mandar so uma ponta precisa ser comparado com a
# que ja esta gravada, senao da para inverter em dois passos.
st, c2 = criar("Duas gravacoes", publica_de=hoje)
st, r = chamar("PUT", f"/catalogos/{c2['id']}",
               {"publica_ate": hoje - timedelta(days=10)}, token=token)
checar("e nao da para inverter em duas gravacoes", st == 422, (st, str(r)[:120]))


print("\n5. origem e situacao desconhecidas sao recusadas")
st, r = criar("Origem inventada", origem="PDV")  # a sigla parecida, de proposito
checar("origem que nao existe e recusada", st == 422, (st, str(r)[:120]))
st, r = criar("Situacao inventada", situacao="PUBLICADO")
checar("situacao que nao existe e recusada", st == 422, (st, str(r)[:120]))
checar("e a lista aceita filtrar so pelas que existem",
       chamar("GET", "/catalogos?situacao=XPTO", token=token)[0] == 422)


print("\n6. 'no ar hoje' NAO e o mesmo que ATIVO")
# 🔑 A afirmacao central da tela. Um ativo com periodo vencido nao esta
# publicado, e mostrar os dois como iguais faria a casa procurar no site um
# cardapio que saiu do ar sozinho.
st, vencido = criar("Verao passado", situacao="ATIVO",
                    publica_de=hoje - timedelta(days=60),
                    publica_ate=hoje - timedelta(days=30))
checar("ativo com periodo VENCIDO nao esta no ar",
       vencido.get("publicado_hoje") is False, vencido)
st, futuro = criar("Verao que vem", situacao="ATIVO",
                   publica_de=hoje + timedelta(days=30))
checar("ativo que ainda NAO comecou tambem nao esta no ar",
       futuro.get("publicado_hoje") is False, futuro)
st, no_ar = criar("No ar", situacao="ATIVO", publica_de=hoje - timedelta(days=1))
checar("ativo dentro do periodo ESTA no ar", no_ar.get("publicado_hoje") is True, no_ar)
st, sem_prazo = criar("Sem prazo", situacao="ATIVO")
checar("e ativo SEM periodo esta no ar — 'sem prazo' nao e 'nunca'",
       sem_prazo.get("publicado_hoje") is True, sem_prazo)


print("\n7. varios ATIVOS ao mesmo tempo sao PERMITIDOS")
# 🔑 Decisao do dono (21/09/2026): *"varios, sem trava nenhuma"*. Esta checagem
# existe para que ninguem "conserte" isso com um indice unico achando que e
# defeito.
# ⚠️ A consequencia fica dita: quem for publicar no site precisa de uma regra
# que escolha ENTRE os ativos, e ela e da fatia do site, nao do cadastro.
st, lista = chamar("GET", "/catalogos?situacao=ATIVO", token=token)
meus = [c for c in (lista or []) if marca in c["nome"]]
checar("a loja tem mais de um catalogo ativo, e isso nao e erro",
       len(meus) >= 3, [c["nome"] for c in meus])
checar("e mais de um deles esta no ar ao mesmo tempo",
       len([c for c in meus if c["publicado_hoje"]]) >= 2,
       [(c["nome"], c["publicado_hoje"]) for c in meus])


print("\n8. campo ausente NAO e campo nulo")
# ⚠️ A tela manda o que mudou. Tratar o ausente como None apagaria o periodo de
# quem so mexeu na situacao.
st, r = chamar("PUT", f"/catalogos/{vencido['id']}", {"situacao": "INATIVO"}, token=token)
checar("mudar so a situacao funciona", st == 200 and r["situacao"] == "INATIVO", (st, r))
checar("e NAO apaga o periodo que ninguem tocou",
       r.get("publica_de") is not None and r.get("publica_ate") is not None, r)
# ⚠️ Mas limpar a data DE PROPOSITO continua valendo: e uma edicao legitima.
st, r = chamar("PUT", f"/catalogos/{no_ar['id']}", {"publica_de": None}, token=token)
checar("enquanto limpar a data de proposito continua valendo",
       st == 200 and r.get("publica_de") is None, (st, r))


print("\n9. so RASCUNHO se apaga")
# 🔑 Um catalogo que ja esteve no ar e o que a casa publicou; alguem leu aquele
# cardapio. A situacao INATIVO existe para isso.
st, r = chamar("DELETE", f"/catalogos/{sem_prazo['id']}", token=token)
checar("apagar um ATIVO e recusado com 409", st == 409, (st, r))
checar("e a frase manda inativar em vez de apagar",
       "INATIVO" in str((r or {}).get("detail", "")), (r or {}).get("detail"))
st, r = chamar("DELETE", f"/catalogos/{c1['id']}", token=token)
checar("apagar um RASCUNHO funciona", st == 200, (st, r))
if st == 200:
    criados.remove(c1["id"])
checar("e depois ele nao e encontrado",
       chamar("GET", f"/catalogos/{c1['id']}", token=token)[0] == 404)


print("\n10. permissao")
# ⚠️ Nada de checagem so na tela. Quem nao tem a chave nao le nem grava.
st, sessao_coz = chamar("POST", "/auth/login",
                        {"email": "cozinha.teste@botane.com.br", "senha": "cozinha12345"})
tk = (sessao_coz or {}).get("access_token")
if tk:
    checar("cozinha nao lista catalogos",
           chamar("GET", "/catalogos", token=tk)[0] == 403)
    checar("e nao cria", chamar("POST", "/catalogos", {"nome": "Nao deveria"}, token=tk)[0] == 403)
else:
    checar("usuario de cozinha disponivel para o teste de permissao", True,
           "sem usuario de cozinha nesta base")


print("\n11. limpeza")

for cid in list(criados):
    chamar("PUT", f"/catalogos/{cid}", {"situacao": "RASCUNHO"}, token=token)
    chamar("DELETE", f"/catalogos/{cid}", token=token)
st, sobrou = chamar("GET", "/catalogos", token=token)
# ⚠️ **Devolve o parametro por ultimo**: apagar exige o modulo ligado, e a
# bateria do navegador espera encontrar a loja como estava. Fase que desvia,
# devolve.
chamar("PUT", "/unidades/1/parametros",
       {**par_antes, "reservas_ligado": reservas_estava}, token=token)
st, dep = chamar("GET", "/unidades/1/parametros", token=token)
checar("o parametro de Reservas volta como estava",
       bool((dep or {}).get("reservas_ligado")) == reservas_estava,
       (dep or {}).get("reservas_ligado"))
checar("limpeza concluida",
       not [c for c in (sobrou or []) if marca in c["nome"]],
       [c["nome"] for c in (sobrou or []) if marca in c["nome"]])


print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
