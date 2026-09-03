"""Zera os dados de operação e deixa a base como uma instalação nova.

    python limpar_dados.py --simular     mostra o que sairia, sem apagar nada
    python limpar_dados.py               apaga (pede confirmação digitada)
    python limpar_dados.py --sim         apaga sem perguntar
    python limpar_dados.py --usuarios-de-teste   leva junto os usuários smoke./tela.
    python limpar_dados.py --so-o-admin          deixa SÓ o administrador
    python limpar_dados.py --tabelas-de-apoio    zera setores, locais e categorias
    python limpar_dados.py --residuo-de-teste    recolhe o apoio e os papéis das suítes
    python limpar_dados.py --cliente-novo        a base do primeiro dia, com o seed de volta
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

import os
import re
import sys

sys.path.insert(0, ".")

from config import ADMIN_EMAIL, DB_HOST, DB_NAME, SCRIPTS_DIR  # noqa: E402
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

# ---------------------------------------------------------------------------
# Resíduo de teste no cadastro de apoio
# ---------------------------------------------------------------------------
# 🔑 **As suítes criam setor, local, categoria e PAPEL por rodada, e ninguém os
# recolhia.** Depois de uma limpeza completa a base ficava com 73 setores, 121
# locais e 28 papéis — dos quais 68, 117 e 22 eram carimbo de rodada. É o mesmo
# buraco que as filiais de teste tinham, numa tabela diferente: `--filiais-de-
# teste` nasceu por isso, e parou nas lojas.
#
# ⚠️ **Aqui o critério é o NOME, e isso é uma exceção consciente.** Para as
# filiais o critério é "estar inativa", que é a marca que a própria suíte deixa
# no `atexit` — não há palpite. Setor e papel não têm marca equivalente: o que
# as suítes deixam é o carimbo de tempo no fim do nome (`COZINHA D05A`,
# `So conta 537000`, `TELA CORRIGIDO 692972`). Casar por nome é justamente o
# tipo de adivinhação que este projeto já removeu uma vez — então ela só é
# aceitável com as duas guardas abaixo, e nunca sozinha:
#
#   1. **nada pode referenciar a linha.** É a guarda de verdade: um setor que
#      algum produto usa não sai, case o nome ou não. Quem responde não é uma
#      lista escrita à mão — é o catálogo do Postgres (`_quem_referencia`), que
#      não envelhece quando alguém cria uma tabela nova.
#   2. **a lista é IMPRESSA antes**, e `--simular` existe para ser usado. Quem
#      confirma é gente, como na tela de duplicados.
#
# ⚠️ O carimbo de 4 caracteres precisa ter LETRA hexadecimal (`D05A`, `CA0D`):
# só dígitos em quatro casas é um ano, e "COZINHA 2024" é nome plausível de
# casa de verdade. De cinco ou seis caracteres o risco desaparece — ninguém
# chama um setor de "SALA 537000".
_CARIMBO = re.compile(r" (?:[0-9A-F]{5,6}|(?=[0-9A-F]{4}$)[0-9A-F]*[A-F][0-9A-F]*)$")

# ⚠️ `papeis` entra junto porque é o mesmo tipo de sujeira, ainda que não seja
# "apoio": a suíte do inventário cria um papel por rodada para provar que quem
# conta não monta a contagem, e eles poluem o cartão "Papéis" de todo cadastro
# de usuário.
RESIDUO = ["setores", "locais_estoque", "categorias", "papeis"]


def _quem_referencia(cur, tabela: str) -> list[tuple[str, str]]:
    """Quem aponta para o `id` desta tabela — perguntado ao Postgres.

    ⚠️ **Nunca uma lista escrita à mão.** Este script já foi pego duas vezes por
    tabela nova (`produto_unidades`, `cmv_movimentacao`), e uma lista fixa aqui
    envelheceria do mesmo jeito — só que apagando o que não devia em vez de
    estourar.
    """
    cur.execute(
        """SELECT filha.relname AS tabela, att.attname AS coluna
             FROM pg_constraint c
             JOIN pg_class filha ON filha.oid = c.conrelid
             JOIN pg_class mae ON mae.oid = c.confrelid
             JOIN unnest(c.conkey) WITH ORDINALITY k(attnum, ord) ON true
             JOIN pg_attribute att
               ON att.attrelid = c.conrelid AND att.attnum = k.attnum
            WHERE c.contype = 'f' AND mae.relname = %s""",
        (tabela,),
    )
    return [(r["tabela"], r["coluna"]) for r in cur.fetchall()]


# ⚠️ **Nem toda filha é uma referência EXTERNA.** `papel_permissoes` é parte do
# papel — todo papel tem as dela, e tratá-la como "alguém usa isto" fazia a
# varredura devolver ZERO papéis: cada um estava preso pelas próprias
# permissões. A lista aqui é de tabelas que PERTENCEM à linha e saem com ela.
_PROPRIAS = {"papeis": {"papel_permissoes"}}


def residuo_de_teste(cur, tabela: str, ignorar: set[str] | None = None,
                     saindo: dict[str, set[int]] | None = None) -> list[dict]:
    """As linhas com carimbo de rodada que NINGUÉM referencia.

    As duas condições valem juntas, sempre: o nome levanta o candidato, e a
    ausência de referência é o que autoriza apagá-lo.

    ⚠️ `ignorar` são as tabelas que vão deixar de existir neste mesmo comando —
    a operação inteira, que está prestes a ser truncada. Sem isso, a lista
    impressa para o operador seria menor que a lista realmente apagada (metade
    dos setores está presa a produtos que vão sumir três linhas adiante), e
    confirmar uma lista que não é a que vai acontecer é pior do que não mostrar
    lista nenhuma.
    """
    ignorar = (ignorar or set()) | _PROPRIAS.get(tabela, set())
    saindo = saindo or {}
    cur.execute(f'SELECT id, nome FROM "{tabela}" ORDER BY id')
    candidatos = [dict(r) for r in cur.fetchall() if _CARIMBO.search(r["nome"] or "")]
    if not candidatos:
        return []

    ligacoes = [(f, c) for f, c in _quem_referencia(cur, tabela) if f not in ignorar]
    presos: set[int] = set()
    ids = [c["id"] for c in candidatos]
    for filha, coluna in ligacoes:
        # ⚠️ A auto-referência (`categorias.id_pai`) conta: categoria que é mãe
        # de outra não sai, senão a filha ficaria órfã.
        # ⚠️ **`saindo` exclui as LINHAS da filha que também vão embora**, e não
        # a filha inteira: um local de VERDADE apontando para um setor tem de
        # continuar segurando aquele setor. Ignorar a tabela toda seria rápido e
        # apagaria cadastro bom.
        fora = list(saindo.get(filha, set()))
        cur.execute(
            f'SELECT DISTINCT "{coluna}" AS id FROM "{filha}" '
            f'WHERE "{coluna}" = ANY(%s) AND NOT (id = ANY(%s))'
            if fora else
            f'SELECT DISTINCT "{coluna}" AS id FROM "{filha}" WHERE "{coluna}" = ANY(%s)',
            (ids, fora) if fora else (ids,),
        )
        presos |= {r["id"] for r in cur.fetchall() if r["id"] is not None}
    return [c for c in candidatos if c["id"] not in presos]


def residuo_completo(cur, ignorar: set[str]) -> dict[str, list[dict]]:
    """A varredura inteira, repetida até parar de render.

    🔑 **Uma passada só não basta, e a razão é o setor.** Desde a migração 051 o
    local de estoque aponta para um setor: o setor de rodada fica preso ao local
    de rodada, que só some na mesma varredura. Uma passada deixaria 45 setores
    para trás e a próxima limpeza os encontraria — dando a impressão de que a
    varredura não funciona.

    ⚠️ **Ponto fixo, não uma ordem escrita à mão.** Ordenar as tabelas à mão
    resolveria hoje e quebraria na primeira chave estrangeira nova, em silêncio.
    Repetir até nada mais sair não envelhece.
    """
    achados: dict[str, list[dict]] = {t: [] for t in RESIDUO}
    vistos: dict[str, set[int]] = {t: set() for t in RESIDUO}
    while True:
        novos = 0
        for tabela in RESIDUO:
            for linha in residuo_de_teste(cur, tabela, ignorar, vistos):
                if linha["id"] in vistos[tabela]:
                    continue
                vistos[tabela].add(linha["id"])
                achados[tabela].append(linha)
                novos += 1
        if not novos:
            return achados


# ---------------------------------------------------------------------------
# A base do primeiro dia
# ---------------------------------------------------------------------------
# 🔑 **`--tabelas-de-apoio` deixa a base MAIS VAZIA que uma instalação nova, e
# isso é de propósito** — sem local de estoque nenhum movimento entra, que é o
# cenário que se quer testar às vezes. Mas quem pede "deixa como cliente novo"
# quer o contrário: a base que o cliente recebe, com os setores, locais e
# categorias que o seed cria no primeiro dia.
#
# ⚠️ **O seed NÃO volta sozinho.** Ele é a migração 005, e o `db_updater` a
# registra por checksum: aplicada uma vez, nunca mais roda. Truncar o apoio sem
# reaplicá-la deixa a casa sem categoria e sem prateleira, para sempre — e a
# diferença só aparece quando alguém tenta cadastrar o primeiro produto.
#
# ⚠️ Ele já se protege sozinho (`WHERE NOT EXISTS`): reaplicá-lo numa tabela que
# tem linha não duplica nada.
_SEED = "005_cadastros_iniciais.sql"

# ⚠️ **O que NÃO sai nem com `--cliente-novo`, e é decisão, não esquecimento:**
# `empresa` (nome, CNPJ e a logo da casa) e `integracoes` (as credenciais do
# Omie e do PDV, cifradas). Apagá-las obrigaria a redigitar app_key/app_secret
# antes de qualquer teste de importação — que é justamente o que se ia testar.
# Já se perdeu uma credencial neste projeto por descuido de script.


def semear(cur) -> int:
    """Reaplica o seed do primeiro dia. Devolve quantas linhas de apoio nasceram."""
    with open(os.path.join(SCRIPTS_DIR, _SEED), encoding="utf-8") as f:
        cur.execute(f.read())
    total = 0
    for t in ("setores", "locais_estoque", "categorias"):
        cur.execute(f'SELECT count(*) AS n FROM "{t}"')
        total += cur.fetchone()["n"]
    return total


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


def _do_residuo(residuo: dict[str, list[dict]]) -> int:
    """Quantas linhas de apoio a varredura levantou.

    ⚠️ **As duas frases que mais importam do script contavam SÓ a operação.**
    Numa base já limpa isso dava "Isto apaga 0 registro(s)" com 209 linhas
    prestes a sair — a pergunta que pede confirmação mostrando o número errado —
    e, no fim, "Apagados 0 registro(s)" depois de apagar 209.
    """
    return sum(len(v) for v in residuo.values())


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
    limpar_residuo = "--residuo-de-teste" in argumentos

    # 🔑 **Uma opção, uma intenção.** "Deixa como cliente novo" é a soma de
    # quatro escolhas mais o seed de volta; pedir as cinco à mão é o tipo de
    # combinação que se erra por esquecer uma — e a que se esquece é sempre o
    # seed, cuja falta só aparece dias depois, quando alguém tenta cadastrar o
    # primeiro produto e não há categoria nenhuma.
    cliente_novo = "--cliente-novo" in argumentos
    if cliente_novo:
        so_o_admin = limpar_apoio = limpar_filiais = limpar_residuo = True

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
        if cliente_novo:
            print("    (mas o seed do primeiro dia volta em seguida: setores,")
            print("     locais e categorias como o cliente os recebe)")

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

    # ⚠️ **A lista sai por INTEIRO, nome a nome.** Um total ("68 setores") não
    # deixa ninguém conferir nada, e é exatamente aqui que um nome de verdade
    # apanhado pelo carimbo apareceria. É a mesma regra da tela de duplicados: o
    # que a máquina levantou existe para ser OLHADO antes de virar exclusão.
    residuo: dict[str, list[dict]] = {}
    if limpar_residuo:
        with get_cursor() as cur:
            # ⚠️ `alvos` entra como "vai deixar de existir": sem isso a lista
            # impressa seria menor que a apagada — metade dos setores está presa
            # a produtos que somem três linhas adiante.
            residuo = residuo_completo(cur, set(alvos))
        quantos = _do_residuo(residuo)
        if not quantos:
            print("  + nenhuma linha de apoio com carimbo de rodada — nada a recolher")
        else:
            print(f"  + {quantos} linha(s) de apoio com carimbo de rodada, que")
            print("    ninguem referencia, tambem sairao:")
        for tabela, linhas in residuo.items():
            if not linhas:
                continue
            print(f"      {tabela} ({len(linhas)}):")
            for linha in linhas:
                print(f"        {linha['id']:>5}  {linha['nome']}")

    if simular:
        print("\n(--simular: nada foi apagado)")
        return 0

    if not sem_perguntar:
        print(f"\nIsto apaga {total + _do_residuo(residuo)} registro(s) e NÃO tem desfazer.")
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

        # 🔑 **As fotos das fichas ficavam órfãs.** `arquivos` não entra no
        # TRUNCATE de propósito — é lá que mora a LOGO da empresa, que é
        # cadastro e fica. Mas a foto do prato tem `dono = 'ficha-<id>'`, e as
        # fichas acabaram de sair: sobravam megabytes de imagem apontando para
        # nada, e o `RESTART IDENTITY` ainda faz a numeração recomeçar, então
        # uma ficha nova acaba herdando o id de uma cujo arquivo continua ali.
        # ⚠️ Só o que é de ficha. A logo tem `dono = 'logo-empresa'` e não é
        # tocada: apagá-la seria a mesma perda que as suítes causavam.
        if "fichas_tecnicas" in alvos:
            cur.execute("DELETE FROM arquivos WHERE dono LIKE 'ficha-%'")

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

        if limpar_residuo:
            # ⚠️ **Recalculado DEPOIS do TRUNCATE, não reaproveitado de cima.**
            # A lista impressa foi levantada com a operação ainda de pé, quando
            # produto e movimento ainda prendiam metade das linhas; aplicá-la
            # agora deixaria para trás justamente o que a limpeza acabou de
            # soltar. Recalcular só pode CRESCER a lista, e cada linha nova
            # passou pelas mesmas duas guardas.
            # A MESMA varredura da lista impressa, agora com a operação já
            # truncada — o `ignorar` fica vazio porque as tabelas já estão
            # vazias de verdade. Duas implementações divergiriam, e a divergência
            # seria exatamente entre o que a pessoa confirmou e o que aconteceu.
            for tabela, linhas in residuo_completo(cur, set()).items():
                alvos_residuo = [x["id"] for x in linhas]
                if not alvos_residuo:
                    continue
                if tabela == "papeis":
                    # `papel_permissoes` não tem CASCADE: sem apagá-la antes, a
                    # exclusão do papel bate na chave estrangeira.
                    cur.execute(
                        "DELETE FROM papel_permissoes WHERE id_papel = ANY(%s)",
                        (alvos_residuo,))
                cur.execute(f'DELETE FROM "{tabela}" WHERE id = ANY(%s)', (alvos_residuo,))

        if cliente_novo:
            # ⚠️ **Depois de tudo**, nunca antes: o TRUNCATE do apoio levaria o
            # seed junto, e a base terminaria vazia do mesmo jeito — com a
            # diferença de que o script teria dito que semeou.
            nasceram = semear(cur)

        depois = contar(cur, alvos)

    sobrou = sum(depois.values())
    print(f"\nApagados {total - sobrou + _do_residuo(residuo)} registro(s).")
    if cliente_novo:
        print(f"Seed do primeiro dia reaplicado: {nasceram} linha(s) de apoio.")
        print("Empresa e credenciais de integração foram PRESERVADAS — sem elas não")
        print("haveria o que importar.")
    print("A base está como uma instalação nova: cadastre os primeiros produtos e comece.")
    print("Entre com o administrador de sempre — usuários e papéis foram preservados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
