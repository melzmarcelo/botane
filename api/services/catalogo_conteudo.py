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


def _preco_vigente(coluna_produto: str) -> str:
    """O preço vigente pela cascata loja → casa (a do site e do feed). Pede `%(u)s`."""
    return f"""(SELECT pr.preco_venda FROM produto_precos pr
                 WHERE pr.id_produto = {coluna_produto} AND pr.vigente_ate IS NULL
                   AND (pr.id_unidade = %(u)s OR pr.id_unidade IS NULL)
                 ORDER BY pr.id_unidade NULLS LAST LIMIT 1)"""


def opcoes_de_escolha(cur, id_unidade: int, itens: list[int]) -> dict[int, list[dict]]:
    """As opções (produtos) de cada item de ESCOLHA, na ordem, com o preço vigente.

    🔑 142: o rótulo é opcional — sem ele, a opção se chama pelo nome de vitrine do produto.
    ⚠️ Volta TAMBÉM a opção inativa, marcada: o cadastro precisa vê-la para tirar; quem a
    esconde do cliente é o feed e o site.
    """
    if not itens:
        return {}
    cur.execute(
        f"""SELECT e.id_item, e.id, e.id_produto, e.rotulo, e.rotulo_en, e.rotulo_de, e.ordem,
                   p.nome AS produto, coalesce(nullif(btrim(p.nome_catalogo), ''), p.nome) AS vitrine,
                   p.nome_catalogo_en, p.nome_catalogo_de, p.ativo, p.foto_url,
                   {_preco_vigente('p.id')} AS preco
              FROM catalogo_item_escolhas e
              JOIN produtos p ON p.id = e.id_produto
             WHERE e.id_item = ANY(%(i)s)
             ORDER BY e.ordem, e.id""",  # noqa: S608 - SQL fixo
        {"u": id_unidade, "i": itens})
    saida: dict[int, list[dict]] = {}
    for r in cur.fetchall():
        d = dict(r)
        d["nome"] = (d["rotulo"] or "").strip() or d["vitrine"]
        saida.setdefault(d.pop("id_item"), []).append(d)
    return saida


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
        """SELECT id, nome, descricao, foto_url, foto_nome, ordem,
                  dias, hora_de, hora_ate, horario_especial, video_url, video_capa_url, abertura
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
        """SELECT id, id_categoria, nome, descricao, foto_url, foto_nome, ordem,
                  dias, hora_de, hora_ate, horario_especial, video_url, video_capa_url, abertura
             FROM catalogo_subcategorias
            WHERE id_categoria = ANY(%s)
            ORDER BY ordem, lower(nome)""",
        (ids,),
    )
    subs = [dict(r) for r in cur.fetchall()]

    cur.execute(
        f"""SELECT i.id, i.id_categoria, i.id_subcategoria, i.id_produto, i.ordem,
                  i.destaque, (i.esgotado AND (i.esgotado_ate IS NULL OR i.esgotado_ate > now())) AS esgotado,
                  CASE WHEN (i.esgotado AND (i.esgotado_ate IS NULL OR i.esgotado_ate > now())) THEN i.esgotado_ate END AS esgotado_ate,
                  i.objetivo, i.margem_nivel, i.tipo,
                  -- 🔑 142: o item de ESCOLHA não tem produto — nome, descrição e foto
                  -- são dele, e ele vale como ativo (quem sai de linha são as opções).
                  coalesce(p.nome, i.nome) AS produto, p.codigo,
                  coalesce(p.ativo, true) AS ativo, coalesce(i.foto_url, p.foto_url) AS foto_url,
                  coalesce(p.video_url IS NOT NULL, false) AS tem_video,
                  coalesce(p.restricoes, '{{}}') AS restricoes,
                  -- 🔑 O nome que o CLIENTE vai ler, para a tela de
                  -- configuração mostrar o que sai na vitrine — e não só o que
                  -- está no cadastro.
                  CASE WHEN i.tipo = 'ESCOLHA' THEN i.nome
                       ELSE nullif(btrim(p.nome_catalogo), '') END AS nome_catalogo,
                  coalesce(i.descricao, p.informacao_adicional) AS informacao_adicional,
                  p.um_estoque,
                  -- 🔑 O preço que o cliente vê, pela MESMA cascata do site e do
                  -- feed (loja → casa). A linha do editor mostra o prato como
                  -- ele sai, e preço errado ali é preço errado no cardápio.
                  -- O item de escolha mostra o MENOR das opções ("a partir de").
                  CASE WHEN i.tipo = 'ESCOLHA' THEN
                      (SELECT min({_preco_vigente('e.id_produto')}) FROM catalogo_item_escolhas e
                         JOIN produtos ep ON ep.id = e.id_produto AND ep.ativo
                        WHERE e.id_item = i.id)
                  ELSE {_preco_vigente('p.id')} END AS preco
             FROM catalogo_itens i
             LEFT JOIN produtos p ON p.id = i.id_produto
            WHERE i.id_categoria = ANY(%(cats)s)
            ORDER BY i.ordem, lower(coalesce(p.nome, i.nome))""",  # noqa: S608 - SQL fixo
        {"u": id_unidade, "cats": ids},
    )
    itens = [dict(r) for r in cur.fetchall()]
    escolhas = opcoes_de_escolha(cur, id_unidade, [i["id"] for i in itens if i["tipo"] == "ESCOLHA"])
    for i in itens:
        if i["tipo"] == "ESCOLHA":
            i["escolhas"] = escolhas.get(i["id"], [])

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
              SET nome = %s, descricao = %s, ordem = %s, abertura = coalesce(%s, abertura)
            WHERE id = %s
        RETURNING id, nome, descricao, foto_url, foto_nome, ordem, abertura""",
        (dados["nome"].strip(), (dados.get("descricao") or "").strip() or None,
         dados.get("ordem", 0), dados.get("abertura"), id_categoria),
    )
    return dict(cur.fetchone())


_MIDIA = "unnest(ARRAY[foto_url, video_url, video_capa_url])"


def midias_do_conteudo(cur, *, catalogo: int | None = None, categoria: int | None = None,
                       subcategoria: int | None = None) -> list[str]:
    """Toda foto e todo vídeo que saem junto quando se apaga um catálogo, uma seção ou uma
    subdivisão — a dela, a das subdivisões de baixo e a dos cartões (120) que o CASCADE leva.

    ⚠️ **Os arquivos moram no banco** (`arquivos`), e o CASCADE só apaga as linhas que
    APONTAM para eles. Até 17/10/2026 a exclusão da seção levava só a `foto_url`: o vídeo e a
    capa dela, a mídia das subdivisões e a dos cartões ficavam no banco sem dono, crescendo
    o backup sem nada à vista. Quem apaga chama `arquivos.remover` em cada uma, no MESMO cursor.
    """
    if subcategoria:
        cur.execute(f"""SELECT {_MIDIA} AS u FROM catalogo_subcategorias WHERE id = %(s)s
                        UNION ALL SELECT {_MIDIA} FROM catalogo_cartoes WHERE id_subcategoria = %(s)s""",
                    {"s": subcategoria})  # noqa: S608 - expressão constante
    elif categoria:
        cur.execute(f"""SELECT {_MIDIA} AS u FROM catalogo_categorias WHERE id = %(c)s
                        UNION ALL SELECT {_MIDIA} FROM catalogo_subcategorias WHERE id_categoria = %(c)s
                        UNION ALL SELECT {_MIDIA} FROM catalogo_cartoes WHERE id_categoria = %(c)s""",
                    {"c": categoria})  # noqa: S608
    else:
        cur.execute(f"""SELECT {_MIDIA} AS u FROM catalogo_categorias WHERE id_catalogo = %(k)s
                        UNION ALL SELECT {_MIDIA} FROM catalogo_subcategorias
                                  WHERE id_categoria IN (SELECT id FROM catalogo_categorias
                                                          WHERE id_catalogo = %(k)s)
                        UNION ALL SELECT {_MIDIA} FROM catalogo_cartoes WHERE id_catalogo = %(k)s""",
                    {"k": catalogo})  # noqa: S608
    return sorted({r["u"] for r in cur.fetchall() if r["u"]})


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
    midias = midias_do_conteudo(cur, categoria=id_categoria)
    cur.execute("DELETE FROM catalogo_categorias WHERE id = %s", (id_categoria,))
    for url in midias:
        arquivos.remover(url, cur)
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
              SET nome = %s, descricao = %s, ordem = %s, abertura = coalesce(%s, abertura)
            WHERE id = %s
        RETURNING id, id_categoria, nome, descricao, foto_url, foto_nome, ordem, abertura""",
        (dados["nome"].strip(), (dados.get("descricao") or "").strip() or None,
         dados.get("ordem", 0), dados.get("abertura"), id_sub),
    )
    return dict(cur.fetchone())


def excluir_subcategoria(cur, id_unidade: int, id_sub: int) -> dict:
    atual = _subcategoria(cur, id_unidade, id_sub)
    cur.execute("SELECT count(*) AS n FROM catalogo_itens WHERE id_subcategoria = %s",
                (id_sub,))
    itens = cur.fetchone()["n"]
    midias = midias_do_conteudo(cur, subcategoria=id_sub)
    cur.execute("DELETE FROM catalogo_subcategorias WHERE id = %s", (id_sub,))
    for url in midias:
        arquivos.remover(url, cur)
    return {"message": f'Subcategoria "{atual["nome"]}" removida.',
            "itens_removidos": itens}


# ---------------------------------------------------------------------------
# A foto das seções
# ---------------------------------------------------------------------------

_TABELA_DA_SECAO = {
    "categoria": ("catalogo_categorias", _categoria),
    "subcategoria": ("catalogo_subcategorias", _subcategoria),
    # 142: o item de ESCOLHA tem foto própria (o produto tem a dele, no cadastro).
    "item": ("catalogo_itens", lambda cur, u, i: _item_de_escolha(cur, u, i)),
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

def _produto_vendavel(cur, id_produto: int) -> dict:
    """O produto, se pode entrar no cardápio: ativo e vendido no PDV.

    ⚠️ A mesma régua para o prato e para a opção do item de escolha (142): a opção é o
    que vai no pedido, e a casa a lança no PDV.
    """
    cur.execute(
        """SELECT id, nome, ativo, integrado_pdv, codigo_pdv
             FROM produtos WHERE id = %s""",
        (id_produto,),
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
    return dict(produto)


def _lugar(cur, id_unidade: int, id_categoria: int, id_sub: int | None) -> dict:
    """A categoria (desta loja, de catálogo PRODUTOS) e a subcategoria, se for dela."""
    categoria = _categoria(cur, id_unidade, id_categoria)
    if id_sub and _subcategoria(cur, id_unidade, id_sub)["id_categoria"] != id_categoria:
        raise HTTPException(status_code=409, detail="Essa subcategoria é de outra categoria.")
    return categoria


def _fim_da_lista(cur, id_categoria: int, id_sub: int | None) -> int:
    cur.execute(
        """SELECT coalesce(max(ordem), 0) AS ultima FROM catalogo_itens
            WHERE id_categoria = %s
              AND ((%s::int IS NULL AND id_subcategoria IS NULL) OR id_subcategoria = %s)""",
        (id_categoria, id_sub, id_sub),
    )
    return min(int(cur.fetchone()["ultima"]) + 10, 999)


def _gravar_opcoes(cur, id_item: int, opcoes: list[dict]) -> None:
    """A lista INTEIRA de opções do item de escolha, na ordem em que veio."""
    if len(opcoes) < 2:
        raise HTTPException(status_code=422,
                            detail="Um item de escolha precisa de pelo menos duas opções.")
    vistos: set[int] = set()
    for o in opcoes:
        if o["id_produto"] in vistos:
            raise HTTPException(status_code=409, detail="O mesmo produto apareceu duas vezes.")
        vistos.add(o["id_produto"])
    cur.execute("SELECT id_produto FROM catalogo_item_escolhas WHERE id_item = %s", (id_item,))
    ja = {r["id_produto"] for r in cur.fetchall()}
    for o in opcoes:
        # ⚠️ Só o produto NOVO passa pela régua: a opção que já estava e saiu de linha
        # não trava a edição do resto (ela aparece marcada para a casa tirar).
        if o["id_produto"] not in ja:
            _produto_vendavel(cur, o["id_produto"])
    cur.execute("DELETE FROM catalogo_item_escolhas WHERE id_item = %s", (id_item,))
    for n, o in enumerate(opcoes):
        cur.execute(
            """INSERT INTO catalogo_item_escolhas (id_item, id_produto, rotulo, ordem)
               VALUES (%s, %s, %s, %s)""",
            (id_item, o["id_produto"], (o.get("rotulo") or "").strip()[:60] or None, (n + 1) * 10))


def criar_escolha(cur, id_unidade: int, id_categoria: int, dados: dict) -> dict:
    """Um item de ESCOLHA na seção (142): nome, descrição e as opções (produtos).

    🔑 Pedido do dono (29/10/2026): "Chocolate Quente (este não é um produto): ao
    selecionar, tem a escolha Preto ou Branco".
    """
    id_sub = dados.get("id_subcategoria")
    _lugar(cur, id_unidade, id_categoria, id_sub)
    nome = dados["nome"].strip()
    cur.execute(
        """INSERT INTO catalogo_itens (id_categoria, id_subcategoria, tipo, nome, descricao, ordem)
           VALUES (%s, %s, 'ESCOLHA', %s, %s, %s) RETURNING id""",
        (id_categoria, id_sub, nome, (dados.get("descricao") or "").strip() or None,
         _fim_da_lista(cur, id_categoria, id_sub)),
    )
    id_item = cur.fetchone()["id"]
    _gravar_opcoes(cur, id_item, dados["opcoes"])
    return {"id": id_item, "nome": nome, "message": f'"{nome}" entrou no cardápio.'}


def _item(cur, id_unidade: int, id_item: int) -> dict:
    """O item, se for desta loja. Nome do produto ou o do item de escolha."""
    cur.execute(
        """SELECT i.id, i.tipo, i.id_produto, i.id_categoria, i.id_subcategoria, i.foto_url,
                  i.nome AS nome_item, i.descricao, c.id_catalogo, coalesce(p.nome, i.nome) AS nome
             FROM catalogo_itens i
             LEFT JOIN produtos p ON p.id = i.id_produto
             JOIN catalogo_categorias c ON c.id = i.id_categoria
             JOIN catalogos k ON k.id = c.id_catalogo
            WHERE i.id = %s AND k.id_unidade = %s""",
        (id_item, id_unidade),
    )
    achado = cur.fetchone()
    if not achado:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    return dict(achado)


def _item_de_escolha(cur, id_unidade: int, id_item: int) -> dict:
    item = _item(cur, id_unidade, id_item)
    if item["tipo"] != "ESCOLHA":
        raise HTTPException(status_code=409,
                            detail=f'"{item["nome"]}" é um produto; nome e foto se mudam no cadastro dele.')
    return item


def atualizar_escolha(cur, id_unidade: int, id_item: int, dados: dict) -> dict:
    """Nome, descrição e a lista de opções do item de escolha — a lista inteira."""
    atual = _item_de_escolha(cur, id_unidade, id_item)
    nome = dados["nome"].strip()
    cur.execute("UPDATE catalogo_itens SET nome = %s, descricao = %s WHERE id = %s",
                (nome, (dados.get("descricao") or "").strip() or None, id_item))
    _gravar_opcoes(cur, id_item, dados["opcoes"])
    return {"id": id_item, "antes": {"nome": atual["nome_item"], "descricao": atual["descricao"]},
            "message": f'"{nome}" atualizado.'}


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

    produto = _produto_vendavel(cur, dados["id_produto"])

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

    # 🔑 **Produto novo entra no FIM da lista** (pedido do dono, 22/09/2026:
    # *"os novos ir adicionando no fim da lista"*). ⚠️ A ordem é de CADA lista —
    # a da subcategoria, ou a dos soltos da categoria —, porque são duas filas
    # diferentes na tela.
    # ⚠️ **O passo é 10, não 1.** Sobra espaço entre dois vizinhos para o dia em
    # que alguém quiser encaixar um no meio sem reescrever a lista inteira.
    cur.execute(
        """SELECT coalesce(max(ordem), 0) AS ultima FROM catalogo_itens
            WHERE id_categoria = %s
              AND ((%s::int IS NULL AND id_subcategoria IS NULL)
                OR id_subcategoria = %s)""",
        (id_categoria, id_sub, id_sub),
    )
    proxima = int(cur.fetchone()["ultima"]) + 10
    cur.execute(
        """INSERT INTO catalogo_itens (id_categoria, id_subcategoria, id_produto, ordem)
           VALUES (%s, %s, %s, %s) RETURNING id""",
        (id_categoria, id_sub, produto["id"], min(proxima, 999)),
    )
    return {"id": cur.fetchone()["id"], "id_produto": produto["id"],
            "produto": produto["nome"],
            "message": f'"{produto["nome"]}" entrou no cardápio.'}


def reordenar(cur, id_unidade: int, ordens: list) -> dict:
    """Grava a nova ordem de uma lista inteira, de uma vez.

    🔑 **A lista INTEIRA, não "sobe um"** (pedido do dono: *"permitir a ordenação
    deles"*). Mandar só o que se moveu deixaria o servidor adivinhando o resto, e
    dois cliques rápidos na tela chegariam fora de ordem — a segunda gravação
    partiria de um estado que a primeira já mudou.

    ⚠️ **Cada item é conferido contra a LOJA.** Sem isso, um id de outra casa
    entraria na lista e seria reordenado junto: é a mesma lição de
    `listar_fechamentos` do CMV.
    """
    if not ordens:
        return {"message": "Nada a reordenar."}
    ids = [o.id for o in ordens]
    cur.execute(
        """SELECT i.id FROM catalogo_itens i
             JOIN catalogo_categorias c ON c.id = i.id_categoria
             JOIN catalogos k ON k.id = c.id_catalogo
            WHERE i.id = ANY(%s) AND k.id_unidade = %s""",
        (ids, id_unidade),
    )
    meus = {r["id"] for r in cur.fetchall()}
    if meus != set(ids):
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    for o in ordens:
        cur.execute("UPDATE catalogo_itens SET ordem = %s WHERE id = %s", (o.ordem, o.id))
    return {"message": f"{len(ordens)} item(ns) reordenado(s)."}


def mover(cur, id_unidade: int, id_item: int, dados: dict) -> dict:
    """Leva o prato para outra seção do MESMO catálogo (reforma de 15/10/2026).

    🔑 **Mover não é tirar e pôr.** Tirar e pôr de novo era o único caminho, e
    perdia destaque, esgotado, objetivo e margem — e o lugar na fila. Aqui o item
    é o mesmo; muda a seção, e ele entra no FIM da lista nova, como quem chega.
    ⚠️ **Só dentro do mesmo catálogo**: o item pertence a um cardápio, e levá-lo
    a outro seria um vínculo novo — que é o "+ pratos" de lá.
    ⚠️ **Repetido na lista de destino é recusado com frase**, como no vincular: o
    índice único garantiria, mas não explicaria.
    """
    cur.execute(
        """SELECT i.id, i.id_produto, i.id_categoria, i.id_subcategoria, c.id_catalogo, coalesce(p.nome, i.nome) AS nome
             FROM catalogo_itens i
             LEFT JOIN produtos p ON p.id = i.id_produto
             JOIN catalogo_categorias c ON c.id = i.id_categoria
             JOIN catalogos k ON k.id = c.id_catalogo
            WHERE i.id = %s AND k.id_unidade = %s""",
        (id_item, id_unidade),
    )
    atual = cur.fetchone()
    if not atual:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    id_cat, id_sub = dados["id_categoria"], dados.get("id_subcategoria")
    destino = _categoria(cur, id_unidade, id_cat)
    if destino["id_catalogo"] != atual["id_catalogo"]:
        raise HTTPException(status_code=409,
                            detail="O prato só se move dentro do mesmo catálogo.")
    if id_sub and _subcategoria(cur, id_unidade, id_sub)["id_categoria"] != id_cat:
        raise HTTPException(status_code=409, detail="Essa subcategoria é de outra categoria.")
    if atual["id_categoria"] == id_cat and atual["id_subcategoria"] == id_sub:
        return {"id": id_item, "antes": {}, "message": f'"{atual["nome"]}" já está aí.'}

    cur.execute(
        """SELECT 1 FROM catalogo_itens
            WHERE id_produto = %s AND id <> %s
              AND ((%s::int IS NULL AND id_subcategoria IS NULL AND id_categoria = %s)
                OR (%s::int IS NOT NULL AND id_subcategoria = %s))""",
        (atual["id_produto"], id_item, id_sub, id_cat, id_sub, id_sub),
    )
    if cur.fetchone():
        raise HTTPException(status_code=409,
                            detail=f'"{atual["nome"]}" já está na lista de destino.')
    cur.execute(
        """SELECT coalesce(max(ordem), 0) AS ultima FROM catalogo_itens
            WHERE id_categoria = %s
              AND ((%s::int IS NULL AND id_subcategoria IS NULL) OR id_subcategoria = %s)""",
        (id_cat, id_sub, id_sub),
    )
    proxima = min(int(cur.fetchone()["ultima"]) + 10, 999)
    cur.execute(
        """UPDATE catalogo_itens SET id_categoria = %s, id_subcategoria = %s, ordem = %s
            WHERE id = %s""",
        (id_cat, id_sub, proxima, id_item),
    )
    return {"id": id_item,
            "antes": {"id_categoria": atual["id_categoria"],
                      "id_subcategoria": atual["id_subcategoria"]},
            "message": f'"{atual["nome"]}" mudou de seção.'}


def desvincular(cur, id_unidade: int, id_item: int) -> dict:
    cur.execute(
        """SELECT i.id, coalesce(p.nome, i.nome) AS nome
             FROM catalogo_itens i
             LEFT JOIN produtos p ON p.id = i.id_produto
             JOIN catalogo_categorias c ON c.id = i.id_categoria
             JOIN catalogos k ON k.id = c.id_catalogo
            WHERE i.id = %s AND k.id_unidade = %s""",
        (id_item, id_unidade),
    )
    achado = cur.fetchone()
    if not achado:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    cur.execute("DELETE FROM catalogo_itens WHERE id = %s RETURNING foto_url", (id_item,))
    foto = cur.fetchone()["foto_url"]
    if foto:  # a foto do item de escolha (142) sai junto
        arquivos.remover(foto, cur)
    return {"message": f'"{achado["nome"]}" saiu do cardápio.'}


# ---------------------------------------------------------------------------
# Cardápio Vivo (113): marcas do item e quando a seção aparece
# ---------------------------------------------------------------------------

def marcar_item(cur, id_unidade: int, id_item: int, dados: dict) -> dict:
    """Destaque e esgotado — decisões DESTE cardápio, por isso no item e não no produto.

    ⚠️ Esgotado revoga a decisão 6 de 28/09 ("não haverá pausa"), por pedido do dono
    em 14/10/2026: o item fica no cardápio, marcado, e não pode ser adicionado.
    🔑 **Volta sozinho** (123): `esgotado_volta = "AMANHA"` grava até as 4h do próximo dia
    da casa; `"MANUAL"` (ou nada — o conector e quem chamava antes) fica até alguém tirar.
    """
    cur.execute(
        """SELECT i.id, i.destaque, (i.esgotado AND (i.esgotado_ate IS NULL OR i.esgotado_ate > now())) AS esgotado,
                  i.esgotado_ate, i.objetivo, i.margem_nivel, coalesce(p.nome, i.nome) AS nome
             FROM catalogo_itens i
             LEFT JOIN produtos p ON p.id = i.id_produto
             JOIN catalogo_categorias c ON c.id = i.id_categoria
             JOIN catalogos k ON k.id = c.id_catalogo
            WHERE i.id = %s AND k.id_unidade = %s""",
        (id_item, id_unidade))
    atual = cur.fetchone()
    if not atual:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    destaque = atual["destaque"] if dados.get("destaque") is None else dados["destaque"]
    esgotado = atual["esgotado"] if dados.get("esgotado") is None else dados["esgotado"]
    if dados.get("esgotado") is None:
        esgotado_ate = atual["esgotado_ate"] if atual["esgotado"] else None
    elif dados["esgotado"] and dados.get("esgotado_volta") == "AMANHA":
        esgotado_ate = proxima_volta()
    else:
        esgotado_ate = None
    # Fase 2 (115): nulo = não mexe; "" = limpa (sem objetivo / nível calculado).
    objetivo = atual["objetivo"] if dados.get("objetivo") is None else (dados["objetivo"] or None)
    nivel = atual["margem_nivel"] if dados.get("margem_nivel") is None else (dados["margem_nivel"] or None)
    cur.execute("""UPDATE catalogo_itens SET destaque = %s, esgotado = %s, esgotado_ate = %s,
                          objetivo = %s, margem_nivel = %s WHERE id = %s""",
                (destaque, esgotado, esgotado_ate, objetivo, nivel, id_item))
    return {"id": id_item, "destaque": destaque, "esgotado": esgotado, "esgotado_ate": esgotado_ate,
            "objetivo": objetivo, "margem_nivel": nivel,
            "antes": {"destaque": atual["destaque"], "esgotado": atual["esgotado"],
                      "objetivo": atual["objetivo"], "margem_nivel": atual["margem_nivel"]},
            "message": f'"{atual["nome"]}": ' + ", ".join(
                [("em destaque" if destaque else "sem destaque"),
                 (("esgotado até amanhã" if esgotado_ate else "esgotado") if esgotado
                  else "disponível")]) + "."}


HORA_DA_VOLTA = 4  # ⚠️ Depois do fechamento de quem vira a noite e antes de quem abre cedo.


def proxima_volta():
    """As 4h da casa do PRÓXIMO dia de trabalho: marcado às 2h da madrugada, volta às 4h de
    hoje — a noite de ontem ainda é o mesmo turno."""
    from datetime import timedelta

    from relogio import agora_da_casa
    agora = agora_da_casa()
    volta = agora.replace(hour=HORA_DA_VOLTA, minute=0, second=0, microsecond=0)
    return volta if agora < volta else volta + timedelta(days=1)


def exibicao_da_secao(cur, id_unidade: int, tipo: str, id_secao: int, dados: dict) -> dict:
    """Dias da semana, faixa de horário e dia especial — quando a seção aparece no feed."""
    tabela, buscar = _TABELA_DA_SECAO[tipo]
    buscar(cur, id_unidade, id_secao)
    cur.execute(
        f"""UPDATE {tabela}
               SET dias = %s, hora_de = %s, hora_ate = %s, horario_especial = %s
             WHERE id = %s
         RETURNING id, dias, hora_de, hora_ate, horario_especial""",  # noqa: S608 - do mapa
        (dados.get("dias"), dados.get("hora_de"), dados.get("hora_ate"),
         bool(dados.get("horario_especial")), id_secao))
    return dict(cur.fetchone()) | {"message": "Exibição da seção gravada."}
