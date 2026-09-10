"""O de-para do Omie: que produto daqui é este código de lá.

São **dois espaços de nome diferentes**, e misturá-los é o erro que este
projeto já pagou uma vez (o casamento por código de cardápio ligou REDBULL a
LIMÃO TAITY, e nenhum dos 78 vínculos criados assim estava certo):

1. `SISTEMA = "OMIE"` — o código que vem na LINHA da nota, que é o código do
   produto **no fornecedor**. É o que `vincular_item` grava quando alguém
   confirma um item pendente com "aprender".
2. `SISTEMA_PRODUTO = "OMIE_PRODUTO"` — o identificador do produto **no Omie**
   (`nCodProd`), o mesmo que mora em `produtos.codigo_omie`.
3. `SISTEMA_EAN = "EAN"` — o código de BARRAS que ficou órfão numa fusão. Não
   vem de sistema nenhum: é do fabricante. Mora aqui porque `codigos_externos`
   já é a tabela de "este código de fora também é este produto", e uma tabela
   nova diria a mesma coisa noutro lugar.

🔑 **O segundo nível nasceu de um defeito real, e é o mesmo caso do PDV.** A
fusão de dois cadastros DESCARTAVA o `codigo_omie` do absorvido — enquanto o
`codigo_pdv` virava apelido, na mesma função, com a justificativa de que senão
"ele voltaria a criar rascunho na importação seguinte". O efeito era este: a
casa juntava os cinco cadastros de ABACATE que o catálogo tinha criado (um por
fornecedor), e na primeira nota que trouxesse o código de um dos absorvidos o
sistema não achava o principal — a cascata filtra `AND ativo`, e o absorvido
está arquivado. O item caía na fila de pendentes e quem clicasse em "criar
produto" recriava o duplicado. O trabalho de juntar se desfazia sozinho.

⚠️ **`produtos.codigo_omie` continua sendo o principal** — único, visível, e o
que a cascata pergunta primeiro. Estes são os apelidos, e existem porque um
produto da casa pode ser vários produtos lá.
"""

SISTEMA = "OMIE"
SISTEMA_PRODUTO = "OMIE_PRODUTO"
SISTEMA_EAN = "EAN"


def por_codigo_omie(cur, codigo: str | None) -> int | None:
    """O produto deste identificador do Omie — pela coluna, depois pelos apelidos.

    ⚠️ A coluna primeiro, e só de produto ATIVO: cadastro desativado guarda
    saldo e razão, mas amarrar nota nova nele o ressuscitaria na compra sem
    ninguém ter decidido. O apelido não filtra por `ativo` porque ele É a
    decisão de alguém — foi gravado justamente para apontar para o principal.
    """
    if not codigo:
        return None
    cur.execute("SELECT id FROM produtos WHERE codigo_omie = %s AND ativo", (str(codigo),))
    achado = cur.fetchone()
    if achado:
        return achado["id"]
    cur.execute(
        "SELECT id_produto FROM codigos_externos WHERE sistema = %s AND codigo = %s",
        (SISTEMA_PRODUTO, str(codigo)),
    )
    achado = cur.fetchone()
    return achado["id_produto"] if achado else None


def gravar_apelido(cur, id_produto: int, codigo: str, descricao: str | None,
                   id_usuario: int | None) -> None:
    """Guarda que este identificador do Omie também é este produto.

    ⚠️ `ON CONFLICT` repõe o dono: repontar um vínculo feito no produto errado
    é a operação normal aqui, não um erro a recusar. Quem registra de onde veio
    é `origem_vinculo`, e a auditoria guarda o dono anterior.
    """
    cur.execute(
        """INSERT INTO codigos_externos (sistema, codigo, id_produto, descricao_externa,
                                         origem_vinculo, confirmado_por)
           VALUES (%s, %s, %s, %s, 'FUSAO', %s)
           ON CONFLICT (sistema, codigo) DO UPDATE
               SET id_produto = EXCLUDED.id_produto,
                   confirmado_por = EXCLUDED.confirmado_por, confirmado_em = now()""",
        (SISTEMA_PRODUTO, str(codigo)[:60], id_produto, (descricao or "")[:200] or None,
         id_usuario),
    )


def por_ean(cur, ean: str | None) -> int | None:
    """O produto deste código de barras — pela coluna, depois pelos apelidos.

    🔑 **Mesma forma do `por_codigo_omie`, e pela mesma razão.** Fundir dois
    cadastros que tinham EANs diferentes deixava o do absorvido preso a um
    cadastro arquivado: a nota seguinte com aquele código não achava ninguém, o
    item caía em pendente e quem clicasse em "criar produto" recriava o
    duplicado que a fusão tinha acabado de eliminar.

    ⚠️ A coluna só de produto ATIVO — amarrar nota nova num cadastro arquivado
    o ressuscitaria na compra sem ninguém ter decidido. O apelido não filtra
    `ativo` porque ele É a decisão de alguém: foi gravado apontando para o
    principal.
    """
    if not ean:
        return None
    cur.execute("SELECT id FROM produtos WHERE codigo_barras = %s AND ativo", (str(ean),))
    achado = cur.fetchone()
    if achado:
        return achado["id"]
    cur.execute(
        "SELECT id_produto FROM codigos_externos WHERE sistema = %s AND codigo = %s",
        (SISTEMA_EAN, str(ean)),
    )
    achado = cur.fetchone()
    return achado["id_produto"] if achado else None


def gravar_apelido_ean(cur, id_produto: int, ean: str, descricao: str | None,
                       id_usuario: int | None) -> None:
    """Guarda que este código de barras também é este produto."""
    cur.execute(
        """INSERT INTO codigos_externos (sistema, codigo, id_produto, descricao_externa,
                                         origem_vinculo, confirmado_por)
           VALUES (%s, %s, %s, %s, 'FUSAO', %s)
           ON CONFLICT (sistema, codigo) DO UPDATE
               SET id_produto = EXCLUDED.id_produto,
                   confirmado_por = EXCLUDED.confirmado_por, confirmado_em = now()""",
        (SISTEMA_EAN, str(ean)[:60], id_produto, (descricao or "")[:200] or None, id_usuario),
    )
