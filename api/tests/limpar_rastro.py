"""Apaga do RAZÃO o rastro dos produtos de uma rodada de teste.

    python tests/limpar_rastro.py TREP-

⚠️ **Exceção deliberada ao append-only, e ela tem um motivo estreito.** O razão
não se apaga para o SISTEMA; aqui a questão é outra: a checagem de
reprocessamento da bateria de tela lança uma saída, depois uma entrada com data
ANTERIOR, e reprocessa. Dali em diante o razão daquele produto é coerente na
ordem da DATA, enquanto `estoque_saldos` e o resto da base seguem coerentes na
ordem de LANÇAMENTO — e o relatório de CMV por grupo, que lê a fotografia pelo
`id DESC`, passa a discordar do CMV do período.

Medido em 16/09/2026: **R$ 256,00 em dois produtos**, derrubando
`smoke_grupos_cmv` e `smoke_relatorios` — duas suítes que não têm nada a ver com
o assunto, com a falha a três telas da causa. É a mesma lição que
`smoke_reprocessar` já paga por dentro: teste que deixa rastro derruba o
próximo, e o que fecha a conta é não deixar rastro nenhum.

⚠️ **Por SQL direto porque NÃO EXISTE rota para isso, e não deve existir.**
`DELETE /produtos` inativa o cadastro e deixa o razão de pé — que é o certo para
o sistema e insuficiente para o teste.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2  # noqa: E402

from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_SSLMODE, DB_USER  # noqa: E402


def limpar(prefixo: str) -> int:
    conexao = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
                               dbname=DB_NAME, sslmode=DB_SSLMODE)
    with conexao, conexao.cursor() as c:
        c.execute("SELECT id FROM produtos WHERE codigo LIKE %s", (f"{prefixo}%",))
        ids = [linha[0] for linha in c.fetchall()]
        if ids:
            c.execute("DELETE FROM movimento_lotes WHERE id_movimento IN ("
                      "SELECT id FROM estoque_movimentos WHERE id_produto = ANY(%s))", (ids,))
            c.execute("DELETE FROM estoque_movimentos WHERE id_produto = ANY(%s)", (ids,))
            c.execute("DELETE FROM estoque_saldos WHERE id_produto = ANY(%s)", (ids,))
            c.execute("DELETE FROM estoque_lotes WHERE id_produto = ANY(%s)", (ids,))
    conexao.close()
    return len(ids)


if __name__ == "__main__":
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("uso: python tests/limpar_rastro.py <prefixo do código>")
        raise SystemExit(2)
    quantos = limpar(sys.argv[1].strip())
    print(f"razão apagado de {quantos} produto(s) com código {sys.argv[1]}*")
