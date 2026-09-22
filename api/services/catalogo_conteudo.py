"""O conteúdo do catálogo de origem PRODUTOS: seções e os produtos de cada uma.

🔑 **Pedido do dono (22/09/2026):** *"vamos adicionar a Origem Produtos. Quando
for esta origem, ao listar os catálogos, ao clicar sobre vai abrir uma nova
página para configuração. Neste, podemos criar Categorias (exemplo: Menu
Principal) e suas SubCategorias (exemplo: Pra Dividir), cada item terá o Nome,
Descrição e uma foto. Após isto, podemos vincular os produtos disponíveis no PDV
para a subcategoria. Somente produtos ativos."*

⚠️ **Arquivo separado do `catalogos.py` de propósito.** Aquele é a CAPA — nome,
período, situação, o PDF. Este é o MIOLO. Juntá-los daria um serviço onde a
maior parte do código não fala da mesma coisa que o nome do arquivo promete.

🔑 **A loja é conferida em CADA função, pelo catálogo.** As seções não carregam
`id_unidade`: elas penduram no catálogo, e ele é de uma loja. Repetir a coluna
abriria a porta para as duas discordarem — o que vale é o dono.
"""

import arquivos
from fastapi import HTTPException
from models.catalogos import ORIGEM_PRODUTOS


def _catalogo_de_produtos(cur, id_unidade: int, id_catalogo: int) -> dict:
    """O catálogo, se for desta loja E se for do tipo que se monta aqui.

    ⚠️ **404 para catálogo de outra loja**, como o resto do módulo: dizer "existe,
    mas não é seu" conta ao usuário de uma loja o que a outra cadastrou.
    ⚠️ **409 para o catálogo de PDF**, não 404: ele existe e é desta casa — o que
    não existe é conteúdo montado item a item nele. A frase diz o que fazer.
    """
    cur.execute(
        "SELECT id, nome, origem, situacao FROM catalogos WHERE id = %s AND id_unidade = %s",
        (id_catalogo, id_unidade),
    )
    achado = cur.fetchone()
    if not achado:
        raise HTTPException(status_code=404, detail="Catálogo não encontrado.")
    if achado["origem"] != ORIGEM_PRODUTOS:
        raise HTTPException(
            status_code=409,
            detail=(f'O catálogo "{achado["nome"]}" é de origem {achado["origem"]}. '
                    "Só o de origem PRODUTOS se monta por categorias."),
        )
    return dict(achado)


def _recusar_nome_repetido(cur, tabela: str, coluna_pai: str, id_pai: int,
                           nome: str, id_atual: int | None, o_que: str) -> None:
    """O índice único já garante; esta função EXPLICA.

    ⚠️ **A frase cita o nome GRAVADO, não o digitado.** Quem escreveu "bebidas"
    e esbarrou em "Bebidas" precisa procurar pelo que está na tela — e é o
    gravado que está lá. Foi um defeito real no cadastro de catálogos.
    """
    cur.execute(
        f"""SELECT id, nome FROM {tabela}
             WHERE {coluna_pai} = %s AND lower(nome) = lower(%s)
               AND (%s::int IS NULL OR id <> %s)""",  # noqa: S608 - nomes fixos
        (id_pai, nome.strip(), id_atual, id_atual),
    )
    achado = cur.fetchone()
    if achado:
        raise HTTPException(
            status_code=409,
            detail=f'Já existe {o_que} chamada "{achado["nome"]}" aqui.',
        )


# ---------------------------------------------------------------------------
# Ler o catálogo inteiro
# ---------------------------------------------------------------------------

def montar(cur, id_unidade: int, id_catalogo: int) -> dict:
    """O catálogo inteiro, em árvore: categorias → subcategorias → produtos.

    🔑 **Três consultas, não uma por seção.** A tela mostra tudo de uma vez, e
    uma consulta por categoria transformaria um cardápio de dez seções em
    dezenas de idas ao banco — o problema N+1, que aparece só quando o cardápio
    cresce, ou seja, em produção.

    ⚠️ **O produto entra com o que o CLIENTE vê** — nome, foto e informação
    adicional (migração 083) —, e também com `ativo`: um produto que foi
    desativado depois de entrar no cardápio precisa aparecer na tela de
    configuração MARCADO, senão a casa não descobre que publicou algo que saiu
    de linha. O site é quem o esconde.
    """
    _catalogo_de_produtos(cur, id_unidade, id_catalogo)

    cur.execute(
        """SELECT id, nome, descricao, foto_url, foto_nome, ordem
             FROM catalogo_categorias
            WHERE id_catalogo = %s
            ORDER BY ordem, lower(nome)""",
        (id_catalogo,),
    )
    categorias = [dict(r) for r in cur.fetchall()]
    if not categorias:
        return {"id_catalogo": id_catalogo, "categorias": []}

    ids = [c["id"] for c in categorias]
    cur.execute(
        """SELECT id, id_categoria, nome, descricao, foto_url, foto_nome, ordem
             FROM catalogo_subcategorias
            WHERE id_categoria = ANY(%s)
            ORDER BY ordem, lower(nome)""",
        (ids,),
    )
    subs = [dict(r) for r in cur.fetchall()]

    cur.execute(
        """SELECT i.id, i.id_categoria, i.id_subcategoria, i.id_produto, i.ordem,
                  p.nome AS produto, p.codigo, p.ativo, p.foto_url,
                  p.informacao_adicional, p.um_estoque
             FROM catalogo_itens i
             JOIN produtos p ON p.id = i.id_produto
            WHERE i.id_categoria = ANY(%s)
            ORDER BY i.ordem, lower(p.nome)""",
        (ids,),
    )
    itens = [dict(r) for r in cur.fetchall()]

    por_sub: dict[int, list] = {}
    soltos: dict[int, list] = {}
    for i in itens:
        if i["id_subcategoria"]:
            por_sub.setdefault(i["id_subcategoria"], []).append(i)
        else:
            soltos.setdefault(i["id_categoria"], []).append(i)

    subs_por_categoria: dict[int, list] = {}
    for sc in subs:
        sc["itens"] = por_sub.get(sc["id"], [])
        subs_por_categoria.setdefault(sc["id_categoria"], []).append(sc)

    for c in categorias:
        c["subcategorias"] = subs_por_categoria.get(c["id"], [])
        # 🔑 Os produtos pendurados DIRETO na categoria, sem subcategoria.
        c["itens"] = soltos.get(c["id"], [])

    return {"id_catalogo": id_catalogo, "categorias": categorias}


def produtos_disponiveis(cur, busca: str | None = None, limite: int = 50) -> list[dict]:
    """Os produtos que podem entrar no cardápio.

    🔑 **"Disponíveis no PDV" e "somente ativos"**, nas palavras do dono.
    ⚠️ **Vai ao PDV NÃO é só `integrado_pdv`.** Aquela marca é sobre ESCRITA —
    se o Botané deve criar ou atualizar o produto lá. Com `codigo_pdv`
    preenchido e a marca desligada existe um estado legítimo e comum: *veio do
    PDV e a casa não quer que o Botané mexa*, e esse produto é vendido no balcão
    todo dia. Filtrar só pela marca esconderia justamente o que a casa mais
    vende. É a mesma regra da aba Catálogo do produto (migração 083).
    """
    onde = ["p.ativo", "(p.integrado_pdv OR p.codigo_pdv IS NOT NULL)"]
    valores: list = []
    if busca and busca.strip():
        onde.append("(p.nome ILIKE %s OR p.codigo ILIKE %s)")
        alvo = f"%{busca.strip()}%"
        valores += [alvo, alvo]
    valores.append(limite)
    cur.execute(
        f"""SELECT p.id, p.codigo, p.nome, p.um_estoque, p.foto_url,
                   p.informacao_adicional
              FROM produtos p
             WHERE {' AND '.join(onde)}
             ORDER BY lower(p.nome)
             LIMIT %s""",  # noqa: S608 - a lista de condições é fixa no código
        valores,
    )
    return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Categorias
# ---------------------------------------------------------------------------

def criar_categoria(cur, id_unidade: int, id_catalogo: int, dados: dict) -> dict:
    _catalogo_de_produtos(cur, id_unidade, id_catalogo)
    _recusar_nome_repetido(cur, "catalogo_categorias", "id_catalogo", id_catalogo,
                           dados["nome"], None, "uma categoria")
    cur.execute(
        """INSERT INTO catalogo_categorias (id_catalogo, nome, descricao, ordem)
           VALUES (%s, %s, %s, %s)
           RETURNING id, nome, descricao, foto_url, foto_nome, ordem""",
        (id_catalogo, dados["nome"].strip(),
         (dados.get("descricao") or "").strip() or None, dados.get("ordem", 0)),
    )
    nova = dict(cur.fetchone())
    nova["subcategorias"] = []
    nova["itens"] = []
    return nova


def _categoria(cur, id_unidade: int, id_categoria: int) -> dict:
    cur.execute(
        """SELECT c.id, c.id_catalogo, c.nome, c.foto_url
             FROM catalogo_categorias c
             JOIN catalogos k ON k.id = c.id_catalogo
            WHERE c.id = %s AND k.id_unidade = %s""",
        (id_categoria, id_unidade),
    )
    achada = cur.fetchone()
    if not achada:
        raise HTTPException(status_code=404, detail="Categoria não encontrada.")
    return dict(achada)


def atualizar_categoria(cur, id_unidade: int, id_categoria: int, dados: dict) -> dict:
    atual = _categoria(cur, id_unidade, id_categoria)
    _recusar_nome_repetido(cur, "catalogo_categorias", "id_catalogo",
                           atual["id_catalogo"], dados["nome"], id_categoria,
                           "uma categoria")
    cur.execute(
        """UPDATE catalogo_categorias
              SET nome = %s, descricao = %s, ordem = %s
            WHERE id = %s
        RETURNING id, nome, descricao, foto_url, foto_nome, ordem""",
        (dados["nome"].strip(), (dados.get("descricao") or "").strip() or None,
         dados.get("ordem", 0), id_categoria),
    )
    return dict(cur.fetchone())


def excluir_categoria(cur, id_unidade: int, id_categoria: int) -> dict:
    """Apaga a categoria — e, com ela, subcategorias e vínculos.

    ⚠️ **O CASCADE é do banco** (migração 084), e é o certo: os vínculos não são
    histórico, são arrumação de cardápio. ⚠️ Mas a TELA precisa avisar quantos
    produtos saem junto — apagar "Menu Principal" com trinta itens dentro não
    pode ser um clique sem aviso. Por isso a contagem sai daqui.
    """
    atual = _categoria(cur, id_unidade, id_categoria)
    cur.execute("SELECT count(*) AS n FROM catalogo_itens WHERE id_categoria = %s",
                (id_categoria,))
    itens = cur.fetchone()["n"]
    arquivos.remover(atual.get("foto_url"), cur)
    cur.execute("DELETE FROM catalogo_categorias WHERE id = %s", (id_categoria,))
    return {"message": f'Categoria "{atual["nome"]}" removida.', "itens_removidos": itens}


# ---------------------------------------------------------------------------
# Subcategorias
# ---------------------------------------------------------------------------

def criar_subcategoria(cur, id_unidade: int, id_categoria: int, dados: dict) -> dict:
    _categoria(cur, id_unidade, id_categoria)
    _recusar_nome_repetido(cur, "catalogo_subcategorias", "id_categoria", id_categoria,
                           dados["nome"], None, "uma subcategoria")
    cur.execute(
        """INSERT INTO catalogo_subcategorias (id_categoria, nome, descricao, ordem)
           VALUES (%s, %s, %s, %s)
           RETURNING id, id_categoria, nome, descricao, foto_url, foto_nome, ordem""",
        (id_categoria, dados["nome"].strip(),
         (dados.get("descricao") or "").strip() or None, dados.get("ordem", 0)),
    )
    nova = dict(cur.fetchone())
    nova["itens"] = []
    return nova


def _subcategoria(cur, id_unidade: int, id_sub: int) -> dict:
    cur.execute(
        """SELECT s.id, s.id_categoria, s.nome, s.foto_url
             FROM catalogo_subcategorias s
             JOIN catalogo_categorias c ON c.id = s.id_categoria
             JOIN catalogos k ON k.id = c.id_catalogo
            WHERE s.id = %s AND k.id_unidade = %s""",
        (id_sub, id_unidade),
    )
    achada = cur.fetchone()
    if not achada:
        raise HTTPException(status_code=404, detail="Subcategoria não encontrada.")
    return dict(achada)


def atualizar_subcategoria(cur, id_unidade: int, id_sub: int, dados: dict) -> dict:
    atual = _subcategoria(cur, id_unidade, id_sub)
    _recusar_nome_repetido(cur, "catalogo_subcategorias", "id_categoria",
                           atual["id_categoria"], dados["nome"], id_sub,
                           "uma subcategoria")
    cur.execute(
        """UPDATE catalogo_subcategorias
              SET nome = %s, descricao = %s, ordem = %s
            WHERE id = %s
        RETURNING id, id_categoria, nome, descricao, foto_url, foto_nome, ordem""",
        (dados["nome"].strip(), (dados.get("descricao") or "").strip() or None,
         dados.get("ordem", 0), id_sub),
    )
    return dict(cur.fetchone())


def excluir_subcategoria(cur, id_unidade: int, id_sub: int) -> dict:
    atual = _subcategoria(cur, id_unidade, id_sub)
    cur.execute("SELECT count(*) AS n FROM catalogo_itens WHERE id_subcategoria = %s",
                (id_sub,))
    itens = cur.fetchone()["n"]
    arquivos.remover(atual.get("foto_url"), cur)
    cur.execute("DELETE FROM catalogo_subcategorias WHERE id = %s", (id_sub,))
    return {"message": f'Subcategoria "{atual["nome"]}" removida.',
            "itens_removidos": itens}


# ---------------------------------------------------------------------------
# A foto das seções
# ---------------------------------------------------------------------------

_TABELA_DA_SECAO = {
    "categoria": ("catalogo_categorias", _categoria),
    "subcategoria": ("catalogo_subcategorias", _subcategoria),
}


def guardar_foto(cur, id_unidade: int, tipo: str, id_secao: int, conteudo: bytes,
                 mime: str, extensao: str, nome_original: str | None) -> dict:
    """Guarda a foto da seção e aponta para ela. Tudo numa transação.

    ⚠️ **Gravar a nova, apontar e apagar a velha são UMA coisa só** — é a lição
    que a logo pagou: gravar numa transação e apagar noutra deixa, num erro no
    meio, o registro apontando para um arquivo que já não existe.
    """
    tabela, buscar = _TABELA_DA_SECAO[tipo]
    atual = buscar(cur, id_unidade, id_secao)
    antiga = atual.get("foto_url")
    url = arquivos.gravar(cur, conteudo, mime, extensao, f"{tipo}-{id_secao}")
    cur.execute(
        f"""UPDATE {tabela}
               SET foto_url = %s, foto_nome = %s, foto_bytes = %s, foto_em = now()
             WHERE id = %s""",  # noqa: S608 - a tabela sai do mapa acima
        (url, (nome_original or "").strip()[:255] or None, len(conteudo), id_secao),
    )
    if antiga and antiga != url:
        arquivos.remover(antiga, cur)
    return {"foto_url": url, "foto_nome": nome_original, "foto_bytes": len(conteudo)}


def remover_foto(cur, id_unidade: int, tipo: str, id_secao: int) -> dict:
    tabela, buscar = _TABELA_DA_SECAO[tipo]
    atual = buscar(cur, id_unidade, id_secao)
    antiga = atual.get("foto_url")
    cur.execute(
        f"""UPDATE {tabela}
               SET foto_url = NULL, foto_nome = NULL, foto_bytes = NULL, foto_em = NULL
             WHERE id = %s""",  # noqa: S608 - a tabela sai do mapa acima
        (id_secao,),
    )
    if antiga:
        arquivos.remover(antiga, cur)
    return {"foto_url": None}


# ---------------------------------------------------------------------------
# Os produtos do cardápio
# ---------------------------------------------------------------------------

def vincular(cur, id_unidade: int, id_categoria: int, dados: dict) -> dict:
    """Pendura um produto na categoria — ou na subcategoria dela.

    ⚠️ **Só produto ATIVO e que vai ao PDV**, como o dono pediu. A recusa é
    aqui, não só na tela: a lista da tela é um conforto; quem garante é o
    servidor, que é a regra 4 da casa.
    ⚠️ **Repetido na MESMA lista é recusado com frase**; o índice único da 084
    já garantiria, e o que ele não faz é explicar.
    """
    _categoria(cur, id_unidade, id_categoria)
    id_sub = dados.get("id_subcategoria")
    if id_sub:
        sub = _subcategoria(cur, id_unidade, id_sub)
        if sub["id_categoria"] != id_categoria:
            raise HTTPException(
                status_code=409,
                detail="Essa subcategoria é de outra categoria.")

    cur.execute(
        """SELECT id, nome, ativo, integrado_pdv, codigo_pdv
             FROM produtos WHERE id = %s""",
        (dados["id_produto"],),
    )
    produto = cur.fetchone()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    if not produto["ativo"]:
        raise HTTPException(
            status_code=409,
            detail=f'"{produto["nome"]}" está inativo e não entra no cardápio.')
    if not (produto["integrado_pdv"] or produto["codigo_pdv"]):
        raise HTTPException(
            status_code=409,
            detail=(f'"{produto["nome"]}" não é vendido no PDV. O cardápio do site '
                    "mostra só o que está no balcão."))

    cur.execute(
        """SELECT 1 FROM catalogo_itens
            WHERE id_produto = %s
              AND ((%s::int IS NULL AND id_subcategoria IS NULL AND id_categoria = %s)
                OR (%s::int IS NOT NULL AND id_subcategoria = %s))""",
        (produto["id"], id_sub, id_categoria, id_sub, id_sub),
    )
    if cur.fetchone():
        raise HTTPException(
            status_code=409,
            detail=f'"{produto["nome"]}" já está nesta lista.')

    cur.execute(
        """INSERT INTO catalogo_itens (id_categoria, id_subcategoria, id_produto, ordem)
           VALUES (%s, %s, %s, %s) RETURNING id""",
        (id_categoria, id_sub, produto["id"], dados.get("ordem", 0)),
    )
    return {"id": cur.fetchone()["id"], "id_produto": produto["id"],
            "produto": produto["nome"],
            "message": f'"{produto["nome"]}" entrou no cardápio.'}


def desvincular(cur, id_unidade: int, id_item: int) -> dict:
    cur.execute(
        """SELECT i.id, p.nome
             FROM catalogo_itens i
             JOIN produtos p ON p.id = i.id_produto
             JOIN catalogo_categorias c ON c.id = i.id_categoria
             JOIN catalogos k ON k.id = c.id_catalogo
            WHERE i.id = %s AND k.id_unidade = %s""",
        (id_item, id_unidade),
    )
    achado = cur.fetchone()
    if not achado:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    cur.execute("DELETE FROM catalogo_itens WHERE id = %s", (id_item,))
    return {"message": f'"{achado["nome"]}" saiu do cardápio.'}
