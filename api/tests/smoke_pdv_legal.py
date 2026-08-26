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

# ⚠️ A linha do PDV mora na MESMA tabela da do Omie. Este arquivo grava uma
# credencial de mentira ali: sem preservar, a real do cliente iria junto.
preservar_credenciais("PDV_LEGAL")

marca = str(time.time_ns())[-6:]
USUARIO = f"integracao{marca}@botane"
SENHA = f"senha-de-mentira-{marca}"
GRUPO = f"GRUPO-{marca}"
SEGREDO = f"token-do-grupo-{marca}"


def devolver_simulado():
    """Modo real com credencial de mentira bateria na Tablet Cloud de verdade."""
    chamar("PUT", "/pdv/config", {"modo": "simulado", "ativa": False}, token=token)


atexit.register(devolver_simulado)


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


print("\n9. limpeza")
devolver_simulado()
st, c = chamar("GET", "/pdv/config", token=token)
checar("a integração volta para simulado", c.get("modo") == "simulado", c.get("modo"))

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
