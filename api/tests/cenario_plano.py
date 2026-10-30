"""Cenário do Plano de ação para o roteiro de navegador (verificar-plano-de-acao.mjs).

    python tests/cenario_plano.py montar <id_unidade>     → imprime o JSON do cenário
    python tests/cenario_plano.py painel <id_unidade>     → um ano de reservas, para o painel
    python tests/cenario_plano.py limpar <id_unidade>

Reservas no PASSADO, gravadas direto no banco: a rota de reservar recusa data passada, e o
plano só existe sobre o passado. ⚠️ Tudo do cenário usa telefones com DDD 00 (prefixo
`00900001`), que ninguém tem — o `limpar` apaga só eles, e roda também antes do `montar`
para uma rodada interrompida não somar com a seguinte.
"""

import json
import sys
from datetime import date, timedelta

sys.path.insert(0, ".")

from database import get_cursor, init_pool  # noqa: E402

PREFIXO = "00900001"
FONES = {"vip": PREFIXO + "001", "org": PREFIXO + "002", "dorm": PREFIXO + "003",
         "parou": PREFIXO + "004"}


def limpar(cur, u: int) -> None:
    cur.execute("DELETE FROM reservas WHERE id_unidade = %s AND telefone LIKE %s",
                (u, PREFIXO + "%"))
    cur.execute("DELETE FROM reserva_clientes WHERE telefone LIKE %s", (PREFIXO + "%",))


def montar(cur, u: int) -> dict:
    limpar(cur, u)
    hoje = date.today()

    def reserva(fone, dias, pessoas=2, nome="Pessoa", id_cliente=None):
        cur.execute(
            """INSERT INTO reservas (id_unidade, data, hora, pessoas, status, origem, nome,
                                     telefone, id_cliente)
               VALUES (%s, %s, '12:00', %s, 'ENCERRADA', 'BALCAO', %s, %s, %s)""",
            (u, hoje - timedelta(days=dias), pessoas, nome, fone, id_cliente))

    for d in (400, 420, 440, 460):
        reserva(FONES["vip"], d, nome="VALENTINA Roteiro")
    reserva(FONES["org"], 400, pessoas=12, nome="Otávio Roteiro")
    reserva(FONES["org"], 430, pessoas=9, nome="Otávio Roteiro")
    reserva(FONES["dorm"], 400, nome="Dora Roteiro")
    cur.execute("""INSERT INTO reserva_clientes (id_unidade, telefone, nome, whatsapp_optout_em)
                   VALUES (%s, %s, 'Paula Roteiro', now()) RETURNING id""",
                (u, FONES["parou"]))
    reserva(FONES["parou"], 400, nome="Paula Roteiro", id_cliente=cur.fetchone()["id"])
    return FONES


def montar_painel(cur, u: int) -> dict:
    """Um ano de reservas espalhadas, para o painel ter o que desenhar (mesmo prefixo).

    Determinístico (sem `random`): o mesmo cenário em toda rodada, para o roteiro poder
    contar. Sábado pesa mais, almoço e café da tarde, um grupo grande a cada sete.
    """
    limpar(cur, u)
    hoje = date.today()
    objetivos = ("Aniversário", "Confraternização", "Negócios", None, None)
    n = 0
    for i in range(1, 360, 3):
        d = hoje - timedelta(days=i)
        if d.isoweekday() == 1:          # a casa não abre na segunda
            continue
        vezes = 3 if d.isoweekday() == 6 else 1
        for k in range(vezes):
            n += 1
            pessoas = 8 + (n % 5) if n % 7 == 0 else 2 + (n % 3)
            status = "NAO_COMPARECEU" if n % 9 == 0 else "ENCERRADA"
            hora = ("12:00", "12:30", "16:00", "10:00")[n % 4]
            cur.execute(
                """INSERT INTO reservas (id_unidade, data, hora, pessoas, status, origem, nome,
                                         telefone, objetivo)
                   VALUES (%s, %s, %s, %s, %s, 'BALCAO', 'Painel roteiro', %s, %s)""",
                (u, d, hora, pessoas, status, f"{PREFIXO}{100 + n % 60:03d}",
                 objetivos[n % len(objetivos)]))
    return {"reservas": n}


if __name__ == "__main__":
    acao, unidade = sys.argv[1], int(sys.argv[2])
    init_pool()
    with get_cursor() as c:
        if acao == "montar":
            print(json.dumps(montar(c, unidade)))
        elif acao == "painel":
            print(json.dumps(montar_painel(c, unidade)))
        else:
            limpar(c, unidade)
            print("{}")
