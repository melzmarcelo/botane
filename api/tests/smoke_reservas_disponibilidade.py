"""A regra de disponibilidade — a peca que tudo o mais consome.

🔑 **E o coracao do modulo, e onde a maioria dos sistemas de reserva erra.** O
prototipo em `apresentacao/reservas-prototipo.html` implementa a mesma regra em
JavaScript e serviu de especificacao executavel.

O que esta suite prova, e por que cada uma importa:

- **"Esgotado" depende do TAMANHO DO GRUPO.** No mesmo horario pode nao haver
  mesa para 6 e haver para 2. Por isso a lista de horarios so se calcula depois
  de saber quantas pessoas sao.
- **Contar lugares livres nao serve**: quatro lugares em duas mesas de dois nao
  sentam um grupo de quatro. A regra aloca MESA.
- **A menor mesa que serve primeiro**: por um casal na mesa de oito e o que faz
  o grupo de oito nao caber meia hora depois.
- **Reserva PENDENTE segura a mesa.** Se nao segurasse, a casa aprovaria no dia
  seguinte e descobriria que nao cabe.
- **A permanencia decide quando a mesa volta**, e ela muda com a hora do dia.

    python tests/smoke_reservas_disponibilidade.py        (API de pe na 9200)
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date, timedelta

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

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

chamar("PUT", f"/unidades/{UNIDADE}/parametros", {"reservas_ligado": True}, token)

# ------------------------------------------------------------------ o cenario
# ⚠️ Ponto de partida MONTADO: a suite grava cadastro e reserva, e os dois
# sobrevivem entre rodadas.
with get_cursor() as cur:
    cur.execute("DELETE FROM reserva_mesas WHERE id_reserva IN "
                "(SELECT id FROM reservas WHERE id_unidade = %s)", (UNIDADE,))
    cur.execute("DELETE FROM reservas WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM reserva_bloqueios WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM mesas WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM saloes WHERE id_unidade = %s", (UNIDADE,))

# Um sabado, sempre: a semana e configurada com o sabado aberto.
DIA = date.today()
while DIA.isoweekday() != 6 or DIA <= date.today():
    DIA += timedelta(days=1)

_st, cfg = chamar("GET", "/reservas/configuracao", token=token)
semana = [{"dia_semana": h["dia_semana"], "aberto": h["dia_semana"] == 6,
           "abre": "11:00", "fecha": "18:00", "ultima_reserva": "15:00"}
          for h in cfg["horarios"]]
st, _r = chamar("PUT", "/reservas/configuracao", {
    "aceita_online": True, "confirmacao": "AUTOMATICA", "teto_online": 8,
    "tolerancia_min": 15, "folga_min": 0, "passo_min": 30,
    "antecedencia_min_horas": 0, "antecedencia_max_dias": 365,
    "cadastro_completo": True, "horarios": semana,
    # Uma faixa so, para o calculo ficar legivel: 90 minutos o dia inteiro.
    "permanencias": [{"nome": "Almoco", "de": "11:00", "ate": "18:00", "minutos": 90}],
}, token)
checar("a semana e configurada com o sabado aberto", st == 200, st)

_st, salao = chamar("POST", "/reservas/saloes", {"nome": f"Principal {marca}"}, token)
SALAO = salao["id"]


def nova_mesa(nome, lugares, maximo):
    _st, r = chamar("POST", "/reservas/mesas",
                    {"id_salao": SALAO, "nome": f"{marca}{nome}",
                     "lugares": lugares, "capacidade_max": maximo}, token)
    return r.get("id")


# Duas de 2 que se juntam, uma de 4, uma de 6.
m01 = nova_mesa("01", 2, 2)
m02 = nova_mesa("02", 2, 2)
m04 = nova_mesa("04", 4, 4)
m06 = nova_mesa("06", 6, 6)
chamar("PUT", f"/reservas/mesas/{m01}", {"junta_com": m02}, token)
checar("o salao do teste tem quatro mesas", all([m01, m02, m04, m06]))


def livres(pessoas, dia=None, ignorar=None):
    caminho = f"/reservas/disponibilidade?data={dia or DIA}&pessoas={pessoas}"
    if ignorar:
        caminho += f"&ignorar={ignorar}"
    _st, r = chamar("GET", caminho, token=token)
    return r


def reservar(hora, pessoas, nome=None, origem="BALCAO", dia=None):
    return chamar("POST", "/reservas", {
        "data": str(dia or DIA), "hora": hora, "pessoas": pessoas,
        "nome": nome or f"Teste {marca}", "origem": origem,
    }, token)


print("\n1. o dia vazio oferece a janela inteira")
d = livres(2)
checar("a disponibilidade responde", bool(d.get("horarios")), d.get("motivo"))
# Das 11:00 as 15:00, de 30 em 30 = 9 horarios.
checar("com um horario a cada 30 minutos, ate a ULTIMA RESERVA",
       len(d["horarios"]) == 9 and d["horarios"][0]["hora"] == "11:00"
       and d["horarios"][-1]["hora"] == "15:00", [h["hora"] for h in d["horarios"]])
# 🔑 A ultima reserva e antes do fechamento: quem senta as 15h sai as 16:30.
checar("e a tela sabe quando a mesa vai vagar",
       d["horarios"][-1]["sai_por_volta"] == "16:30", d["horarios"][-1])
checar("com tudo livre num dia sem reserva nenhuma",
       all(h["livre"] for h in d["horarios"]))

print("\n2. a MENOR mesa que serve, e nao a primeira que couber")
# 🔑 Por um casal na mesa de 6 e o que faz o grupo de 6 nao caber depois.
st, casal = reservar("12:00", 2)
checar("um casal as 12:00 e aceito", st == 201, (st, casal))
checar("e senta na MENOR mesa que serve, nao na de 6",
       casal.get("mesas") in ([f"{marca}01"], [f"{marca}02"]), casal.get("mesas"))
st, r6 = reservar("12:00", 6, nome=f"Grupo {marca}")
checar("e o grupo de 6 ainda cabe as 12:00, na mesa de 6", st == 201, (st, r6))
checar("na mesa certa", r6.get("mesas") == [f"{marca}06"], r6.get("mesas"))

print("\n3. 'esgotado' depende do TAMANHO DO GRUPO")
# 🔑 A checagem que define a regra: mesmo horario, respostas diferentes.
d6 = livres(6)
d2 = livres(2)
as_12_para_6 = next(h for h in d6["horarios"] if h["hora"] == "12:00")
as_12_para_2 = next(h for h in d2["horarios"] if h["hora"] == "12:00")
checar("as 12:00 NAO ha mais mesa para 6", not as_12_para_6["livre"], as_12_para_6)
checar("mas AINDA ha para 2, no mesmo horario", as_12_para_2["livre"], as_12_para_2)

print("\n4. contar lugares livres nao serve — a regra aloca MESA")
# Sobram a 02 (2 lugares) e a 04 (4). Sao 6 lugares livres, e um grupo de 5 nao
# senta: nenhuma mesa sozinha serve, e a junta possivel (01+02) tem a 01 ocupada.
d5 = livres(5)
as_12_para_5 = next(h for h in d5["horarios"] if h["hora"] == "12:00")
checar("com 6 lugares livres em duas mesas, um grupo de 5 NAO senta",
       not as_12_para_5["livre"], as_12_para_5)
st, r = reservar("12:00", 5)
checar("e a tentativa e recusada com 409", st == 409, (st, r))
checar("dizendo para olhar os horarios disponiveis",
       "horários" in (r.get("detail") or ""), r.get("detail"))

print("\n5. a permanencia decide quando a mesa volta")
# A reserva das 12:00 na mesa de 6 ocupa ate 13:30 (folga 0 neste teste).
# ⚠️ **Esta secao vem ANTES da junta de proposito.** Ela mede a mesa de 6, e a
# secao seguinte vai ocupa-la as 14:00. Na primeira versao a ordem estava
# trocada: esta checagem media um salao que a secao anterior ja tinha enchido, e
# acusava a regra de um estado que o proprio teste criara.
mapa = {h["hora"]: h["livre"] for h in livres(6)["horarios"]}
checar("as 13:00 a mesa de 6 ainda esta ocupada", mapa["13:00"] is False, mapa)
# 🔑 13:30 e o limite exato: a janela nova comeca quando a antiga termina, e
# intervalos que se TOCAM nao se cruzam.
checar("as 13:30 ela ja vagou — os intervalos se tocam, nao se cruzam",
       mapa["13:30"] is True, mapa)

print("\n6. a JUNTA e o ULTIMO recurso — mesa inteira vem antes")
# 🔑 **Mesa sozinha ganha da junta, e isso e produto, nao acaso.** Juntar mesas e
# trabalho fisico e fragmenta o salao: so se faz quando nao ha mesa que sirva.
# A primeira versao desta suite esperava a junta com a mesa de 6 ainda LIVRE — e
# acusou de defeito exatamente o comportamento certo.
st, q1 = reservar("14:00", 4, nome=f"Quarteto A {marca}")
checar("o primeiro grupo de 4 senta na mesa de 4 (a menor que serve)",
       st == 201 and q1.get("mesas") == [f"{marca}04"], (st, q1.get("mesas")))
st, q2 = reservar("14:00", 4, nome=f"Quarteto B {marca}")
checar("o segundo vai para a de 6, que e a menor que SOBROU",
       st == 201 and q2.get("mesas") == [f"{marca}06"], (st, q2.get("mesas")))
st, q3 = reservar("14:00", 4, nome=f"Quarteto C {marca}")
checar("so o terceiro usa a JUNTA das duas de 2", st == 201, (st, q3))
checar("ocupando as DUAS mesas",
       sorted(q3.get("mesas") or []) == [f"{marca}01", f"{marca}02"], q3.get("mesas"))
st, _r = reservar("14:00", 2)
checar("e as 14:00 nao sobra mesa nem para um casal", st == 409, st)

print("\n7. reserva PENDENTE tambem segura a mesa")
# 🔑 Uma das duas descobertas do prototipo: se nao segurasse, a casa aprovaria
# no dia seguinte e descobriria que nao cabe.
# ⚠️ **Num dia LIMPO, de proposito.** Testar isto no dia que as secoes anteriores
# encheram misturaria duas causas — "a pendente segurou" e "ja nao havia mesa".
OUTRO = DIA + timedelta(days=7)
st, pend = chamar("POST", "/reservas", {
    "data": str(OUTRO), "hora": "15:00", "pessoas": 6,
    "nome": f"Pendente {marca}", "origem": "SITE",
}, token)
checar("uma reserva do site as 15:00 e aceita no dia limpo", st == 201, (st, pend))
id_pendente = pend.get("id")
# A loja esta em confirmacao AUTOMATICA; forca PENDENTE para provar a regra.
with get_cursor() as cur:
    cur.execute("UPDATE reservas SET status = 'PENDENTE' WHERE id = %s", (id_pendente,))
as_15 = next(h for h in livres(6, dia=OUTRO)["horarios"] if h["hora"] == "15:00")
checar("e mesmo PENDENTE ela segura a mesa", not as_15["livre"], as_15)
# ⚠️ Cancelar SOLTA — cancelada e nao-compareceu sao os unicos que soltam.
st, _r = chamar("PUT", f"/reservas/{id_pendente}/status", {"status": "CANCELADA"}, token)
checar("cancelar responde 200", st == 200, st)
as_15 = next(h for h in livres(6, dia=OUTRO)["horarios"] if h["hora"] == "15:00")
checar("e a mesa volta a ficar livre", as_15["livre"], as_15)

print("\n8. o ciclo de status so anda pelos caminhos que existem")
st, r = chamar("PUT", f"/reservas/{id_pendente}/status", {"status": "CHEGOU"}, token)
checar("marcar chegada de quem cancelou e recusado", st == 409, (st, r))
checar("dizendo em que estado ela esta",
       "CANCELADA" in (r.get("detail") or ""), r.get("detail"))
st, _r = chamar("PUT", f"/reservas/{r6['id']}/status", {"status": "CHEGOU"}, token)
checar("mas confirmada -> chegou passa", st == 200, st)
st, _r = chamar("PUT", f"/reservas/{r6['id']}/status", {"status": "ENCERRADA"}, token)
checar("e chegou -> encerrada tambem", st == 200, st)
# ⚠️ ENCERRADA continua segurando a mesa daquele horario: a mesa FOI usada, e a
# agenda tem de continuar explicando por que ela esteve ocupada.
checar("encerrada continua contando como mesa usada naquele horario",
       not next(h for h in livres(6)["horarios"] if h["hora"] == "12:00")["livre"])
# Cancela o casal para a agenda do dia ter uma linha cancelada na secao 12.
st, _r = chamar("PUT", f"/reservas/{casal['id']}/status", {"status": "CANCELADA"}, token)
checar("e cancelar a reserva do casal passa", st == 200, st)


print("\n9. o que a JANELA do dia recusa")
st, r = reservar("09:00", 2)
checar("antes de abrir e recusado", st == 409, (st, r))
checar("dizendo qual e a janela", "11:00" in (r.get("detail") or ""), r.get("detail"))
st, r = reservar("16:00", 2)
checar("depois da ULTIMA RESERVA tambem", st == 409, (st, r))
# Domingo esta fechado na configuracao deste teste.
domingo = DIA + timedelta(days=1)
st, r = reservar("12:00", 2, dia=domingo)
checar("e num dia da semana fechado, idem", st == 409, (st, r))
checar("dizendo que a casa nao atende nesse dia",
       "dia da semana" in (r.get("detail") or ""), r.get("detail"))
d = livres(2, dia=domingo)
checar("a disponibilidade do domingo vem vazia, COM motivo",
       d["horarios"] == [] and "dia da semana" in (d.get("motivo") or ""), d)

print("\n10. o teto e a antecedencia valem para o SITE, nao para o balcao")
# ⚠️ Quem liga fala com uma pessoa, e essa pessoa pode aceitar um grupo maior
# sabendo que vai juntar mesas na mao.
st, r = chamar("POST", "/reservas", {
    "data": str(DIA), "hora": "11:00", "pessoas": 9,
    "nome": f"Grupao {marca}", "origem": "SITE",
}, token)
checar("grupo acima do teto pelo SITE e recusado", st == 409, (st, r))
checar("mandando falar com a casa", "fale com a casa" in (r.get("detail") or "").lower(),
       r.get("detail"))

print("\n11. bloqueio do dia")
st, r = chamar("POST", "/reservas/bloqueios",
               {"de": str(DIA), "ate": str(DIA), "motivo": f"Evento {marca}"}, token)
checar("criar bloqueio responde 201", st == 201, (st, r))
# 🔑 Nao cancela o que ja estava marcado: a casa precisa da lista para ligar.
checar("e AVISA quantas reservas ja existem no periodo",
       r.get("reservas_no_periodo", 0) > 0, r.get("reservas_no_periodo"))
checar("dizendo que elas continuam na agenda",
       "continuam na agenda" in (r.get("message") or ""), r.get("message"))
d = livres(2)
checar("com o bloqueio, o dia nao oferece horario nenhum", d["horarios"] == [], d)
checar("e o motivo vem junto", f"Evento {marca}" in (d.get("motivo") or ""), d.get("motivo"))
st, r = reservar("12:00", 2)
checar("e marcar no dia bloqueado e recusado", st == 409, (st, r))
_st, bloqueios = chamar("GET", "/reservas/bloqueios", token=token)
for b in bloqueios:
    chamar("DELETE", f"/reservas/bloqueios/{b['id']}", token=token)
checar("removido o bloqueio, o dia volta a oferecer horarios",
       bool(livres(2)["horarios"]))

print("\n12. a agenda do dia, como a recepcao olha")
_st, ag = chamar("GET", f"/reservas/agenda?data={DIA}", token=token)
checar("a agenda responde com as reservas do dia", len(ag.get("reservas") or []) >= 4,
       len(ag.get("reservas") or []))
checar("em ordem de horario",
       [x["hora"] for x in ag["reservas"]] == sorted(x["hora"] for x in ag["reservas"]))
checar("com a mesa de cada uma", all(x["mesas"] or x["status"] == "CANCELADA"
                                     for x in ag["reservas"]), ag["reservas"][:1])
checar("e o total de pessoas esperadas",
       ag["esperados"] == sum(x["pessoas"] for x in ag["reservas"]
                              if x["status"] in ("PENDENTE", "CONFIRMADA", "CHEGOU",
                                                 "ENCERRADA")), ag["esperados"])
# ⚠️ Cancelada nao mostra hora de saida: ela nao vai ocupar mesa nenhuma.
cancelada = next((x for x in ag["reservas"] if x["status"] == "CANCELADA"), None)
checar("e a cancelada nao promete hora de saida",
       cancelada is not None and cancelada["sai_por_volta"] is None, cancelada)

print("\n13. mesa com reserva nao se apaga — e quem barra e o BANCO")
# 🔑 A promessa feita na migracao 069: "quem vai barrar isto e o BANCO, quando
# `reserva_mesas` nascer". E o ON DELETE RESTRICT da 070.
st, r = chamar("DELETE", f"/reservas/mesas/{m06}", token=token)
# ⚠️ **409, e nao "algum erro".** A primeira versao desta checagem afirmava so
# `st >= 400` — e passou sobre um **500 com texto de Postgres**, que foi o que
# derrubou a bateria do navegador inteira num "Internal Server Error". Quem
# GARANTE e o ON DELETE RESTRICT; quem EXPLICA e a rota, e o teste tem de exigir
# a explicacao, senao ela pode sumir sem ninguem notar.
checar("excluir mesa que ja hospedou reserva responde 409", st == 409, (st, r))
checar("dizendo quantas reservas ela recebeu",
       "reserva" in (r.get("detail") or "").lower(), r.get("detail"))
checar("e mandando DESATIVAR em vez de apagar",
       "desative" in (r.get("detail") or "").lower(), r.get("detail"))

print("\n13b. REMARCAR — a ligacao mais comum depois de marcar")
# 🔑 *"Da para passar para as 13h?"* Sem isto, a recepcao teria de cancelar e
# recriar, perdendo o historico da reserva.
# ⚠️ **Num dia LIMPO**, pela mesma razao das secoes 7 e 8: o dia das secoes 1 a 6
# esta cheio, e "nao cabe" se confundiria com "o remarcar nao funciona".
DIA_R = DIA + timedelta(days=14)
st, rem = reservar("12:00", 2, nome=f"Remarcar {marca}", dia=DIA_R)
checar("a reserva nasce as 12:00", st == 201, (st, rem))
mesa_inicial = (rem.get("mesas") or [None])[0]

# 🔑 **A reserva nao pode disputar mesa CONSIGO MESMA.** Passar das 12:00 para
# as 12:30 esbarraria na propria permanencia (90 min), e o sistema responderia
# "nao ha mesa" apontando para a mesa que a propria reserva ocupa. E para isto
# que a disponibilidade tem o `ignorar` — e este e o unico chamador dele.
st, r = chamar("PUT", f"/reservas/{rem['id']}", {"hora": "12:30"}, token)
checar("remarcar meia hora adiante responde 200", st == 200, (st, r))
checar("e a mensagem diz o horario novo e a mesa",
       "12:30" in (r.get("message") or ""), r.get("message"))
_st, ag = chamar("GET", f"/reservas/agenda?data={DIA_R}", token=token)
linha = next(x for x in ag["reservas"] if x["id"] == rem["id"])
checar("a agenda mostra a reserva no horario novo", linha["hora"] == "12:30", linha)
checar("e a hora de saida acompanha", linha["sai_por_volta"] == "14:00", linha)

# ⚠️ So o que veio muda: quem adia meia hora nao repete data nem pessoas.
checar("o que nao foi informado NAO muda", linha["pessoas"] == 2, linha)

# Crescer o grupo troca de mesa: a de 2 nao serve mais.
st, r = chamar("PUT", f"/reservas/{rem['id']}", {"pessoas": 6}, token)
checar("aumentar o grupo para 6 responde 200", st == 200, (st, r))
checar("e a mesa MUDA — a de 2 nao serve mais",
       (r.get("mesas") or [None])[0] != mesa_inicial, (mesa_inicial, r.get("mesas")))
_st, ag = chamar("GET", f"/reservas/agenda?data={DIA_R}", token=token)
linha = next(x for x in ag["reservas"] if x["id"] == rem["id"])
checar("a agenda mostra o grupo novo e a mesa nova",
       linha["pessoas"] == 6 and linha["mesas"] == f"{marca}06", linha)
# ⚠️ Uma mesa por reserva: o DELETE + INSERT nao pode deixar a antiga presa.
checar("e a mesa antiga foi solta, nao ficou grudada",
       "+" not in linha["mesas"], linha["mesas"])

# Mudar de DIA: sao dois dias travados, e a trava vai do menor para o maior.
st, r = chamar("PUT", f"/reservas/{rem['id']}",
               {"data": str(DIA_R + timedelta(days=7)), "hora": "11:00"}, token)
checar("remarcar para outro dia responde 200", st == 200, (st, r))
_st, ag_velho = chamar("GET", f"/reservas/agenda?data={DIA_R}", token=token)
checar("a reserva sai da agenda do dia antigo",
       not any(x["id"] == rem["id"] for x in ag_velho["reservas"]))
_st, ag_novo = chamar("GET", f"/reservas/agenda?data={DIA_R + timedelta(days=7)}", token=token)
checar("e aparece na do dia novo",
       any(x["id"] == rem["id"] for x in ag_novo["reservas"]))

print("\n13c. o que o REMARCAR recusa")
st, r = chamar("PUT", f"/reservas/{rem['id']}", {}, token)
checar("remarcar sem dizer o que muda e recusado", st == 422, st)
st, r = chamar("PUT", f"/reservas/{rem['id']}", {"hora": "09:00"}, token)
checar("para fora da janela do dia, recusado", st == 409, (st, r))
checar("dizendo qual e a janela", "11:00" in (r.get("detail") or ""), r.get("detail"))
# ⚠️ **Falhando, a reserva fica COMO ESTAVA.** Uma remarcacao recusada que
# deixasse a reserva sem mesa seria pior que a recusa.
_st, ag = chamar("GET", f"/reservas/agenda?data={DIA_R + timedelta(days=7)}", token=token)
linha = next(x for x in ag["reservas"] if x["id"] == rem["id"])
checar("e a reserva continua inteira depois da recusa",
       linha["hora"] == "11:00" and linha["mesas"], linha)

# 🔑 So o que ainda nao sentou se remarca: CHEGOU quer dizer que as pessoas
# estao na mesa, e mudar o horario delas nao descreve nada que aconteca no salao.
chamar("PUT", f"/reservas/{rem['id']}/status", {"status": "CHEGOU"}, token)
st, r = chamar("PUT", f"/reservas/{rem['id']}", {"hora": "12:00"}, token)
checar("quem ja chegou nao se remarca", st == 409, (st, r))
checar("dizendo o porque", "sentou" in (r.get("detail") or "").lower(), r.get("detail"))
chamar("PUT", f"/reservas/{rem['id']}/status", {"status": "ENCERRADA"}, token)


print("\n14. limpeza")
with get_cursor() as cur:
    cur.execute("DELETE FROM reserva_mesas WHERE id_reserva IN "
                "(SELECT id FROM reservas WHERE id_unidade = %s)", (UNIDADE,))
    cur.execute("DELETE FROM reservas WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM reserva_bloqueios WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM mesas WHERE id_unidade = %s", (UNIDADE,))
    cur.execute("DELETE FROM saloes WHERE id_unidade = %s", (UNIDADE,))
    for tabela in ("reserva_permanencias", "reserva_horarios", "reserva_config"):
        cur.execute(f"DELETE FROM {tabela} WHERE id_unidade = %s", (UNIDADE,))
chamar("PUT", f"/unidades/{UNIDADE}/parametros", {"reservas_ligado": False}, token)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
