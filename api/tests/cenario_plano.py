"""Cenário do Plano de ação para o roteiro de navegador (verificar-plano-de-acao.mjs).

    python tests/cenario_plano.py montar <id_unidade>     → imprime o JSON do cenário
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


if __name__ == "__main__":
    acao, unidade = sys.argv[1], int(sys.argv[2])
    init_pool()
    with get_cursor() as c:
        if acao == "montar":
            print(json.dumps(montar(c, unidade)))
        else:
            limpar(c, unidade)
            print("{}")
