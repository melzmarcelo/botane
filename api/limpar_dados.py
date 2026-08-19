"""Zera os dados de operação e deixa a base como uma instalação nova.

    python limpar_dados.py --simular     mostra o que sairia, sem apagar nada
    python limpar_dados.py               apaga (pede confirmação digitada)
    python limpar_dados.py --sim         apaga sem perguntar
    python limpar_dados.py --usuarios-de-teste   leva junto os usuários smoke./tela.
    python limpar_dados.py --so-o-admin          deixa SÓ o administrador
    python limpar_dados.py --tabelas-de-apoio    zera setores, locais e categorias
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

from config import ADMIN_EMAIL, DB_HOST, DB_NAME  # noqa: E402
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

# As "tabelas de apoio" da tela de cadastros, menos as unidades de medida — que
# não são escolha da casa (KG é KG) e cuja tabela sustenta toda conversão de
# embalagem.
#
# ⚠️ Isto deixa a base MAIS VAZIA que uma instalação nova: a migração de seed
# cria setores, locais e categorias. Sem local de estoque, nenhum movimento é
# possível até alguém criar o primeiro — que é justamente o que se quer testar
# quando se pede esta limpeza.
#
# `usuario_setores` entra junto por obrigação: ele referencia `setores`, e o
# Postgres recusa truncar uma tabela referenciada sem levar quem a referencia.
# Faz sentido de qualquer forma — vínculo de pessoa com um setor que deixou de
# existir não é dado, é lixo.
APOIO = ["locais_estoque", "categorias", "usuario_setores", "setores"]

PRESERVADAS = [
    "empresa", "unidades", "parametros", "locais_estoque",
    "setores", "categorias", "unidades_medida", "perda_motivos",
    "usuarios", "papeis", "permissoes", "papel_permissoes", "usuario_papeis",
    "usuario_setores", "integracoes", "schema_migrations",
]


def _sql_usuarios(so_o_admin: bool, contar: bool = False) -> str:
    """Quem sai da tabela de usuários.

    Dois modos: só o resíduo dos testes, ou **tudo menos o administrador** —
    este último é o que prepara a base para entregar ao cliente, que vai criar a
    própria equipe.
    """
    filtro = (
        "email <> %s"
        if so_o_admin
        else """(email LIKE 'smoke.%%' OR email LIKE 'tela.%%'
                 OR email LIKE '%%.teste@%%' OR email LIKE 'cozinha.teste@%%')
                AND email <> %s"""
    )
    alvo = "SELECT count(*) AS n" if contar else "DELETE"
    return f"{alvo} FROM usuarios WHERE {filtro}"


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
    so_o_admin = "--so-o-admin" in argumentos
    limpar_apoio = "--tabelas-de-apoio" in argumentos

    # A trava que importa: este script existe para a base LOCAL de
    # desenvolvimento. Apontado para outro servidor, ele para aqui.
    if DB_HOST not in ("localhost", "127.0.0.1", "::1"):
        print(f"Recusado: o banco está em {DB_HOST}, que não é local.")
        print("Este script só roda contra a base local de desenvolvimento.")
        return 1

    alvos = list(OPERACAO) + ([] if manter_auditoria else ["auditoria"])
    if limpar_apoio:
        alvos += APOIO

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
        if t not in alvos:
            print(f"  {t:24} {n:>7}")

    if limpar_apoio:
        print("\n  ! sem local de estoque, nenhum movimento entra até criarem o primeiro")

    if limpar_usuarios or so_o_admin:
        with get_cursor() as cur:
            cur.execute(_sql_usuarios(so_o_admin, contar=True), (ADMIN_EMAIL,))
            quantos = cur.fetchone()["n"]
        rotulo = "além do administrador" if so_o_admin else "de teste"
        print(f"\n  + {quantos} usuário(s) {rotulo} também sairão")

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
        cur.execute(f"TRUNCATE {lista} RESTART IDENTITY")

        # `RESTART IDENTITY` reinicia só as sequences que PERTENCEM às colunas
        # das tabelas truncadas. `seq_codigo_produto` é independente (é ela que
        # gera o P0001) e sobrevive: sem esta linha, o primeiro produto da base
        # limpa nascia P0504 e a numeração começava no meio.
        if "produtos" in alvos:
            cur.execute("ALTER SEQUENCE IF EXISTS seq_codigo_produto RESTART")

        if limpar_usuarios or so_o_admin:
            # O vínculo com papéis cai por CASCADE; sessões e tokens já foram
            # truncados acima. O administrador nunca entra na conta: sem ele
            # ninguém entra para criar os outros.
            cur.execute(_sql_usuarios(so_o_admin), (ADMIN_EMAIL,))

        depois = contar(cur, alvos)

    sobrou = sum(depois.values())
    print(f"\nApagados {total - sobrou} registro(s).")
    print("A base está como uma instalação nova: cadastre os primeiros produtos e comece.")
    print("Entre com o administrador de sempre — usuários e papéis foram preservados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
