"""Zera os dados de operação e deixa a base como uma instalação nova.

    python limpar_dados.py --simular     mostra o que sairia, sem apagar nada
    python limpar_dados.py               apaga (pede confirmação digitada)
    python limpar_dados.py --sim         apaga sem perguntar
    python limpar_dados.py --usuarios-de-teste   leva junto os usuários smoke./tela.
    python limpar_dados.py --manter-auditoria    preserva o histórico

**O que sai:** tudo que é operação — produtos, fornecedores, fichas, o razão de
estoque, notas, vendas, inventários, produções, fechamentos, de-para e o log de
sincronização. Mais as sessões e os links de recuperação de senha, que são de
quem estava usando a base antiga.

**O que fica:** empresa, loja, parâmetros, locais de estoque, setores,
categorias, unidades de medida, motivos de perda, e todo o acesso (usuários,
papéis e permissões) — além da configuração de integrações, cujas credenciais
seguem cifradas.

Produtos e fornecedores saem inteiros de propósito: a instalação nova também
nasce sem nenhum. O que o seed cria (setores, locais, categorias, unidades de
medida) está na lista dos que ficam, então a base limpa é exatamente a base de
um primeiro dia — que é o cenário que interessa testar.
"""

import sys

sys.path.insert(0, ".")

from config import DB_HOST, DB_NAME  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

# A ordem não importa: o TRUNCATE é um só, e o conjunto é fechado — nenhuma
# tabela de fora aponta para estas, então não é preciso CASCADE (que poderia
# levar junto justamente o que se quer preservar).
OPERACAO = [
    # razão de estoque e o que pendura nele
    "movimento_lotes", "estoque_lotes", "estoque_movimentos", "estoque_saldos",
    "inventario_itens", "inventarios", "producoes",
    # compras
    "nota_itens", "notas_entrada", "codigos_externos", "sync_log",
    # vendas e apuração
    "venda_itens", "vendas", "cmv_fechamentos",
    # cadastro de produto e o que depende dele
    "kit_itens", "ficha_itens", "fichas_tecnicas",
    "produto_precos", "produto_fornecedor", "produtos", "fornecedores",
    # sessões e links de senha da base antiga
    "sessoes", "senha_tokens",
]

PRESERVADAS = [
    "empresa", "unidades", "parametros", "locais_estoque",
    "setores", "categorias", "unidades_medida", "perda_motivos",
    "usuarios", "papeis", "permissoes", "papel_permissoes", "usuario_papeis",
    "usuario_setores", "integracoes", "schema_migrations",
]


def contar(cur, tabelas: list[str]) -> dict[str, int]:
    contagem = {}
    for t in tabelas:
        cur.execute(f'SELECT count(*) AS n FROM "{t}"')
        contagem[t] = cur.fetchone()["n"]
    return contagem


def main() -> int:
    argumentos = set(sys.argv[1:])
    simular = "--simular" in argumentos
    sem_perguntar = "--sim" in argumentos
    manter_auditoria = "--manter-auditoria" in argumentos
    limpar_usuarios = "--usuarios-de-teste" in argumentos

    # A trava que importa: este script existe para a base LOCAL de
    # desenvolvimento. Apontado para outro servidor, ele para aqui.
    if DB_HOST not in ("localhost", "127.0.0.1", "::1"):
        print(f"Recusado: o banco está em {DB_HOST}, que não é local.")
        print("Este script só roda contra a base local de desenvolvimento.")
        return 1

    alvos = list(OPERACAO) + ([] if manter_auditoria else ["auditoria"])

    init_pool()
    with get_cursor() as cur:
        antes = contar(cur, alvos)
        fica = contar(cur, PRESERVADAS)

    total = sum(antes.values())
    print(f"Banco: {DB_NAME} em {DB_HOST}\n")
    print("SAI (dados de operação):")
    for t, n in sorted(antes.items(), key=lambda x: -x[1]):
        if n:
            print(f"  {t:24} {n:>7}")
    print(f"  {'':24} {'-' * 7}\n  {'total':24} {total:>7}\n")
    print("FICA (cadastro base e acesso):")
    for t, n in sorted(fica.items()):
        print(f"  {t:24} {n:>7}")

    if limpar_usuarios:
        with get_cursor() as cur:
            cur.execute(
                """SELECT count(*) AS n FROM usuarios
                    WHERE email LIKE 'smoke.%' OR email LIKE 'tela.%'
                       OR email LIKE '%.teste@%' OR email LIKE 'cozinha.teste@%'""")
            print(f"\n  + {cur.fetchone()['n']} usuário(s) de teste também sairão")

    if simular:
        print("\n(--simular: nada foi apagado)")
        return 0

    if not sem_perguntar:
        print(f"\nIsto apaga {total} registro(s) e NÃO tem desfazer.")
        resposta = input('Digite "limpar" para confirmar: ').strip().lower()
        if resposta != "limpar":
            print("Cancelado — nada foi apagado.")
            return 1

    with get_cursor() as cur:
        lista = ", ".join(f'"{t}"' for t in alvos)
        # RESTART IDENTITY para os códigos automáticos (P0001…) recomeçarem do
        # começo: base nova com produto P0507 confundiria mais do que ajudaria.
        cur.execute(f"TRUNCATE {lista} RESTART IDENTITY")

        if limpar_usuarios:
            cur.execute(
                """DELETE FROM usuarios
                    WHERE (email LIKE 'smoke.%' OR email LIKE 'tela.%'
                           OR email LIKE '%.teste@%' OR email LIKE 'cozinha.teste@%')
                      AND email <> %s""",
                (__import__("config").ADMIN_EMAIL,),
            )

        depois = contar(cur, alvos)

    sobrou = sum(depois.values())
    print(f"\nApagados {total - sobrou} registro(s).")
    print("A base está como uma instalação nova: cadastre os primeiros produtos e comece.")
    print("Entre com o administrador de sempre — usuários e papéis foram preservados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
