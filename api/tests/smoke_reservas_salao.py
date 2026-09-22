"""Saloes, mesas e lugares — e a junta, que vale nos DOIS sentidos.

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

print("\n3. a junta vale nos DOIS sentidos")
st, r = chamar("PUT", f"/reservas/mesas/{m07}", {"junta_com": m08}, token)
checar("juntar a 07 com a 08 responde 200", st == 200, (st, r))
dados = olhar()
a07, a08 = mesa_chamada(dados, f"{marca}-07"), mesa_chamada(dados, f"{marca}-08")
checar("a 07 aponta para a 08", a07["junta_com"] == m08, a07)
# 🔑 O ponto do teste: gravar de um lado so deixaria a alocacao achando um par
# que a outra mesa nao conhece.
checar("e a 08 aponta de volta para a 07, sem ninguem ter pedido",
       a08["junta_com"] == m07, a08)
checar("a tela recebe o NOME do par, nao so o id",
       a07["junta_com_nome"] == f"{marca}-08", a07)
# Agora a junta 6+6 = 12 passa a ser o maior grupo, acima da mesa de 8.
checar("o maior grupo passa a ser a JUNTA: 6+6 = 12", olhar()["maior_grupo"] == 12)

print("\n4. trocar o par nao deixa triangulo")
# ⚠️ Sem desfazer a junta anterior dos dois lados, a 08 ficaria apontando para a
# 07 enquanto a 07 aponta para a 01 — um triangulo que nenhuma das tres descreve.
st, r = chamar("PUT", f"/reservas/mesas/{m07}", {"junta_com": m01}, token)
checar("mudar o par da 07 para a 01 responde 200", st == 200, (st, r))
dados = olhar()
checar("a 07 agora aponta para a 01",
       mesa_chamada(dados, f"{marca}-07")["junta_com"] == m01)
checar("a 01 aponta de volta para a 07",
       mesa_chamada(dados, f"{marca}-01")["junta_com"] == m07)
checar("e a 08 foi SOLTA, nao ficou apontando para a 07",
       mesa_chamada(dados, f"{marca}-08")["junta_com"] is None,
       mesa_chamada(dados, f"{marca}-08"))

print("\n5. o que a junta recusa")
st, r = chamar("PUT", f"/reservas/mesas/{m07}", {"junta_com": m07}, token)
checar("uma mesa nao encosta nela mesma", st == 422, (st, r))
st, r = chamar("PUT", f"/reservas/mesas/{m07}", {"junta_com": 99999999}, token)
checar("junta com mesa inexistente e recusada", st == 404, (st, r))
# ⚠️ "Nao mandou" e "mandou nulo" sao coisas diferentes: renomear a mesa NAO
# pode soltar o par dela.
st, _r = chamar("PUT", f"/reservas/mesas/{m07}", {"nome": f"{marca}-07b"}, token)
dados = olhar()
checar("renomear a mesa NAO desfaz a junta",
       mesa_chamada(dados, f"{marca}-07b")["junta_com"] == m01, dados["mesas"])
st, _r = chamar("PUT", f"/reservas/mesas/{m07}", {"junta_com": None}, token)
dados = olhar()
checar("mas mandar nulo DESFAZ, nos dois lados",
       mesa_chamada(dados, f"{marca}-07b")["junta_com"] is None
       and mesa_chamada(dados, f"{marca}-01")["junta_com"] is None, dados["mesas"])

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
# Mesa se apaga enquanto ninguem sentou nela — e apagar solta a vizinha.
chamar("PUT", f"/reservas/mesas/{m01}", {"junta_com": m02}, token)
st, r = chamar("DELETE", f"/reservas/mesas/{m01}", token=token)
checar("a mesa se exclui", st == 200, (st, r))
dados = olhar()
checar("e a vizinha dela fica solta, nao apontando para o vazio",
       mesa_chamada(dados, f"{marca}-02")["junta_com"] is None,
       mesa_chamada(dados, f"{marca}-02"))

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
    cur.execute("DELETE FROM mesas WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM saloes WHERE id_unidade = %s", (UNIDADE,))
# 🔑 E a loja volta ao que era ANTES desta suite — inclusive o interruptor.
devolver_a_reserva()

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
