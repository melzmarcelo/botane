"""O que o Cardápio Vivo (113) acrescentou ao PRODUTO: vídeo, restrições e adicionais.

🔑 **No produto, não no item do catálogo** (decisão do dono, 14/10/2026): o mesmo
prato em "Pra Dividir" e em "Menu Principal" tem o mesmo vídeo, as mesmas
restrições e os mesmos adicionais. Gravar no item obrigaria a repetir — e as duas
cópias divergiriam.

⚠️ **Router próprio, mesma permissão do cadastro** (`cadastros.produtos`): o
`produtos.py` já passa de mil linhas, e estas rotas falam de vitrine, não de estoque.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

import arquivos
import auditoria
from database import get_cursor
from models.cardapio_vivo import GrupoAdicional, RestricoesDoProduto
from seguranca import Contexto, requer_permissao
from services import cardapio_vivo as servico

router = APIRouter(prefix="/produtos", tags=["produtos"])
_PRODUTOS = requer_permissao("cadastros.produtos")


def _produto(cur, id_produto: int) -> dict:
    cur.execute("""SELECT id, nome, video_url, video_capa_url, video_nome, video_bytes,
                          video_segundos, restricoes
                     FROM produtos WHERE id = %s""", (id_produto,))
    achado = cur.fetchone()
    if not achado:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return dict(achado)


def _adicionais(cur, id_produto: int) -> list[dict]:
    cur.execute(
        """SELECT g.id, g.nome, g.minimo, g.maximo, g.permite_repetir,
                  coalesce(json_agg(json_build_object(
                      'id', o.id, 'nome', o.nome, 'preco', o.preco, 'ativo', o.ativo,
                      'incluso', o.incluso,
                      'id_produto_ref', o.id_produto_ref, 'produto_ref', r.nome)
                      ORDER BY o.ordem, o.id) FILTER (WHERE o.id IS NOT NULL), '[]') AS opcoes
             FROM produto_adicionais_grupos g
             LEFT JOIN produto_adicionais_opcoes o ON o.id_grupo = g.id
             LEFT JOIN produtos r ON r.id = o.id_produto_ref
            WHERE g.id_produto = %s
            GROUP BY g.id ORDER BY g.ordem, g.id""",
        (id_produto,))
    return [dict(r) for r in cur.fetchall()]


@router.get("/{id_produto}/cardapio")
def cardapio_do_produto(id_produto: int, ctx: Contexto = Depends(_PRODUTOS)) -> dict:
    """Vídeo, restrições e adicionais do produto — a parte do Cardápio Vivo da aba Catálogo."""
    with get_cursor() as cur:
        p = _produto(cur, id_produto)
        return {
            "video": ({"url": p["video_url"], "capa": p["video_capa_url"], "nome": p["video_nome"],
                       "bytes": p["video_bytes"],
                       "segundos": float(p["video_segundos"]) if p["video_segundos"] else None}
                      if p["video_url"] else None),
            "restricoes": list(p["restricoes"] or []),
            "opcoes_restricoes": [{"chave": k, "nome": v} for k, v in servico.RESTRICOES.items()],
            "adicionais": _adicionais(cur, id_produto),
        }


@router.post("/{id_produto}/video")
async def enviar_video(id_produto: int, arquivo: UploadFile = File(...),
                       ctx: Contexto = Depends(_PRODUTOS)) -> dict:
    """Converte e guarda o vídeo do prato (MP4 720p, mudo, até 15 s) e a capa.

    ⚠️ **A conversão roda FORA do laço e sem transação aberta**: são segundos de CPU,
    e segurar uma conexão do pool durante o ffmpeg travaria a casa inteira.
    ⚠️ Vídeo novo, capa nova e a remoção dos antigos são UMA transação — a lição da logo.
    """
    cru = await arquivos.ler_video(arquivo)
    mp4, capa, segundos = await run_in_threadpool(arquivos.converter_video, cru)
    with get_cursor() as cur:
        antes = _produto(cur, id_produto)
        url = arquivos.gravar(cur, mp4, arquivos.VIDEO_TIPO, ".mp4", f"video-{id_produto}")
        url_capa = arquivos.gravar(cur, capa, "image/webp", ".webp", f"capa-{id_produto}")
        cur.execute(
            """UPDATE produtos SET video_url = %s, video_capa_url = %s, video_nome = %s,
                      video_bytes = %s, video_segundos = %s, video_em = now()
                WHERE id = %s""",
            (url, url_capa, (arquivo.filename or "").strip()[:255] or None, len(mp4),
             segundos, id_produto))
        for velho in (antes["video_url"], antes["video_capa_url"]):
            if velho:
                arquivos.remover(velho, cur)
        auditoria.registrar(cur, ctx.id_usuario, "produto", id_produto, "enviar_video",
                            antes={"video_nome": antes["video_nome"]},
                            depois={"video_nome": arquivo.filename, "bytes": len(mp4),
                                    "enviado_bytes": len(cru), "segundos": segundos})
    return {"video": {"url": url, "capa": url_capa, "nome": arquivo.filename,
                      "bytes": len(mp4), "segundos": segundos},
            "message": f"Vídeo convertido: {segundos:.0f} s, {len(mp4) / 1048576:.1f} MB."}


@router.delete("/{id_produto}/video")
def remover_video(id_produto: int, ctx: Contexto = Depends(_PRODUTOS)) -> dict:
    with get_cursor() as cur:
        antes = _produto(cur, id_produto)
        cur.execute("""UPDATE produtos SET video_url = NULL, video_capa_url = NULL,
                              video_nome = NULL, video_bytes = NULL, video_segundos = NULL,
                              video_em = NULL WHERE id = %s""", (id_produto,))
        for velho in (antes["video_url"], antes["video_capa_url"]):
            if velho:
                arquivos.remover(velho, cur)
        auditoria.registrar(cur, ctx.id_usuario, "produto", id_produto, "remover_video",
                            antes={"video_nome": antes["video_nome"]})
    return {"video": None, "message": "Vídeo removido — o cardápio volta a mostrar a foto."}


@router.put("/{id_produto}/restricoes")
def gravar_restricoes(id_produto: int, body: RestricoesDoProduto,
                      ctx: Contexto = Depends(_PRODUTOS)) -> dict:
    desconhecidas = set(body.restricoes) - set(servico.RESTRICOES)
    if desconhecidas:
        raise HTTPException(status_code=422,
                            detail=f"Restrição desconhecida: {', '.join(sorted(desconhecidas))}.")
    novas = [k for k in servico.RESTRICOES if k in body.restricoes]
    with get_cursor() as cur:
        antes = _produto(cur, id_produto)
        cur.execute("UPDATE produtos SET restricoes = %s WHERE id = %s", (novas, id_produto))
        auditoria.registrar(cur, ctx.id_usuario, "produto", id_produto, "restricoes",
                            antes={"restricoes": list(antes["restricoes"] or [])},
                            depois={"restricoes": novas})
    return {"restricoes": novas, "message": "Restrições gravadas."}


@router.put("/{id_produto}/adicionais")
def gravar_adicionais(id_produto: int, body: list[GrupoAdicional],
                      ctx: Contexto = Depends(_PRODUTOS)) -> dict:
    """Grava os grupos de adicionais INTEIROS, na ordem em que chegam.

    🔑 **A lista inteira, como a ordem do catálogo**: mandar só o grupo mexido deixaria
    o servidor adivinhando a ordem dos outros. Pedido antigo não depende disto — o que
    o cliente escolheu fica congelado no pedido (fase 2).
    """
    if len(body) > 15:
        raise HTTPException(status_code=422, detail="No máximo 15 grupos de adicionais.")
    with get_cursor() as cur:
        _produto(cur, id_produto)
        refs = sorted({o.id_produto_ref for g in body for o in g.opcoes if o.id_produto_ref})
        if id_produto in refs:
            raise HTTPException(status_code=422,
                                detail="O adicional não pode apontar para o próprio produto.")
        if refs:
            cur.execute("SELECT id FROM produtos WHERE id = ANY(%s) AND ativo", (refs,))
            if {r["id"] for r in cur.fetchall()} != set(refs):
                raise HTTPException(status_code=422,
                                    detail="Um adicional aponta para produto inativo ou inexistente.")
        antes = _adicionais(cur, id_produto)
        cur.execute("DELETE FROM produto_adicionais_grupos WHERE id_produto = %s", (id_produto,))
        for ordem_g, g in enumerate(body):
            cur.execute(
                """INSERT INTO produto_adicionais_grupos
                       (id_produto, nome, minimo, maximo, ordem, permite_repetir)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                (id_produto, g.nome.strip(), g.minimo, g.maximo, ordem_g, g.permite_repetir))
            id_grupo = cur.fetchone()["id"]
            for ordem_o, o in enumerate(g.opcoes):
                cur.execute(
                    """INSERT INTO produto_adicionais_opcoes
                           (id_grupo, nome, preco, id_produto_ref, ordem, ativo, incluso)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (id_grupo, o.nome.strip(),
                     # ⚠️ Com produto, o preço é o DELE (cascata da loja): um preço digitado
                     # aqui seria a segunda regra de preço que a casa evita.
                     None if o.id_produto_ref else o.preco,
                     o.id_produto_ref, ordem_o, o.ativo, o.incluso))
        depois = _adicionais(cur, id_produto)
        auditoria.registrar(cur, ctx.id_usuario, "produto", id_produto, "adicionais",
                            antes={"grupos": [g["nome"] for g in antes]},
                            depois={"grupos": [g["nome"] for g in depois]})
    return {"adicionais": depois, "message": "Adicionais gravados."}
