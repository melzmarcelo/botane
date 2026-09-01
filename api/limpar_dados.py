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
    # ⚠️ `inventario_contadores` aponta para `inventarios`: sem ela aqui, o
    # TRUNCATE falha no meio e quem rodou acha que limpou. Foi a guarda do
    # próprio script que avisou — a mensagem do Postgres passa longe disso.
    "inventario_contadores", "inventario_itens", "inventarios",
    "producao_agenda", "producoes",
    # remessa entre lojas: os itens apontam para movimentos do razão, e a
    # cabeça aponta para locais e usuários
    "transferencia_itens", "transferencias",
    # compras
    "nota_itens", "notas_entrada", "codigos_externos", "sync_log",
    # vendas e apuração
    "venda_itens", "vendas", "cmv_movimentacao", "cmv_fechamentos",
    # cadastro de produto e o que depende dele
    "kit_itens", "ficha_itens", "fichas_tecnicas",
    "produto_precos", "produto_fornecedor", "produto_unidades", "produtos", "fornecedores",
    # o que já mandamos ao PDV — e o que estava esperando ir
    # ⚠️ **A fila do PDV é DERIVADA, e por isso aguenta perder o histórico**: ela
    # relê o cardápio de lá e reconhece o que já está adotado. O que não pode
    # ficar é pendência e envio apontando para produto que não existe mais.
    "pdv_pendencias", "pdv_envios",
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

# ---------------------------------------------------------------------------
# Filiais de teste
# ---------------------------------------------------------------------------
# 🔑 **As suítes criam uma loja por rodada, e ninguém as apagava.** `unidades`
# está em PRESERVADAS — é cadastro base, e numa casa de verdade a loja fica —,
# então elas se acumulavam: dezenove numa base de desenvolvimento. E não é só
# sujeira de lista: **filial ATIVA muda a barra superior**, porque o seletor de
# loja aparece e vira o primeiro `<select>` do documento; aí checagens de tela
# que nada têm a ver com loja passam a ler id de loja.
#
# ⚠️ **O critério é ESTAR INATIVA, não o nome.** As suítes desativam a filial
# delas no `atexit`, então "inativa" é exatamente a marca que elas deixam — e
# casar por nome ("Filial de teste…") seria adivinhação, que é o palpite que
# este projeto já removeu uma vez. A loja que a casa usa está ativa, e fica.
# ⚠️ A matriz nunca entra, marcada ou não: sem ela não há loja padrão.
_FILIAIS = "SELECT id FROM unidades WHERE NOT ativo AND NOT matriz"

_SQL_FILIAIS_CONTAR = f"SELECT count(*) AS n FROM ({_FILIAIS}) AS f"

# A ordem importa: o que aponta para a loja sai antes dela.
_SQL_FILIAIS = [
    f"DELETE FROM locais_estoque WHERE id_unidade IN ({_FILIAIS})",
    f"DELETE FROM setores WHERE id_unidade IN ({_FILIAIS})",
    f"DELETE FROM parametros WHERE id_unidade IN ({_FILIAIS})",
    f"DELETE FROM integracoes WHERE id_unidade IN ({_FILIAIS})",
    f"DELETE FROM unidades WHERE id IN ({_FILIAIS})",
]

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
        # ⚠️ `semana.` faltava, e são CINCO por rodada: `cenario_semana.py` cria
        # um usuário por papel (gerente, conferente, cozinha, salão, contador).
        # Sem eles no filtro, a base "entregue ao cliente" ia com a equipe de
        # uma suíte dentro.
        # ⚠️ `conta.` entrou depois: é o contador que a suíte do inventário cria
        # a cada rodada, para provar que quem conta não monta a contagem. Sem
        # ele no filtro, a base "entregue ao cliente" ia com dezesseis deles.
        else """(email LIKE 'smoke.%%' OR email LIKE 'tela.%%'
                 OR email LIKE 'semana.%%' OR email LIKE 'conta.%%'
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


def referenciam(cur, alvos: list[str]) -> set[str]:
    """Quem aponta para as tabelas que vão ser limpas e ficou de fora da lista.

    O Postgres recusa truncar uma tabela referenciada por outra que não esteja
    no mesmo comando. Descobrir isso ANTES é a diferença entre uma frase que
    diz o que fazer e um traceback no meio da limpeza.
    """
    cur.execute(
        """
        SELECT DISTINCT filha.relname AS tabela
          FROM pg_constraint c
          JOIN pg_class filha ON filha.oid = c.conrelid
          JOIN pg_class mae ON mae.oid = c.confrelid
         WHERE c.contype = 'f' AND mae.relname = ANY(%s) AND filha.relname <> ALL(%s)
        """,
        (alvos, alvos),
    )
    return {r["tabela"] for r in cur.fetchall()}


def main() -> int:
    argumentos = set(sys.argv[1:])
    simular = "--simular" in argumentos
    sem_perguntar = "--sim" in argumentos
    manter_auditoria = "--manter-auditoria" in argumentos
    limpar_usuarios = "--usuarios-de-teste" in argumentos
    so_o_admin = "--so-o-admin" in argumentos
    limpar_apoio = "--tabelas-de-apoio" in argumentos
    limpar_filiais = "--filiais-de-teste" in argumentos

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
        # Tabela nova que aponta para uma das alvos derruba o TRUNCATE inteiro,
        # e a mensagem do Postgres passa longe de "atualize a lista deste
        # script". Já aconteceu duas vezes (produto_unidades, cmv_movimentacao):
        # a limpeza estourava e quem rodou achava que tinha limpado.
        faltando = referenciam(cur, alvos)
        if faltando:
            print("Recusado: estas tabelas apontam para as que seriam limpas e")
            print("não estão na lista — o TRUNCATE falharia no meio:")
            for t in sorted(faltando):
                print(f"  {t}")
            print()
            print("Adicione-as a OPERACAO (ou a APOIO) em limpar_dados.py.")
            return 1

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

    if limpar_filiais:
        with get_cursor() as cur:
            cur.execute(_SQL_FILIAIS_CONTAR)
            quantas = cur.fetchone()["n"]
        print(f"\n  + {quantas} loja(s) INATIVA(s) tambem sairao, com os locais,")
        print("    parametros, setores e integracoes que sao so delas")

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

        if limpar_filiais:
            # ⚠️ **Depois do TRUNCATE**, nunca antes: enquanto houver movimento,
            # venda ou nota apontando para a loja, a exclusão bate na chave
            # estrangeira. Limpa a operação primeiro e a loja fica solta.
            for comando in _SQL_FILIAIS:
                cur.execute(comando)

        depois = contar(cur, alvos)

    sobrou = sum(depois.values())
    print(f"\nApagados {total - sobrou} registro(s).")
    print("A base está como uma instalação nova: cadastre os primeiros produtos e comece.")
    print("Entre com o administrador de sempre — usuários e papéis foram preservados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
