"""Onde mora o vínculo entre o item do PDV e o produto daqui.

Em dois níveis, e a ordem é a regra:

1. **`produtos.codigo_pdv`** — o código PRINCIPAL, visível e editável na tela do
   produto, espelho exato do `codigo_omie`. Com os dois preenchidos, o cadastro
   é o mesmo produto nas duas integrações, e isso se lê sem abrir o banco.
2. **`codigos_externos` com `sistema = 'PDV_LEGAL'`** — os APELIDOS.

⚠️ **O segundo nível não é sobra de projeto antigo: o caso é real.** Na conta do
cliente, "ENTREGA" tem QUATRO códigos de cardápio distintos apontando para a
mesma coisa. Guardar só um faria os outros três virarem rascunho na importação
seguinte — o duplicado renascendo sozinho, e sem ninguém ter feito nada.

⚠️ **Nada aqui adivinha.** Este arquivo responde "que produto tem este código",
e a resposta é sim ou não. Casar por nome parecido era o que existia antes, e
custava caro nos dois sentidos: não achava "BEB CERV HEINEKEN 350ML" contra
"CERVEJA HEINEKEN PILSEN" (63,8% de semelhança, o mesmo produto) e juntava
"CAKE BOARD N19" com "CAKE BOARD N21", que são tamanhos diferentes. Quem
reconhece produto é gente; o sistema guarda o que ela disse.
"""

SISTEMA = "PDV_LEGAL"


def por_codigo(cur, codigo: str) -> int | None:
    """O produto deste código do PDV — pela coluna, depois pelos apelidos."""
    if not codigo:
        return None
    cur.execute("SELECT id FROM produtos WHERE codigo_pdv = %s", (str(codigo),))
    achado = cur.fetchone()
    if achado:
        return achado["id"]
    cur.execute(
        "SELECT id_produto FROM codigos_externos WHERE sistema = %s AND codigo = %s",
        (SISTEMA, str(codigo)),
    )
    achado = cur.fetchone()
    return achado["id_produto"] if achado else None


def de_para(cur) -> dict[str, int]:
    """Todos os códigos do PDV → produto, de uma vez só.

    ⚠️ Uma consulta, não uma por item: um dia de 48 cupons tem ~100 linhas, e o
    de-para inteiro de um cardápio cabe folgado na memória.

    ⚠️ **A coluna sobrescreve o apelido**, e não o contrário: se um código estiver
    nos dois lugares apontando para produtos diferentes, o principal é o que a
    tela mostra — e o que a tela mostra tem de ser o que o sistema usa.
    """
    cur.execute(
        "SELECT codigo, id_produto FROM codigos_externos WHERE sistema = %s", (SISTEMA,)
    )
    mapa = {str(r["codigo"]): r["id_produto"] for r in cur.fetchall()}
    cur.execute("SELECT codigo_pdv, id FROM produtos WHERE codigo_pdv IS NOT NULL")
    mapa.update({str(r["codigo_pdv"]): r["id"] for r in cur.fetchall()})
    return mapa


def gravar(cur, id_produto: int, codigo: str, descricao: str | None = None,
           id_usuario: int | None = None) -> str:
    """Liga este código a este produto. Devolve "principal" ou "apelido".

    ⚠️ **O primeiro código de um produto vai para a COLUNA; os seguintes viram
    apelido.** Sobrescrever a coluna faria o vínculo principal trocar sozinho a
    cada importação, e o campo que a tela mostra mudaria sem ninguém mexer nele.

    ⚠️ O código já usado por OUTRO produto não é movido aqui — isso é decisão de
    quem enxerga os dois cadastros, e o caminho é o botão Vincular.
    """
    codigo = str(codigo)
    dono = por_codigo(cur, codigo)
    if dono is not None and dono != id_produto:
        return "de_outro"

    cur.execute("SELECT codigo_pdv FROM produtos WHERE id = %s", (id_produto,))
    linha = cur.fetchone()
    if linha and not linha["codigo_pdv"]:
        cur.execute("UPDATE produtos SET codigo_pdv = %s WHERE id = %s", (codigo, id_produto))
        # ⚠️ Se este código estava como apelido, sai de lá: dois lugares com o
        # mesmo fato divergem no primeiro que alguém editar.
        cur.execute(
            "DELETE FROM codigos_externos WHERE sistema = %s AND codigo = %s", (SISTEMA, codigo)
        )
        return "principal"

    if linha and linha["codigo_pdv"] == codigo:
        return "principal"

    cur.execute(
        """INSERT INTO codigos_externos (sistema, codigo, id_produto, descricao_externa,
                                         origem_vinculo, confirmado_por)
           VALUES (%s, %s, %s, %s, 'APELIDO', %s)
           ON CONFLICT (sistema, codigo) DO UPDATE
               SET id_produto = EXCLUDED.id_produto,
                   descricao_externa = EXCLUDED.descricao_externa""",
        (SISTEMA, codigo, id_produto, descricao, id_usuario),
    )
    return "apelido"


def codigos_de(cur, id_produto: int) -> dict:
    """O principal e os apelidos de um produto — é o que a tela mostra."""
    cur.execute("SELECT codigo_pdv FROM produtos WHERE id = %s", (id_produto,))
    linha = cur.fetchone()
    cur.execute(
        """SELECT codigo FROM codigos_externos
            WHERE sistema = %s AND id_produto = %s ORDER BY codigo""",
        (SISTEMA, id_produto),
    )
    apelidos = [r["codigo"] for r in cur.fetchall()]
    return {"codigo_pdv": (linha or {}).get("codigo_pdv"), "apelidos_pdv": apelidos}
