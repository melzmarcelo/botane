"""O envio de e-mail desiste DENTRO do prazo, e diz por quê.

Em produção, o botão "Testar" de Integrações devolvia **504** — o roteamento
do App Platform desistindo antes da API. A causa era aritmética: o `timeout=`
do smtplib vale para CADA operação de socket, e são quatro em sequência
(conectar, STARTTLS, autenticar, enviar). Com 20 s em cada, o pior caso era
80 s, e o gateway desiste em ~60. O erro que chegava não era o do SMTP, era o
do gateway — e não dizia nada sobre a causa.

O que este arquivo cobra:

1. `_resta` nunca devolve zero (0 em socket é NÃO BLOQUEANTE, não "sem espera")
2. um servidor que **engole os pacotes** falha dentro do orçamento, não em 80 s
   — é o caso da porta bloqueada na saída, o mais comum em nuvem
3. a mensagem do erro leva o texto do socket, que é o que separa as causas
4. um servidor que **recusa** a conexão falha na hora, sem gastar o orçamento

    python tests/smoke_email_prazo.py         (não precisa da API de pé)

⚠️ **Não toca no banco nem na configuração da casa.** Chama `email.entregar`
com um dicionário montado aqui — pôr o SMTP real em modo "real" apontando para
um endereço morto deixaria a recuperação de senha quebrada em silêncio.
"""

import socket
import sys
import time
from email.message import EmailMessage

sys.path.insert(0, ".")
from services import email as correio  # noqa: E402

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


def _mensagem() -> EmailMessage:
    m = EmailMessage()
    m["From"] = "botane@exemplo.com.br"
    m["To"] = "ninguem@exemplo.com.br"
    m["Subject"] = "prazo"
    m.set_content("teste de prazo")
    return m


print("1. o piso do prazo restante")
checar("orçamento é o do envio inteiro, não de cada passo",
       correio.ORCAMENTO_ENVIO <= 30, correio.ORCAMENTO_ENVIO)
# ⚠️ settimeout(0) põe o socket em modo NÃO BLOQUEANTE — a operação falha na
# hora com um erro que não parece tempo esgotado. Por isso o piso de 1 s.
checar("prazo já vencido não vira zero", correio._resta(time.monotonic() - 99) >= 1.0,
       correio._resta(time.monotonic() - 99))
checar("e prazo em aberto devolve o que falta",
       9.0 < correio._resta(time.monotonic() + 10) <= 10.0,
       correio._resta(time.monotonic() + 10))


print("\n2. servidor que engole os pacotes falha DENTRO do orçamento")
# 192.0.2.1 é TEST-NET-1 (RFC 5737): reservado para documentação, não é
# roteável. Ninguém responde e ninguém recusa — os pacotes somem, que é
# exatamente o que uma porta bloqueada na saída faz.
cfg_buraco = {"servidor": "192.0.2.1", "porta": 587, "seguranca": "starttls",
              "usuario": "u", "senha": "s"}
t0 = time.monotonic()
erro = None
try:
    correio.entregar(cfg_buraco, _mensagem())
except correio.ErroEmail as e:
    erro = e.mensagem
gasto = time.monotonic() - t0

checar("levantou ErroEmail em vez de pendurar", erro is not None, erro)
# A folga cobre o custo do DNS e do encerramento; o que se cobra é que NÃO
# tenha somado quatro prazos.
teto = correio.ORCAMENTO_ENVIO + 10
checar(f"e desistiu em {gasto:.1f}s, dentro do teto de {teto}s", gasto < teto, gasto)
checar("bem antes dos ~60s em que o gateway desiste",
       gasto < 55, gasto)
checar("a mensagem leva o texto do socket, que separa as causas",
       erro and ("timed out" in erro.lower() or "timeout" in erro.lower()
                 or "unreachable" in erro.lower()),
       erro)


print("\n3. servidor que RECUSA falha na hora, sem gastar o orçamento")
# Porta fechada em 127.0.0.1: o sistema operacional responde na hora com
# "connection refused". É o caso de servidor errado ou porta errada, e não
# pode consumir o prazo inteiro — senão quem digitou a porta errada espera
# 20 s para descobrir.
livre = socket.socket()
livre.bind(("127.0.0.1", 0))
porta_morta = livre.getsockname()[1]
livre.close()

cfg_recusa = {"servidor": "127.0.0.1", "porta": porta_morta, "seguranca": "starttls"}
t0 = time.monotonic()
erro2 = None
try:
    correio.entregar(cfg_recusa, _mensagem())
except correio.ErroEmail as e:
    erro2 = e.mensagem
gasto2 = time.monotonic() - t0

checar("levantou ErroEmail", erro2 is not None, erro2)
checar(f"e foi rápido ({gasto2:.1f}s), sem esperar o prazo", gasto2 < 5, gasto2)
checar("com a recusa nomeada na mensagem",
       erro2 and ("refused" in erro2.lower() or "recusou" in erro2.lower()
                  or "10061" in erro2),
       erro2)


print(f"\n{ok} ok, {len(falhas)} falha(s)")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
