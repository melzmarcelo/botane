"""Reservas: o modulo nasce desligado, e ligar muda TRES coisas.

🔑 **Pedido do dono (14/09/2026):** *"isto tudo vai ser habilitado via parametro
na loja, podemos iniciar criando este parametro e colocando no menu, caso
habilitado a opcao de Reservas. E a primeira tela que e as configuracoes, e
tambem, caso tenha habilitado, disponibilizar nas permissoes dos usuarios os
itens de Reserva que vamos criando."*

⚠️ **A trava do servidor NAO e redundancia da do menu.** Esconder o item e
conforto; o que impede uma loja sem o modulo de ganhar configuracao de reserva e
a recusa do router. A regra da casa e nada de checagem so na tela.

⚠️ **Esconder a permissao do catalogo nao revoga nada.** Quem ja tem a chave
continua com ela — desligar o modulo e tirar da vitrine, nao confiscar.

    python tests/smoke_reservas_config.py        (API de pe na 9200)
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []


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
checar("a loja atual responde", bool(UNIDADE), eu.get("unidades"))


def ligar(valor: bool):
    st, r = chamar("PUT", f"/unidades/{UNIDADE}/parametros", {"reservas_ligado": valor}, token)
    return st, r


print("\n0. o estado de partida: DESLIGADO")
# ⚠️ A base pode vir de uma rodada anterior: garante o ponto de partida.
ligar(False)
st, p = chamar("GET", f"/unidades/{UNIDADE}/parametros", token=token)
checar("o parametro existe e comeca desligado",
       st == 200 and p.get("reservas_ligado") is False, (st, p.get("reservas_ligado")))
_st, eu = chamar("GET", "/auth/me", token=token)
checar("e o /auth/me diz ao menu que nao ha reservas",
       eu.get("reservas_ligado") is False, eu.get("reservas_ligado"))

print("\n1. desligado, o catalogo de permissoes nao oferece reservas")
st, perms = chamar("GET", "/permissoes", token=token)
chaves = {x["chave"] for x in perms}
checar("a lista responde", st == 200 and len(chaves) > 20, st)
checar("e nenhuma chave de reservas aparece",
       not any(c.startswith("reservas.") for c in chaves),
       sorted(c for c in chaves if c.startswith("reservas.")))
# ⚠️ Mas elas EXISTEM no banco: o catalogo filtra a vitrine, nao apaga o dado.
with get_cursor() as cur:
    cur.execute("SELECT count(*) AS n FROM permissoes WHERE chave LIKE 'reservas.%%'")
    checar("as tres chaves continuam existindo no banco", cur.fetchone()["n"] == 3)

print("\n2. desligado, a rota recusa mesmo com permissao")
# 🔑 O admin tem todas as permissoes; quem recusa aqui e a trava do modulo.
st, r = chamar("GET", "/reservas/configuracao", token=token)
checar("a configuracao responde 409 com o modulo desligado", st == 409, (st, r))
checar("e diz ONDE se liga",
       "lojas" in (r.get("detail") or "").lower(), r.get("detail"))

print("\n3. ligando o modulo na loja")
st, r = ligar(True)
checar("o parametro aceita ser ligado", st == 200, (st, r))
_st, eu = chamar("GET", "/auth/me", token=token)
checar("o /auth/me passa a liberar o menu", eu.get("reservas_ligado") is True)
st, perms = chamar("GET", "/permissoes", token=token)
chaves = {x["chave"] for x in perms}
checar("e o catalogo passa a oferecer as tres chaves",
       {"reservas.ver", "reservas.editar", "reservas.configurar"} <= chaves,
       sorted(c for c in chaves if c.startswith("reservas.")))
modulos = {x["modulo"] for x in perms if x["chave"].startswith("reservas.")}
checar("agrupadas no modulo Reservas", modulos == {"Reservas"}, modulos)

print("\n4. a configuracao nasce na primeira visita")
# ⚠️ **A suite precisa MONTAR o estado virgem**, e a razao esta na secao 7: ela
# prova que desligar o modulo NAO apaga a configuracao. Ou seja, a rodada
# seguinte encontraria a semana da rodada anterior — cinco dias abertos e duas
# faixas — e acusaria de defeito exatamente o comportamento que a outra secao
# exige. Foi assim que estas quatro checagens cairam na primeira bateria.
with get_cursor() as cur:
    for tabela in ("reserva_permanencias", "reserva_horarios", "reserva_config"):
        cur.execute(f"DELETE FROM {tabela} WHERE id_unidade = %s", (UNIDADE,))
st, cfg = chamar("GET", "/reservas/configuracao", token=token)
checar("a tela responde 200", st == 200, (st, cfg))
checar("com a semana INTEIRA, sete dias", len(cfg.get("horarios") or []) == 7,
       len(cfg.get("horarios") or []))
# ⚠️ ISO: 1 = segunda … 7 = domingo. Nao e o getDay() do JavaScript.
dias = [h["dia_semana"] for h in cfg["horarios"]]
checar("em ISO e em ordem, de segunda a domingo", dias == [1, 2, 3, 4, 5, 6, 7], dias)
checar("a primeira linha e a segunda-feira", cfg["horarios"][0]["nome"] == "Segunda",
       cfg["horarios"][0]["nome"])
# 🔑 Nasce FECHADA em todos os dias: o contrario faria a agenda afirmar um
# horario que ninguem conferiu.
checar("a casa nasce fechada em todos os dias", cfg.get("dias_abertos") == 0,
       cfg.get("dias_abertos"))
checar("e a tela sabe disso pelo servidor, nao por conta propria",
       not any(h["aberto"] for h in cfg["horarios"]))
# ⚠️ As faixas de permanencia JA nascem preenchidas: elas nao afirmam que a casa
# abre, so dizem quanto tempo uma refeicao dura.
checar("as faixas de permanencia nascem com as tres padrao",
       len(cfg.get("permanencias") or []) == 3, cfg.get("permanencias"))
checar("com o almoco segurando mais que o cafe",
       any(f["minutos"] == 90 for f in cfg["permanencias"]), cfg["permanencias"])
checar("e as horas vem como HH:MM, que e o que o campo de hora fala",
       cfg["horarios"][0]["abre"] == "09:00", cfg["horarios"][0]["abre"])

print("\n5. gravar a semana e as faixas")
corpo = {
    "aceita_online": False,
    "confirmacao": "MANUAL",
    "teto_online": 8,
    "tolerancia_min": 15,
    "folga_min": 15,
    "passo_min": 30,
    "antecedencia_min_horas": 2,
    "antecedencia_max_dias": 30,
    "cadastro_completo": True,
    # Terca a sexta 09:30-18:00 (ultima 17:00); sabado 09:00-18:30; resto fechado.
    "horarios": [
        {"dia_semana": 1, "aberto": False, "abre": "09:30", "fecha": "18:00",
         "ultima_reserva": "17:00"},
        *[{"dia_semana": d, "aberto": True, "abre": "09:30", "fecha": "18:00",
           "ultima_reserva": "17:00"} for d in (2, 3, 4, 5)],
        {"dia_semana": 6, "aberto": True, "abre": "09:00", "fecha": "18:30",
         "ultima_reserva": "17:00"},
        {"dia_semana": 7, "aberto": False, "abre": "09:00", "fecha": "18:00",
         "ultima_reserva": "17:00"},
    ],
    "permanencias": [
        {"nome": "Cafe da manha", "de": "09:00", "ate": "11:00", "minutos": 60},
        {"nome": "Almoco", "de": "11:00", "ate": "15:00", "minutos": 90},
    ],
}
st, r = chamar("PUT", "/reservas/configuracao", corpo, token)
checar("salvar responde 200", st == 200, (st, r))
checar("e o servidor devolve a contagem de dias abertos", r.get("dias_abertos") == 5,
       r.get("dias_abertos"))
st, cfg = chamar("GET", "/reservas/configuracao", token=token)
sabado = next(h for h in cfg["horarios"] if h["dia_semana"] == 6)
checar("o sabado guardou a janela propria",
       sabado["abre"] == "09:00" and sabado["fecha"] == "18:30", sabado)
# 🔑 Tres horas, nao uma: a ultima reserva e antes do fechamento, e a diferenca
# e a permanencia de quem senta por ultimo.
checar("com a ultima reserva ANTES do fechamento",
       sabado["ultima_reserva"] == "17:00" and sabado["ultima_reserva"] < sabado["fecha"],
       sabado)
segunda = next(h for h in cfg["horarios"] if h["dia_semana"] == 1)
# ⚠️ Dia fechado guarda o horario dele: reabrir nao obriga a redigitar.
checar("o dia fechado guardou o horario dele",
       segunda["aberto"] is False and segunda["abre"] == "09:30", segunda)
checar("as faixas foram reescritas para duas", len(cfg["permanencias"]) == 2,
       cfg["permanencias"])
checar("e a confirmacao manual ficou gravada", cfg["confirmacao"] == "MANUAL",
       cfg["confirmacao"])

print("\n6. o que a configuracao RECUSA")
mau = json.loads(json.dumps(corpo))
mau["horarios"][5]["ultima_reserva"] = "19:00"   # depois do fechamento do sabado
st, r = chamar("PUT", "/reservas/configuracao", mau, token)
checar("ultima reserva depois do fechamento e recusada", st == 422, st)

mau = json.loads(json.dumps(corpo))
mau["horarios"] = mau["horarios"][:6]            # semana incompleta
st, r = chamar("PUT", "/reservas/configuracao", mau, token)
checar("semana incompleta e recusada", st == 422, st)

# 🔑 Faixas sobrepostas dariam duas respostas para a mesma hora, e o calculo
# pegaria a primeira — a mesa liberaria num horario que depende da ORDEM.
mau = json.loads(json.dumps(corpo))
mau["permanencias"] = [
    {"nome": "Almoco", "de": "11:00", "ate": "15:00", "minutos": 90},
    {"nome": "Tarde", "de": "14:00", "ate": "18:00", "minutos": 60},
]
st, r = chamar("PUT", "/reservas/configuracao", mau, token)
checar("faixas de permanencia sobrepostas sao recusadas", st == 422, st)

mau = json.loads(json.dumps(corpo))
mau["confirmacao"] = "TALVEZ"
st, _r = chamar("PUT", "/reservas/configuracao", mau, token)
checar("confirmacao fora das duas opcoes e recusada", st == 422, st)

print("\n7. desligar nao apaga nada")
st, _r = ligar(False)
checar("o modulo se desliga", st == 200)
st, _r = chamar("GET", "/reservas/configuracao", token=token)
checar("a tela volta a recusar", st == 409, st)
with get_cursor() as cur:
    cur.execute("SELECT confirmacao FROM reserva_config WHERE id_unidade = %s", (UNIDADE,))
    linha = cur.fetchone()
    # ⚠️ Desligar e tirar da vitrine, nao confiscar: religar devolve tudo.
    checar("mas a configuracao continua guardada",
           bool(linha) and linha["confirmacao"] == "MANUAL", linha)
    cur.execute("SELECT count(*) AS n FROM reserva_horarios WHERE id_unidade = %s", (UNIDADE,))
    checar("e a semana tambem", cur.fetchone()["n"] == 7)
st, _r = ligar(True)
st, cfg = chamar("GET", "/reservas/configuracao", token=token)
checar("religar devolve a configuracao como estava",
       st == 200 and cfg["dias_abertos"] == 5 and cfg["confirmacao"] == "MANUAL",
       (st, cfg.get("dias_abertos")))

print("\n8. limpeza - a loja volta ao estado de partida")
# ⚠️ Desliga o modulo E apaga a configuracao que esta suite criou: a base local
# volta a nao ter reserva nenhuma, que e como ela estava antes.
ligar(False)
with get_cursor() as cur:
    for tabela in ("reserva_permanencias", "reserva_horarios", "reserva_config"):
        cur.execute(f"DELETE FROM {tabela} WHERE id_unidade = %s", (UNIDADE,))

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
