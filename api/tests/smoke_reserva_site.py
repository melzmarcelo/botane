"""A reserva marcada pelo SITE, com o cadastro de quem marca.

🔑 **Pedido do dono (21/09/2026):** *"para a realização de reserva, precisamos de
um cadastro simples do usuário. Clica em Reserve sua Mesa, abre uma tela com o
número do telefone; caso não tenha cadastrada, realiza o cadastro com Nome,
telefone, gênero e cidade."*

⚠️ **É o primeiro lugar em que a INTERNET grava neste sistema.** Todo o resto do
que o público alcança só lê o que a casa publicou. Por isso metade desta suíte
não é sobre marcar mesa: é sobre o que a rota RECUSA — telefone que não confere,
cadastro incompleto, telefone que já tem reservas demais e origem que bate na
porta rápido demais.

    python tests/smoke_reserva_site.py        (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import preservar_reserva  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
MARCA = "sitereserva"

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None, origem=None):
    req = urllib.request.Request(BASE + urllib.parse.quote(caminho, safe="/?=&"),
                                 method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    # 🔑 O limite por origem lê `X-Forwarded-For`: é o que o balanceador manda.
    if origem:
        req.add_header("X-Forwarded-For", origem)
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

devolver_a_reserva = preservar_reserva(UNIDADE)


def esvaziar_a_loja():
    """Tira TUDO da reserva desta loja — o `preservar_reserva` devolve no fim.

    ⚠️ **Apagar mesa sem soltar a reserva que a segura é RECUSADO pelo banco**
    (`reserva_mesas_id_mesa_fkey`, com `ON DELETE RESTRICT` de propósito: a mesa
    é a resposta para onde aquelas pessoas sentaram). Uma primeira versão desta
    suíte limpava só o que ELA tinha criado, filtrando pelo telefone — e
    quebrava no PREPARO no dia em que outra suíte deixasse uma reserva para
    trás. Suíte que depende do rastro da vizinha passa ou falha pela ordem.
    🔑 **Ordem: vínculo, reserva, mesa, salão.** É a das chaves estrangeiras.
    ⚠️ E limpar a loja inteira só é seguro porque a foto já foi tirada lá em
    cima: sem `preservar_reserva`, isto seria a suíte apagando dado da casa.
    """
    with get_cursor() as cur:
        cur.execute("""DELETE FROM reserva_mesas WHERE id_reserva IN
                         (SELECT id FROM reservas WHERE id_unidade = %s)""", (UNIDADE,))
        cur.execute("DELETE FROM reservas WHERE id_unidade = %s", (UNIDADE,))
        cur.execute("DELETE FROM mesas WHERE id_unidade = %s", (UNIDADE,))
        cur.execute("DELETE FROM saloes WHERE id_unidade = %s", (UNIDADE,))
        cur.execute("DELETE FROM reserva_clientes WHERE id_unidade = %s", (UNIDADE,))
        cur.execute("DELETE FROM reserva_tentativas WHERE id_unidade = %s", (UNIDADE,))


def limpar_quem_reservou():
    """Tira clientes, reservas e batidas — e DEIXA o salão de pé.

    ⚠️ **Não é o `esvaziar_a_loja`.** Uma versão desta suíte usava aquele no meio
    do roteiro, e levava as mesas junto: as três checagens seguintes recusavam
    por "não há mesa livre" enquanto mediam outra coisa — confirmação manual,
    teto do site e cadastro simples. Limpeza no meio do teste tem de tirar só o
    que o teste sujou.
    """
    with get_cursor() as cur:
        cur.execute("""DELETE FROM reserva_mesas WHERE id_reserva IN
                         (SELECT id FROM reservas WHERE id_unidade = %s)""", (UNIDADE,))
        cur.execute("DELETE FROM reservas WHERE id_unidade = %s", (UNIDADE,))
        cur.execute("DELETE FROM reserva_clientes WHERE id_unidade = %s", (UNIDADE,))
        cur.execute("DELETE FROM reserva_tentativas WHERE id_unidade = %s", (UNIDADE,))


def sem_tentativas():
    """Zera a contagem de origem: o limite tem seção própria, no fim."""
    with get_cursor() as cur:
        cur.execute("DELETE FROM reserva_tentativas WHERE id_unidade = %s", (UNIDADE,))


def ligar(valor: bool):
    return chamar("PUT", f"/unidades/{UNIDADE}/parametros", {"reservas_ligado": valor}, token)


print("\n0. o cenario: casa aberta, salao com mesas e a semana inteira")
ligar(True)
esvaziar_a_loja()
_st, salao = chamar("POST", "/reservas/saloes", {"nome": f"Salao {MARCA}"}, token)
ID_SALAO = salao.get("id")
for n in range(1, 5):
    chamar("POST", "/reservas/mesas",
           {"id_salao": ID_SALAO, "nome": f"{MARCA}-{n:02d}", "lugares": 4}, token)

# ⚠️ **A semana INTEIRA aberta**, senão o dia escolhido cai num dia fechado e a
# recusa viria da janela — escondendo o que esta suíte quer medir.
_st, cfg = chamar("GET", "/reservas/configuracao", token=token)
BASE_CFG = {
    **cfg,
    "aceita_online": False,
    "confirmacao": "AUTOMATICA",
    "cadastro_completo": True,
    "teto_online": 8,
    "antecedencia_min_horas": 0,
    "antecedencia_max_dias": 60,
    "horarios": [{"dia_semana": d, "aberto": True, "abre": "09:00", "fecha": "22:00",
                  "ultima_reserva": "20:00"} for d in range(1, 8)],
    "permanencias": [{"nome": "Unica", "de": "09:00", "ate": "22:00", "minutos": 60}],
}


def gravar_config(**mudancas):
    st, r = chamar("PUT", "/reservas/configuracao", {**BASE_CFG, **mudancas}, token)
    return st, r


st, _r = gravar_config()
checar("a configuracao do cenario grava", st == 200, (st, _r))

DIA = (date.today() + timedelta(days=3)).isoformat()
FONE = "47999100001"


def reservar(**campos):
    corpo = {"telefone": FONE, "nome": "Marina Duarte", "genero": "FEMININO",
             "cidade": "Blumenau", "nascimento": "1988-03-09",
             "data": DIA, "hora": "19:00", "pessoas": 2}
    corpo.update(campos)
    return chamar("POST", f"/publico/{UNIDADE}/reserva", corpo, origem="203.0.113.7")


print("\n1. com a casa NAO aceitando reserva online")
# 🔑 `aceita_online` existia desde a migracao 068 e nao fazia nada. Agora e a
# porta — e ela nasce fechada, que e o estado certo para um recurso novo.
st, r = chamar("GET", f"/publico/{UNIDADE}/reserva")
checar("a pergunta responde 200, nao um erro", st == 200, (st, r))
checar("dizendo que a casa nao aceita", r.get("aceita") is False, r)
st, r = chamar("POST", f"/publico/{UNIDADE}/reserva/telefone", {"telefone": FONE})
checar("e a busca de cadastro e recusada com explicacao",
       st == 409 and "site" in (r.get("detail") or "").lower(), (st, r))
st, r = reservar()
checar("como a propria reserva", st == 409, (st, r))

print("\n2. a casa passa a aceitar")
gravar_config(aceita_online=True)
sem_tentativas()
st, r = chamar("GET", f"/publico/{UNIDADE}/reserva")
checar("a pergunta passa a dizer que sim", r.get("aceita") is True, r)
checar("e conta o que o site precisa saber ANTES de perguntar qualquer coisa",
       r.get("cadastro_completo") is True and r.get("confirma_na_hora") is True
       and r.get("teto") == 8, r)

print("\n3. o telefone, antes de qualquer cadastro")
st, r = chamar("POST", f"/publico/{UNIDADE}/reserva/telefone", {"telefone": "123"})
checar("telefone curto demais e recusado, dizendo o formato",
       st == 422 and "DDD" in (r.get("detail") or ""), (st, r))
st, r = chamar("POST", f"/publico/{UNIDADE}/reserva/telefone", {"telefone": FONE})
checar("telefone desconhecido responde 200, nao 404", st == 200, (st, r))
# ⚠️ Um 404 para desconhecido e 200 para conhecido diria a MESMA coisa que
# mostrar o nome, so que pelo codigo de status.
checar("dizendo que nao ha cadastro, e sem dica nenhuma",
       r.get("cadastrado") is False and r.get("dica") is None, r)

print("\n4. o que o cadastro novo EXIGE")
sem_tentativas()
st, r = reservar(genero=None, cidade=None)
checar("sem genero e sem cidade e recusado", st == 422, (st, r))
checar("e a mensagem diz os DOIS que faltam",
       "gênero" in (r.get("detail") or "") and "cidade" in (r.get("detail") or ""),
       r.get("detail"))
st, r = reservar(nascimento=None)
# 🔑 Migracao 086 (pedido do dono, 24/09/2026): a data entra no cadastro completo.
checar("sem data de nascimento e recusado, dizendo qual falta",
       st == 422 and "nascimento" in (r.get("detail") or ""), (st, r))
st, r = reservar(cidade=None)
checar("faltando so a cidade, a mensagem fala so dela",
       st == 422 and "cidade" in (r.get("detail") or "")
       and "gênero" not in (r.get("detail") or ""), (st, r))

print("\n5. a primeira reserva, com o cadastro junto")
st, feita = reservar()
checar("a reserva nasce (201)", st == 201, (st, feita))
checar("confirmada na hora, porque a casa configurou AUTOMATICA",
       feita.get("confirmada") is True and feita.get("status") == "CONFIRMADA", feita)
checar("e o site sabe que o cadastro era novo", feita.get("cadastro_novo") is True, feita)
checar("a resposta devolve o que a tela precisa mostrar",
       feita.get("hora") == "19:00" and feita.get("pessoas") == 2
       and feita.get("nome") == "Marina", feita)
# ⚠️ **Nada de id interno.** E a mesma regra das rotas de leitura: a tentacao e
# devolver o registro e o preco e vazar o que ninguem pediu.
checar("e NADA de id interno da reserva nem da mesa",
       "id" not in feita and "mesas" not in feita and "id_cliente" not in feita,
       list(feita))

with get_cursor() as cur:
    cur.execute(
        """SELECT r.origem, r.status, r.telefone, r.id_cliente, c.nome, c.genero, c.cidade
             FROM reservas r JOIN reserva_clientes c ON c.id = r.id_cliente
            WHERE r.id_unidade = %s ORDER BY r.id DESC LIMIT 1""",
        (UNIDADE,))
    linha = cur.fetchone()
    checar("no banco ela e da origem SITE", linha and linha["origem"] == "SITE", linha)
    checar("ligada ao cadastro que acabou de nascer",
           linha and linha["id_cliente"] and linha["nome"] == "Marina Duarte", linha)
    checar("com genero e cidade guardados",
           linha and linha["genero"] == "FEMININO" and linha["cidade"] == "Blumenau", linha)
    cur.execute("SELECT nascimento FROM reserva_clientes WHERE id_unidade = %s "
                "AND telefone = %s", (UNIDADE, FONE))
    checar("e a data de nascimento tambem",
           str((cur.fetchone() or {}).get("nascimento")) == "1988-03-09")
    cur.execute("SELECT count(*) AS n FROM reserva_mesas WHERE id_reserva IN "
                "(SELECT id FROM reservas WHERE id_unidade = %s)", (UNIDADE,))
    # 🔑 A mesa e alocada pela MESMA regra do balcao — se nao fosse, a reserva
    # nasceria sem mesa e a agenda nao saberia onde sentar ninguem.
    checar("e com mesa de verdade alocada", cur.fetchone()["n"] >= 1)

print("\n6. o telefone que JA tem cadastro")
sem_tentativas()
st, r = chamar("POST", f"/publico/{UNIDADE}/reserva/telefone", {"telefone": FONE})
checar("agora ele responde que ha cadastro", r.get("cadastrado") is True, r)
# 🔑 **Decisao do dono**: confirma, nao revela.
checar("com a dica mascarada", r.get("dica") == "M••••• D•••••", r.get("dica"))
checar("e SEM o nome inteiro em lugar nenhum da resposta",
       "Marina Duarte" not in json.dumps(r, ensure_ascii=False), r)

# ⚠️ A mascara tem de esconder o TAMANHO tambem? Nao — esconder o nome basta;
# o que ela nao pode e deixar o nome legivel.
st, r = chamar("POST", f"/publico/{UNIDADE}/reserva/telefone",
               {"telefone": "(47) 99910-0001"})
checar("e o mesmo numero com mascara acha o MESMO cadastro",
       r.get("cadastrado") is True, r)

print("\n7. o nome e o que prova que o telefone e seu")
sem_tentativas()
st, r = reservar(nome="Outra Pessoa", hora="20:00")
checar("nome que nao confere e recusado (409)", st == 409, (st, r))
checar("dizendo o que fazer, sem revelar o nome certo",
       "não confere" in (r.get("detail") or "")
       and "Marina" not in (r.get("detail") or ""), r.get("detail"))
# ⚠️ Exigir o nome completo identico faria a DONA do cadastro ser recusada no
# proprio telefone — e a saida dela seria se cadastrar de novo.
st, r = reservar(nome="marina duarte dos santos", hora="20:00")
checar("o primeiro nome basta, sem caixa e sem sobrenome novo", st == 201, (st, r))
checar("e agora o cadastro nao e mais novo", r.get("cadastro_novo") is False, r)

print("\n8. o limite por TELEFONE")
sem_tentativas()
st, r = reservar(hora="18:00")
checar("a terceira reserva ainda passa", st == 201, (st, r))
st, r = reservar(hora="17:00")
checar("a quarta e recusada (429)", st == 429, (st, r))
checar("dizendo quantas ja estao em aberto e o que fazer",
       "3 reservas" in (r.get("detail") or "") and "casa" in (r.get("detail") or ""),
       r.get("detail"))
# 🔑 **Cancelada nao ocupa nada.** Somar o que ja morreu faria o cliente fiel ser
# barrado justamente por ser fiel.
with get_cursor() as cur:
    cur.execute("""UPDATE reservas SET status = 'CANCELADA'
                    WHERE id = (SELECT max(id) FROM reservas WHERE id_unidade = %s)""",
                (UNIDADE,))
st, r = reservar(hora="17:00")
checar("cancelando uma, a vaga volta", st == 201, (st, r))

print("\n8b. suas reservas (pedido do dono, 23/09/2026)")
sem_tentativas()


# 🔑 **Só o telefone** desde 24/09/2026 (pedido do dono). O nome, SE vier, ainda
# e conferido — e isso continua coberto pelas chamadas com `nome="Outra"`.
def minhas(nome=None, telefone=FONE):
    corpo = {"telefone": telefone}
    if nome:
        corpo["nome"] = nome
    return chamar("POST", f"/publico/{UNIDADE}/reserva/minhas", corpo,
                  origem="203.0.113.7")


st, r = minhas()
# ⚠️ Tres em aberto: a secao 8 cancelou uma e marcou outra no lugar.
checar("quem confere o nome ve as proprias reservas em aberto",
       st == 200 and len(r.get("reservas") or []) == 3, (st, r))
checar("sem id nem mesa, so o que a pessoa marcou",
       all(set(x) == {"data", "hora", "pessoas", "confirmada", "observacao"}
           for x in (r.get("reservas") or [])), r)
st, r = minhas(nome="Outra")
checar("nome que nao confere e recusado com a mesma frase da reserva",
       st == 409 and "não confere" in (r.get("detail") or ""), (st, r))
st, r = minhas(telefone="47999108888")
checar("telefone sem cadastro devolve lista vazia, nao 404",
       st == 200 and r.get("reservas") == [], (st, r))
# 🔑 A do balcao entra tambem: mesmo telefone, com mascara, e a mesma pessoa.
with get_cursor() as cur:
    cur.execute(
        """INSERT INTO reservas (id_unidade, data, hora, pessoas, status, origem, nome, telefone)
           VALUES (%s, %s, '12:00', 3, 'CONFIRMADA', 'BALCAO', 'Marina D', '(47) 99910-0001')""",
        (UNIDADE, DIA))
st, r = minhas()
checar("a reserva feita pelo balcao, no mesmo telefone, entra na lista",
       any(x["hora"] == "12:00" and x["pessoas"] == 3 for x in (r.get("reservas") or [])), r)



def cancelar(data=DIA, hora="12:00", nome=None, telefone=FONE):
    corpo = {"telefone": telefone, "data": data, "hora": hora}
    if nome:
        corpo["nome"] = nome
    return chamar("POST", f"/publico/{UNIDADE}/reserva/cancelar", corpo,
                  origem="203.0.113.7")


sem_tentativas()
st, r = cancelar(nome="Outra")
checar("cancelar com nome que nao confere e recusado", st == 409, (st, r))
st, r = cancelar(telefone="47999108888")
checar("telefone sem cadastro recebe 'nao encontrada', sem dizer se existe",
       st == 404, (st, r))
st, r = cancelar(hora="21:00")
checar("horario que a pessoa nao tem recebe 404", st == 404, (st, r))
st, r = cancelar()
checar("a propria reserva (mesmo a do balcao) e cancelada", st == 200, (st, r))
with get_cursor() as cur:
    cur.execute("""SELECT status, observacao_interna FROM reservas
                    WHERE id_unidade = %s AND data = %s AND hora = '12:00'""",
                (UNIDADE, DIA))
    linha = cur.fetchone()
checar("no banco ela fica CANCELADA, nao apagada, com o recado para o balcao",
       linha and linha["status"] == "CANCELADA"
       and "cliente no site" in (linha["observacao_interna"] or ""), linha)
st, r = minhas()
checar("e sai de Suas reservas",
       not any(x["hora"] == "12:00" for x in (r.get("reservas") or [])), r)
st, r = cancelar()
checar("cancelar de novo a mesma da 404", st == 404, (st, r))
with get_cursor() as cur:
    cur.execute(
        """INSERT INTO reservas (id_unidade, data, hora, pessoas, status, origem, nome, telefone)
           VALUES (%s, current_date, '00:00', 2, 'CONFIRMADA', 'BALCAO', 'Marina D', %s)""",
        (UNIDADE, FONE))
st, r = cancelar(data=date.today().isoformat(), hora="00:00")
checar("reserva cujo horario ja passou nao se cancela pelo site",
       st == 409 and "passou" in (r.get("detail") or ""), (st, r))

print("\n8d. so o telefone basta (pedido do dono, 24/09/2026)")
sem_tentativas()
# ⚠️ O telefone chega aqui no limite de reservas em aberto: sem soltar, a
# reserva abaixo levaria 429 medindo outra coisa.
with get_cursor() as cur:
    cur.execute("UPDATE reservas SET status = 'CANCELADA' WHERE id_unidade = %s "
                "AND telefone = %s", (UNIDADE, FONE))
st, r = chamar("POST", f"/publico/{UNIDADE}/cliente/telefone", {"telefone": FONE},
               origem="203.0.113.7")
checar("o telefone cadastrado devolve o PRIMEIRO nome, para a saudacao",
       st == 200 and r.get("nome") == "Marina", (st, r))
checar("e nunca o nome inteiro",
       "Duarte" not in json.dumps(r, ensure_ascii=False), r)
st, r = reservar(nome=None, genero=None, cidade=None, nascimento=None, hora="10:00",
                 data=(date.today() + timedelta(days=4)).isoformat())
checar("quem ja tem cadastro reserva SEM mandar o nome", st == 201, (st, r))
st, r = chamar("POST", f"/publico/{UNIDADE}/cliente",
               {"telefone": "47999106161", "genero": "OUTRO", "cidade": "Blumenau",
                "nascimento": "1990-01-01"}, origem="203.0.113.7")
checar("mas quem e NOVO precisa dizer o nome", st == 422 and "nome" in
       (r.get("detail") or ""), (st, r))


print("\n8c. so os horarios que ainda da tempo de marcar")
ONTEM = (date.today() - timedelta(days=1)).isoformat()
HOJE = date.today().isoformat()
AMANHA = (date.today() + timedelta(days=1)).isoformat()
st, r = chamar("GET", f"/publico/{UNIDADE}/horarios?dia={ONTEM}&pessoas=2")
checar("dia que ja passou nao oferece horario, e diz por que",
       st == 200 and r.get("horarios") == [] and "passou" in (r.get("motivo") or ""), (st, r))
gravar_config(aceita_online=True, antecedencia_min_horas=30)
st, r = chamar("GET", f"/publico/{UNIDADE}/horarios?dia={HOJE}&pessoas=2")
checar("com 30h de antecedencia, hoje nao oferece nada, e fala da antecedencia",
       st == 200 and r.get("horarios") == [] and "30h" in (r.get("motivo") or ""), (st, r))
st, r = reservar(data=HOJE, hora="20:00", telefone="47999107777", nome="Ana Paz")
checar("e a gravacao recusa o mesmo que a lista escondeu",
       st == 409 and "antecedência" in (r.get("detail") or ""), (st, r))
gravar_config(aceita_online=True)
st, r = chamar("GET", f"/publico/{UNIDADE}/horarios?dia={AMANHA}&pessoas=2")
checar("sem antecedencia, amanha continua com o dia inteiro",
       st == 200 and "09:00" in (r.get("horarios") or []), (st, r))

print("\n9. o limite por ORIGEM")
limpar_quem_reservou()
# ⚠️ Esta secao gasta o limite de proposito: por isso ela e a ultima, e usa uma
# origem so dela.
respostas = [chamar("POST", f"/publico/{UNIDADE}/reserva/telefone",
                    {"telefone": "47999109999"}, origem="198.51.100.4")[0]
             for _ in range(22)]
checar("as primeiras batidas passam", respostas[0] == 200 and respostas[10] == 200,
       respostas[:3])
checar("e a partir do limite a porta fecha (429)", respostas[-1] == 429, respostas[-3:])
# 🔑 **Outra origem nao paga pela primeira.** Um limite global faria um visitante
# exagerado derrubar o site para a casa inteira.
st, _r = chamar("POST", f"/publico/{UNIDADE}/reserva/telefone",
                {"telefone": "47999109999"}, origem="198.51.100.9")
checar("mas outra origem continua entrando", st == 200, st)

print("\n10. o que a casa ainda decide")
sem_tentativas()
limpar_quem_reservou()
gravar_config(aceita_online=True, confirmacao="MANUAL")
st, r = reservar(hora="19:30")
checar("com confirmacao MANUAL a reserva nasce PENDENTE",
       st == 201 and r.get("status") == "PENDENTE", (st, r))
# ⚠️ **A tela nao pode dizer "reservado" quando a casa ainda vai olhar.**
checar("e o site e avisado de que ela NAO esta confirmada",
       r.get("confirmada") is False, r)

# 🔑 **O calendario da agenda** (pedido do dono, 24/09/2026). Aqui a loja tem
# exatamente UMA reserva — a pendente logo acima —, entao os numeros sao exatos.
st, cal = chamar("GET", f"/reservas/calendario?mes={DIA[:7]}", token=token)
dia_cal = next((d for d in (cal or {}).get("dias", []) if d["data"] == DIA), {})
checar("o calendario responde o mes inteiro, um item por dia",
       st == 200 and len(cal.get("dias") or []) >= 28 and cal["dias"][0]["data"].endswith("-01"),
       (st, len((cal or {}).get("dias") or [])))
checar("e resume o dia: 1 reserva, 2 pessoas, 1 aguardando",
       dia_cal.get("reservas") == 1 and dia_cal.get("pessoas") == 2
       and dia_cal.get("pendentes") == 1, dia_cal)
checar("com a casa aberta, pela semana configurada", dia_cal.get("aberta") is True, dia_cal)
with get_cursor() as cur:
    cur.execute("UPDATE reservas SET status = 'CANCELADA' WHERE id_unidade = %s AND data = %s",
                (UNIDADE, DIA))
st, cal = chamar("GET", f"/reservas/calendario?mes={DIA[:7]}", token=token)
dia_cal = next((d for d in (cal or {}).get("dias", []) if d["data"] == DIA), {})
# ⚠️ Cancelada nao enche o dia: o calendario conta so o que segura mesa.
checar("cancelada sai da conta do calendario",
       dia_cal.get("reservas") == 0 and dia_cal.get("pendentes") == 0, dia_cal)
checar("mes invalido e recusado (422)",
       chamar("GET", "/reservas/calendario?mes=2026-13", token=token)[0] == 422)
st, ag = chamar("GET", f"/reservas/agenda?data={DIA}", token=token)
checar("a agenda do dia traz a janela para a linha do tempo",
       ag.get("abre") == "09:00" and ag.get("fecha") == "22:00" and ag.get("passo"),
       {k: ag.get(k) for k in ("abre", "fecha", "passo")})

sem_tentativas()
limpar_quem_reservou()
gravar_config(aceita_online=True, teto_online=4)
st, r = reservar(pessoas=6, hora="19:00")
checar("grupo acima do teto do site e mandado falar com a casa",
       st == 409 and "fale com a casa" in (r.get("detail") or "").lower(), (st, r))

sem_tentativas()
gravar_config(aceita_online=True, cadastro_completo=False)
st, r = reservar(telefone="47999100002", nome="Joao Reis", genero=None, cidade=None,
                 hora="19:00")
checar("com cadastro simples, so o nome basta", st == 201, (st, r))

print("\n11. limpeza")
esvaziar_a_loja()
devolver_a_reserva()

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
