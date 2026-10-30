"""Os cartões de conteúdo do Cardápio Vivo (120) e o vídeo da abertura de seção.

🔑 **Pedido do dono (16/10/2026):** *"colocar algo entre os pratos que vai além de pratos — um
cardápio de massas, e antes postar um vídeo, texto ou foto com uma introdução, bem como seções
entre os pratos"*. Decisões dele: a abertura de seção é AUTOMÁTICA (foto e descrição que a
seção já tem, ou o vídeo dela), o vídeo é SUBIDO no sistema e os cartões ficam SÓ no feed.

🔑 **Onde o cartão fica**: `id_categoria` nulo = abertura do cardápio; senão, na lista da seção
(ou da subdivisão), ANTES do prato `antes_do_item` — ou no fim dela, sem prato. Colado no prato,
o cartão acompanha a reordenação (setas, vencedor do A/B) sem ninguém mexer nele.
⚠️ A loja é conferida pelo catálogo em toda função, como em `catalogo_conteudo`.
"""

from datetime import timedelta

import arquivos
from fastapi import HTTPException
from services import catalogo_conteudo, traducao

# Um cartão a cada QUATRO pratos é o teto recomendado ao dono: mais que isso vira propaganda,
# e quem está na mesa quer achar o prato. A tela avisa; o servidor não proíbe.
PRATOS_POR_CARTAO = 4

_COLUNAS = """k.id, k.id_catalogo, k.id_categoria, k.id_subcategoria, k.antes_do_item,
              k.titulo, k.texto, k.foto_url, k.video_url, k.video_capa_url, k.video_segundos,
              k.id_item_link, k.ativo, k.criado_em"""


def _cartao(cur, id_unidade: int, id_cartao: int) -> dict:
    cur.execute(f"""SELECT {_COLUNAS} FROM catalogo_cartoes k
                      JOIN catalogos c ON c.id = k.id_catalogo
                     WHERE k.id = %s AND c.id_unidade = %s""", (id_cartao, id_unidade))  # noqa: S608
    achado = cur.fetchone()
    if not achado:
        raise HTTPException(status_code=404, detail="Cartão não encontrado.")
    return dict(achado)


def _conferir_lugar(cur, id_catalogo: int, dados: dict) -> None:
    """A seção, a subdivisão, o prato da posição e o do botão — todos DESTE catálogo."""
    cat, sub = dados.get("id_categoria"), dados.get("id_subcategoria")
    if sub and not cat:
        raise HTTPException(status_code=422, detail="A subdivisão precisa da seção dela.")
    if cat:
        cur.execute("SELECT 1 FROM catalogo_categorias WHERE id = %s AND id_catalogo = %s",
                    (cat, id_catalogo))
        if not cur.fetchone():
            raise HTTPException(status_code=422, detail="A seção não é deste cardápio.")
    if sub:
        cur.execute("SELECT 1 FROM catalogo_subcategorias WHERE id = %s AND id_categoria = %s",
                    (sub, cat))
        if not cur.fetchone():
            raise HTTPException(status_code=422, detail="A subdivisão não é desta seção.")
    antes = dados.get("antes_do_item")
    if antes:
        if not cat:
            raise HTTPException(status_code=422,
                                detail="A abertura do cardápio vem antes de tudo — não antes de um prato.")
        # ⚠️ O prato da posição é da MESMA lista: "antes do Ravióli" numa seção onde ele não
        # está seria um cartão que nunca aparece onde a casa pôs.
        cur.execute("""SELECT 1 FROM catalogo_itens WHERE id = %s AND id_categoria = %s
                          AND id_subcategoria IS NOT DISTINCT FROM %s""", (antes, cat, sub))
        if not cur.fetchone():
            raise HTTPException(status_code=422, detail="O prato da posição não está nesta lista.")
    link = dados.get("id_item_link")
    if link:
        cur.execute("""SELECT 1 FROM catalogo_itens i JOIN catalogo_categorias g ON g.id = i.id_categoria
                        WHERE i.id = %s AND g.id_catalogo = %s""", (link, id_catalogo))
        if not cur.fetchone():
            raise HTTPException(status_code=422, detail="O prato do botão não é deste cardápio.")


def _texto(v: str | None) -> str | None:
    return (v or "").strip() or None


PERIODOS = (30, 90, 365)


def listar(cur, id_unidade: int, id_catalogo: int, dias: int = 30) -> dict:
    """Os cartões do catálogo, com quantas vezes cada um foi visto nos últimos `dias`.

    🔑 **A atenção vem junto** (pedido do dono: saber se o vídeo de abertura prende ou se o
    cliente passa direto): vistas, segundos em média e cliques no "Ver o prato".
    🔑 **O período passa da retenção** (1.1.111): os dias que o bruto já não tem saem do resumo
    do dia (124), como no relatório do anúncio. Aqui não há pessoas — só vistas e cliques, que
    somam igual dos dois lados.
    """
    if dias not in PERIODOS:
        raise HTTPException(status_code=422, detail="O período é de 30, 90 ou 365 dias.")
    catalogo_conteudo._catalogo_de_produtos(cur, id_unidade, id_catalogo)
    janela = "AND e.quando >= current_date - %(dias)s::int"
    p = {"u": id_unidade, "c": id_catalogo, "dias": dias}
    cur.execute(
        f"""SELECT {_COLUNAS},
                   count(e.id) FILTER (WHERE e.tipo = 'viu_cartao') AS vistas,
                   coalesce(sum(e.duracao_ms) FILTER (WHERE e.tipo = 'viu_cartao'), 0) AS soma_ms,
                   count(e.id) FILTER (WHERE e.tipo = 'clicou_cartao') AS cliques
              FROM catalogo_cartoes k
              LEFT JOIN cardapio_eventos e ON e.id_cartao = k.id AND e.id_unidade = %(u)s {janela}
             WHERE k.id_catalogo = %(c)s
             GROUP BY k.id
             ORDER BY k.id""",  # noqa: S608
        p)
    cartoes = [dict(r) for r in cur.fetchall()]
    # A abertura AUTOMÁTICA das seções também é medida (`viu_secao`).
    cur.execute(
        f"""SELECT e.id_categoria, e.id_subcategoria, count(*) AS vistas,
                   coalesce(sum(e.duracao_ms), 0) AS soma_ms
              FROM cardapio_eventos e
             WHERE e.tipo = 'viu_secao' AND e.id_unidade = %(u)s {janela}
               AND e.id_categoria IN (SELECT id FROM catalogo_categorias WHERE id_catalogo = %(c)s)
             GROUP BY 1, 2""",  # noqa: S608
        p)
    secoes = [dict(r) for r in cur.fetchall()]
    resumido = _somar_resumo(cur, id_unidade, id_catalogo, dias, cartoes, secoes)
    for linha in cartoes + secoes:
        soma = linha.pop("soma_ms")
        linha["segundos"] = round(float(soma) / 1000 / linha["vistas"], 1) if linha["vistas"] else None
    return {"cartoes": cartoes, "aberturas": secoes, "pratos_por_cartao": PRATOS_POR_CARTAO,
            "dias": dias, "resumido": resumido}


def _somar_resumo(cur, id_unidade: int, id_catalogo: int, dias: int,
                  cartoes: list[dict], secoes: list[dict]) -> dict | None:
    """Os dias do período antes do primeiro evento bruto da loja, lidos do resumo (124)."""
    cur.execute("""SELECT current_date - %s::int AS de, current_date AS hoje,
                          (SELECT min(quando)::date FROM cardapio_eventos WHERE id_unidade = %s) AS desde""",
                (dias, id_unidade))
    r = cur.fetchone()
    corte = min(r["desde"], r["hoje"] + timedelta(days=1)) if r["desde"] else r["hoje"] + timedelta(days=1)
    if r["de"] >= corte:
        return None
    cur.execute(
        """SELECT d.tipo, d.id_ref, d.id_sub, count(DISTINCT d.dia) AS dias,
                  sum(d.vistas) AS vistas, sum(d.soma_ms) AS soma_ms, sum(d.cliques) AS cliques
             FROM cardapio_conteudo_dia d
            WHERE d.id_unidade = %(u)s AND d.dia >= %(de)s AND d.dia < %(corte)s
              AND ((d.tipo = 'CARTAO' AND d.id_ref IN (SELECT id FROM catalogo_cartoes WHERE id_catalogo = %(c)s))
                OR (d.tipo = 'SECAO' AND d.id_ref IN (SELECT id FROM catalogo_categorias WHERE id_catalogo = %(c)s)))
            GROUP BY 1, 2, 3""",
        {"u": id_unidade, "de": r["de"], "corte": corte, "c": id_catalogo})
    linhas = cur.fetchall()
    if not linhas:
        return None
    por_cartao = {k["id"]: k for k in cartoes}
    for d in linhas:
        if d["tipo"] == "CARTAO":
            alvo = por_cartao.get(d["id_ref"])
            if alvo is None:
                continue
            alvo["cliques"] += d["cliques"]
        else:
            sub = d["id_sub"] or None
            alvo = next((s for s in secoes if s["id_categoria"] == d["id_ref"] and s["id_subcategoria"] == sub), None)
            if alvo is None:
                alvo = {"id_categoria": d["id_ref"], "id_subcategoria": sub, "vistas": 0, "soma_ms": 0}
                secoes.append(alvo)
        alvo["vistas"] += d["vistas"]
        alvo["soma_ms"] += d["soma_ms"]
    ate = corte - timedelta(days=1)
    return {"ate": ate, "aviso": "Os dias até {} vêm do resumo diário.".format(ate.strftime("%d/%m/%Y"))}


def criar(cur, id_unidade: int, id_catalogo: int, dados: dict, id_usuario: int | None) -> dict:
    catalogo_conteudo._catalogo_de_produtos(cur, id_unidade, id_catalogo)
    _conferir_lugar(cur, id_catalogo, dados)
    cur.execute(
        """INSERT INTO catalogo_cartoes (id_catalogo, id_categoria, id_subcategoria, antes_do_item,
                                         titulo, texto, id_item_link, ativo, criado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (id_catalogo, dados.get("id_categoria"), dados.get("id_subcategoria"),
         dados.get("antes_do_item"), _texto(dados.get("titulo")), _texto(dados.get("texto")),
         dados.get("id_item_link"), dados.get("ativo", True), id_usuario))
    novo = cur.fetchone()["id"]
    traducao.tentar(cur, "cartao", novo)
    return _cartao(cur, id_unidade, novo)


def atualizar(cur, id_unidade: int, id_cartao: int, dados: dict) -> dict:
    atual = _cartao(cur, id_unidade, id_cartao)
    _conferir_lugar(cur, atual["id_catalogo"], dados)
    cur.execute(
        """UPDATE catalogo_cartoes
              SET id_categoria = %s, id_subcategoria = %s, antes_do_item = %s, titulo = %s,
                  texto = %s, id_item_link = %s, ativo = %s
            WHERE id = %s""",
        (dados.get("id_categoria"), dados.get("id_subcategoria"), dados.get("antes_do_item"),
         _texto(dados.get("titulo")), _texto(dados.get("texto")), dados.get("id_item_link"),
         dados.get("ativo", True), id_cartao))
    traducao.tentar(cur, "cartao", id_cartao)
    return _cartao(cur, id_unidade, id_cartao)


def remover(cur, id_unidade: int, id_cartao: int) -> dict:
    atual = _cartao(cur, id_unidade, id_cartao)
    for velho in (atual["foto_url"], atual["video_url"], atual["video_capa_url"]):
        arquivos.remover(velho, cur)
    cur.execute("DELETE FROM catalogo_cartoes WHERE id = %s", (id_cartao,))
    return {"message": "Cartão removido."}


# ---------------------------------------------------------------------------
# A mídia do cartão — UMA de cada vez: foto OU vídeo
# ---------------------------------------------------------------------------

def guardar_foto(cur, id_unidade: int, id_cartao: int, conteudo: bytes, mime: str,
                 extensao: str) -> dict:
    """A foto troca o vídeo: o cartão mostra uma mídia só, e a escolhida é a última enviada."""
    atual = _cartao(cur, id_unidade, id_cartao)
    url = arquivos.gravar(cur, conteudo, mime, extensao, f"cartao-{id_cartao}")
    cur.execute("""UPDATE catalogo_cartoes SET foto_url = %s, video_url = NULL, video_capa_url = NULL,
                          video_segundos = NULL WHERE id = %s""", (url, id_cartao))
    for velho in (atual["foto_url"], atual["video_url"], atual["video_capa_url"]):
        if velho and velho != url:
            arquivos.remover(velho, cur)
    return _cartao(cur, id_unidade, id_cartao)


def guardar_video(cur, id_unidade: int, id_cartao: int, mp4: bytes, capa: bytes,
                  segundos: float) -> dict:
    atual = _cartao(cur, id_unidade, id_cartao)
    url = arquivos.gravar(cur, mp4, arquivos.VIDEO_TIPO, ".mp4", f"cartao-video-{id_cartao}")
    url_capa = arquivos.gravar(cur, capa, "image/webp", ".webp", f"cartao-capa-{id_cartao}")
    cur.execute("""UPDATE catalogo_cartoes SET video_url = %s, video_capa_url = %s,
                          video_segundos = %s, foto_url = NULL WHERE id = %s""",
                (url, url_capa, segundos, id_cartao))
    for velho in (atual["foto_url"], atual["video_url"], atual["video_capa_url"]):
        if velho:
            arquivos.remover(velho, cur)
    return _cartao(cur, id_unidade, id_cartao)


def remover_midia(cur, id_unidade: int, id_cartao: int) -> dict:
    atual = _cartao(cur, id_unidade, id_cartao)
    cur.execute("""UPDATE catalogo_cartoes SET foto_url = NULL, video_url = NULL,
                          video_capa_url = NULL, video_segundos = NULL WHERE id = %s""", (id_cartao,))
    for velho in (atual["foto_url"], atual["video_url"], atual["video_capa_url"]):
        if velho:
            arquivos.remover(velho, cur)
    return _cartao(cur, id_unidade, id_cartao)


# ---------------------------------------------------------------------------
# O vídeo da abertura de seção
# ---------------------------------------------------------------------------

def guardar_video_secao(cur, id_unidade: int, tipo: str, id_secao: int, mp4: bytes,
                        capa: bytes) -> dict:
    tabela, buscar = catalogo_conteudo._TABELA_DA_SECAO[tipo]
    buscar(cur, id_unidade, id_secao)
    cur.execute(f"SELECT video_url, video_capa_url FROM {tabela} WHERE id = %s", (id_secao,))  # noqa: S608
    antes = dict(cur.fetchone())
    url = arquivos.gravar(cur, mp4, arquivos.VIDEO_TIPO, ".mp4", f"{tipo}-video-{id_secao}")
    url_capa = arquivos.gravar(cur, capa, "image/webp", ".webp", f"{tipo}-capa-{id_secao}")
    cur.execute(f"UPDATE {tabela} SET video_url = %s, video_capa_url = %s WHERE id = %s",  # noqa: S608
                (url, url_capa, id_secao))
    for velho in antes.values():
        if velho:
            arquivos.remover(velho, cur)
    return {"video_url": url, "video_capa_url": url_capa}


def remover_video_secao(cur, id_unidade: int, tipo: str, id_secao: int) -> dict:
    tabela, buscar = catalogo_conteudo._TABELA_DA_SECAO[tipo]
    buscar(cur, id_unidade, id_secao)
    cur.execute(f"SELECT video_url, video_capa_url FROM {tabela} WHERE id = %s", (id_secao,))  # noqa: S608
    antes = dict(cur.fetchone())
    cur.execute(f"UPDATE {tabela} SET video_url = NULL, video_capa_url = NULL WHERE id = %s",  # noqa: S608
                (id_secao,))
    for velho in antes.values():
        if velho:
            arquivos.remover(velho, cur)
    return {"video_url": None, "video_capa_url": None}


# ---------------------------------------------------------------------------
# O que o feed recebe
# ---------------------------------------------------------------------------

def do_site(cur, id_catalogo: int, idioma: str | None) -> list[dict]:
    """Os cartões no SITE (catálogo simples): foto, título e texto — SEM vídeo.

    🔑 Pedido do dono (30/10/2026): *"quando o catálogo é somente um catálogo, eu gostaria de ter
    uma imagem e mensagem de abertura assim como adicionar cartões, mas sem vídeo"*. São os
    MESMOS cartões do feed; o vídeo é do Cardápio Vivo. Cartão com vídeo mostra a CAPA dele
    como foto; o que só tinha o vídeo (sem capa, sem texto) não aparece.
    `id_categoria` nulo = a abertura do cardápio (a capa no topo do site).
    """
    saida = []
    for c in do_feed(cur, id_catalogo, idioma):
        m = c["midia"]
        foto = m.get("foto") if m["tipo"] == "FOTO" else m.get("capa") if m["tipo"] == "VIDEO" else None
        if not (foto or (c["titulo"] or "").strip() or (c["texto"] or "").strip()):
            continue
        saida.append({"id": c["id"], "id_categoria": c["id_categoria"], "id_subcategoria": c["id_subcategoria"],
                      "antes_do_item": c["antes_do_item"], "id_item_link": c["id_item_link"],
                      "titulo": c["titulo"], "texto": c["texto"], "foto": foto})
    return saida


def do_feed(cur, id_catalogo: int, idioma: str | None) -> list[dict]:
    """Os cartões ATIVOS e com conteúdo, traduzidos e com a mídia resolvida.

    ⚠️ Quem decide ONDE cada um entra é a tela: ela recebe os pratos já filtrados (horário,
    esgotado escondido, filtro de restrição) e reordenados (A/B), e o cartão cola no prato que
    sobrou. Fazer isso aqui exigiria repetir no servidor tudo o que a tela já faz.
    """
    cur.execute(
        """SELECT id, id_categoria, id_subcategoria, antes_do_item, titulo, titulo_en, titulo_de,
                  texto, texto_en, texto_de, foto_url, video_url, video_capa_url, id_item_link
             FROM catalogo_cartoes
            WHERE id_catalogo = %s AND ativo
              AND (coalesce(btrim(titulo), '') <> '' OR coalesce(btrim(texto), '') <> ''
                   OR foto_url IS NOT NULL OR video_url IS NOT NULL)
            ORDER BY id""", (id_catalogo,))
    saida = []
    for r in cur.fetchall():
        if r["video_url"]:
            midia = {"tipo": "VIDEO", "video": r["video_url"], "capa": r["video_capa_url"]}
        elif r["foto_url"]:
            midia = {"tipo": "FOTO", "foto": r["foto_url"]}
        else:
            midia = {"tipo": "NENHUMA"}
        saida.append({
            "id": r["id"], "id_categoria": r["id_categoria"], "id_subcategoria": r["id_subcategoria"],
            "antes_do_item": r["antes_do_item"], "id_item_link": r["id_item_link"],
            "titulo": traducao.escolher(r["titulo"], r["titulo_en"], r["titulo_de"], idioma),
            "texto": traducao.escolher(r["texto"], r["texto_en"], r["texto_de"], idioma),
            "midia": midia,
        })
    return saida
