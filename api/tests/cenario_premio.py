"""Cenário do prêmio no documento para o roteiro de navegador (verificar-premio-documento.mjs).

    python tests/cenario_premio.py montar <id_unidade>   → imprime o JSON do cenário
    python tests/cenario_premio.py limpar <id_unidade>

Um cliente com um prêmio JÁ ENTREGUE no balcão e sem documento — o caso principal da 147:
o almoço vai num documento do PDV que não é importado, e o documento manual chega depois.
⚠️ Telefone com DDD 00 (prefixo `00900002`), que ninguém tem: o `limpar` apaga só ele, e
roda também antes do `montar` para uma rodada interrompida não somar com a seguinte.
"""

import json
import sys
from datetime import date, timedelta

sys.path.insert(0, ".")

from database import get_cursor, init_pool  # noqa: E402

PREFIXO = "00900002"
FONE = PREFIXO + "001"


def limpar(cur) -> None:
    # O documento aponta para o prêmio (sem cascata): sai antes do cliente.
    cur.execute("""SELECT v.id FROM vendas v JOIN fidelidade_premios p ON p.id = v.id_premio
                     JOIN reserva_clientes c ON c.id = p.id_cliente
                    WHERE c.telefone LIKE %s""", (PREFIXO + "%",))
    ids = [r["id"] for r in cur.fetchall()]
    if ids:
        # ⚠️ O movimento de estoque da baixa sai junto (05/11/2026). Sem isto ficava no razão um
        # movimento apontando para venda apagada, e o link dele levava a "Venda não encontrada".
        # Mesma exceção deliberada ao append-only de `tests/limpar_rastro.py`: rastro de TESTE.
        # ⚠️ E o estorno da baixa (venda cancelada) sai ANTES do original: `id_estorno_de` aponta
        # para ele sem cascata.
        cur.execute("""SELECT id FROM estoque_movimentos
                        WHERE origem_tipo = 'VENDA' AND origem_id = ANY(%s)""", (ids,))
        movs = [r["id"] for r in cur.fetchall()]
        cur.execute("SELECT id FROM estoque_movimentos WHERE id_estorno_de = ANY(%s)", (movs,))
        movs += [r["id"] for r in cur.fetchall() if r["id"] not in movs]
        cur.execute("DELETE FROM movimento_lotes WHERE id_movimento = ANY(%s)", (movs,))
        cur.execute("DELETE FROM estoque_movimentos WHERE id = ANY(%s) AND id_estorno_de IS NOT NULL", (movs,))
        cur.execute("DELETE FROM estoque_movimentos WHERE id = ANY(%s)", (movs,))
        cur.execute("DELETE FROM venda_itens WHERE id_venda = ANY(%s)", (ids,))
        cur.execute("DELETE FROM vendas WHERE id = ANY(%s)", (ids,))
    # Selos e prêmios penduram no cliente com ON DELETE CASCADE.
    cur.execute("DELETE FROM reserva_clientes WHERE telefone LIKE %s", (PREFIXO + "%",))


def montar(cur, u: int) -> dict:
    limpar(cur)
    hoje = date.today()
    cur.execute("INSERT INTO reserva_clientes (nome, telefone) VALUES (%s, %s) RETURNING id",
                ("Cliente Prêmio Tela", FONE))
    cliente = cur.fetchone()["id"]
    codigo = "ZQ" + str(cliente % 10000).zfill(4).translate(str.maketrans("0123456789",
                                                                           "ABCDEFGHJK"))
    cur.execute(
        """INSERT INTO fidelidade_premios (id_cliente, id_unidade, codigo, premio, visitas,
                                           dias_consumo, vence_em, vale_de, emitido_em,
                                           usado_em, id_unidade_uso)
           VALUES (%s, %s, %s, 'Almoço cortesia', 10, '{1,2,3,4,5,6,7}', %s, %s,
                   now() - interval '3 days', now(), %s)""",
        (cliente, u, codigo, hoje + timedelta(days=20), hoje - timedelta(days=2), u))
    return {"cliente": cliente, "codigo": codigo}


if __name__ == "__main__":
    init_pool()
    acao, unidade = sys.argv[1], int(sys.argv[2])
    with get_cursor() as cur:
        if acao == "montar":
            print(json.dumps(montar(cur, unidade)))
        elif acao == "limpar":
            limpar(cur)
