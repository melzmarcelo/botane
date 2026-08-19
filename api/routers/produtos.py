"""Produtos — o cadastro central.

Leitura só exige autenticação: a cozinha consulta produto sem poder editar.
Escrita exige `cadastros.produtos`.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response

import auditoria
from database import get_cursor
from models.produtos import (
    KitRequest,
    ContagemProdutos,
    ProdutoCreate,
    ProdutoResponse,
    ProdutoResumo,
    ProdutoUpdate,
    STATUS,
    TIPOS,
)
from seguranca import Contexto, contexto_atual, requer_permissao
from services import kits

def _com_total(linhas: list[dict], resposta, offset: int) -> list[dict]:
    """Tira o `_total` das linhas e o devolve no cabeçalho `X-Total`.

    A tela precisa saber que existe mais coisa além da página — sem isso, uma
    lista cheia e uma lista cortada são indistinguíveis, e o usuário conclui que
    o produto não existe quando ele está na página seguinte.
    """
    total = linhas[0].pop("_total", len(linhas)) if linhas else offset
    for l in linhas[1:]:
        l.pop("_total", None)
    if resposta is not None:
        resposta.headers["X-Total"] = str(total)
    return linhas


router = APIRouter(prefix="/produtos", tags=["produtos"])

_EDITAVEIS = (
    "codigo", "nome", "nome_curto", "tipo", "id_categoria", "id_setor",
    "producao_propria", "controla_estoque", "um_estoque", "um_compra", "fator_compra",
    "perecivel", "validade_dias", "controla_lote", "controla_validade",
    "estoque_minimo", "estoque_maximo", "ncm", "codigo_barras", "codigo_omie",
    "observacao", "status", "ativo",
)


def _proximo_codigo(cur) -> str:
    cur.execute("SELECT nextval('seq_codigo_produto') AS n")
    return f"P{cur.fetchone()['n']:04d}"


def _valida_basico(dados: dict) -> None:
    if dados.get("tipo") and dados["tipo"] not in TIPOS:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Use: {', '.join(TIPOS)}")
    if dados.get("status") and dados["status"] not in STATUS:
        raise HTTPException(status_code=400, detail=f"Status inválido. Use: {', '.join(STATUS)}")
    if dados.get("producao_propria") and dados.get("tipo") not in (None, "PRODUZIDO", "KIT"):
        raise HTTPException(
            status_code=400,
            detail="Produção própria só vale para produto produzido ou kit.",
        )


def _gravar_preco(cur, id_produto: int, preco: float | None, id_usuario: int) -> None:
    """Fecha o preço vigente e abre outro. O histórico é o que sustenta a margem."""
    if preco is None:
        return
    cur.execute(
        """SELECT id, preco_venda FROM produto_precos
            WHERE id_produto = %s AND id_unidade IS NULL AND vigente_ate IS NULL""",
        (id_produto,),
    )
    atual = cur.fetchone()
    if atual and float(atual["preco_venda"]) == float(preco):
        return
    if atual:
        cur.execute(
            "UPDATE produto_precos SET vigente_ate = current_date WHERE id = %s", (atual["id"],)
        )
    cur.execute(
        """INSERT INTO produto_precos (id_produto, preco_venda, criado_por)
           VALUES (%s, %s, %s)""",
        (id_produto, preco, id_usuario),
    )


def _gravar_fornecedores(cur, id_produto: int, lista) -> None:
    cur.execute("DELETE FROM produto_fornecedor WHERE id_produto = %s", (id_produto,))
    for f in lista:
        cur.execute(
            """INSERT INTO produto_fornecedor
                   (id_produto, id_fornecedor, codigo_no_fornecedor, embalagem, fator,
                    ultimo_preco, preferencial)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id_produto, id_fornecedor) DO UPDATE
                   SET codigo_no_fornecedor = EXCLUDED.codigo_no_fornecedor,
                       embalagem = EXCLUDED.embalagem,
                       fator = EXCLUDED.fator,
                       ultimo_preco = EXCLUDED.ultimo_preco,
                       preferencial = EXCLUDED.preferencial""",
            (id_produto, f.id_fornecedor, f.codigo_no_fornecedor, f.embalagem,
             f.fator, f.ultimo_preco, f.preferencial),
        )


@router.get("", response_model=list[ProdutoResumo])
def listar(
    busca: str | None = Query(default=None, max_length=80),
    tipo: str | None = None,
    id_categoria: int | None = None,
    id_setor: int | None = None,
    status: str | None = None,
    incluir_inativos: bool = False,
    limite: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    resposta: Response = None,
    ctx: Contexto = Depends(contexto_atual),
) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT p.id, p.codigo, p.nome, p.tipo, c.nome AS categoria, s.nome AS setor,
                   p.um_estoque, p.producao_propria, p.controla_estoque, p.status, p.ativo,
                   (SELECT pp.preco_venda FROM produto_precos pp
                     WHERE pp.id_produto = p.id AND pp.vigente_ate IS NULL
                     ORDER BY pp.vigente_de DESC LIMIT 1) AS preco_venda,
                   -- Quantos existiriam sem o LIMIT. Sai na mesma varredura: uma
                   -- segunda consulta de count repetiria o filtro inteiro e
                   -- poderia até discordar desta, se algo mudasse no meio.
                   count(*) OVER () AS _total
              FROM produtos p
              LEFT JOIN categorias c ON c.id = p.id_categoria
              LEFT JOIN setores s ON s.id = p.id_setor
             WHERE (%s OR p.ativo)
               AND (%s::varchar IS NULL OR p.tipo = %s)
               AND (%s::int IS NULL OR p.id_categoria = %s)
               AND (%s::int IS NULL OR p.id_setor = %s)
               AND (%s::varchar IS NULL OR p.status = %s)
               AND (%s::varchar IS NULL
                    OR lower(p.nome) LIKE lower('%%' || %s || '%%')
                    OR lower(p.codigo) LIKE lower('%%' || %s || '%%')
                    OR coalesce(p.codigo_barras, '') LIKE '%%' || %s || '%%')
             ORDER BY p.ativo DESC, lower(p.nome)
             LIMIT %s OFFSET %s
            """,
            (incluir_inativos, tipo, tipo, id_categoria, id_categoria, id_setor, id_setor,
             status, status, busca, busca, busca, busca, limite, offset),
        )
        linhas = [dict(r) for r in cur.fetchall()]
    return _com_total(linhas, resposta, offset)


@router.get("/contagem", response_model=ContagemProdutos)
def contagem(ctx: Contexto = Depends(contexto_atual)) -> dict:
    with get_cursor() as cur:
        cur.execute(
            """SELECT tipo, count(*) FILTER (WHERE ativo) AS n,
                      count(*) FILTER (WHERE NOT ativo) AS inativos,
                      count(*) FILTER (WHERE status = 'RASCUNHO' AND ativo) AS rascunhos
                 FROM produtos GROUP BY tipo"""
        )
        linhas = cur.fetchall()
    return {
        "total": sum(l["n"] for l in linhas),
        "por_tipo": {l["tipo"]: l["n"] for l in linhas},
        "rascunhos": sum(l["rascunhos"] for l in linhas),
        "inativos": sum(l["inativos"] for l in linhas),
    }


@router.get("/{id_produto}", response_model=ProdutoResponse)
def obter(id_produto: int, ctx: Contexto = Depends(contexto_atual)) -> dict:
    with get_cursor() as cur:
        cur.execute(
            """SELECT p.*, c.nome AS categoria, s.nome AS setor
                 FROM produtos p
                 LEFT JOIN categorias c ON c.id = p.id_categoria
                 LEFT JOIN setores s ON s.id = p.id_setor
                WHERE p.id = %s""",
            (id_produto,),
        )
        p = cur.fetchone()
        if not p:
            raise HTTPException(status_code=404, detail="Produto não encontrado")
        produto = dict(p)

        cur.execute(
            """SELECT preco_venda, vigente_de FROM produto_precos
                WHERE id_produto = %s AND vigente_ate IS NULL
                ORDER BY vigente_de DESC LIMIT 1""",
            (id_produto,),
        )
        preco = cur.fetchone()
        produto["preco_venda"] = preco["preco_venda"] if preco else None
        produto["preco_desde"] = preco["vigente_de"] if preco else None

        cur.execute(
            """SELECT pf.id_fornecedor, f.nome AS fornecedor, pf.codigo_no_fornecedor,
                      pf.embalagem, pf.fator, pf.ultimo_preco, pf.ultima_compra, pf.preferencial
                 FROM produto_fornecedor pf
                 JOIN fornecedores f ON f.id = pf.id_fornecedor
                WHERE pf.id_produto = %s
                ORDER BY pf.preferencial DESC, lower(f.nome)""",
            (id_produto,),
        )
        produto["fornecedores"] = [dict(r) for r in cur.fetchall()]
    return produto


@router.post("", status_code=201)
def criar(body: ProdutoCreate,
          ctx: Contexto = Depends(requer_permissao("cadastros.produtos"))) -> dict:
    dados = body.model_dump()
    fornecedores = dados.pop("fornecedores", [])
    preco = dados.pop("preco_venda", None)
    _valida_basico(dados)

    with get_cursor() as cur:
        codigo = (dados.get("codigo") or "").strip() or _proximo_codigo(cur)
        cur.execute("SELECT nome FROM produtos WHERE lower(codigo) = lower(%s)", (codigo,))
        existente = cur.fetchone()
        if existente:
            raise HTTPException(
                status_code=409, detail=f"O código {codigo} já é de {existente['nome']}"
            )
        dados["codigo"] = codigo
        dados["criado_por"] = ctx.id_usuario
        dados["nome"] = dados["nome"].strip()

        colunas = ", ".join(dados)
        marcas = ", ".join(["%s"] * len(dados))
        cur.execute(
            f"INSERT INTO produtos ({colunas}) VALUES ({marcas}) RETURNING id",
            list(dados.values()),
        )
        novo = cur.fetchone()["id"]
        _gravar_preco(cur, novo, preco, ctx.id_usuario)
        _gravar_fornecedores(cur, novo, body.fornecedores)
        auditoria.registrar(cur, ctx.id_usuario, "produto", novo, "criar",
                            depois={"codigo": codigo, "nome": dados["nome"], "tipo": dados["tipo"]})
    return {"id": novo, "codigo": codigo, "message": "Produto criado"}


@router.put("/{id_produto}")
def atualizar(id_produto: int, body: ProdutoUpdate,
              ctx: Contexto = Depends(requer_permissao("cadastros.produtos"))) -> dict:
    dados = body.model_dump(exclude_unset=True)
    fornecedores = dados.pop("fornecedores", None)
    preco = dados.pop("preco_venda", None)

    with get_cursor() as cur:
        cur.execute(
            "SELECT codigo, nome, tipo, status, producao_propria FROM produtos WHERE id = %s",
            (id_produto,),
        )
        antes = cur.fetchone()
        if not antes:
            raise HTTPException(status_code=404, detail="Produto não encontrado")

        # O tipo que vale na validação é o novo, se veio; senão o que já estava.
        _valida_basico({**dict(antes), **dados})

        if "codigo" in dados and dados["codigo"]:
            cur.execute(
                "SELECT nome FROM produtos WHERE lower(codigo) = lower(%s) AND id <> %s",
                (dados["codigo"], id_produto),
            )
            outro = cur.fetchone()
            if outro:
                raise HTTPException(status_code=409, detail=f"O código já é de {outro['nome']}")

        campos = {k: v for k, v in dados.items() if k in _EDITAVEIS}
        if campos:
            sets = ", ".join(f"{c} = %s" for c in campos)
            cur.execute(
                f"UPDATE produtos SET {sets} WHERE id = %s", [*campos.values(), id_produto]
            )
        _gravar_preco(cur, id_produto, preco, ctx.id_usuario)
        if fornecedores is not None:
            _gravar_fornecedores(cur, id_produto, body.fornecedores or [])

        auditoria.registrar(cur, ctx.id_usuario, "produto", id_produto, "atualizar",
                            antes=dict(antes), depois=campos)
    return {"message": "Produto atualizado"}


@router.get("/{id_produto}/kit")
def obter_kit(id_produto: int, ctx: Contexto = Depends(contexto_atual)) -> dict:
    """A composição do combo e quanto ele custa hoje.

    O custo vem junto de propósito: montar a composição sem ver o custo sair é
    trabalhar às cegas — o combo existe para ter preço, e o preço depende disto.
    """
    with get_cursor() as cur:
        itens = kits.componentes(cur, id_produto)
        valor, origem, detalhe = kits.custo(cur, id_produto)
        # Dinheiro só para quem pode ver custo de ficha: a mesma chave que
        # esconde o custo da receita esconde o do combo.
        if not ctx.pode("fichas.custos"):
            return {"itens": itens, "custo": None, "origem": None, "detalhe": []}
    return {
        "itens": itens,
        "custo": float(valor) if valor is not None else None,
        "origem": origem,
        "detalhe": detalhe,
    }


@router.put("/{id_produto}/kit")
def gravar_kit(id_produto: int, body: KitRequest,
               ctx: Contexto = Depends(requer_permissao("cadastros.produtos"))) -> dict:
    with get_cursor() as cur:
        r = kits.gravar(cur, id_produto, [i.model_dump() for i in body.itens])
        valor, origem, _ = kits.custo(cur, id_produto)
        auditoria.registrar(cur, ctx.id_usuario, "produto", id_produto, "kit_composicao",
                            depois={"itens": r["itens"]})
    return r | {
        "custo": float(valor) if valor is not None else None,
        "origem": origem,
        "message": f"Composição gravada com {r['itens']} componente(s)",
    }


@router.post("/{id_produto}/revisar")
def revisar(id_produto: int,
            ctx: Contexto = Depends(requer_permissao("cadastros.produtos"))) -> dict:
    """Tira o produto de rascunho — o que libera ele para entrar no estoque."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT um_estoque, fator_compra, status FROM produtos WHERE id = %s", (id_produto,)
        )
        p = cur.fetchone()
        if not p:
            raise HTTPException(status_code=404, detail="Produto não encontrado")
        if not p["um_estoque"] or not p["fator_compra"]:
            raise HTTPException(
                status_code=400,
                detail="Defina a unidade de estoque e o fator de conversão antes de ativar.",
            )
        cur.execute(
            """UPDATE produtos SET status = 'ATIVO', revisado_em = now(), revisado_por = %s
                WHERE id = %s""",
            (ctx.id_usuario, id_produto),
        )
        auditoria.registrar(cur, ctx.id_usuario, "produto", id_produto, "revisar",
                            antes={"status": p["status"]}, depois={"status": "ATIVO"})
    return {"message": "Produto revisado e ativo"}


@router.delete("/{id_produto}")
def desativar(id_produto: int,
              ctx: Contexto = Depends(requer_permissao("cadastros.produtos"))) -> dict:
    """Desativa. Produto com movimento no razão nunca pode sumir do histórico."""
    with get_cursor() as cur:
        cur.execute("UPDATE produtos SET ativo = false WHERE id = %s", (id_produto,))
        auditoria.registrar(cur, ctx.id_usuario, "produto", id_produto, "desativar")
    return {"message": "Produto desativado"}
