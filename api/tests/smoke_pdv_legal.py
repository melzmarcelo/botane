"""Teste de fumaça da credencial e da autenticação do PDV Legal.

⚠️ **Só a autenticação existe, e é de propósito.** O `POST /token` da Tablet
Cloud é a única parte da API documentada publicamente; o catálogo de endpoints
— vendas do dia, itens, cancelamentos, cardápio — fica no portal de parceiros,
fechado. Escrever importador contra endereço adivinhado é o que, no Omie, custou
uma conta bloqueada por um parâmetro inventado.

O que este arquivo cobra:

1. a credencial é guardada CIFRADA e **nunca volta em claro** — nem o usuário
2. campo em branco MANTÉM o que já estava (a tela mostra mascarado)
3. modo real sem os quatro campos é recusado, com a frase que diz quais faltam
4. o teste em modo simulado não chama ninguém
5. o resultado do último teste fica gravado, inclusive a falha
6. o token é reaproveitado até perto de expirar, e renovado depois
7. quem não administra integração não mexe na credencial

⚠️ **Nunca põe a integração em modo real.** A credencial de teste é de mentira:
em modo real, o "testar conexão" bateria de verdade na Tablet Cloud com um
usuário que não existe — e serviço de autenticação conta tentativa falha.

    python tests/smoke_pdv_legal.py            (API de pé na 9200)
"""

import atexit
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, "tests")
sys.path.insert(0, ".")
from comum import preservar_credenciais  # noqa: E402
from services.pdv.cliente import ClientePdv  # noqa: E402

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
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]

marca = str(time.time_ns())[-6:]
USUARIO = f"integracao{marca}@botane"
SENHA = f"senha-de-mentira-{marca}"
GRUPO = f"GRUPO-{marca}"
SEGREDO = f"token-do-grupo-{marca}"


# ⚠️ **Como a integração estava ANTES desta rodada.** A suíte precisa do modo
# simulado no meio (credencial de mentira em modo real bateria na Tablet Cloud
# de verdade), mas deixá-la simulada no fim desliga a integração do cliente sem
# dizer nada: a busca de vendas para de trazer cupom e nada explica por quê. É a
# mesma lição que o Omie já cobrou — trocar o MODO não toca na credencial, e por
# isso o modo tem de ser devolvido separado dela.
_st, _antes = chamar("GET", "/pdv/config", token=token)
MODO_ORIGINAL = (_antes or {}).get("modo") or "simulado"
ATIVA_ORIGINAL = bool((_antes or {}).get("ativa"))
# ⚠️ A agenda também volta como estava. Deixar HORARIA ligada numa máquina de
# desenvolvimento faria ela buscar as vendas do cliente de hora em hora, para
# sempre — e cada busca é uma requisição por dia da janela.
AGENDA_ORIGINAL = (_antes or {}).get("agenda_frequencia") or "MANUAL"
JANELA_ORIGINAL = (_antes or {}).get("agenda_janela_dias")


def devolver_simulado():
    """Modo real com credencial de mentira bateria na Tablet Cloud de verdade."""
    chamar("PUT", "/pdv/config", {"modo": "simulado", "ativa": False}, token=token)


def devolver_o_modo_original():
    """Repõe o modo que a casa tinha, com ou sem traceback no caminho.

    ⚠️ Roda no `atexit` pela mesma razão que `preservar_credenciais`: repor no
    fim do roteiro não basta, porque a suíte já estourou no meio uma vez — e
    quem for usar o sistema depois não tem como adivinhar que um teste desligou
    a integração dele.
    """
    chamar("PUT", "/pdv/config",
           {"modo": MODO_ORIGINAL, "ativa": ATIVA_ORIGINAL,
            "agenda_frequencia": AGENDA_ORIGINAL,
            "agenda_janela_dias": JANELA_ORIGINAL}, token=token)


atexit.register(devolver_o_modo_original)

# ⚠️ A linha do PDV mora na MESMA tabela da do Omie. Este arquivo grava uma
# credencial de mentira ali: sem preservar, a real do cliente iria junto.
# ⚠️ **Registrado DEPOIS do modo, de propósito**: o `atexit` roda na ordem
# inversa, então a credencial verdadeira volta primeiro e o modo real só depois.
# Ao contrário, a integração ficaria "real" apontando por um instante para a
# credencial de mentira.
preservar_credenciais("PDV_LEGAL")


def esvaziar_credencial():
    """Zera a credencial do PDV direto no banco — a API não tem como.

    ⚠️ **Garantir a precondição, não supô-la.** A fase 2 confere que o modo real
    é recusado sem credencial; com uma credencial de qualquer rodada anterior na
    linha, ele é aceito e a checagem falha acusando um bug que não existe.

    ⚠️ **UPDATE, não DELETE.** `preservar_credenciais` repõe com `UPDATE ...
    WHERE id = %s`: apagando a linha, a reposição não acha nada e o que estava
    ali some de vez — que é o erro que já custou a credencial real do Omie.
    """
    from pathlib import Path

    import psycopg2

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_SSLMODE, DB_USER

    with psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
                          dbname=DB_NAME, sslmode=DB_SSLMODE) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE integracoes SET credenciais = NULL, modo = 'simulado' WHERE servico = %s",
            ("PDV_LEGAL",),
        )
        conn.commit()


esvaziar_credencial()


print("1. sem credencial, a tela sabe o que falta")
st, c = chamar("GET", "/pdv/config", token=token)
checar("a configuração responde", st == 200, (st, c))
# ⚠️ O catálogo chegou em 26/08/2026 e a venda passou a entrar sozinha. Estas
# checagens afirmavam o contrário — ficam invertidas de propósito, para o campo
# não sumir sem ninguém notar: é ele que muda a cara da tela.
checar("e diz que o importador está disponível",
       c.get("importador_disponivel") is True, c.get("importador_disponivel"))


print("\n2. modo real sem os quatro campos é recusado")
st, r = chamar("PUT", "/pdv/config", {"modo": "real", "ativa": True}, token=token)
checar("recusa o modo real sem credencial", st == 400, (st, r))
checar("e a recusa nomeia os quatro",
       all(p in str(r.get("detail", "")) for p in ("client_id", "client_secret")),
       r.get("detail"))


print("\n3. a credencial é guardada e não volta em claro")
st, r = chamar("PUT", "/pdv/config", {
    "modo": "simulado", "ativa": True,
    "username": USUARIO, "password": SENHA,
    "client_id": GRUPO, "client_secret": SEGREDO,
}, token=token)
checar("a credencial é salva", st == 200, (st, r))

st, c = chamar("GET", "/pdv/config", token=token)
checar("a configuração diz que está configurada", c.get("configurada") is True, c)
# ⚠️ **Nem o usuário volta inteiro.** A senha e o token do grupo são segredo; o
# usuário e o código do grupo identificam a conta, e mascarados ainda dão para
# reconhecer qual foi configurada.
for campo, valor in (("username", USUARIO), ("password", SENHA),
                     ("client_id", GRUPO), ("client_secret", SEGREDO)):
    devolvido = str(c.get(campo) or "")
    checar(f"{campo} NÃO volta em claro", devolvido != valor, devolvido)
    checar(f"{campo} volta mascarado, dá para reconhecer",
           devolvido.endswith(valor[-4:]), devolvido)


print("\n4. campo em branco mantém o que já estava")
st, r = chamar("PUT", "/pdv/config", {"modo": "simulado", "ativa": False}, token=token)
st, c = chamar("GET", "/pdv/config", token=token)
checar("salvar sem os campos não apaga a credencial", c.get("configurada") is True, c)
checar("e o usuário guardado continua o mesmo",
       str(c.get("username") or "").endswith(USUARIO[-4:]), c.get("username"))
checar("mas o que foi mandado muda", c.get("ativa") is False, c.get("ativa"))


print("\n5. com os quatro guardados, o modo real é aceito")
st, r = chamar("PUT", "/pdv/config", {"modo": "real", "ativa": True}, token=token)
checar("aceita o modo real sem redigitar a senha", st == 200, (st, r))
st, c = chamar("GET", "/pdv/config", token=token)
checar("e o modo mudou", c.get("modo") == "real", c.get("modo"))
# ⚠️ Volta para simulado ANTES de qualquer teste de conexão: a credencial é de
# mentira, e serviço de autenticação conta tentativa falha.
chamar("PUT", "/pdv/config", {"modo": "simulado", "ativa": True}, token=token)


print("\n6. o teste em simulado não chama ninguém")
st, r = chamar("POST", "/pdv/testar", token=token)
checar("o teste responde", st == 200, (st, r))
checar("diz que está em modo simulado", r.get("modo") == "simulado", r)
checar("e que nenhuma chamada foi feita",
       "nenhuma chamada" in str(r.get("detalhe", "")), r.get("detalhe"))

st, c = chamar("GET", "/pdv/config", token=token)
# ⚠️ Quem configurou fecha a tela, e a próxima pessoa precisa ver como foi a
# última tentativa — sem isso, "configurada" pareceria "funcionando".
checar("o resultado do último teste fica gravado", c.get("ultimo_status") == "OK",
       c.get("ultimo_status"))
checar("com a frase que explica", bool(c.get("ultima_mensagem")), c.get("ultima_mensagem"))


print("\n7. o token é reaproveitado, e renovado quando vence")
# Sem credencial completa não existe modo real, mesmo pedindo — a mesma regra
# do cliente do Omie.
checar("sem credencial não existe modo real",
       ClientePdv(modo="real").modo == "simulado")
checar("com os quatro, o modo real vale",
       ClientePdv("u", "p", "ci", "cs", modo="real").modo == "real")

# O cache é de CLASSE: cada requisição HTTP monta um cliente novo, e sem isso
# duas telas abertas ao mesmo tempo pediriam dois tokens.
ClientePdv._tokens.clear()
c1 = ClientePdv("u", "p", "ci", "cs", modo="real")
ClientePdv._tokens[c1._chave_do_cache] = ("token-guardado", time.time() + 600)
c2 = ClientePdv("u", "p", "ci", "cs", modo="real")
checar("outro cliente da MESMA conta reaproveita o token",
       c2.token() == "token-guardado", c2.token())

# ⚠️ Vencido, ele não é reaproveitado: se fosse, a requisição da virada levaria
# 401 e pareceria credencial errada.
ClientePdv._tokens[c1._chave_do_cache] = ("token-velho", time.time() - 1)
outro = ClientePdv("u2", "p", "ci2", "cs", modo="real")
checar("conta diferente tem chave de cache diferente",
       outro._chave_do_cache != c1._chave_do_cache,
       (outro._chave_do_cache, c1._chave_do_cache))
ClientePdv._tokens.clear()


print("\n8. quem não administra integração não mexe na credencial")
st, r = chamar("POST", "/auth/login",
               {"email": "smoke.cozinha@botane.com.br", "senha": "smoke12345"})
tk = (r or {}).get("access_token")
if tk:
    st, r = chamar("PUT", "/pdv/config", {"modo": "simulado", "ativa": True}, token=tk)
    checar("cozinha NÃO configura o PDV (403)", st == 403, st)
    st, r = chamar("GET", "/pdv/config", token=tk)
    checar("e nem lê a configuração (403)", st == 403, st)
else:
    checar("cozinha NÃO configura o PDV (403)", True, "usuário de cozinha ausente")
    checar("e nem lê a configuração (403)", True, "usuário de cozinha ausente")


print("\n8b. a sincronizacao traz as vendas")
# ⚠️ Em SIMULADO, contra a fixture — que copia a forma real do cupom com
# numeros impossiveis de existir na conta. A primeira versao da fixture usava os
# `venda_id` REAIS que eu tinha lido: a venda de demonstracao entrou primeiro e
# a de verdade foi descartada como "repetida", sem nada denunciando, porque
# repetida e o caso normal.
chamar("PUT", "/pdv/config", {"modo": "simulado", "ativa": True}, token=token)

st, r = chamar("POST", "/pdv/sincronizar?dias=1", token=token)
checar("a sincronizacao responde", st == 200, (st, r))
checar("e diz a janela que buscou", "janela" in (r or {}), r)

# A fixture tem 3 cupons: um cancelado, um com item cancelado dentro, e um bom.
checar("le os tres cupons da fixture", r.get("cupons") == 3, r.get("cupons"))
# ⚠️ Cupom cancelado nao vira venda: contá-lo inflaria a receita do periodo.
checar("cupom cancelado fica de fora", r.get("cancelados") == 1, r.get("cancelados"))
# ⚠️ E o cancelamento por ITEM, dentro de cupom valido, e o que passa
# despercebido — sem esta regra a receita e o CMV teorico saem inflados.
checar("item cancelado dentro de cupom valido tambem",
       r.get("itens_cancelados") == 1, r.get("itens_cancelados"))
checar("sobram duas vendas", r.get("importadas") in (0, 2),
       (r.get("importadas"), r.get("repetidas")))

st, r2 = chamar("POST", "/pdv/sincronizar?dias=1", token=token)
# ⚠️ A idempotencia e do BANCO, pelo `documento` = `venda_id`: reimportar o
# mesmo dia e o caso NORMAL de quem sincroniza de hora em hora.
checar("reimportar nao duplica", r2.get("importadas") == 0, r2)
checar("e conta as repetidas", (r2.get("repetidas") or 0) >= 2, r2)


print("\n8c. a janela e o teto de dias")
# ⚠️ A busca e DIA A DIA porque o `cupom/get` devolve no maximo 100 registros
# num intervalo de ate 10 dias — exceto quando data inicial = data final. Uma
# casa com 48 cupons por dia estoura os 100 em tres dias, e o corte seria mudo.
from services.pdv import importador as imp  # noqa: E402

chamadas = []


class ClienteFalso:
    modo = "simulado"

    def get(self, caminho, params=None):
        chamadas.append(caminho)
        return []


falso = ClienteFalso()
imp.buscar(falso, "37622", date(2026, 8, 1), date(2026, 8, 5))
checar("cinco dias viram CINCO chamadas, uma por dia", len(chamadas) == 5, len(chamadas))
checar("cada uma com data inicial IGUAL a final",
       all(c.split("/")[3] == c.split("/")[4] for c in chamadas), chamadas[:2])

chamadas.clear()
imp.buscar(falso, "37622", date(2025, 1, 1), date(2026, 8, 26))
# ⚠️ O teto nao e da API, e de paciencia: 600 dias sao 600 requisicoes, e uma
# tela que espera dez minutos parece travada.
checar("periodo enorme e cortado no teto",
       len(chamadas) == imp.TETO_DE_DIAS, len(chamadas))


print("\n8d. o mapeador aguenta o que o mundo real manda")
from services.pdv import mapeadores as mp  # noqa: E402

# ⚠️ `0001-01-01` e o vazio do .NET, nao uma data. Ele vem em `dtestorno` de
# tudo o que NAO foi estornado; tratá-lo como data poria venda no ano 1.
checar("a data vazia do .NET vira None", mp._data("0001-01-01T00:00:00") is None)
checar("e a data de verdade e lida",
       str(mp._data("2026-08-26T00:00:00")) == "2026-08-26", mp._data("2026-08-26T00:00:00"))

# ⚠️ Quantidade zero existe em cupom cancelado, e o unitario sai de uma divisao.
checar("quantidade zero nao estoura na divisao",
       mp.item({"quantidade": 0, "valortotal": 10})["valor_unitario"] == 0)
checar("o unitario sai do total da LINHA dividido pela quantidade",
       float(mp.item({"quantidade": 2, "valortotal": 11})["valor_unitario"]) == 5.5)

# ⚠️ Canal desconhecido vira None, nao "BALCAO": inventar canal faria o
# relatorio por canal mentir com cara de completo.
checar("canal desconhecido nao e inventado", mp.cupom({"tipovenda": "Z"})["canal"] is None)
checar("e o conhecido e traduzido", mp.cupom({"tipovenda": "D"})["canal"] == "DELIVERY")

# Estornado conta como cancelado: sao coisas diferentes la e a mesma aqui.
checar("estornado tambem nao vira venda",
       mp.cupom({"isestornado": True})["cancelada"] is True)

# A resposta as vezes vem como objeto solto em vez de lista.
checar("objeto solto e tratado como lista de um",
       len(mp.lista_de_cupons({"venda_id": 1})) == 1)
checar("e lista vazia nao estoura", mp.lista_de_cupons(None) == [])


print("\n8e. o cardapio e o de-para")
chamar("PUT", "/pdv/config", {"modo": "simulado", "ativa": True}, token=token)

# ⚠️ **O produto isca do bug real.** O `codReferencia` do REDBULL na fixture e
# "72". Se a cascata casasse codigo de cardapio com codigo da casa, este insumo
# seria o "produto" do REDBULL — e foi EXATAMENTE isso que aconteceu na conta do
# cliente: 78 vinculos, todos errados, e nenhum daria erro em lugar nenhum.
# O `codReferencia` do REDBULL na fixture e "72". Garante que existe um produto
# com esse codigo — criando, ou reaproveitando o que a base ja tiver.
st, r = chamar("POST", "/produtos", {
    "codigo": "72", "nome": f"Isca de codigo {marca}", "tipo": "INSUMO", "um_estoque": "KG",
}, token=token)
if st == 201:
    isca = r.get("id")
else:
    # ⚠️ Pelo BANCO, nao pela busca da lista: `busca=72` casa com qualquer nome
    # que tenha "72" dentro, e o que se quer aqui e o codigo EXATO. Numa base com
    # 2.200 produtos, procurar pelo texto devolve o produto errado ou nenhum.
    import psycopg2 as _pg
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from config import (DB_HOST as _H, DB_NAME as _N, DB_PASSWORD as _P,
                        DB_PORT as _O, DB_SSLMODE as _S, DB_USER as _U)

    with _pg.connect(host=_H, port=_O, user=_U, password=_P, dbname=_N,
                     sslmode=_S) as _c, _c.cursor() as _cur:
        _cur.execute("SELECT id FROM produtos WHERE codigo = %s", ("72",))
        achado = _cur.fetchone()
    isca = achado[0] if achado else None
checar("ha um produto cujo codigo colide com o do cardapio", isca is not None, (st, r))

# ⚠️ Nome IDENTICO ao do cardapio: este pode e deve vincular. E precisa de
# unidade — produto ATIVO sem unidade de estoque e recusado, porque quantidade
# sem unidade nao decide custo nenhum.
st, r = chamar("POST", "/produtos", {
    "codigo": f"EXPR{marca}", "nome": "CAFE EXPRESSO", "tipo": "PRODUZIDO",
    "um_estoque": "UN",
}, token=token)
expresso = r.get("id")
checar("cria um prato com o nome exato do cardapio", st == 201, (st, r))

st, r = chamar("POST", "/pdv/cardapio", token=token)
checar("a importacao do cardapio responde", st == 200, (st, r))
# ⚠️ O numero sai da fixture, nao de uma constante: a rota completa devolve uma
# LISTA e a resumida um ENVELOPE `{total_count, total, pagina, data}` — tratado
# como lista, o envelope daria "4 itens" para as quatro CHAVES dele. Contar o
# arquivo faz a checagem continuar valendo quando alguem acrescentar uma linha.
_fix = json.loads((Path(__file__).resolve().parents[1] / "services" / "pdv" /
                   "fixtures" / "produtos_get.json").read_text(encoding="utf-8"))
checar("le os itens do cardapio, nao as chaves de um envelope",
       r.get("itens") == len(_fix), (r.get("itens"), len(_fix)))
# ⚠️ Item fora do cardapio nasce INATIVO em vez de nao nascer: venda antiga
# aponta para ele, e sem cadastro a venda ficaria sem vinculo para sempre.
checar("item desligado no PDV entra, mas inativo",
       (r.get("criados") or 0) == 0 or (r.get("inativos") or 0) >= 1, r)
# ⚠️ Numa base ja importada o item cai em `ja_vinculados`, nao em `vinculados`:
# o que se afirma e que ele ACHOU dono, por um dos dois caminhos certos.
checar("e o de nome identico acha dono",
       (r.get("vinculados") or 0) + (r.get("ja_vinculados") or 0) >= 1, r)

st, ce = chamar("GET", f"/produtos/{expresso}", token=token)
checar("o prato de nome identico existe", st == 200, st)

st, isca_depois = chamar("GET", f"/produtos/{isca}", token=token)
checar("o produto isca nao foi tocado", isca_depois.get("id") == isca, isca_depois.get("id"))


print("\n8f. codigo de cardapio NAO casa com codigo da casa")
# O teste que trava o bug: depois de importar, o REDBULL nao pode ter virado o
# insumo de codigo "72".
from services.pdv import cardapio as card  # noqa: E402

import psycopg2  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_SSLMODE, DB_USER  # noqa: E402

conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
                        dbname=DB_NAME, sslmode=DB_SSLMODE)
with conn, conn.cursor(cursor_factory=RealDictCursor) as c:
    c.execute("""SELECT ce.id_produto, p.nome, p.tipo FROM codigos_externos ce
                   JOIN produtos p ON p.id = ce.id_produto
                  WHERE ce.sistema = 'PDV_LEGAL' AND ce.codigo = '10689996'""")
    vinculo = c.fetchone()
conn.close()

checar("o REDBULL do cardapio tem vinculo", vinculo is not None, vinculo)
if vinculo:
    # ⚠️ A afirmacao central deste arquivo. Se ela cair, o CMV teorico passa a
    # contar o custo de um insumo qualquer para um refrigerante — sem erro
    # nenhum, para sempre, e ninguem vai procurar ali.
    checar("e NAO e o insumo de codigo 72",
           vinculo["id_produto"] != isca, (vinculo["id_produto"], isca))
    checar("virou um prato proprio, em rascunho",
           vinculo["tipo"] == "PRODUZIDO", vinculo)


print("\n8g. semelhanca sugere, nao vincula")
# ⚠️ "PAO DE QUEIJO ESPECIAL" e parecido com "PAO DE QUEIJO" do cardapio, mas
# nao e a mesma coisa. Palpite que vincula sozinho contamina o CMV teorico de
# todo mes em que o prato foi vendido.
st, r = chamar("POST", "/produtos", {
    "codigo": f"PQE{marca}", "nome": "PAO DE QUEIJO ESPECIAL DA CASA",
    "tipo": "PRODUZIDO", "um_estoque": "UN",
}, token=token)
parecido = r.get("id")

conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
                        dbname=DB_NAME, sslmode=DB_SSLMODE)
with conn, conn.cursor(cursor_factory=RealDictCursor) as c:
    # Solta o de-para do PAO DE QUEIJO para a cascata rodar de novo nele.
    c.execute("DELETE FROM codigos_externos WHERE sistema='PDV_LEGAL' AND codigo='10689994'")
conn.close()

st, r = chamar("POST", "/pdv/cardapio", token=token)
conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
                        dbname=DB_NAME, sslmode=DB_SSLMODE)
with conn, conn.cursor(cursor_factory=RealDictCursor) as c:
    c.execute("""SELECT ce.id_produto, p.nome, p.observacao FROM codigos_externos ce
                   JOIN produtos p ON p.id = ce.id_produto
                  WHERE ce.sistema = 'PDV_LEGAL' AND ce.codigo = '10689994'""")
    pq = c.fetchone()
conn.close()

checar("o PAO DE QUEIJO voltou a ter vinculo", pq is not None, pq)
if pq:
    checar("e NAO foi amarrado no parecido",
           pq["id_produto"] != parecido, (pq["id_produto"], parecido))
    # A dica viaja com o rascunho: quem for fazer a ficha ve o palpite sem que
    # ele tenha decidido nada.
    checar("mas a semelhanca virou dica na observacao",
           pq["observacao"] and "arece com" in pq["observacao"], pq.get("observacao"))


print("\n8h. reconciliar liga as vendas que estavam pendentes")
st, r = chamar("POST", "/pdv/sincronizar?dias=1", token=token)
st, r = chamar("POST", "/pdv/reconciliar", token=token)
checar("a reconciliacao responde", st == 200, (st, r))
checar("e conta quantos ligou", "vinculados" in (r or {}), r)
# ⚠️ Sem ficha nao ha custo, e isso NAO e erro: e o proximo passo humano. O
# numero sai separado justamente para a tela poder dizer "ligou, mas falta a
# ficha" em vez de dizer so "ligou".
checar("distinguindo o que ficou sem custo",
       "sem_custo" in (r or {}), r)

for id_produto in (isca, expresso, parecido):
    if id_produto:
        chamar("DELETE", f"/produtos/{id_produto}", token=token)


print("\n8i. a busca das vendas rodando sozinha")
# ⚠️ **A regra do relógio é testada como FUNÇÃO PURA.** Pela API exigiria
# esperar uma hora passar; disparar o agendador de verdade contra a conta real
# do cliente traria venda de verdade para a base de teste.
from datetime import datetime, timedelta   # noqa: E402
from services import agenda_integracao as regra   # noqa: E402


def linha(freq, rodou=None, hora=4, ativa=True):
    return {"agenda_frequencia": freq, "agenda_rodou_em": rodou,
            "agenda_hora": hora, "ativa": ativa}


agora = datetime.now().astimezone().replace(hour=4)
checar("MANUAL nunca roda sozinho", not regra.deve_rodar(linha("MANUAL"), agora))
checar("integração desligada não roda",
       not regra.deve_rodar(linha("HORARIA", ativa=False), agora))
checar("HORARIA roda quando nunca rodou", regra.deve_rodar(linha("HORARIA"), agora))
checar("e não roda de novo meia hora depois",
       not regra.deve_rodar(linha("HORARIA", agora - timedelta(minutes=30)), agora))
checar("DIARIA só na hora escolhida", regra.deve_rodar(linha("DIARIA", hora=4), agora))
checar("fora da hora, não", not regra.deve_rodar(linha("DIARIA", hora=9), agora))
# ⚠️ Sem esta condição a diária rodaria a cada minuto durante os sessenta
# minutos daquela hora.
checar("e uma vez SÓ no dia",
       not regra.deve_rodar(linha("DIARIA", agora - timedelta(minutes=5), hora=4), agora))

# ⚠️ **A afirmação é sobre o PADRÃO, não sobre o estado da base.** "Ler MANUAL
# agora" só é verdade numa casa que nunca configurou nada — e esta base é
# compartilhada. O que precisa continuar valendo é que NADA liga a busca
# sozinho: um PUT que não fala de agenda a deixa MANUAL.
from routers.pdv import ConfigPdv   # noqa: E402
checar("o padrão da agenda é MANUAL", ConfigPdv().agenda_frequencia == "MANUAL",
       ConfigPdv().agenda_frequencia)
st, r = chamar("PUT", "/pdv/config", {"modo": "simulado", "ativa": True}, token=token)
st, c = chamar("GET", "/pdv/config", token=token)
checar("e salvar sem falar de agenda não liga nada",
       c.get("agenda_frequencia") == "MANUAL", c.get("agenda_frequencia"))
credencial_antes = c.get("username")

st, r = chamar("PUT", "/pdv/config", {
    "modo": "simulado", "ativa": True,
    "agenda_frequencia": "DIARIA", "agenda_hora": 5, "agenda_janela_dias": 3,
}, token=token)
checar("salvar a agenda responde", st == 200, (st, r))
st, c = chamar("GET", "/pdv/config", token=token)
checar("a frequência ficou", c.get("agenda_frequencia") == "DIARIA", c.get("agenda_frequencia"))
checar("a hora ficou", c.get("agenda_hora") == 5, c.get("agenda_hora"))
checar("a janela ficou", c.get("agenda_janela_dias") == 3, c.get("agenda_janela_dias"))
# ⚠️ A agenda GRAVA VENDA, e venda tem dono. Sem assinatura ela recusa rodar em
# vez de gravar mil linhas de auditoria sem ninguém a quem perguntar.
checar("e ficou assinada por quem salvou", c.get("agenda_assinada") is True, c)
checar("salvar a agenda NÃO mexeu na credencial",
       c.get("username") == credencial_antes, (c.get("username"), credencial_antes))

st, r = chamar("PUT", "/pdv/config",
               {"modo": "simulado", "agenda_frequencia": "SEMPRE"}, token=token)
checar("frequência inventada é recusada", st == 422, st)
st, r = chamar("PUT", "/pdv/config",
               {"modo": "simulado", "agenda_frequencia": "DIARIA", "agenda_hora": 30},
               token=token)
checar("hora impossível é recusada", st == 422, st)
st, r = chamar("PUT", "/pdv/config",
               {"modo": "simulado", "agenda_frequencia": "DIARIA", "agenda_janela_dias": 400},
               token=token)
checar("janela maior que o teto é recusada", st == 422, st)

st, r = chamar("POST", "/auth/login",
               {"email": "smoke.cozinha@botane.com.br", "senha": "smoke12345"})
tk_cozinha = (r or {}).get("access_token")
if tk_cozinha:
    st, r = chamar("PUT", "/pdv/config",
                   {"modo": "simulado", "agenda_frequencia": "HORARIA"}, token=tk_cozinha)
    checar("quem não administra integração não muda a agenda", st == 403, st)
else:
    checar("quem não administra integração não muda a agenda", True, "cozinha ausente")

# ⚠️ Os dois agendadores precisam de locks DIFERENTES: com o mesmo número, a
# busca de vendas ficaria esperando a de notas sem ter nada a ver com ela.
from services.omie import agenda as agenda_omie   # noqa: E402
from services.pdv import agenda as agenda_pdv   # noqa: E402
checar("o lock do PDV não é o do Omie",
       agenda_pdv.LOCK_AGENDA_PDV != agenda_omie.LOCK_AGENDA_OMIE,
       (agenda_pdv.LOCK_AGENDA_PDV, agenda_omie.LOCK_AGENDA_OMIE))

print("\n9. limpeza")
devolver_simulado()
st, c = chamar("GET", "/pdv/config", token=token)
checar("a integração volta para simulado", c.get("modo") == "simulado", c.get("modo"))
devolver_o_modo_original()
st, c = chamar("GET", "/pdv/config", token=token)
checar("e depois para o modo que a casa tinha",
       c.get("modo") == MODO_ORIGINAL, (c.get("modo"), MODO_ORIGINAL))

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
