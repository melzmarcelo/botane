"""Apaga os clientes (e os pedidos deles) que os verificadores de pedido criam na base local.

    python tests/limpar_clientes_de_teste.py

🔑 **Por que existe (04/11/2026):** `verificar.mjs` (fase dos pedidos) e
`verificar-pedido-site.mjs` cadastram um cliente novo a cada rodada, pelo site, e não há rota
para apagar cliente nem pedido — de propósito. Em cinco semanas eram 164 "Tela Pedido" e 14
"Site Pedido", com 68 pedidos: janeiro aparecia com quase o dobro de aniversários no Painel de
clientes, e os 1988-01-02 inflavam a faixa de 35-39 na pirâmide.

⚠️ **Por SQL direto, como `limpar_rastro.py`**, e casando nome + nascimento + cidade EXATOS do
cadastro de teste: um cliente de verdade chamado "Site Pedido" teria de ter nascido no mesmo dia
e morar na mesma cidade. ⚠️ Só para a base de CASA: em produção não há verificador rodando.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2  # noqa: E402

from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_SSLMODE, DB_USER  # noqa: E402

# (nome, nascimento, cidade) — exatamente o que os dois verificadores cadastram.
DE_TESTE = [
    ("Tela Pedido", "1988-01-02", "Blumenau"),   # verificar.mjs, fase dos pedidos
    ("Site Pedido", "1992-03-04", "Blumenau"),   # verificar-pedido-site.mjs
]


def limpar() -> tuple[int, int]:
    conexao = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
                               dbname=DB_NAME, sslmode=DB_SSLMODE)
    clientes = pedidos = 0
    with conexao, conexao.cursor() as c:
        for nome, nascimento, cidade in DE_TESTE:
            c.execute("""SELECT id FROM reserva_clientes
                          WHERE nome = %s AND nascimento = %s AND cidade = %s""",
                      (nome, nascimento, cidade))
            ids = [x[0] for x in c.fetchall()]
            if not ids:
                continue
            # O pedido guarda o cliente com SET NULL: apagar só o cliente deixaria o pedido órfão.
            c.execute("DELETE FROM pedidos WHERE id_cliente = ANY(%s)", (ids,))
            pedidos += c.rowcount
            c.execute("DELETE FROM reserva_clientes WHERE id = ANY(%s)", (ids,))
            clientes += c.rowcount
    conexao.close()
    return clientes, pedidos


if __name__ == "__main__":
    n_clientes, n_pedidos = limpar()
    print(f"clientes de teste apagados: {n_clientes} (com {n_pedidos} pedido(s))")
