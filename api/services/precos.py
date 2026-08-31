"""O preço de venda — um lugar só que sabe de quem ele é.

🔑 **O preço pode ser da CASA ou da LOJA, e a regra é: o da loja manda; sem ele,
vale o da casa.** A coluna `produto_precos.id_unidade` existe desde o começo e
ninguém a usava — todo preço nascia global. No PDV ele é **por filial**, e duas
lojas podem cobrar valores diferentes pelo mesmo prato; sem essa resolução, a
filial que cobra mais barato teria o preço da matriz no cardápio e na margem.

⚠️ **A queda para o preço da casa não é conveniência, é o caso comum.** A casa
que abre a segunda loja cobra o mesmo na maioria dos itens; obrigar a cadastrar
o preço duas vezes faria a filial nascer com centenas de pratos sem preço — e
prato sem preço não vende.

⚠️ **É a mesma forma da reserva do custo**: o específico primeiro, o geral
depois. Lá é o médio da loja caindo para o preço do fornecedor (que é da rede);
aqui é o preço da loja caindo para o da casa.

⚠️ E o índice único já previa os dois: `(id_produto, coalesce(id_unidade, 0))
WHERE vigente_ate IS NULL`. Um preço vigente da casa e um por loja convivem sem
migração nenhuma.
"""

# O SQL da resolução, para quem precisa dele DENTRO de uma consulta maior.
# ⚠️ Escrito uma vez e reusado: seis consultas tinham o `id_unidade IS NULL`
# copiado por dentro, e uma cópia sempre fica para trás quando a regra muda —
# foi assim que o preço da loja ficou dois meses sendo ignorado.
SQL_VIGENTE = """
    (SELECT pp.preco_venda FROM produto_precos pp
      WHERE pp.id_produto = {produto} AND pp.vigente_ate IS NULL
        AND (pp.id_unidade = {unidade} OR pp.id_unidade IS NULL)
      -- ⚠️ O da LOJA primeiro: `NULLS LAST` põe o da casa no fim, e o `LIMIT 1`
      -- escolhe o específico quando ele existe.
      ORDER BY pp.id_unidade NULLS LAST
      LIMIT 1)
"""


def sql_vigente(produto: str = "p.id", unidade: str = "%(unidade)s") -> str:
    """O trecho de SQL que resolve o preço vigente, pronto para embutir.

    `produto` e `unidade` são as EXPRESSÕES de quem chama — a coluna do produto
    na consulta dele e o parâmetro da loja.
    """
    return SQL_VIGENTE.format(produto=produto, unidade=unidade)


def vigente(cur, id_produto: int, id_unidade: int | None = None):
    """O preço que vale para este produto nesta loja, ou `None`."""
    cur.execute(
        """SELECT preco_venda FROM produto_precos
            WHERE id_produto = %(p)s AND vigente_ate IS NULL
              AND (id_unidade = %(u)s OR id_unidade IS NULL)
            ORDER BY id_unidade NULLS LAST LIMIT 1""",
        {"p": id_produto, "u": id_unidade},
    )
    linha = cur.fetchone()
    return linha["preco_venda"] if linha else None


def gravar(cur, id_produto: int, preco, id_usuario: int,
           id_unidade: int | None = None) -> bool:
    """Fecha o preço vigente DAQUELE dono e abre outro. Devolve se mudou.

    ⚠️ **Só grava quando MUDA.** `produto_precos` é histórico: uma linha nova a
    cada salvamento transformaria "quando o preço subiu?" — que é a pergunta que
    a tabela existe para responder — em ruído.

    ⚠️ **`id_unidade` nulo é o preço DA CASA, e não é o mesmo que "a loja 1".**
    Fechar o da casa ao gravar o de uma loja apagaria o preço de todas as
    outras; cada dono tem a sua linha vigente, e o índice único garante isso.
    """
    if preco is None:
        return False
    cur.execute(
        """SELECT id, preco_venda FROM produto_precos
            WHERE id_produto = %(p)s AND vigente_ate IS NULL
              AND id_unidade IS NOT DISTINCT FROM %(u)s""",
        {"p": id_produto, "u": id_unidade},
    )
    atual = cur.fetchone()
    if atual and float(atual["preco_venda"]) == float(preco):
        return False
    if atual:
        cur.execute(
            "UPDATE produto_precos SET vigente_ate = current_date WHERE id = %s",
            (atual["id"],),
        )
    cur.execute(
        """INSERT INTO produto_precos (id_produto, id_unidade, preco_venda, criado_por)
           VALUES (%s, %s, %s, %s)""",
        (id_produto, id_unidade, preco, id_usuario),
    )
    return True
