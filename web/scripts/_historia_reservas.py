"""Histórico de reservas para `verificar-paineis-leadsfood.mjs`, quando a base local não tem.

🔑 O painel de reservas só desenha o ano contra ano e a sazonalidade com reservas de meses
FECHADOS. A base local já ficou sem nenhuma (25/11/2026), e o roteiro falhava por falta de dado,
não por defeito. Este script cria um ano e pouco de reservas marcadas pelo telefone e apaga
depois.

    python scripts/_historia_reservas.py criar
    python scripts/_historia_reservas.py apagar
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))
from database import get_cursor  # noqa: E402

PREFIXO = "00900005"  # o da suíte da API é 00900004: as duas não se apagam


def criar() -> None:
    hoje = date.today()
    with get_cursor() as cur:
        n = 0
        # Do mesmo mês do ano retrasado até o mês passado: os 12 meses da sazonalidade e os
        # dois anos do ano contra ano. Quantidade variando, para haver pico e vale.
        for k in range(24, 0, -1):
            m = hoje.year * 12 + hoje.month - 1 - k
            ano, mes = m // 12, m % 12 + 1
            for i in range(1 + (mes * 7) % 5):
                n += 1
                cur.execute(
                    """INSERT INTO reservas (id_unidade, data, hora, pessoas, status, origem,
                                             nome, telefone)
                       VALUES (1, %s, '12:00', %s, 'ENCERRADA', 'BALCAO', 'Painel navegador', %s)""",
                    (date(ano, mes, 10 + i), 2 + i, f"{PREFIXO}{n:03d}"))
    print(f"{n} reservas de teste")


def apagar() -> None:
    with get_cursor() as cur:
        cur.execute("DELETE FROM reservas WHERE telefone LIKE %s", (f"{PREFIXO}%",))
        print(f"{cur.rowcount} reservas de teste apagadas")


if __name__ == "__main__":
    {"criar": criar, "apagar": apagar}[sys.argv[1]]()
