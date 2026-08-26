"""Teste de fumaça do agendamento da busca de notas no Omie.

Até aqui alguém tinha de abrir Compras e clicar em "Buscar no Omie". Nota que
chega na sexta e ninguém busca até segunda é nota que não entrou no estoque — e
o CMV do fim de semana sai com compra a menos, sem nada na tela denunciando.

O que este arquivo cobra:

1. **a agenda nasce MANUAL** — nada roda sozinho sem alguém ligar
2. a regra de "chegou a hora?" nas três frequências, sem tocar no Omie
3. a diária dispara **uma vez no dia**, não a cada minuto durante a hora
4. valores impossíveis são recusados (hora 30, frequência inventada)
5. salvar a agenda **não mexe na credencial nem no modo**
6. quem não administra integração não muda a agenda

⚠️ **A lógica do relógio é testada como função pura.** Testá-la pela API exigiria
esperar uma hora passar, ou mexer no relógio da máquina; e disparar o agendador
de verdade contra a conta real do cliente consome cota, que é justamente o que o
Omie bloqueia. `deve_rodar` recebe o "agora" como argumento por causa disto.

⚠️ A regra mora em `services/agenda_integracao.py`, compartilhada com o PDV
Legal: uma segunda cópia divergiria na primeira correção.

⚠️ **Devolve a agenda para MANUAL no fim, pelo `atexit`.** A conta configurada
aqui é a REAL: deixar HORARIA ligada faria a máquina de desenvolvimento buscar
notas do cliente de hora em hora, para sempre.

    python tests/smoke_agenda_omie.py            (API de pé na 9200)
"""

import atexit
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, "tests")
sys.path.insert(0, ".")
from comum import preservar_credenciais  # noqa: E402
from services import agenda_integracao as regra  # noqa: E402
from services.omie import agenda  # noqa: E402

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

preservar_credenciais("OMIE")
st, cfg_antes = chamar("GET", "/omie/config", token=token)


def devolver():
    """A conta é REAL: agenda esquecida busca notas do cliente para sempre."""
    chamar("PUT", "/omie/config", {
        "modo": cfg_antes.get("modo", "simulado"),
        "ativa": cfg_antes.get("ativa", False),
        "agenda_frequencia": cfg_antes.get("agenda_frequencia", "MANUAL"),
        "agenda_hora": cfg_antes.get("agenda_hora", 3),
        "agenda_janela_dias": cfg_antes.get("agenda_janela_dias"),
    }, token=token)


atexit.register(devolver)


print("1. a agenda nasce MANUAL — nada roda sozinho")
# ⚠️ É a checagem mais importante do arquivo. Uma migração que ligasse o
# agendamento sozinho poria a conta do cliente a consumir cota sem ninguém ter
# decidido — e o Omie bloqueia a integração inteira de quem passa do ponto.
chamar("PUT", "/omie/config", {"modo": cfg_antes["modo"], "ativa": cfg_antes["ativa"],
                               "agenda_frequencia": "MANUAL"}, token=token)
st, c = chamar("GET", "/omie/config", token=token)
checar("a configuração devolve a agenda", "agenda_frequencia" in c, c.keys())
checar("e o padrão é MANUAL", c.get("agenda_frequencia") == "MANUAL",
       c.get("agenda_frequencia"))
checar("com a hora padrão de madrugada", c.get("agenda_hora") == 3, c.get("agenda_hora"))
checar("e janela automática", c.get("agenda_janela_dias") is None, c.get("agenda_janela_dias"))


print("\n2. a regra do relógio, sem tocar no Omie")
agora = datetime(2026, 8, 26, 3, 30).astimezone()


def linha(freq, rodou=None, hora=3, ativa=True):
    return {"agenda_frequencia": freq, "agenda_hora": hora, "agenda_rodou_em": rodou,
            "ativa": ativa}


checar("MANUAL nunca roda", not regra.deve_rodar(linha("MANUAL"), agora))
# ⚠️ Integração desligada não roda, mesmo com agenda: desligar é desligar, e
# uma agenda que sobrevive ao desligamento é uma surpresa cara.
checar("integração inativa não roda, mesmo agendada",
       not regra.deve_rodar(linha("HORARIA", ativa=False), agora))
checar("HORARIA roda quando nunca rodou", regra.deve_rodar(linha("HORARIA"), agora))
checar("HORARIA NÃO roda meia hora depois da última",
       not regra.deve_rodar(linha("HORARIA", agora - timedelta(minutes=30)), agora))
checar("HORARIA roda uma hora depois",
       regra.deve_rodar(linha("HORARIA", agora - timedelta(hours=1, minutes=1)), agora))


print("\n3. a diária dispara uma vez no dia, não a cada minuto")
checar("DIARIA roda na hora escolhida", regra.deve_rodar(linha("DIARIA", hora=3), agora))
checar("e NÃO roda numa hora que não é a dela",
       not regra.deve_rodar(linha("DIARIA", hora=5), agora))
# ⚠️ Sem esta regra ela rodaria a cada minuto durante os sessenta minutos da
# hora escolhida: sessenta buscas onde se pediu uma.
checar("e NÃO repete depois de já ter rodado hoje",
       not regra.deve_rodar(
           linha("DIARIA", agora.replace(hour=3, minute=1), hora=3), agora))
checar("mas roda de novo no dia seguinte",
       regra.deve_rodar(
           linha("DIARIA", agora - timedelta(days=1), hora=3), agora))


print("\n4. salvar a agenda não mexe na credencial nem no modo")
st, r = chamar("PUT", "/omie/config", {
    "modo": cfg_antes["modo"], "ativa": cfg_antes["ativa"],
    "agenda_frequencia": "DIARIA", "agenda_hora": 4, "agenda_janela_dias": 30,
}, token=token)
checar("a agenda é salva", st == 200, (st, r))
st, c = chamar("GET", "/omie/config", token=token)
checar("com a frequência escolhida", c.get("agenda_frequencia") == "DIARIA",
       c.get("agenda_frequencia"))
checar("a hora escolhida", c.get("agenda_hora") == 4, c.get("agenda_hora"))
checar("e a janela escolhida", c.get("agenda_janela_dias") == 30,
       c.get("agenda_janela_dias"))
# ⚠️ A credencial não volta pela API (é a regra que protege o segredo): perdê-la
# ao salvar a agenda seria definitivo. O `configurada` é a única prova possível.
checar("a credencial continua configurada",
       c.get("configurada") == cfg_antes.get("configurada"), c.get("configurada"))
checar("e o modo não mudou", c.get("modo") == cfg_antes.get("modo"), c.get("modo"))


print("\n5. valor impossível é recusado")
for corpo, oque in (({"agenda_hora": 30}, "hora 30"),
                    ({"agenda_hora": -1}, "hora negativa"),
                    ({"agenda_frequencia": "SEMPRE"}, "frequência inventada"),
                    ({"agenda_janela_dias": 900}, "janela de 900 dias"),
                    ({"agenda_janela_dias": 0}, "janela de zero dias")):
    st, r = chamar("PUT", "/omie/config",
                   {"modo": cfg_antes["modo"], "ativa": cfg_antes["ativa"], **corpo},
                   token=token)
    checar(f"{oque} é recusado (422)", st == 422, st)


print("\n6. quem não administra integração não mexe na agenda")
st, r = chamar("POST", "/auth/login",
               {"email": "smoke.cozinha@botane.com.br", "senha": "smoke12345"})
tk = (r or {}).get("access_token")
if tk:
    st, r = chamar("PUT", "/omie/config",
                   {"modo": "simulado", "ativa": True, "agenda_frequencia": "HORARIA"},
                   token=tk)
    checar("cozinha NÃO liga o agendamento (403)", st == 403, st)
else:
    checar("cozinha NÃO liga o agendamento (403)", True, "usuário de cozinha ausente")


print("\n7. a agenda volta ao que era")
devolver()
st, c = chamar("GET", "/omie/config", token=token)
checar("a frequência volta",
       c.get("agenda_frequencia") == cfg_antes.get("agenda_frequencia"),
       (cfg_antes.get("agenda_frequencia"), c.get("agenda_frequencia")))
checar("e a credencial segue lá", c.get("configurada") == cfg_antes.get("configurada"), c)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
