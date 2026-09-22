"""O agendador dispara na hora da CASA, não na do contêiner.

🔑 **O relato do dono (04/09/2026):** configurou a busca para as 20h em
produção e nunca havia registro daquela execução. A suspeita dele era que a
busca manual estivesse consumindo a cota do dia — não estava: `regra.marcar`,
que é o único lugar que move `agenda_rodou_em`, tem exatamente dois chamadores,
os dois agendadores.

⚠️ **A causa era o FUSO.** O agendador perguntava a hora ao sistema operacional
(`datetime.now().astimezone()`), e no App Platform o contêiner roda em UTC:
"buscar às 20h" era avaliado contra as 20h UTC, que são 17h em Brasília. A busca
não deixava de rodar — rodava três horas antes.

🔑 **Nenhuma suíte pegaria isso rodando normal**, porque a máquina de casa está
no mesmo fuso que o código presumia. Este arquivo existe para forçar o que só
acontece no ar: um `agora` em UTC.

🔑 **E o mesmo erro voltou em 22/09/2026, noutro lugar**: a tarja do site do
cliente dizia *"Fechado · abre Qua 09:30"* às 15:25 de uma terça, com a casa
aberta até as 18:00. 15:25 em Blumenau são 18:25 em UTC. Duas ocorrências
distantes, a mesma causa — e foi isso que tirou o helper de dentro do agendador
e o pôs em `relogio.py`. Esta suíte cobre as duas.

Este arquivo NÃO fala com a API — testa a regra pura, que é onde a decisão mora.

    python tests/smoke_agenda_fuso.py
"""

import sys
from datetime import datetime, timedelta, timezone
from datetime import time as dt_time
from zoneinfo import ZoneInfo

sys.path.insert(0, ".")

from config import FUSO_DA_CASA  # noqa: E402
import relogio  # noqa: E402
from services import agenda_integracao as regra  # noqa: E402

ok = 0
falhas: list[str] = []


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


CASA = ZoneInfo(FUSO_DA_CASA)
UTC = timezone.utc


def linha(freq="DIARIA", hora=20, rodou=None, ativa=True):
    return {"agenda_frequencia": freq, "agenda_hora": hora,
            "agenda_rodou_em": rodou, "ativa": ativa}


print("1. a hora vem da CASA, nao do sistema operacional")
agora = regra.agora_da_casa()
checar("agora_da_casa devolve hora com fuso", agora.tzinfo is not None, agora)
# ⚠️ O deslocamento do Brasil e -3h desde que o horario de verao acabou, em 2019.
checar("e o deslocamento e o do Brasil (-3h)",
       agora.utcoffset() == timedelta(hours=-3), agora.utcoffset())


print("\n2. as 17h de Brasilia NAO disparam uma busca marcada para as 20h")
# 🔑 **O caso exato do relato.** As 17h de Brasilia sao 20h UTC. Com o agendador
# lendo a hora do conteiner, `agora.hour` seria 20 e a busca dispararia — tres
# horas cedo, e nunca no horario escolhido.
dezessete = datetime(2026, 9, 4, 17, 0, tzinfo=CASA)
checar("as 17h da casa nao disparam", not regra.deve_rodar(linha(hora=20), dezessete),
       dezessete)
# A prova de que o engano era esse: o MESMO instante, lido em UTC, dispara.
checar("mas o MESMO instante lido em UTC dispararia — era esse o defeito",
       regra.deve_rodar(linha(hora=20), dezessete.astimezone(UTC)),
       dezessete.astimezone(UTC).hour)


print("\n3. as 20h da casa disparam")
vinte = datetime(2026, 9, 4, 20, 5, tzinfo=CASA)
checar("as 20h05 da casa disparam", regra.deve_rodar(linha(hora=20), vinte), vinte)
# ⚠️ E continua valendo depois: quem volta do ar as 23h ainda busca no mesmo dia,
# senao um restart as 20h01 pularia o dia inteiro.
vinte_e_tres = datetime(2026, 9, 4, 23, 30, tzinfo=CASA)
checar("e as 23h30 tambem, se ainda nao rodou",
       regra.deve_rodar(linha(hora=20), vinte_e_tres), vinte_e_tres)


print("\n4. a data de 'ja rodou hoje' se compara no MESMO fuso")
# 🔑 **O segundo efeito, e o pior porque e intermitente.** `agenda_rodou_em`
# volta do banco com o fuso da sessao (America/Sao_Paulo) e `agora` esta no da
# casa. Entre 21h e a meia-noite de Brasilia a data em UTC ja e a do dia
# seguinte: comparar `.date()` de fusos diferentes fazia o agendador ora pular um
# dia, ora rodar duas vezes.
rodou_as_21 = datetime(2026, 9, 4, 21, 0, tzinfo=CASA)
mais_tarde = datetime(2026, 9, 4, 23, 0, tzinfo=CASA)
checar("rodou as 21h, as 23h do mesmo dia nao roda de novo",
       not regra.deve_rodar(linha(hora=20, rodou=rodou_as_21), mais_tarde),
       (rodou_as_21, mais_tarde))
# ⚠️ O mesmo carimbo, entregue em UTC pelo driver, tem de dar a MESMA resposta —
# e e isso que o `astimezone` no comparador garante.
checar("e o mesmo carimbo lido em UTC nao muda a resposta",
       not regra.deve_rodar(linha(hora=20, rodou=rodou_as_21.astimezone(UTC)), mais_tarde),
       rodou_as_21.astimezone(UTC))
# No dia seguinte, roda.
amanha = datetime(2026, 9, 5, 20, 1, tzinfo=CASA)
checar("e no dia seguinte volta a rodar",
       regra.deve_rodar(linha(hora=20, rodou=rodou_as_21), amanha), amanha)


print("\n5. o que NAO mudou")
checar("MANUAL nunca dispara", not regra.deve_rodar(linha(freq="MANUAL"), vinte))
checar("integracao inativa nunca dispara",
       not regra.deve_rodar(linha(ativa=False), vinte))
# HORARIA compara intervalo, nao hora do relogio — subtracao entre datas com
# fuso ja e correta em qualquer fuso, e continua sendo.
uma_hora_atras = vinte - timedelta(hours=1, minutes=1)
checar("HORARIA dispara passada uma hora",
       regra.deve_rodar(linha(freq="HORARIA", rodou=uma_hora_atras), vinte))
checar("e nao dispara antes disso",
       not regra.deve_rodar(linha(freq="HORARIA", rodou=vinte - timedelta(minutes=10)), vinte))


print("\n4. a tarja do site do cliente: aberto agora?")
# 🔑 **A regra da tarja, isolada.** `routers/publico.py` compara
# `agora_da_casa().time()` com a janela do dia; aqui se prova que a comparacao
# muda de resposta conforme o relogio — que e o defeito que o dono viu.
ABRE, FECHA = dt_time(9, 30), dt_time(18, 0)


def aberta(quando):
    return ABRE <= quando.time() <= FECHA


# Uma terca as 15:25 na casa — dentro do expediente, sem discussao.
na_casa = datetime(2026, 9, 22, 15, 25, tzinfo=ZoneInfo(FUSO_DA_CASA))
no_conteiner = na_casa.astimezone(timezone.utc).replace(tzinfo=None)
checar("as 15:25 na casa, ela esta ABERTA", aberta(na_casa) is True, na_casa)
# ⚠️ **O mesmo instante, lido pelo relogio do conteiner, da o contrario.** E o
# sintoma exato: 18:25 passa das 18:00, e a tarja dizia "Fechado".
checar("e o relogio do conteiner (18:25 UTC) diria FECHADA",
       aberta(no_conteiner) is False, no_conteiner)
checar("sendo o MESMO instante, so que em fusos diferentes",
       na_casa.astimezone(timezone.utc)
       == no_conteiner.replace(tzinfo=timezone.utc), (na_casa, no_conteiner))

# 🔑 E o helper devolve a hora da casa, com fuso, venha de onde vier o processo.
agora = relogio.agora_da_casa()
checar("agora_da_casa traz fuso, nunca hora solta", agora.tzinfo is not None, agora)
checar("e o deslocamento e o de Brasilia",
       agora.utcoffset() == timedelta(hours=-3), agora.utcoffset())

print("\n5. a data da casa, entre 21h e a meia-noite")
# ⚠️ **`date.today()` num servidor em UTC vira o dia SEGUINTE** nessa janela — e
# e ela que decide se um catalogo esta publicado hoje.
noite = datetime(2026, 9, 22, 22, 10, tzinfo=ZoneInfo(FUSO_DA_CASA))
checar("as 22:10 de 22/09 na casa, a data e 22/09", noite.date().day == 22, noite)
checar("mas em UTC ja e 23/09",
       noite.astimezone(timezone.utc).date().day == 23,
       noite.astimezone(timezone.utc))
checar("e hoje_da_casa concorda com a data da casa",
       relogio.hoje_da_casa() == relogio.agora_da_casa().date())


print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
