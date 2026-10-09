"""O produto novo do Omie que chega na nota — e o item pendente que se religa sozinho.

Relato do dono (09/10/2026): *"sobre novos produtos que são cadastrados no Omie e
vêm na nota, estes são puxados para o Botané? pois alguns não vem o cadastro novo
de lá."* Medido no ar: quase cinquenta itens na fila, vários com um cadastro de
nome IDÊNTICO já existindo — o produto tinha vindo, só que depois da nota.

Três coisas mudaram em `importador.sincronizar_completo`, e são as que esta suíte
afirma:
1. o item pendente é RELIGADO em toda busca, sem ninguém clicar em reconciliar
2. a nota nova com produto desconhecido faz o catálogo vir NAQUELA busca, mesmo
   quando a agenda já o trouxe hoje
3. sem nota nova pedindo, o catálogo NÃO é varrido de novo

⚠️ **Tudo acontece numa transação que é DESFEITA no fim.** O Omie é de mentira,
montado aqui, e nada desta rodada fica na base — nem nota, nem produto, nem
registro de sincronização. (`importada_em = now()` é o instante da transação, e é
por isso que a nota inserida aqui conta como "desta busca".)

    python tests/smoke_omie_religar.py            (não precisa da API de pé)
"""

import sys
import time

sys.path.insert(0, "tests")
sys.path.insert(0, ".")
from database import get_cursor  # noqa: E402
from services.omie import importador  # noqa: E402

ok = 0
falhas: list[str] = []


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


class OmieDeMentira:
    """Só o que a busca usa: nenhuma nota nova, e um catálogo com o que se disser."""

    modo = "real"

    def __init__(self, catalogo):
        self.catalogo = catalogo
        self.chamadas: list[str] = []

    def paginar(self, _servico, call, _chave, **_resto):
        self.chamadas.append(call)
        if call == "ListarProdutos" and self.catalogo:
            yield {}, self.catalogo

    def chamar(self, *_a, **_k):  # nenhuma nota nova: o detalhe nunca é pedido
        raise AssertionError("o detalhe de nota não deveria ser pedido aqui")


class Desfazer(Exception):
    """Levantada no fim de cada cenário: a transação inteira volta atrás."""


marca = str(time.time_ns() // 100)[-7:]


def cenario(nome, corpo):
    print(nome)
    try:
        with get_cursor() as cur:
            cur.execute("SELECT id FROM unidades WHERE ativo ORDER BY id LIMIT 1")
            corpo(cur, cur.fetchone()["id"])
            raise Desfazer
    except Desfazer:
        pass


def nota_com_item(cur, id_unidade, codigo_omie, descricao):
    cur.execute(
        """INSERT INTO notas_entrada (id_unidade, numero, status, origem)
           VALUES (%s, %s, 'IMPORTADA', 'OMIE') RETURNING id""",
        (id_unidade, f"RL{marca}"))
    id_nota = cur.fetchone()["id"]
    cur.execute(
        """INSERT INTO nota_itens (id_nota, seq, descricao_fornecedor, quantidade, codigo_omie)
           VALUES (%s, 1, %s, 1, %s) RETURNING id""",
        (id_nota, descricao, codigo_omie))
    return id_nota, cur.fetchone()["id"]


def produto_do_item(cur, id_item):
    cur.execute("SELECT id_produto FROM nota_itens WHERE id = %s", (id_item,))
    return cur.fetchone()["id_produto"]


# Código que não existe em catálogo nenhum: leva a marca da rodada.
CODIGO = f"88{marca}"
NO_OMIE = [{"codigo_produto": int(CODIGO), "codigo": f"RL-{marca}",
            "descricao": f"Produto novo do Omie {marca}", "unidade": "KG"}]


def a_nota_pede_o_catalogo(cur, id_unidade):
    _nota, id_item = nota_com_item(cur, id_unidade, CODIGO, f"Produto novo do Omie {marca}")
    checar("o item nasce sem produto: ninguém aqui conhece o código",
           produto_do_item(cur, id_item) is None)
    omie = OmieDeMentira(NO_OMIE)
    # ⚠️ `catalogo=False` é a agenda dizendo "já trouxe o catálogo hoje".
    r = importador.sincronizar_completo(cur, id_unidade, omie, None, dias=1, catalogo=False)
    checar("a busca percebe que a nota trouxe produto desconhecido",
           r.get("catalogo_pela_nota") is True, r.get("catalogo_pela_nota"))
    checar("e vai ao catálogo NESTA busca, mesmo a agenda já tendo ido hoje",
           "ListarProdutos" in omie.chamadas, omie.chamadas)
    checar("o cadastro novo é criado", (r.get("cadastros") or {}).get("criados") == 1,
           r.get("cadastros"))
    checar("e o item da nota encontra o produto sozinho", r.get("religados", 0) >= 1,
           r.get("religados"))
    cur.execute("SELECT codigo_omie, nome FROM produtos WHERE id = %s",
                (produto_do_item(cur, id_item),))
    ligado = cur.fetchone() or {}
    checar("que é o do código do Omie que veio na nota",
           str(ligado.get("codigo_omie")) == CODIGO, ligado)


def sem_nota_nova_o_catalogo_descansa(cur, id_unidade):
    omie = OmieDeMentira(NO_OMIE)
    r = importador.sincronizar_completo(cur, id_unidade, omie, None, dias=1, catalogo=False)
    checar("sem nota nova pedindo, o catálogo NÃO é varrido de novo",
           "ListarProdutos" not in omie.chamadas and r.get("catalogo_pela_nota") is False,
           (omie.chamadas, r.get("catalogo_pela_nota")))
    checar("e a religação roda mesmo assim, sem erro",
           "erro_ao_religar" not in r and "religados" in r, r)


def o_cadastro_que_chegou_depois(cur, id_unidade):
    # A nota de ONTEM: não é "desta busca", então não dispara o catálogo.
    _nota, id_item = nota_com_item(cur, id_unidade, CODIGO, f"Produto novo do Omie {marca}")
    cur.execute("UPDATE notas_entrada SET importada_em = now() - interval '1 day' "
                "WHERE id = %s", (_nota,))
    # O cadastro chega depois, por qualquer caminho — aqui, direto.
    cur.execute(
        """INSERT INTO produtos (codigo, nome, tipo, um_estoque, codigo_omie, status)
           VALUES (%s, %s, 'INSUMO', 'KG', %s, 'ATIVO') RETURNING id""",
        (f"RL-{marca}", f"Produto novo do Omie {marca}", CODIGO))
    id_produto = cur.fetchone()["id"]
    omie = OmieDeMentira([])
    r = importador.sincronizar_completo(cur, id_unidade, omie, None, dias=1, catalogo=False)
    checar("nota de ontem não dispara a varredura do catálogo",
           "ListarProdutos" not in omie.chamadas, omie.chamadas)
    # 🔑 A afirmação central: era este o item que ficava na fila até alguém clicar.
    checar("mas o item dela é religado ao cadastro que chegou depois",
           produto_do_item(cur, id_item) == id_produto, produto_do_item(cur, id_item))
    checar("e a resposta conta quantos encontraram o produto", r.get("religados", 0) >= 1,
           r.get("religados"))
    # ⚠️ **Só as notas que GANHARAM vínculo são recalculadas na busca.** Passar todas
    # as abertas a limpo a cada busca deixou a tela de compras esperando segundos
    # (medido na bateria do navegador, com 954 notas abertas na base local).
    medido = importador.reconciliar(cur, id_unidade, so_as_mexidas=True)
    checar("e a busca automática não recalcula as notas que não mudaram",
           medido["recalculadas"] == medido["notas"], medido)


def nota_lancada_nao_se_mexe(cur, id_unidade):
    id_nota, id_item = nota_com_item(cur, id_unidade, CODIGO, f"Produto novo do Omie {marca}")
    cur.execute("UPDATE notas_entrada SET status = 'LANCADA', "
                "importada_em = now() - interval '1 day' WHERE id = %s", (id_nota,))
    cur.execute(
        """INSERT INTO produtos (codigo, nome, tipo, um_estoque, codigo_omie, status)
           VALUES (%s, %s, 'INSUMO', 'KG', %s, 'ATIVO')""",
        (f"RL-{marca}", f"Produto novo do Omie {marca}", CODIGO))
    importador.sincronizar_completo(cur, id_unidade, OmieDeMentira([]), None, dias=1,
                                    catalogo=False)
    # ⚠️ Os movimentos dela já estão no razão: trocar o produto do item faria a
    # tela contar uma história diferente do que o estoque registrou.
    checar("item de nota JÁ LANÇADA não é religado", produto_do_item(cur, id_item) is None,
           produto_do_item(cur, id_item))


cenario("1. a nota nova traz produto que só existe no Omie", a_nota_pede_o_catalogo)
cenario("\n2. busca sem nota nova", sem_nota_nova_o_catalogo_descansa)
cenario("\n3. o cadastro chegou depois da nota", o_cadastro_que_chegou_depois)
cenario("\n4. o que já foi lançado fica como está", nota_lancada_nao_se_mexe)

print("\n5. nada ficou na base")
with get_cursor() as cur:
    cur.execute("SELECT count(*) AS n FROM produtos WHERE codigo_omie = %s", (CODIGO,))
    checar("nenhum produto desta rodada", cur.fetchone()["n"] == 0)
    cur.execute("SELECT count(*) AS n FROM notas_entrada WHERE numero = %s", (f"RL{marca}",))
    checar("nenhuma nota desta rodada", cur.fetchone()["n"] == 0)

print("\n6. a religação que falha não derruba a busca")


def religar_quebrado(cur, id_unidade):
    original = importador.reconciliar

    def quebra(c, _id_unidade, **_resto):
        # Um erro de BANCO de verdade: é ele que aborta a transação.
        c.execute("SELECT 1 FROM tabela_que_nao_existe")

    importador.reconciliar = quebra
    try:
        r = importador.sincronizar_completo(cur, id_unidade, OmieDeMentira([]), None,
                                            dias=1, catalogo=False)
    finally:
        importador.reconciliar = original
    checar("o erro da religação viaja na resposta", "erro_ao_religar" in r, r)
    # ⚠️ A afirmação que importa: depois do erro a transação CONTINUA usável. Sem
    # o ponto de retorno, esta consulta morreria em "transação abortada" — e com
    # ela a gravação das notas que a busca acabou de trazer.
    cur.execute("SELECT 1 AS vivo")
    checar("e a transação da busca continua de pé", cur.fetchone()["vivo"] == 1)


cenario("", religar_quebrado)

checar("o teto do catálogo passa dos 3.000 produtos", importador.TETO_DO_CATALOGO * 50 >= 10000,
       importador.TETO_DO_CATALOGO)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print(f"  - {x}")
sys.exit(1 if falhas else 0)
