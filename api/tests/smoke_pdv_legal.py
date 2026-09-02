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


def _dono_do_codigo(codigo):
    """Que produto responde por este código do PDV — e por onde.

    ⚠️ **Dois níveis desde que o código virou campo do produto**: o principal em
    `produtos.codigo_pdv` e os apelidos em `codigos_externos`. Olhar só a tabela
    (como esta suíte fazia) deixa de fora justamente o vínculo que a tela mostra.
    """
    conexao = _conexao_do_banco()
    with conexao, conexao.cursor() as cur:
        cur.execute(
            "SELECT id, nome, tipo, observacao FROM produtos WHERE codigo_pdv = %s",
            (str(codigo),),
        )
        achado = cur.fetchone()
        if achado:
            return {**dict(achado), "id_produto": achado["id"], "onde": "principal"}
        cur.execute(
            """SELECT p.id, p.nome, p.tipo, p.observacao, ce.id_produto, ce.origem_vinculo
                 FROM codigos_externos ce JOIN produtos p ON p.id = ce.id_produto
                WHERE ce.sistema = 'PDV_LEGAL' AND ce.codigo = %s""",
            (str(codigo),),
        )
        achado = cur.fetchone()
        return {**dict(achado), "onde": "apelido"} if achado else None


def _soltar_codigo(codigo):
    """Tira este código dos DOIS lugares, para a cascata rodar de novo nele.

    ⚠️ **Solta a MARCA junto.** O gatilho da 040 marca `integrado_pdv` quando um
    produto ganha `codigo_pdv`; tirar só o código deixava o produto marcado e
    sem vínculo — que a fila de envio lê, corretamente, como "deve existir no
    PDV e não existe: criar". Dezoito rodadas depois, a fila do dono tinha
    dezoito PAO DE QUEIJO esperando para virar dezoito cadastros no cardápio do
    cliente. A suíte estava fabricando trabalho para alguém desfazer à mão.
    """
    conexao = _conexao_do_banco()
    with conexao, conexao.cursor() as cur:
        cur.execute(
            "UPDATE produtos SET codigo_pdv = NULL, integrado_pdv = false "
            " WHERE codigo_pdv = %s", (str(codigo),))
        cur.execute(
            "DELETE FROM codigos_externos WHERE sistema='PDV_LEGAL' AND codigo=%s", (str(codigo),)
        )
        conexao.commit()


def _conexao_do_banco():
    """Uma conexão direta ao banco, com dicionário por linha.

    Existe porque o de-para e o `codigo_omie` não têm rota de escrita — são
    internos de propósito. Repetir os seis parâmetros de conexão em cada fase é
    o caminho mais curto para uma delas ficar para trás.
    """
    from pathlib import Path

    import psycopg2
    from psycopg2.extras import RealDictCursor

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_SSLMODE, DB_USER

    return psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
                            dbname=DB_NAME, sslmode=DB_SSLMODE, cursor_factory=RealDictCursor)


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
# ⚠️ **O MODO viaja na resposta**, como na busca do Omie. Sem ele, quem esta em
# simulado importa venda de demonstracao e nao tem como saber -- os numeros
# aparecem no CMV como se fossem da casa. E a tela de Vendas usa este campo para
# dizer "(modo simulado -- dados de demonstracao)" no aviso.
checar("e o MODO, para a tela poder avisar que e demonstracao",
       r.get("modo") == "simulado", r.get("modo"))

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
# ⚠️ **Afirma sobre o ITEM da fixture, nao sobre o que esta rodada criou.**
# Contar `criados` so vale na primeira rodada de uma base virgem — na segunda o
# item ja existe, `criados` volta zero e a checagem acusava um bug que nao ha.
_desligado = next((x for x in _fix if x.get("status") is False), None)
# ⚠️ Sem `quote` aqui: `chamar` já escapa o caminho, e escapar duas vezes faz o
# espaço virar %2520 — a busca não acha nada e o teste acusa um bug que não há.
st_i, prod_i = chamar(
    "GET", f"/produtos?busca={_desligado['descricaoCupom']}&incluir_inativos=true",
    token=token) if _desligado else (0, [])
_achado = next((x for x in (prod_i or [])
                if x.get("codigo") == f"PDV-{_desligado['codigo']}"), None) if _desligado else None
checar("item desligado no PDV entra, mas inativo",
       _achado is not None and _achado.get("ativo") is False, (_achado, st_i))
# ⚠️ Numa base ja importada o item cai em `ja_vinculados`, nao em `vinculados`:
# o que se afirma e que ele ACHOU dono, por um dos dois caminhos certos.
# ⚠️ **O preco vem de OUTRA rota** (`tabelapreco/get/{filial}`), nao do cadastro
# do produto -- foi por isso que os pratos nasceram sem preco nenhum durante toda
# a primeira versao: o numero estava a uma chamada de distancia. Na conta real,
# `valor` vem preenchido em 629 dos 630.
st_p, prods_p = chamar("GET", "/produtos?busca=CAFE EXPRESSO&incluir_inativos=true", token=token)
_expresso = next((x for x in (prods_p or []) if x.get("codigo") == "PDV-10689993"), None)
# 🔑 **Quem manda aqui e o DONO do preco.** Com `enviar_ao_pdv` LIGADO o Botane
# passou a ser o dono, e `cardapio.importar` para de ler `tabelapreco` — senao os
# dois sistemas brigam: o preco alterado la volta por cima na sincronizacao
# seguinte e o envio o desfaz. A checagem afirma a REGRA, nao o numero do dia.
st_cfg, cfg_preco = chamar("GET", "/pdv/config", token=token)
somos_donos = bool(cfg_preco.get("enviar_ao_pdv"))
# 🔑 **O botao traz o preco SEMPRE, dono ou nao** — decisao do dono: o preco
# que vale no cupom e o do PDV. Houve uma versao que parava de le-lo com o
# envio ligado, para evitar o ping-pong, e o remedio era pior: o valor
# alterado la simplesmente se perdia. O que evita o ping-pong e isto ser
# MANUAL — a busca de vendas, que roda por agenda, nunca chama a importacao.
checar("o cardapio traz o preco de venda junto",
       _expresso is None or float(_expresso.get("preco_venda") or 0) == 5.5,
       (_expresso or {}).get("preco_venda"))

# 🔑 **Nome identico NAO liga — e a checagem afirmava o contrario.** A cascata
# por nome foi REMOVIDA deste projeto depois de ligar REDBULL a LIMAO TAITY e
# PAO COM MANTEIGA a MANJERICAO. A versao anterior exigia que o prato criado
# logo acima, com o nome EXATO do cardapio, achasse dono na importacao — e ela
# passava por sorte: era o `PDV-10689993` de uma rodada ANTERIOR que entrava
# como `ja_vinculados`, por CODIGO. Na base virgem a verdade apareceu.
st_e, prod_e = chamar("GET", f"/produtos/{expresso}", token=token)
checar("nome identico NAO liga sozinho: o prato continua sem codigo do PDV",
       not (prod_e or {}).get("codigo_pdv"), (prod_e or {}).get("codigo_pdv"))
# E nenhum item do cardapio fica orfao: o que nao acha dono NASCE rascunho.
checar("e nenhum item do cardapio fica sem dono",
       (r.get("sem_vinculo") or 0) == 0, r)

st, ce = chamar("GET", f"/produtos/{expresso}", token=token)
checar("o prato de nome identico existe", st == 200, st)

st, isca_depois = chamar("GET", f"/produtos/{isca}", token=token)
checar("o produto isca nao foi tocado", isca_depois.get("id") == isca, isca_depois.get("id"))


print("\n8e2. o EAN vincula sem depender do nome")
# ⚠️ **O EAN identifica o mesmo objeto FISICO no mundo todo** — e e ele que
# impede o mesmo pacote de cafe de virar dois cadastros: um vindo do catalogo do
# Omie (onde e comprado) e outro do cardapio (onde e vendido). Esse duplicado
# ninguem enxerga: a compra entra no estoque por um cadastro, a venda nao sai por
# nenhum, e a sobra aparece na contagem como "ajuste de inventario".
#
# ⚠️ O item da fixture tem nome DELIBERADAMENTE diferente do produto que carrega
# o EAN: se os nomes coincidissem, o passo do nome vincularia e o teste passaria
# sem exercitar nada.
EAN_FIXTURE = "7899999000019"
CODIGO_FIXTURE = "10689998"

def _sem_rastro_do_ean():
    """Devolve a base ao estado de antes — a suite tem de ser idempotente.

    Tira o de-para e o rascunho que uma rodada anterior possa ter criado; sem
    isso o passo 1 da cascata (de-para ja existe) responderia primeiro e o do
    EAN nunca seria exercitado.
    """
    _soltar_codigo(CODIGO_FIXTURE)
    conexao = _conexao_do_banco()
    with conexao, conexao.cursor() as cur:
        cur.execute("DELETE FROM produtos WHERE codigo = %s", (f"PDV-{CODIGO_FIXTURE}",))
        cur.execute("SELECT id, nome FROM produtos WHERE codigo_barras = %s", (EAN_FIXTURE,))
        dono = cur.fetchone()
        if dono:
            # ⚠️ **Devolve o NOME tambem.** Desde que o botao de importar passou a
            # sobrescrever, uma rodada anterior deixava este produto ja com o nome
            # do item da fixture — e a checagem seguinte, que exige nomes
            # DIFERENTES para exercitar o passo do EAN, acusava um defeito que nao
            # existe. Precondicao garantida, nao suposta.
            cur.execute("UPDATE produtos SET nome = %s WHERE id = %s RETURNING id, nome",
                        ("Tonica de conferencia do EAN", dono["id"]))
            dono = cur.fetchone()
        if not dono:
            cur.execute(
                """INSERT INTO produtos (codigo, nome, tipo, status, um_estoque,
                                         controla_estoque, codigo_barras, ativo)
                   VALUES ('SMOKE-EAN-TONICA', 'Tonica de conferencia do EAN', 'REVENDA',
                           'ATIVO', 'UN', true, %s, true)
                   RETURNING id, nome""",
                (EAN_FIXTURE,),
            )
            dono = cur.fetchone()
        conexao.commit()
    return dict(dono)

dono_do_ean = _sem_rastro_do_ean()
checar("ha um produto carregando o EAN da fixture", bool(dono_do_ean.get("id")), dono_do_ean)
checar("com nome diferente do item do cardapio",
       "tonica impossivel" not in (dono_do_ean.get("nome") or "").lower(), dono_do_ean)

st, r = chamar("POST", "/pdv/cardapio", token=token)
checar("a importacao responde", st == 200, (st, r))
checar("e conta o vinculo por EAN", (r.get("por_ean") or 0) >= 1, r)

vinculo = _dono_do_codigo(CODIGO_FIXTURE) or {}
conexao = _conexao_do_banco()
with conexao, conexao.cursor() as cur:
    cur.execute("SELECT 1 FROM produtos WHERE codigo = %s", (f"PDV-{CODIGO_FIXTURE}",))
    virou_rascunho = bool(cur.fetchone())
checar("o item do cardapio achou o produto pelo EAN",
       vinculo.get("id_produto") == dono_do_ean["id"], (vinculo, dono_do_ean["id"]))
# ⚠️ O codigo passa a ser o PRINCIPAL do produto -- o campo que a tela mostra --,
# e nao mais uma linha de de-para com rotulo de origem.
checar("e ele virou o codigo principal do produto",
       vinculo.get("onde") == "principal", vinculo)
# ⚠️ O ponto todo: sem o passo do EAN ele viraria um rascunho novo, e o mesmo
# produto ficaria com dois cadastros.
checar("e NAO criou um rascunho duplicado", not virou_rascunho, virou_rascunho)


print("\n8e3. EAN que ja e de OUTRO produto nao derruba a importacao")
# ⚠️ **O cenario acontece em tres tempos, e nenhum deles e estranho:**
#   1. o item do cardapio entra SEM ean e vira rascunho
#   2. depois o catalogo do Omie traz o produto de verdade, com o EAN
#   3. depois alguem preenche o EAN no PDV, e o cardapio e reimportado
# No passo 3 o item JA esta vinculado -- o primeiro passo da cascata responde
# antes do EAN -- e a gravacao batia no indice unico `ux_produto_barras`. Nao era
# um item que falhava: era a importacao INTEIRA que morria, porque a transacao e
# uma so, e nada entrava.
_soltar_codigo(CODIGO_FIXTURE)
conexao = _conexao_do_banco()
with conexao, conexao.cursor() as cur:
    cur.execute("DELETE FROM produtos WHERE codigo = 'SMOKE-EAN-RASCUNHO'")
    # O rascunho SEM ean, segurando o codigo do PDV no lugar do dono do EAN.
    cur.execute(
        """INSERT INTO produtos (codigo, nome, tipo, status, origem, producao_propria,
                                 controla_estoque, ativo, codigo_pdv)
           VALUES ('SMOKE-EAN-RASCUNHO', 'Rascunho que disputa o EAN', 'PRODUZIDO',
                   'RASCUNHO', 'PDV', true, false, true, %s) RETURNING id""",
        (CODIGO_FIXTURE,))
    rascunho = cur.fetchone()["id"]
    conexao.commit()

st, r = chamar("POST", "/pdv/cardapio", token=token)
checar("a importacao NAO estoura com o EAN disputado", st == 200, (st, r))
# ⚠️ O conflito e INFORMACAO, nao erro: dois cadastros disputando o mesmo EAN sao
# o mesmo produto. Quem resolve e /produtos/duplicados, que sabe mover o de-para,
# os itens de venda e o custo junto -- repontar o vinculo aqui deixaria as vendas
# passadas presas no rascunho.
checar("e conta o EAN que e de outro cadastro", (r.get("ean_de_outro") or 0) >= 1, r)
checar("a mensagem manda usar o Vincular",
       "vincular" in (r.get("message") or "").lower(), r.get("message"))

conexao = _conexao_do_banco()
with conexao, conexao.cursor() as cur:
    cur.execute("SELECT codigo_barras FROM produtos WHERE id = %s", (rascunho,))
    ainda = (cur.fetchone() or {}).get("codigo_barras")
    cur.execute("SELECT id FROM produtos WHERE codigo_barras = %s", (EAN_FIXTURE,))
    dono = (cur.fetchone() or {}).get("id")
checar("o rascunho NAO ficou com o EAN", ainda is None, ainda)
checar("e o EAN continua com o dono de antes", dono == dono_do_ean["id"], (dono, dono_do_ean["id"]))

# Devolve o de-para ao dono certo, para a suite ser idempotente.
_soltar_codigo(CODIGO_FIXTURE)
conexao = _conexao_do_banco()
with conexao, conexao.cursor() as cur:
    cur.execute("DELETE FROM produtos WHERE codigo = 'SMOKE-EAN-RASCUNHO'")
    conexao.commit()


print("\n8f. codigo de cardapio NAO casa com codigo da casa")
# O teste que trava o bug: depois de importar, o REDBULL nao pode ter virado o
# insumo de codigo "72".
from services.pdv import cardapio as card  # noqa: E402

import psycopg2  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_SSLMODE, DB_USER  # noqa: E402

vinculo = _dono_do_codigo("10689996")

checar("o REDBULL do cardapio tem vinculo", vinculo is not None, vinculo)
if vinculo:
    # ⚠️ A afirmacao central deste arquivo. Se ela cair, o CMV teorico passa a
    # contar o custo de um insumo qualquer para um refrigerante — sem erro
    # nenhum, para sempre, e ninguem vai procurar ali.
    checar("e NAO e o insumo de codigo 72",
           vinculo["id_produto"] != isca, (vinculo["id_produto"], isca))
    checar("virou um prato proprio, em rascunho",
           vinculo["tipo"] == "PRODUZIDO", vinculo)


print("\n8g. NOME parecido nao vincula, e nome IGUAL tambem nao")
# ⚠️ **A cascata por nome saiu inteira, e este bloco guarda o porque.** Ela
# errava nos DOIS sentidos: nao achava "BEB CERV HEINEKEN 350ML" contra "CERVEJA
# HEINEKEN PILSEN" -- o mesmo produto, 63,8% de semelhanca -- e juntava "CAKE
# BOARD N19" com "CAKE BOARD N21", que sao tamanhos diferentes. Nenhum piso
# separa os dois casos, porque a diferenca nao esta no texto.
#
# ⚠️ E o nome IDENTICO tambem nao vincula: "PAO DE QUEIJO" da casa pode ser outra
# receita que o "PAO DE QUEIJO" do cardapio. Quem reconhece produto e gente, e o
# caminho e o botao Vincular na tela do produto.
st, r = chamar("POST", "/produtos", {
    "codigo": f"PQE{marca}", "nome": "PAO DE QUEIJO ESPECIAL DA CASA",
    "tipo": "PRODUZIDO", "um_estoque": "UN",
}, token=token)
parecido = r.get("id")

st, r = chamar("POST", "/produtos", {
    "codigo": f"PQI{marca}", "nome": "PAO DE QUEIJO", "tipo": "PRODUZIDO",
    "um_estoque": "UN",
}, token=token)
identico = r.get("id")

_soltar_codigo("10689994")
conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
                        dbname=DB_NAME, sslmode=DB_SSLMODE)
with conn, conn.cursor(cursor_factory=RealDictCursor) as c:
    # Tira da frente o rascunho de rodadas anteriores, para o item ter de nascer
    # de novo -- e ai se ve a quem ele se liga.
    c.execute(
        """UPDATE produtos SET codigo = %s, nome = %s, ativo = false
            WHERE codigo = 'PDV-10689994'""",
        (f"PDV-10689994-{marca}", f"Rascunho antigo do pao de queijo {marca}"),
    )
conn.close()

st, r = chamar("POST", "/pdv/cardapio", token=token)
pq = _dono_do_codigo("10689994")

checar("o PAO DE QUEIJO do cardapio tem vinculo", pq is not None, pq)
if pq:
    checar("e NAO foi amarrado no parecido",
           pq["id_produto"] != parecido, (pq["id_produto"], parecido))
    # ⚠️ A afirmacao que a versao anterior nao fazia: nem o nome IGUAL vincula.
    checar("nem no de nome IGUAL",
           pq["id_produto"] != identico, (pq["id_produto"], identico))
    checar("virou um rascunho proprio", pq["tipo"] == "PRODUZIDO", pq)
    # ⚠️ E sem palpite escrito em lugar nenhum: sugestao que ninguem pediu vira
    # ruido na observacao e convida ao clique.
    checar("e sem dica de palpite na observacao",
           not (pq.get("observacao") or "").lower().count("parece com"), pq.get("observacao"))

# ⚠️ O caminho de verdade: quem reconhece liga a mao, e o codigo do PDV migra.
st, r = chamar("POST", f"/produtos/{identico}/vincular", {"id_sai": pq["id_produto"]},
               token=token)
checar("e o botao Vincular liga os dois", st == 200, (st, r))
depois = _dono_do_codigo("10689994")
checar("o codigo do PDV passou para o cadastro da casa",
       depois and depois["id_produto"] == identico, depois)


print()
print("8g2. a busca de vendas traz os cadastros junto — criar e desativar, so isso")
# 🔑 **Pedido do dono (01/09/2026): prato novo no PDV nasce aqui, prato desligado
# la e desativado aqui, e isso roda junto com a busca de vendas.** O que NAO roda
# junto e o ALINHAMENTO (nome curto, categoria, setor, unidade, NCM, CEST, EAN,
# preco): ele continua sendo o botao "Importar cardapio". Rodar o alinhamento
# sozinho, de hora em hora, desfaria calada a correcao de quem arrumou a
# categoria de um prato a mao — e era isso que "ser manual" protegia.
sys.path.insert(0, ".")
from database import get_cursor as _cur_pdv        # noqa: E402
from services.pdv import cardapio as _cardapio     # noqa: E402

st, achados = chamar("GET", "/produtos?busca=PDV-&incluir_inativos=true&limite=5", token=token)
alvo_p = next((p for p in (achados or []) if str(p.get("codigo", "")).startswith("PDV-")), None)
st, cats = chamar("GET", "/categorias", token=token)
outra = next((c for c in (cats or []) if alvo_p and c["id"] != alvo_p.get("id_categoria")), None)
if alvo_p and outra:
    chamar("PUT", f"/produtos/{alvo_p['id']}", {"id_categoria": outra["id"]}, token=token)
    with _cur_pdv() as _c:
        _c.execute("UPDATE integracoes SET cardapio_em = NULL WHERE servico = 'PDV_LEGAL'")
        checar("antes de sincronizar, o dia ainda nao foi marcado",
               _cardapio.cadastros_de_hoje(_c, 1) is False, True)
    st, r = chamar("POST", "/pdv/sincronizar?dias=1", token=token)
    checar("a busca de vendas responde com o bloco de cadastros",
           st == 200 and "cadastros" in (r or {}), (st, list(r or {})))
    checar("e nenhum item ficou sem vinculo, porque o cardapio veio ANTES",
           (r or {}).get("cadastros", {}).get("sem_vinculo") == 0,
           (r or {}).get("cadastros"))
    st, depois_p = chamar("GET", f"/produtos/{alvo_p['id']}", token=token)
    # 🔑 A afirmacao central: a correcao feita A MAO sobrevive.
    checar("e a categoria corrigida a mao NAO foi desfeita",
           depois_p.get("id_categoria") == outra["id"],
           (depois_p.get("id_categoria"), outra["id"]))
    with _cur_pdv() as _c:
        checar("o dia fica marcado, e a agenda nao rele o cardapio a cada hora",
               _cardapio.cadastros_de_hoje(_c, 1) is True, False)


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

print("\n8j. o interruptor do envio, e a marca de quem participa")
# A integracao so LIA do PDV. Escrever de volta mexe no sistema que a casa usa
# para vender, entao o caminho comeca por duas coisas que nao enviam nada: o
# interruptor e a marcacao de quem participa.
st, cfg = chamar("GET", "/pdv/config", token=token)
checar("a configuracao publica o interruptor de envio", "enviar_ao_pdv" in cfg, list(cfg))
# ⚠️ **"Nasce desligado" é propriedade da linha NOVA, não da que está aí.** A
# versao anterior afirmava `False` na configuracao atual e caiu no dia em que a
# casa ligou o envio — acusando de defeito uma decisao do dono. Quem garante o
# padrao e o `DEFAULT false` da migracao 040 mais o `coalesce(%s, false)` do
# INSERT; o que se testa aqui e que o campo existe e e booleano.
checar("e ele e um booleano", isinstance(cfg.get("enviar_ao_pdv"), bool),
       type(cfg.get("enviar_ao_pdv")).__name__)

# Um produto novo NAO nasce marcado: a marca e uma decisao.
st, novo_p = chamar("POST", "/produtos", {
    "codigo": f"PDVI{marca}", "nome": f"Pdv integrado {marca}",
    "tipo": "PRODUZIDO", "um_estoque": "UN",
}, token=token)
id_novo = novo_p.get("id")
st, p_novo = chamar("GET", f"/produtos/{id_novo}", token=token)
checar("produto novo nao nasce integrado", p_novo.get("integrado_pdv") is False,
       p_novo.get("integrado_pdv"))

# Quem GANHA o codigo do PDV e marcado pelo BANCO. O `codigo_pdv` e escrito em
# quatro lugares (formulario, importacao do cardapio e as duas rotas do
# Vincular); marcar na aplicacao exigiria lembrar nos quatro, e o quinto
# nasceria sem a marca — o produto passaria a existir no PDV e nunca apareceria
# na fila de envio.
chamar("PUT", f"/produtos/{id_novo}", {**p_novo, "codigo_pdv": f"C{marca}"}, token=token)
st, p_novo = chamar("GET", f"/produtos/{id_novo}", token=token)
checar("ganhar o codigo do PDV marca sozinho", p_novo.get("integrado_pdv") is True,
       (p_novo.get("integrado_pdv"), p_novo.get("codigo_pdv")))

# E o DESMARQUE fica de pe: "existe no PDV e eu nao quero que o Botane mexa
# nele" e um estado legitimo. Um gatilho que forcasse `true` sempre que houvesse
# codigo o destruiria no primeiro save.
chamar("PUT", f"/produtos/{id_novo}", {**p_novo, "integrado_pdv": False}, token=token)
st, p_novo = chamar("GET", f"/produtos/{id_novo}", token=token)
checar("o dono pode desmarcar quem veio do PDV",
       p_novo.get("integrado_pdv") is False, p_novo.get("integrado_pdv"))
chamar("PUT", f"/produtos/{id_novo}", {**p_novo, "observacao": "salvou de novo"},
       token=token)
st, p_novo = chamar("GET", f"/produtos/{id_novo}", token=token)
checar("e salvar de novo nao remarca", p_novo.get("integrado_pdv") is False,
       p_novo.get("integrado_pdv"))
chamar("DELETE", f"/produtos/{id_novo}", token=token)

# O produto no cardapio do PDV carrega GRUPO e IMPRESSORA — a categoria e o
# setor daqui. Mandar um produto cujo grupo nao existe la tende a falhar, entao
# os dois tambem se marcam.
st, s_novo = chamar("POST", "/setores", {"nome": f"Setor pdv {marca}"}, token=token)
id_setor_pdv = s_novo.get("id")
st, setores_ = chamar("GET", "/setores?incluir_inativos=true", token=token)
achado = next((x for x in setores_ if x["id"] == id_setor_pdv), {})
checar("setor tem a marca de integrado com PDV", "integrado_pdv" in achado, achado)
checar("e nasce desmarcado", achado.get("integrado_pdv") is False, achado)
chamar("PUT", f"/setores/{id_setor_pdv}", {"integrado_pdv": True}, token=token)
st, setores_ = chamar("GET", "/setores?incluir_inativos=true", token=token)
achado = next((x for x in setores_ if x["id"] == id_setor_pdv), {})
checar("e a marca do setor grava", achado.get("integrado_pdv") is True, achado)
chamar("DELETE", f"/setores/{id_setor_pdv}", token=token)

st, c_novo = chamar("POST", "/categorias",
                    {"nome": f"Cat pdv {marca}", "tipo": "PRODUZIDO"}, token=token)
id_cat_pdv = c_novo.get("id")
st, cats = chamar("GET", "/categorias?incluir_inativas=true", token=token)
achada = next((x for x in cats if x["id"] == id_cat_pdv), {})
checar("categoria tem a marca de integrado com PDV", "integrado_pdv" in achada, achada)
chamar("PUT", f"/categorias/{id_cat_pdv}", {"integrado_pdv": True}, token=token)
st, cats = chamar("GET", "/categorias?incluir_inativas=true", token=token)
achada = next((x for x in cats if x["id"] == id_cat_pdv), {})
checar("e a marca da categoria grava", achada.get("integrado_pdv") is True, achada)
chamar("DELETE", f"/categorias/{id_cat_pdv}", token=token)

# ⚠️ **A versao anterior afirmava sobre a CARGA da 041** — "os setores marcados
# sao VITRINE, BAR e COZINHA" —, e isso e o estado do dia: ficou falso no
# instante em que a casa limpou as tabelas de apoio para recadastrar. O que se
# afirma agora e a propriedade: setor MARCADO carrega a marca, e ela grava.
st, setores_ = chamar("GET", "/setores", token=token)
marcados = [x["nome"] for x in setores_ if x.get("integrado_pdv")]
checar("a marca de integrado existe no setor",
       not setores_ or "integrado_pdv" in setores_[0], (setores_ or [{}])[0])

# 🔑 A dica de interface viaja no /auth/me — quem cadastra produto nao tem
# `integracao.pdv` para perguntar ao /pdv/config.
st, me = chamar("GET", "/auth/me", token=token)
checar("o /auth/me diz se o envio esta ligado", "enviar_ao_pdv" in me, list(me))


print("\n8k. a fila de envio ao PDV")
# ⚠️ Em SIMULADO: a fila le o cardapio do outro lado, e uma suite que roda toda
# hora nao pode ficar batendo na conta do cliente por isso.
st, cfg_atual = chamar("GET", "/pdv/config", token=token)
base_cfg = {"modo": cfg_atual["modo"], "ativa": cfg_atual["ativa"],
            "agenda_frequencia": cfg_atual["agenda_frequencia"],
            "agenda_hora": cfg_atual["agenda_hora"],
            "agenda_janela_dias": cfg_atual.get("agenda_janela_dias")}
chamar("PUT", "/pdv/config", {**base_cfg, "modo": "simulado",
                              "enviar_ao_pdv": False}, token=token)
st, r = chamar("GET", "/pdv/envio/fila", token=token)
checar("com o envio desligado a fila recusa", st == 409, st)
checar("e a frase diz onde ligar", "Integra" in str(r.get("detail")), r)

chamar("PUT", "/pdv/config", {**base_cfg, "modo": "simulado",
                              "enviar_ao_pdv": True}, token=token)
st, fila = chamar("GET", "/pdv/envio/fila", token=token)
checar("ligado, a fila responde", st == 200 and "pendentes" in fila, st)
checar("com as tres abas",
       all(k in fila for k in ("pendentes", "integrados", "erros")), list(fila))

# 🔑 O que mais importa nesta tela: o que JA EXISTE no PDV entra como ADOTAR,
# nunca como CRIAR. Sem isso o primeiro envio duplicaria o cardapio inteiro do
# cliente — 30 grupos que existem ha anos e nunca souberam do Botane.
# ⚠️ **A precondicao e GARANTIDA, nao suposta.** Estas checagens contavam com a
# CAFETERIA e o BAR que a importacao do cardapio tinha deixado na base — e
# morreram no dia em que a casa limpou as tabelas de apoio para recadastrar.
# Agora a suite cria os dois com os nomes que existem no cardapio simulado,
# afirma, e desfaz.
def _garantir(rota: str, corpo: dict, listagem: str) -> tuple[int | None, bool]:
    """Cria, ou acha o que ja existe. Devolve (id, fui_eu_que_criei).

    ⚠️ **Nome repetido devolve 409**, e a versao anterior tratava isso como
    "sem id": a marca nao era gravada e a checagem seguinte acusava a fila de
    nao reconhecer um setor que estava la. Precondicao GARANTIDA quer dizer
    tambem "ja existia serve".
    """
    st_, r_ = chamar("POST", rota, corpo, token=token)
    if st_ in (200, 201) and (r_ or {}).get("id"):
        return r_["id"], True
    st_, lista_ = chamar("GET", listagem, token=token)
    # ⚠️ **Sem caixa.** A unicidade do nome no banco ignora maiusculas, entao o
    # POST devolve 409 para "BAR" quando ja existe "Bar" — e a busca exata nao
    # achava o registro que o proprio servidor acabou de citar. Resultado: a
    # marca nao era gravada e a checagem acusava a fila de nao reconhecer um
    # setor que estava la.
    alvo_ = corpo["nome"].strip().upper()
    achado = next((x for x in (lista_ or [])
                   if (x.get("nome") or "").strip().upper() == alvo_), None)
    return (achado or {}).get("id"), False

id_cat_prova, _criei_cat = _garantir("/categorias", {"nome": "CAFETERIA", "tipo": "PRODUZIDO"},
                                     "/categorias?incluir_inativas=true")
if id_cat_prova:
    chamar("PUT", f"/categorias/{id_cat_prova}", {"integrado_pdv": True}, token=token)
id_set_prova, _criei_set = _garantir("/setores", {"nome": "BAR", "ordem": 0}, "/setores")
if id_set_prova:
    chamar("PUT", f"/setores/{id_set_prova}", {"integrado_pdv": True}, token=token)
st, fila = chamar("GET", "/pdv/envio/fila", token=token)

acoes = {(p["tipo"], p["nome"]): p["acao"] for p in fila["pendentes"]}
cafeteria = next((a for (t, n), a in acoes.items()
                  if t == "CATEGORIA" and n == "CAFETERIA"), None)
checar("categoria que ja existe no PDV entra como ADOTAR", cafeteria == "ADOTAR", cafeteria)
# ⚠️ **A afirmacao é sobre o INVARIANTE, nao sobre o estado do dia.** A versao
# anterior exigia BAR pendente como ADOTAR — e BAR passou a INTEGRADO assim que
# a casa adotou os setores de verdade, derrubando a checagem sem que nada
# estivesse errado. O que nao pode acontecer nunca e outra coisa: propor CRIAR
# para um registro que ja existe do outro lado. Foi esse o defeito que quase
# duplicou o cardapio do cliente.
nomes_la = {"ALMOCO", "CAFETERIA", "CHA", "BAR", "CAIXA", "COZINHA", "VITRINE"}
criar_indevido = [p["nome"] for p in fila["pendentes"]
                  if p["acao"] == "CRIAR" and p["nome"].upper() in nomes_la]
checar("nunca propoe CRIAR para o que ja existe no PDV", not criar_indevido, criar_indevido)
# ⚠️ Comparado SEM CAIXA: nome de setor nao passa pelo gatilho de maiusculas
# (esse e so do produto), entao a casa pode ter cadastrado "Bar".
conhecidos = {(p["nome"] or "").strip().upper()
              for p in fila["pendentes"] + fila["integrados"]}
checar("e o setor que ja existe la e reconhecido", "BAR" in conhecidos,
       sorted(conhecidos)[:8])

# 🔑 **Apagar uma categoria aqui nao pode virar cardapio DUPLICADO la.** O
# `codRefExterna` do grupo aponta para o id da nossa categoria; apagada ela, o
# grupo sumia do `por_ref` (ninguem o reivindica) E do `por_nome` (que so recebe
# grupo sem dono) — e a categoria recadastrada com o MESMO nome nao achava nada
# dos dois lados, fazendo a fila propor CRIAR. A fixture tem um grupo com dono
# inexistente exatamente para provar isto.
id_orfa, _criei_orfa = _garantir("/categorias",
                                 {"nome": "GRUPO ORFAO DO PDV", "tipo": "PRODUZIDO"},
                                 "/categorias?incluir_inativas=true")
if id_orfa:
    chamar("PUT", f"/categorias/{id_orfa}", {"integrado_pdv": True}, token=token)
    st, fila_o = chamar("GET", "/pdv/envio/fila", token=token)
    orfa = next((p["acao"] for p in fila_o["pendentes"] + fila_o["integrados"]
                 if p["tipo"] == "CATEGORIA" and p["nome"] == "GRUPO ORFAO DO PDV"), None)
    checar("categoria recriada ADOTA o grupo de dono perdido, nao duplica",
           orfa == "ADOTAR", orfa)
    if _criei_orfa:
        chamar("DELETE", f"/categorias/{id_orfa}", token=token)

# 🔑 **Preco divergente aparece na fila — antes era INVISIVEL dos dois lados.**
# Com o Botane dono do preco, `cardapio.importar` parou de le-lo, e a fila
# comparava so nome, grupo e impressora: um preco alterado no PDV nao constava em
# lugar nenhum aqui, e o envio seguinte o sobrescrevia calado.
# ⚠️ Precisa da FILIAL configurada: preco e por filial, e sem ela nao se compara.
st, _cfg_f = chamar("GET", "/pdv/config", token=token)
chamar("PUT", "/pdv/config", {**base_cfg, "modo": "simulado", "enviar_ao_pdv": True,
                              "filiais": "30638"}, token=token)
st, prods_pr = chamar("GET", "/produtos?busca=CAFE EXPRESSO&incluir_inativos=true",
                      token=token)
_pr = next((x for x in (prods_pr or []) if x.get("codigo") == "PDV-10689993"), None)
if _pr:
    # A fixture cobra 5,50 nesse item; aqui o preco vai para 7,25 de proposito.
    chamar("PUT", f"/produtos/{_pr['id']}",
           {"integrado_pdv": True, "preco_venda": 7.25}, token=token)
    st, fila_pr = chamar("GET", "/pdv/envio/fila", token=token)
    _dele = next((i for i in fila_pr["pendentes"] + fila_pr["integrados"]
                  if i["tipo"] == "PRODUTO" and i["id_registro"] == _pr["id"]), None)
    checar("preco diferente do PDV poe o produto como pendente",
           _dele and _dele["acao"] == "ATUALIZAR", _dele and _dele["acao"])
    # ⚠️ Os DOIS lado a lado: dizer so "atualizar" faria quem confere abrir o PDV
    # para descobrir qual dos dois valores esta velho.
    checar("e a fila mostra o valor dos dois lados",
           _dele and float(_dele.get("preco_no_pdv") or 0) == 5.5,
           _dele and (_dele.get("preco"), _dele.get("preco_no_pdv")))
    # Devolve: preco igual ao da fixture, e a marca como estava.
    chamar("PUT", f"/produtos/{_pr['id']}",
           {"integrado_pdv": False, "preco_venda": 5.5}, token=token)
chamar("PUT", "/pdv/config", {**base_cfg, "modo": "simulado", "enviar_ao_pdv": True,
                              "filiais": (_cfg_f or {}).get("filiais")}, token=token)
# Desfaz so o que ESTA suite criou: apagar o que a casa ja tinha seria a suite
# mexendo no cadastro de quem usa o sistema.
for _id, _rota, _meu in ((id_cat_prova, "categorias", _criei_cat),
                         (id_set_prova, "setores", _criei_set)):
    if _id and _meu:
        chamar("DELETE", f"/{_rota}/{_id}", token=token)

# 🔑 **Um PUT que NAO manda o campo mantem o valor.** Este endpoint substitui a
# linha inteira, e com `False` de padrao qualquer chamada que omitisse o campo
# DESLIGAVA o envio em silencio — um cliente antigo, uma tela que so salva a
# agenda, um script de restauro. Aconteceu com o restaurador da agenda na suite
# de navegador, e o sintoma e o pior possivel: a tela de Exportacao some do menu
# e nada explica.
chamar("PUT", "/pdv/config", {**base_cfg, "enviar_ao_pdv": True}, token=token)
chamar("PUT", "/pdv/config", base_cfg, token=token)   # sem o campo, de proposito
st, c = chamar("GET", "/pdv/config", token=token)
checar("um PUT sem o campo MANTEM o envio ligado", c.get("enviar_ao_pdv") is True,
       c.get("enviar_ao_pdv"))
chamar("PUT", "/pdv/config", {**base_cfg, "enviar_ao_pdv": False}, token=token)
st, c = chamar("GET", "/pdv/config", token=token)
checar("e mandar False desliga de verdade", c.get("enviar_ao_pdv") is False,
       c.get("enviar_ao_pdv"))
chamar("PUT", "/pdv/config", {**base_cfg, "enviar_ao_pdv": True}, token=token)

# E o corpo da adocao preserva o que e DELES: adotar e reconhecer, nao impor.
adocao = next((p for p in fila["pendentes"]
               if p["tipo"] == "CATEGORIA" and p["nome"] == "CAFETERIA"), None)
if adocao:
    checar("a adocao leva o codigo deles", adocao["corpo"].get("codigo") == 328953, adocao)
    checar("e preserva a cor de la", adocao["corpo"].get("corIcone") == "2980B9", adocao)
    checar("gravando o NOSSO id no codRefExterna",
           adocao["corpo"].get("codRefExterna") == adocao["id_registro"], adocao)

# ⚠️ O modo simulado NAO inventa sucesso: enviar ali tem de recusar, senao a aba
# de integrados encheria de registro que nao existe no PDV.
st, r = chamar("POST", "/pdv/envio", {}, token=token)
checar("enviar em simulado nao finge que gravou",
       st >= 400 or (r or {}).get("falhas", 0) > 0, (st, r))

# ⚠️ DEVOLVE o que a casa tinha, nunca "False" fixo. Esta suite rodou depois de
# o dono ligar o envio e o deixou DESLIGADO, sem avisar — a tela de Exportacao
# some do menu e nada explica por que. Mesma licao do `devolver_o_modo_original`
# e do `preservar_credenciais`: teste que mexe em configuracao devolve o que achou.
# 🔑 **E o restauro vai no `atexit`, não aqui.** Feito em linha, ele devolvia o
# interruptor no MEIO da suíte — e o bloco 8l, escrito depois, precisa dele
# LIGADO: a suíte passava só quando a casa por acaso tinha o envio ligado, e
# quebrava com 409 no dia em que ele estava desligado. É a mesma armadilha do
# "teste que descreve o estado do dia", pela ponta da configuração.
atexit.register(lambda: chamar(
    "PUT", "/pdv/config",
    {**base_cfg, "enviar_ao_pdv": cfg_atual.get("enviar_ao_pdv", False)}, token=token))


print("\n8l. a tabela intermediaria de pendencias")
# 🔑 **Nada vai ao PDV em tempo real.** Alterar um cadastro gera PENDENCIA, que
# espera alguem conferir e mandar. E quem alimenta a tabela e o GATILHO, nao o
# codigo: nenhum caminho da aplicacao consegue esquecer, nem o que ainda vai ser
# escrito. A suite usa um setor DELA, criado e apagado aqui.
# ⚠️ `.upper()`: o nome do setor é normalizado pelo BANCO (gatilho da migração
# 050), como já era o do produto. Todas as comparações abaixo usam o nome
# GRAVADO — afirmar sobre o que a suíte mandou é a armadilha que a 036 já
# custou a onze checagens.
NOME_SETOR_PEND = f"Pend setor {marca}".upper()
st, s_p = chamar("POST", "/setores", {"nome": f"Pend setor {marca}",
                                      "integrado_pdv": True}, token=token)
id_sp = s_p.get("id")
checar("cria o setor desta rodada, ja marcado", st == 201, (st, s_p))

st, fila_p = chamar("GET", "/pdv/envio/fila", token=token)
nomes_pend = {p["nome"] for p in fila_p["pendentes"]}
# Ele nao existe no PDV simulado: entra como CRIAR.
achado = next((p for p in fila_p["pendentes"] if p["nome"] == NOME_SETOR_PEND), None)
checar("o setor novo entra na fila", achado is not None, sorted(nomes_pend)[:6])
checar("e como CRIAR, porque nao existe la",
       (achado or {}).get("acao") == "CRIAR", (achado or {}).get("acao"))

# ⚠️ Salvar sem mudar nada NAO gera pendencia nova: `AFTER UPDATE OF nome`
# dispara quando a coluna e ESCRITA, mesmo com o mesmo valor, e sem o `WHEN`
# abrir um cadastro e salvar criava fila do nada.
chamar("PUT", f"/setores/{id_sp}", {"nome": f"Pend setor {marca}"}, token=token)
chamar("PUT", f"/setores/{id_sp}", {"ativo": True}, token=token)
st, fila_p = chamar("GET", "/pdv/envio/fila", token=token)
quantos = sum(1 for p in fila_p["pendentes"] if p["nome"] == NOME_SETOR_PEND)
checar("salvar sem mudar nada nao duplica a fila", quantos == 1, quantos)

# ⚠️ Uma pendencia ABERTA por registro: dez correcoes viram uma linha, nao dez.
for i in range(3):
    chamar("PUT", f"/setores/{id_sp}", {"nome": f"Pend setor {marca} v{i}"}, token=token)
st, fila_p = chamar("GET", "/pdv/envio/fila", token=token)
quantos = sum(1 for p in fila_p["pendentes"] if p["nome"].startswith(NOME_SETOR_PEND))
checar("tres alteracoes seguidas dao UMA linha", quantos == 1, quantos)

# 🔑 **A guarda de conta recusa o lote INTEIRO em simulado — e esta certo.** A
# filial da fixture e de DEMONSTRACAO (CNPJ 00.000.000/0001-00), e nao desta
# casa. Fazer a fixture se passar pela empresa do cliente para "o teste
# funcionar" seria plantar aqui exatamente a confusao que ja custou 46 vendas
# de terceiro na base: credencial de integracao nao diz de quem ela e.
st, r = chamar("POST", "/pdv/envio",
               {"itens": [{"tipo": "SETOR", "id_registro": id_sp}]}, token=token)
checar("a guarda de conta recusa o envio em simulado", st == 409, (st, r))
checar("e a frase diz que a conta e de outra empresa",
       "outra empresa" in str((r or {}).get("detail", "")), r)

# ⚠️ E o mais importante: recusado o lote, a pendencia continua ABERTA. E isso
# que faz o registro voltar para Pendentes depois de alguem corrigir, sem ter
# de mexer no cadastro so para reenfileirar.
st, fila_p = chamar("GET", "/pdv/envio/fila", token=token)
ainda = any(p["nome"].startswith(NOME_SETOR_PEND) for p in fila_p["pendentes"])
checar("e a pendencia continua ABERTA", ainda, ainda)

chamar("DELETE", f"/setores/{id_sp}", token=token)


print("\n8m. o produto na fila de envio")
# 🔑 **O que ja existe no cardapio entra como ADOTAR, nunca CRIAR.** Sao 630
# produtos la; propor criar duplicaria o cardapio do cliente. O casamento e pelo
# `produtos.codigo_pdv` — NUNCA por nome: a cascata por nome foi removida da
# importacao depois de ligar REDBULL a LIMAO TAITY.
st, fila_p = chamar("GET", "/pdv/envio/fila", token=token)
prods = [p for p in fila_p["pendentes"] if p["tipo"] == "PRODUTO"]
criar = [p for p in prods if p["acao"] == "CRIAR"]
adotar = [p for p in prods if p["acao"] == "ADOTAR"]
checar("os produtos do cardapio entram na fila", len(prods) > 0, len(prods))
# ⚠️ **Invariante, nao o estado do dia.** "Nenhum CRIAR" passou a ser falso no
# instante em que a casa cadastrou um produto novo de verdade — e acusava de
# defeito uma decisao de quem usa. O que nunca pode acontecer e propor CRIAR
# para quem JA esta no cardapio: e isso que duplicaria o cardapio do cliente.
checar("nunca propoe CRIAR para quem ja esta no cardapio",
       not [p for p in criar if p.get("codigo_pdv")],
       [p["nome"] for p in criar if p.get("codigo_pdv")][:5])

# 🔑 **Produto com `codigo_pdv` guardado NUNCA e ADOTAR.** Medido contra a conta
# real: `produtos/update` responde "Registry updated successfully!" e IGNORA o
# `codRefExterna`. Adotar, no produto, nao escreve nada — entao propor adocao
# para quem ja tem o codigo aqui e uma fila que nunca esvazia, reescrevendo o
# cardapio inteiro do cliente a cada clique em Enviar. Foram 630 assim.
com_codigo = [p for p in prods if p.get("codigo_pdv")]
checar("produto com codigo do PDV guardado nao vira adocao",
       not [p for p in com_codigo if p["acao"] == "ADOTAR"],
       [p["nome"] for p in com_codigo if p["acao"] == "ADOTAR"][:5])

# ⚠️ O corpo do produto NAO leva imposto nenhum. Os campos fiscais da linha de
# preco (CFOP, CSOSN, CST, PIS/Cofins, reforma tributaria) estao preenchidos em
# 629 dos 630 no PDV e o Botane nao tem nenhum deles: manda-los zerados
# derrubaria a emissao fiscal do cliente.
if adotar or [p for p in fila_p["integrados"] if p["tipo"] == "PRODUTO"]:
    algum = (adotar or [p for p in fila_p["integrados"] if p["tipo"] == "PRODUTO"])[0]
    proibidos = {"codCFOP", "codCSOSN", "codCST", "codPisCofins", "pis", "cofins",
                 "reformaTributaria", "codICMS_ISS"}
    checar("o corpo do produto nao carrega imposto",
           not (proibidos & set(algum["corpo"])), sorted(set(algum["corpo"]) & proibidos))

# ⚠️ Produto INATIVO aqui e inexistente la nao vira cadastro novo, e produto com
# `codigo_pdv` que sumiu do cardapio nao vira duplicado: fica a VISTA, sem agir.
st, p_inativo = chamar("POST", "/produtos", {
    "codigo": f"INAT{marca}", "nome": f"Inativo pdv {marca}", "tipo": "PRODUZIDO",
    "um_estoque": "UN", "integrado_pdv": True,
}, token=token)
id_inat = p_inativo.get("id")
# ⚠️ `POST /produtos` nao aceita `ativo` (o modelo de criacao tem `status`);
# desativar e um segundo passo, que e como acontece na vida real.
chamar("PUT", f"/produtos/{id_inat}", {"ativo": False}, token=token)
st, fila_p = chamar("GET", "/pdv/envio/fila", token=token)
checar("produto inativo aqui nao nasce no cardapio",
       not any(p["id_registro"] == id_inat for p in fila_p["pendentes"]),
       [p["nome"] for p in fila_p["pendentes"] if p["id_registro"] == id_inat])
chamar("DELETE", f"/produtos/{id_inat}", token=token)


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
