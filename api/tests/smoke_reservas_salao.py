"""Saloes, mesas e lugares — e os conjuntos de mesas que se juntam.

🔑 **Pedido do dono (14/09/2026):** *"para controle interno, ter o cadastro de
saloes, cadastro de mesas, lugares por mesas."*

🔑 **`lugares` e `capacidade_max` sao DOIS numeros de proposito**: o confortavel
e o com-cadeira-extra. A alocacao usa o maximo, o relatorio de ocupacao usa os
lugares. Um campo so obrigaria a escolher entre mentir para o cliente e recusar
mesa que caberia.

⚠️ **A junta e RELACAO, nao atributo.** Gravar so de um lado deixaria a alocacao
achando um par que a outra mesa nao conhece — e qual das duas vale dependeria de
por onde a consulta entrou.

    python tests/smoke_reservas_salao.py        (API de pe na 9200)
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import preservar_reserva  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []
marca = uuid.uuid4().hex[:4].upper()


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + urllib.parse.quote(caminho, safe="/?=&"), method=metodo)
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


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()

_st, eu = chamar("GET", "/auth/me", token=token)
UNIDADE = (eu.get("unidades") or [{}])[0].get("id")


def ligar(valor: bool):
    return chamar("PUT", f"/unidades/{UNIDADE}/parametros", {"reservas_ligado": valor}, token)

# 🔑 **A suite devolve o que encontrou.** Ela precisa desmontar a reserva da loja
# para testar (modulo desligado, salao vazio, semana em branco), e sem isto o
# estado de teste ficava para tras — foi assim que a configuracao da casa se
# perdeu numa rodada de bateria. Ver `preservar_reserva` em `comum.py`.
devolver_a_reserva = preservar_reserva(UNIDADE)


def olhar():
    _st, r = chamar("GET", "/reservas/salao", token=token)
    return r


def mesa_chamada(dados, nome):
    return next((m for m in dados["mesas"] if m["nome"] == nome), None)


print("\n0. o salao segue a trava do modulo")
ligar(False)
st, r = chamar("GET", "/reservas/salao", token=token)
checar("com o modulo desligado, o salao responde 409", st == 409, (st, r))
ligar(True)
# ⚠️ Ponto de partida MONTADO: a suite grava cadastro, e cadastro sobrevive.
with get_cursor() as cur:
    # ⚠️ **Mesa com reserva pendurada NÃO se apaga** — `reserva_mesas_id_mesa_fkey`
    # é `ON DELETE RESTRICT` de propósito: a mesa é a resposta para onde aquelas
    # pessoas sentaram. Soltar o vínculo e a reserva primeiro é a ordem das
    # chaves estrangeiras.
    # 🔑 **Isto passou despercebido por depender da ORDEM das suítes**: a de
    # disponibilidade rodava antes e apagava as reservas dela na limpeza, então
    # esta sempre encontrava a loja vazia. No dia em que aquela passou a DEVOLVER
    # o que encontrou (`preservar_reserva`), esta quebrou no preparo.
    cur.execute("""DELETE FROM reserva_mesas WHERE id_reserva IN
                     (SELECT id FROM reservas WHERE id_unidade = %s)""", (UNIDADE,))
    cur.execute("DELETE FROM reservas WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM mesa_conjuntos WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM mesas WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM saloes WHERE id_unidade = %s", (UNIDADE,))
st, vazio = chamar("GET", "/reservas/salao", token=token)
checar("e ligado, responde 200 mesmo sem salao nenhum", st == 200, st)
checar("com tudo zerado", vazio["saloes"] == [] and vazio["lugares"] == 0
       and vazio["maior_grupo"] == 0, vazio)

print("\n1. cadastrar salao e mesas")
st, r = chamar("POST", "/reservas/saloes", {"nome": f"Salao principal {marca}"}, token)
principal = r.get("id")
checar("o salao nasce", st == 201 and bool(principal), (st, r))
st, r = chamar("POST", "/reservas/saloes", {"nome": f"Varanda {marca}", "ordem": 1}, token)
varanda = r.get("id")
checar("e o segundo tambem", st == 201 and bool(varanda), (st, r))
# ⚠️ O indice unico ja garantiria — o que ele nao faz e EXPLICAR.
st, r = chamar("POST", "/reservas/saloes", {"nome": f"salao principal {marca}"}, token)
checar("nome repetido (ate com outra caixa) e recusado com explicacao",
       st == 409 and "nome" in (r.get("detail") or "").lower(), (st, r))

def nova_mesa(nome, salao, lugares, maximo=None):
    corpo = {"id_salao": salao, "nome": nome, "lugares": lugares}
    if maximo is not None:
        corpo["capacidade_max"] = maximo
    st, r = chamar("POST", "/reservas/mesas", corpo, token)
    return st, r.get("id"), r

st, m01, _r = nova_mesa(f"{marca}-01", principal, 2, 3)
st2, m02, _r = nova_mesa(f"{marca}-02", principal, 2, 3)
st3, m07, _r = nova_mesa(f"{marca}-07", principal, 4, 6)
st4, m08, _r = nova_mesa(f"{marca}-08", principal, 4, 6)
st5, m12, _r = nova_mesa(f"{marca}-12", varanda, 6, 8)
checar("as cinco mesas nascem", all(x == 201 for x in (st, st2, st3, st4, st5)))

dados = olhar()
checar("os lugares somam o CONFORTAVEL: 2+2+4+4+6 = 18", dados["lugares"] == 18,
       dados["lugares"])
checar("e a capacidade maxima soma o com-cadeira-extra: 3+3+6+6+8 = 26",
       dados["capacidade_max"] == 26, dados["capacidade_max"])
# 🔑 Sem junta nenhuma, o maior grupo e a maior mesa sozinha — a 12, com 8.
checar("sem junta, o maior grupo e a maior mesa: 8", dados["maior_grupo"] == 8,
       dados["maior_grupo"])
checar("o salao mostra quantas mesas tem cada um",
       next(s for s in dados["saloes"] if s["id"] == principal)["mesas"] == 4)

print("\n2. o maximo nunca e menor que o confortavel")
st, _id, r = nova_mesa(f"{marca}-99", principal, 6, 4)
checar("criar com maximo menor que os lugares e recusado", st == 422, (st, r))
st, r = chamar("PUT", f"/reservas/mesas/{m12}", {"capacidade_max": 4}, token)
checar("e baixar o maximo abaixo dos lugares tambem", st == 422, (st, r))
# ⚠️ A coerencia e entre o valor NOVO e o que FICA: mandar so `lugares` tem de
# ser comparado ao maximo ja gravado.
st, r = chamar("PUT", f"/reservas/mesas/{m01}", {"lugares": 5}, token)
checar("subir so os lugares acima do maximo gravado tambem e recusado",
       st == 422, (st, r))
checar("e a mensagem mostra os dois numeros",
       "5" in (r.get("detail") or "") and "3" in (r.get("detail") or ""), r.get("detail"))

print("\n3. o CONJUNTO: mesas que se juntam, com capacidade propria (migracao 109)")
# 🔑 A junta era so em PAR (`mesas.junta_com`) e valia sempre a soma. Agora e um
# conjunto de 2 a 4 mesas, e a capacidade e a que a casa informa.


def conjunto_de(dados, *ids_mesas):
    alvo = sorted(ids_mesas)
    return next((c for c in dados["conjuntos"]
                 if sorted(m["id"] for m in c["mesas"]) == alvo), None)


st, r = chamar("POST", "/reservas/conjuntos", {"mesas": [m07, m08]}, token)
c78 = r.get("id")
checar("juntar a 07 com a 08 responde 201", st == 201 and c78, (st, r))
checar("sem dizer a capacidade, vale a soma dos maximos: 6 + 6 = 12",
       r.get("capacidade") == 12, r)
dados = olhar()
c = conjunto_de(dados, m07, m08)
checar("o salao devolve o conjunto com o NOME das mesas e a soma delas",
       c and sorted(m["nome"] for m in c["mesas"]) == [f"{marca}-07", f"{marca}-08"]
       and c["soma_maximos"] == 12, dados["conjuntos"])
checar("a mesa deixou de carregar a junta — ela mora no conjunto",
       "junta_com" not in mesa_chamada(dados, f"{marca}-07"), mesa_chamada(dados, f"{marca}-07"))
checar("o maior grupo passa a ser o CONJUNTO: 12", dados["maior_grupo"] == 12,
       dados["maior_grupo"])
# 🔑 Decisao do dono (07/10/2026): vale o numero que a casa informou, mesmo
# abaixo da soma — a casa sabe quantos cabem.
st, r = chamar("PUT", f"/reservas/conjuntos/{c78}", {"capacidade": 10}, token)
checar("baixar a capacidade do conjunto para 10 responde 200", st == 200, (st, r))
dados = olhar()
checar("e o maior grupo acompanha a capacidade INFORMADA (10), nao a soma (12)",
       dados["maior_grupo"] == 10 and conjunto_de(dados, m07, m08)["soma_maximos"] == 12,
       (dados["maior_grupo"], dados["conjuntos"]))

print("\n4. tres mesas, e a mesma mesa em mais de um conjunto")
st, r = chamar("POST", "/reservas/conjuntos", {"mesas": [m01, m07, m08], "capacidade": 13}, token)
c178 = r.get("id")
checar("tres mesas viram um conjunto (o par nao deixava)", st == 201 and c178, (st, r))
dados = olhar()
checar("a 07 esta em DOIS conjuntos",
       sum(1 for c in dados["conjuntos"] if any(m["id"] == m07 for m in c["mesas"])) == 2,
       dados["conjuntos"])
checar("e o maior grupo passa a 13", dados["maior_grupo"] == 13, dados["maior_grupo"])
st, r = chamar("POST", "/reservas/conjuntos", {"mesas": [m08, m07]}, token)
checar("o mesmo grupo de mesas nao vira dois conjuntos (409), em qualquer ordem",
       st == 409 and "capacidade" in (r.get("detail") or ""), (st, r))

print("\n5. o que o conjunto recusa")
st, r = chamar("POST", "/reservas/conjuntos", {"mesas": [m07]}, token)
checar("uma mesa so nao e conjunto (422)", st == 422, st)
st, r = chamar("POST", "/reservas/conjuntos", {"mesas": [m07, m07]}, token)
checar("uma mesa nao se junta com ela mesma (422)", st == 422, st)
st, r = chamar("POST", "/reservas/conjuntos", {"mesas": [m01, m02, m07, m08, m12]}, token)
checar("cinco mesas passam do limite de quatro (422)", st == 422, st)
st, r = chamar("POST", "/reservas/conjuntos", {"mesas": [m07, 99999999]}, token)
checar("mesa inexistente recusa o conjunto (404)", st == 404, (st, r))
st, r = chamar("POST", "/reservas/conjuntos", {"mesas": [m01, m02], "capacidade": 0}, token)
checar("capacidade zero e recusada (422)", st == 422, st)
st, r = chamar("PUT", "/reservas/conjuntos/99999999", {"capacidade": 4}, token)
checar("mudar conjunto que nao existe da 404", st == 404, st)
st, r = chamar("PUT", f"/reservas/mesas/{m07}", {"junta_com": m01}, token)
checar("o campo antigo da junta nao faz mais nada (400: nada para alterar)", st == 400, (st, r))
st, _r = chamar("PUT", f"/reservas/mesas/{m07}", {"nome": f"{marca}-07b"}, token)
checar("renomear a mesa NAO desfaz os conjuntos dela",
       len(olhar()["conjuntos"]) == 2, olhar()["conjuntos"])
st, r = chamar("DELETE", f"/reservas/conjuntos/{c178}", token=token)
checar("desfazer o conjunto responde 200", st == 200, (st, r))
st, r = chamar("DELETE", f"/reservas/conjuntos/{c178}", token=token)
checar("e desfazer de novo da 404", st == 404, st)
chamar("DELETE", f"/reservas/conjuntos/{c78}", token=token)
dados = olhar()
checar("sem conjunto nenhum, as mesas continuam e o maior grupo volta a 8",
       dados["conjuntos"] == [] and dados["maior_grupo"] == 8
       and mesa_chamada(dados, f"{marca}-07b") is not None, dados["maior_grupo"])

print("\n6. desligar o salao tira as mesas da conta")
# 🔑 E a Varanda no inverno: sai da disponibilidade sem perder cadastro.
st, r = chamar("PUT", f"/reservas/saloes/{varanda}", {"ativo": False}, token)
checar("desligar a varanda responde 200", st == 200, (st, r))
dados = olhar()
checar("os lugares caem de 18 para 12 (a mesa de 6 saiu)", dados["lugares"] == 12,
       dados["lugares"])
checar("mas a mesa dela continua CADASTRADA",
       mesa_chamada(dados, f"{marca}-12") is not None)
checar("e o maior grupo cai para 6, que e a maior que sobrou",
       dados["maior_grupo"] == 6, dados["maior_grupo"])
chamar("PUT", f"/reservas/saloes/{varanda}", {"ativo": True}, token)
checar("religar devolve os lugares", olhar()["lugares"] == 18)

# Mesa desativada tambem sai da conta, sem sair do cadastro.
chamar("PUT", f"/reservas/mesas/{m12}", {"ativo": False}, token)
checar("desativar a mesa tira os lugares dela", olhar()["lugares"] == 12)
chamar("PUT", f"/reservas/mesas/{m12}", {"ativo": True}, token)

print("\n7. o teto do site contra o salao")
# 🔑 Uma das duas descobertas do prototipo: teto maior que a maior junta e uma
# promessa que o salao nao cumpre, e quem pedir mais nao acha horario NENHUM
# sem saber por que. Por isso o numero vem junto na tela de configuracao.
st, cfg = chamar("GET", "/reservas/configuracao", token=token)
checar("a configuracao devolve o maior grupo do salao",
       cfg.get("maior_grupo") == olhar()["maior_grupo"], cfg.get("maior_grupo"))

print("\n8. salao com mesa nao se exclui")
st, r = chamar("DELETE", f"/reservas/saloes/{principal}", token=token)
checar("excluir salao com mesas e recusado", st == 409, (st, r))
checar("e a mensagem manda DESLIGAR em vez de apagar",
       "deslig" in (r.get("detail") or "").lower(), r.get("detail"))
# Mesa se apaga enquanto ninguem sentou nela — e leva junto os conjuntos dela.
# ⚠️ "01 + 02 + 07 acomoda 9" sem a 01 nao e um conjunto de 6: e um numero que
# ninguem informou. O conjunto inteiro deixa de existir.
chamar("POST", "/reservas/conjuntos", {"mesas": [m01, m02, m07], "capacidade": 9}, token)
chamar("POST", "/reservas/conjuntos", {"mesas": [m02, m08]}, token)
st, r = chamar("DELETE", f"/reservas/mesas/{m01}", token=token)
checar("a mesa se exclui", st == 200, (st, r))
dados = olhar()
checar("o conjunto de que ela fazia parte some INTEIRO, e o outro fica",
       len(dados["conjuntos"]) == 1 and conjunto_de(dados, m02, m08) is not None,
       dados["conjuntos"])
chamar("DELETE", f"/reservas/conjuntos/{conjunto_de(dados, m02, m08)['id']}", token=token)

print("\n9. montar o salao em LOTE")
# 🔑 Pedido do dono depois de ver a tela: montar um salao de doze mesas era
# clicar "+ mesa" doze vezes e renomear cada uma. O trabalho real do cadastro e
# esse, e ele acontece uma vez — no dia em que a casa entra no sistema.
st, r = chamar("POST", "/reservas/mesas/em-lote",
               {"id_salao": varanda, "quantidade": 6, "lugares": 4,
                "capacidade_max": 5, "prefixo": f"{marca}V"}, token)
checar("criar seis mesas de uma vez responde 201", st == 201, (st, r))
checar("e diz quantas nasceram e de que tamanho",
       "6 mesas" in (r.get("message") or "") and "4 lugares" in (r.get("message") or ""),
       r.get("message"))
checar("com os nomes numerados a partir do 01",
       r.get("criadas") == [f"{marca}V0{n}" for n in range(1, 7)], r.get("criadas"))
dados = olhar()
nascidas = [m for m in dados["mesas"] if m["nome"].startswith(f"{marca}V")]
checar("as seis existem no salao pedido",
       len(nascidas) == 6 and all(m["id_salao"] == varanda for m in nascidas), len(nascidas))
checar("com os dois numeros que o lote pediu",
       all(m["lugares"] == 4 and m["capacidade_max"] == 5 for m in nascidas), nascidas[:1])

# ⚠️ Pedir mais PULA os nomes ja usados em vez de recusar o lote: o nome e unico
# por LOJA, e "ja existe a V03" seria resposta inutil para quem so quis mais tres.
st, r = chamar("POST", "/reservas/mesas/em-lote",
               {"id_salao": varanda, "quantidade": 3, "lugares": 2,
                "prefixo": f"{marca}V"}, token)
checar("o lote seguinte continua a numeracao, sem colidir", st == 201
       and r.get("criadas") == [f"{marca}V07", f"{marca}V08", f"{marca}V09"],
       (st, r.get("criadas")))
# Sem prefixo, o maximo nao informado vale os lugares — quem nao tem cadeira
# extra nao precisa dizer nada.
st, r = chamar("POST", "/reservas/mesas/em-lote",
               {"id_salao": principal, "quantidade": 2, "lugares": 3}, token)
checar("sem maximo informado, ele vale os lugares", st == 201, (st, r))
dados = olhar()
novas = [m for m in dados["mesas"] if m["nome"] in (r.get("criadas") or [])]
checar("as duas nascem com maximo igual aos lugares",
       all(m["capacidade_max"] == 3 for m in novas), novas)
st, r = chamar("POST", "/reservas/mesas/em-lote",
               {"id_salao": varanda, "quantidade": 2, "lugares": 6, "capacidade_max": 4}, token)
checar("e o lote tambem recusa maximo menor que os lugares", st == 422, st)
st, r = chamar("POST", "/reservas/mesas/em-lote",
               {"id_salao": varanda, "quantidade": 99, "lugares": 2}, token)
checar("pedir mais que o teto de 50 e recusado", st == 422, st)

print("\n9b. as caracteristicas da mesa e a conferencia do cadastro (migracao 106)")
# 🔑 Primeira entrega do estudo `docs/salao-estudo.md` (06/10/2026). Um salao
# MONTADO do zero, para as respostas serem conferidas a mao:
#     A 2/2 · B 4/5 · C 4/4 · D 6/8, com C e D juntas (4 + 8 = 12)
with get_cursor() as cur:
    cur.execute("""DELETE FROM reserva_mesas WHERE id_reserva IN
                     (SELECT id FROM reservas WHERE id_unidade = %s)""", (UNIDADE,))
    cur.execute("DELETE FROM reservas WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM mesa_conjuntos WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM mesas WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM saloes WHERE id_unidade = %s", (UNIDADE,))
st, r = chamar("POST", "/reservas/saloes", {"nome": f"Conferencia {marca}"}, token)
conferencia = r.get("id")
ids = {}
for nome, lugares, maximo, marcas in (("A", 2, 2, ["JANELA"]), ("B", 4, 5, []),
                                      ("C", 4, 4, []), ("D", 6, 8, [])):
    st, r = chamar("POST", "/reservas/mesas", {
        "id_salao": conferencia, "nome": f"{marca}{nome}", "lugares": lugares,
        "capacidade_max": maximo, "caracteristicas": marcas}, token)
    ids[nome] = r.get("id")
checar("as quatro mesas da conferencia nascem", all(ids.values()), ids)
dados = olhar()
checar("a mesa criada com caracteristica a devolve",
       mesa_chamada(dados, f"{marca}A")["caracteristicas"] == ["JANELA"],
       mesa_chamada(dados, f"{marca}A"))
checar("e quem nasceu sem nenhuma devolve lista vazia, nao nulo",
       mesa_chamada(dados, f"{marca}B")["caracteristicas"] == [],
       mesa_chamada(dados, f"{marca}B"))

st, r = chamar("PUT", f"/reservas/mesas/{ids['B']}",
               {"caracteristicas": ["SOFA", "ACESSIVEL", "SOFA"]}, token)
checar("gravar caracteristicas e aceito", st == 200, (st, r))
checar("sem repeticao e em ordem",
       mesa_chamada(olhar(), f"{marca}B")["caracteristicas"] == ["ACESSIVEL", "SOFA"],
       mesa_chamada(olhar(), f"{marca}B"))
st, r = chamar("PUT", f"/reservas/mesas/{ids['B']}", {"lugares": 4}, token)
checar("mudar outra coisa NAO apaga as caracteristicas",
       mesa_chamada(olhar(), f"{marca}B")["caracteristicas"] == ["ACESSIVEL", "SOFA"])
st, r = chamar("PUT", f"/reservas/mesas/{ids['B']}", {"caracteristicas": ["PISCINA"]}, token)
checar("caracteristica fora da lista e recusada (422)", st == 422, (st, r))
st, r = chamar("PUT", f"/reservas/mesas/{ids['B']}", {"caracteristicas": []}, token)
checar("lista vazia limpa as caracteristicas",
       st == 200 and mesa_chamada(olhar(), f"{marca}B")["caracteristicas"] == [], (st, r))

_st, r = chamar("POST", "/reservas/conjuntos", {"mesas": [ids["C"], ids["D"]]}, token)
conjunto_cd = r.get("id")
_st, cfg = chamar("GET", "/reservas/configuracao", token=token)
dados = olhar()
checar("o salao devolve o teto do site, o mesmo da configuracao",
       "teto_online" in dados and dados["teto_online"] == cfg.get("teto_online"),
       (dados.get("teto_online"), cfg.get("teto_online")))


def senta(pessoas):
    _st, x = chamar("GET", f"/reservas/salao/simular?pessoas={pessoas}", token=token)
    return x


x = senta(2)
checar("grupo de 2 senta na A — a menor que serve",
       x["cabe"] and x["como"] == "mesa" and [m["nome"] for m in x["mesas"]] == [f"{marca}A"], x)
x = senta(5)
checar("grupo de 5 senta na B, pelo MAXIMO dela (5), nao pelos lugares (4)",
       x["cabe"] and [m["nome"] for m in x["mesas"]] == [f"{marca}B"], x)
x = senta(6)
checar("grupo de 6 senta na D sozinha — mesa inteira ganha da junta",
       x["como"] == "mesa" and [m["nome"] for m in x["mesas"]] == [f"{marca}D"], x)
x = senta(9)
checar("grupo de 9 so cabe na junta C + D",
       x["como"] == "junta" and sorted(m["nome"] for m in x["mesas"]) == [f"{marca}C", f"{marca}D"]
       and x["capacidade"] == 12, x)
checar("e a resposta diz o salao de cada mesa",
       all(m["salao"] == f"Conferencia {marca}" for m in x["mesas"]), x["mesas"])
x = senta(13)
checar("grupo de 13 nao cabe, e a resposta diz o maior que cabe (12)",
       x["cabe"] is False and x["como"] is None and x["mesas"] == [] and x["maior_grupo"] == 12, x)
checar("a conferencia concorda com o maior_grupo do salao",
       x["maior_grupo"] == olhar()["maior_grupo"], (x["maior_grupo"], olhar()["maior_grupo"]))

# Desligar a D tira a mesa E a junta dela da conta.
chamar("PUT", f"/reservas/mesas/{ids['D']}", {"ativo": False}, token)
x = senta(6)
checar("com a D desligada, grupo de 6 deixa de caber", x["cabe"] is False, x)
checar("e o maior grupo cai para 5", x["maior_grupo"] == 5, x["maior_grupo"])
chamar("PUT", f"/reservas/mesas/{ids['D']}", {"ativo": True}, token)
chamar("PUT", f"/reservas/saloes/{conferencia}", {"ativo": False}, token)
x = senta(2)
checar("com o salao desligado, ninguem senta", x["cabe"] is False and x["maior_grupo"] == 0, x)
chamar("PUT", f"/reservas/saloes/{conferencia}", {"ativo": True}, token)

st, r = chamar("GET", "/reservas/salao/simular?pessoas=0", token=token)
checar("grupo de zero pessoas e recusado (422)", st == 422, st)
st, r = chamar("GET", "/reservas/salao/simular", token=token)
checar("e sem dizer quantas pessoas tambem", st == 422, st)

print("\n9d. a capacidade do conjunto, os dias do salao e o site (migracao 109)")
# 🔑 Terceira entrega do estudo (07/10/2026) — as duas que mexem na regra.
chamar("PUT", f"/reservas/conjuntos/{conjunto_cd}", {"capacidade": 10}, token)
x = senta(10)
checar("o conjunto C + D informado como 10 senta um grupo de 10",
       x["como"] == "junta" and x["capacidade"] == 10, x)
x = senta(11)
checar("mas nao um de 11, mesmo com as mesas somando 12 — vale o que a casa informou",
       x["cabe"] is False and x["maior_grupo"] == 10, x)
chamar("PUT", f"/reservas/conjuntos/{conjunto_cd}", {"capacidade": 12}, token)

dados = olhar()
do_salao = next(s_ for s_ in dados["saloes"] if s_["id"] == conferencia)
checar("salao nasce atendendo os sete dias e aceitando o site",
       do_salao["dias_semana"] == [1, 2, 3, 4, 5, 6, 7] and do_salao["aceita_site"] is True,
       do_salao)

# O Mezanino: uma mesa de 10, so de sexta a domingo — e um conjunto dela com a D.
_st, r = chamar("POST", "/reservas/saloes", {"nome": f"Mezanino {marca}", "ordem": 9}, token)
mezanino = r.get("id")
_st, r = chamar("POST", "/reservas/mesas", {"id_salao": mezanino, "nome": f"{marca}E",
                                           "lugares": 10, "capacidade_max": 10}, token)
ids["E"] = r.get("id")
_st, r = chamar("POST", "/reservas/conjuntos", {"mesas": [ids["D"], ids["E"]], "capacidade": 16},
                token)
checar("um conjunto pode ter mesas de saloes diferentes", _st == 201, (_st, r))
st, r = chamar("PUT", f"/reservas/saloes/{mezanino}", {"dias_semana": [7, 5, 6, 5]}, token)
checar("os dias do salao se gravam", st == 200, (st, r))
checar("sem repeticao e em ordem",
       next(s_ for s_ in olhar()["saloes"] if s_["id"] == mezanino)["dias_semana"] == [5, 6, 7])


def senta_em(pessoas, dia_semana=None, site=False):
    caminho = f"/reservas/salao/simular?pessoas={pessoas}"
    if dia_semana:
        caminho += f"&dia_semana={dia_semana}"
    if site:
        caminho += "&site=true"
    _st, x = chamar("GET", caminho, token=token)
    return x


nomes = lambda x: sorted(m["nome"] for m in x["mesas"])  # noqa: E731
x = senta_em(10, dia_semana=6)
checar("no sabado, o grupo de 10 senta na mesa do Mezanino", nomes(x) == [f"{marca}E"], x)
x = senta_em(10, dia_semana=2)
checar("na terca o Mezanino nao abre: o grupo de 10 vai para o conjunto C + D",
       nomes(x) == [f"{marca}C", f"{marca}D"], x)
x = senta_em(14, dia_semana=6)
checar("no sabado, 14 pessoas sentam no conjunto D + E, pela capacidade dele (16)",
       nomes(x) == [f"{marca}D", f"{marca}E"] and x["capacidade"] == 16, x)
x = senta_em(14, dia_semana=2)
checar("na terca esse conjunto NAO existe — uma das mesas dele esta fechada",
       x["cabe"] is False and x["maior_grupo"] == 12, x)
x = senta_em(14)
checar("sem dizer o dia, a pergunta e sobre o cadastro inteiro", x["cabe"] is True, x)

st, r = chamar("PUT", f"/reservas/saloes/{mezanino}", {"dias_semana": []}, token)
checar("salao sem dia nenhum e recusado (422) — para isso existe desligar", st == 422, st)
st, r = chamar("PUT", f"/reservas/saloes/{mezanino}", {"dias_semana": [8]}, token)
checar("dia da semana fora de 1 a 7 e recusado (422)", st == 422, st)

st, r = chamar("PUT", f"/reservas/saloes/{mezanino}", {"aceita_site": False}, token)
checar("tirar o salao do site responde 200", st == 200, (st, r))
x = senta_em(10, dia_semana=6, site=True)
checar("pelo site, no sabado, o grupo de 10 NAO ve o Mezanino: vai para C + D",
       nomes(x) == [f"{marca}C", f"{marca}D"], x)
x = senta_em(10, dia_semana=6)
checar("mas o balcao continua vendo", nomes(x) == [f"{marca}E"], x)
dados = olhar()
checar("o salao separa o maior grupo da CASA (16) do que o SITE senta (12)",
       dados["maior_grupo"] == 16 and dados["maior_grupo_site"] == 12,
       (dados["maior_grupo"], dados.get("maior_grupo_site")))
checar("renomear o salao NAO mexe nos dias nem no site",
       chamar("PUT", f"/reservas/saloes/{mezanino}", {"nome": f"Mez {marca}"}, token)[0] == 200
       and next(s_ for s_ in olhar()["saloes"] if s_["id"] == mezanino)["dias_semana"] == [5, 6, 7]
       and next(s_ for s_ in olhar()["saloes"] if s_["id"] == mezanino)["aceita_site"] is False)
# O Mezanino sai de cena: a planta, a seguir, mede o salao A/B/C/D.
chamar("PUT", f"/reservas/saloes/{mezanino}", {"ativo": False}, token)

print("\n9c. a planta do salao: formato e posicao (migracao 108)")
# 🔑 Segunda entrega do estudo (07/10/2026). So DESENHO: nada aqui pode mudar a
# resposta de "onde o grupo senta".
antes_da_planta = {n: senta(n) for n in (2, 5, 9, 12)}
dados = olhar()
a, b = mesa_chamada(dados, f"{marca}A"), mesa_chamada(dados, f"{marca}B")
checar("mesa nasce QUADRADA e sem posicao",
       a.get("formato") == "QUADRADA" and a.get("pos_x") is None and a.get("pos_y") is None, a)
st, r = chamar("PUT", f"/reservas/mesas/{a['id']}", {"formato": "REDONDA"}, token)
checar("o formato se muda pela mesa", st == 200
       and mesa_chamada(olhar(), f"{marca}A")["formato"] == "REDONDA", (st, r))
st, r = chamar("PUT", f"/reservas/mesas/{a['id']}", {"formato": "OVAL"}, token)
checar("formato fora da lista e recusado (422)", st == 422, st)
st, r = chamar("PUT", f"/reservas/mesas/{a['id']}", {"lugares": 2}, token)
checar("mudar outra coisa NAO mexe no formato",
       mesa_chamada(olhar(), f"{marca}A")["formato"] == "REDONDA")

st, r = chamar("PUT", "/reservas/salao/planta", {"posicoes": [
    {"id": a["id"], "pos_x": 30, "pos_y": 60},
    {"id": b["id"], "pos_x": 180, "pos_y": 60},
]}, token)
checar("a planta grava as duas mesas de uma vez", st == 200 and "2 mesas" in r.get("message", ""),
       (st, r))
dados = olhar()
checar("e cada uma fica onde foi posta",
       (mesa_chamada(dados, f"{marca}A")["pos_x"], mesa_chamada(dados, f"{marca}A")["pos_y"]) == (30, 60)
       and (mesa_chamada(dados, f"{marca}B")["pos_x"], mesa_chamada(dados, f"{marca}B")["pos_y"]) == (180, 60),
       [(m["nome"], m["pos_x"], m["pos_y"]) for m in dados["mesas"]])
checar("quem nao foi mexida continua sem posicao",
       mesa_chamada(dados, f"{marca}C")["pos_x"] is None, mesa_chamada(dados, f"{marca}C"))

st, r = chamar("PUT", "/reservas/salao/planta", {"posicoes": [
    {"id": a["id"], "pos_x": 90, "pos_y": 90},
    {"id": 999999999, "pos_x": 10, "pos_y": 10},
]}, token)
checar("mesa que nao existe recusa a planta INTEIRA (404)", st == 404, (st, r))
checar("e nada do corpo recusado foi gravado",
       mesa_chamada(olhar(), f"{marca}A")["pos_x"] == 30, mesa_chamada(olhar(), f"{marca}A"))
st, r = chamar("PUT", "/reservas/salao/planta",
               {"posicoes": [{"id": a["id"], "pos_x": -5, "pos_y": 10}]}, token)
checar("posicao negativa e recusada (422)", st == 422, st)
st, r = chamar("PUT", "/reservas/salao/planta",
               {"posicoes": [{"id": a["id"], "pos_x": 99999, "pos_y": 10}]}, token)
checar("e fora da planta tambem (422)", st == 422, st)
st, r = chamar("PUT", "/reservas/salao/planta", {"posicoes": []}, token)
checar("planta vazia e recusada (422)", st == 422, st)
checar("formato e posicao NAO mudam onde o grupo senta",
       {n: senta(n) for n in (2, 5, 9, 12)} == antes_da_planta)

print("\n10. limpeza")
with get_cursor() as cur:
    # ⚠️ **Mesa com reserva pendurada NÃO se apaga** — `reserva_mesas_id_mesa_fkey`
    # é `ON DELETE RESTRICT` de propósito: a mesa é a resposta para onde aquelas
    # pessoas sentaram. Soltar o vínculo e a reserva primeiro é a ordem das
    # chaves estrangeiras.
    # 🔑 **Isto passou despercebido por depender da ORDEM das suítes**: a de
    # disponibilidade rodava antes e apagava as reservas dela na limpeza, então
    # esta sempre encontrava a loja vazia. No dia em que aquela passou a DEVOLVER
    # o que encontrou (`preservar_reserva`), esta quebrou no preparo.
    cur.execute("""DELETE FROM reserva_mesas WHERE id_reserva IN
                     (SELECT id FROM reservas WHERE id_unidade = %s)""", (UNIDADE,))
    cur.execute("DELETE FROM reservas WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM mesa_conjuntos WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM mesas WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM saloes WHERE id_unidade = %s", (UNIDADE,))
# 🔑 E a loja volta ao que era ANTES desta suite — inclusive o interruptor.
devolver_a_reserva()

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
