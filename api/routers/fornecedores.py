"""Fornecedores. Leitura livre a autenticados; escrita com `cadastros.fornecedores`."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response

import auditoria
from database import get_cursor
from paginacao import pagina
from models.cadastros import FornecedorCreate, FornecedorResponse, FornecedorUpdate
from seguranca import Contexto, contexto_atual, requer_permissao

router = APIRouter(prefix="/fornecedores", tags=["fornecedores"])

_CAMPOS = list(FornecedorCreate.model_fields.keys())


def _so_digitos(cnpj: str | None) -> str | None:
    if not cnpj:
        return None
    limpo = "".join(c for c in cnpj if c.isdigit())
    return limpo or None


@router.get("", response_model=list[FornecedorResponse])
def listar(
    busca: str | None = Query(default=None, max_length=80),
    incluir_inativos: bool = False,
    # 🔑 **O filtro que os seletores de COMPRA usam** (04/09/2026). A tabela
    # passou a guardar gente que não vende nada para a casa — funcionário,
    # sócio —, e sem este recorte o seletor de fornecedor da nota viraria uma
    # lista de funcionários. ⚠️ Nulo traz TODOS: a tela de Pessoas é a lista
    # inteira, e é ela que herda o comportamento antigo.
    so_fornecedores: bool | None = None,
    limite: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    resposta: Response = None,
    ctx: Contexto = Depends(contexto_atual),
) -> list[dict]:
    with get_cursor() as cur:
        linhas = pagina(
            cur,
            f"""SELECT f.id, {', '.join('f.' + c for c in _CAMPOS)},
                       (SELECT count(*) FROM produto_fornecedor pf
                         WHERE pf.id_fornecedor = f.id) AS produtos,
                       (SELECT max(pf.ultima_compra) FROM produto_fornecedor pf
                         WHERE pf.id_fornecedor = f.id) AS ultima_compra,
                       -- Quem entra no sistema como esta pessoa. Nulo é o caso
                       -- comum: a maioria das pessoas não tem login.
                       (SELECT u.nome FROM usuarios u
                         WHERE u.id_pessoa = f.id AND u.ativo LIMIT 1) AS usuario
                  FROM fornecedores f
                 WHERE (%s OR f.ativo)
                   AND (%s::bool IS NULL OR f.fornecedor = %s)
                   AND (%s::varchar IS NULL
                        OR lower(f.nome) LIKE lower('%%' || %s || '%%')
                        OR lower(coalesce(f.nome_fantasia, '')) LIKE lower('%%' || %s || '%%')
                        OR coalesce(f.cnpj, '') LIKE '%%' || %s || '%%')
                 ORDER BY f.ativo DESC, lower(f.nome)""",
            (incluir_inativos, so_fornecedores, so_fornecedores, busca, busca, busca, busca),
            limite=limite, offset=offset, resposta=resposta,
        )
    return linhas


@router.get("/{id_fornecedor}", response_model=FornecedorResponse)
def obter(id_fornecedor: int, ctx: Contexto = Depends(contexto_atual)) -> dict:
    with get_cursor() as cur:
        cur.execute(
            f"""SELECT id, {', '.join(_CAMPOS)},
                       (SELECT u.nome FROM usuarios u
                         WHERE u.id_pessoa = fornecedores.id AND u.ativo LIMIT 1) AS usuario
                  FROM fornecedores WHERE id = %s""", (id_fornecedor,)
        )
        f = cur.fetchone()
        if not f:
            raise HTTPException(status_code=404, detail="Fornecedor não encontrado")
    return dict(f)


@router.get("/{id_fornecedor}/produtos")
def produtos_da_pessoa(id_fornecedor: int,
                       ctx: Contexto = Depends(contexto_atual)) -> list[dict]:
    """O que esta pessoa fornece — e por quanto, da última vez.

    🔑 **Pedido do dono (09/09/2026):** *"no cadastro de pessoas, criar um grupo
    dos produtos que a pessoa/fornecedor está vinculado"*. A ficha dela já dizia
    **quantos** (`12 produto(s)`), e o número sozinho não responde a pergunta
    que se faz olhando para ela: *o que a gente compra deste aqui?*. Para
    descobrir, era preciso ir à lista de produtos e filtrar um por um.

    ⚠️ **`ultimo_preco` é POR UNIDADE DE ESTOQUE**, nunca por embalagem — é o
    mesmo número que a cascata de custo lê como segundo degrau. Mostrá-lo ao
    lado do fator da embalagem é o que deixa a conta conferível: caixa com 12,
    R$ 2,50 a unidade, R$ 30,00 a caixa.

    ⚠️ **Só os ATIVOS** (decisão do dono, 09/09/2026). A primeira versão
    trazia o inativo marcado, com o argumento de que ele explica a nota antiga;
    na base real isso encheu a lista de cadastro arquivado e afogou o que a
    pessoa fornece HOJE, que é a pergunta da ficha. O vínculo com o arquivado
    continua existindo e aparece na ficha do PRODUTO.

    ⚠️ Só autenticação: é leitura de cadastro, e a ficha da pessoa já é visível
    a quem chega nela. Quem edita passa pelas rotas de produto.
    """
    with get_cursor() as cur:
        cur.execute("SELECT 1 FROM fornecedores WHERE id = %s", (id_fornecedor,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Pessoa não encontrada")
        cur.execute(
            """SELECT p.id, p.codigo, p.nome, p.um_estoque, p.ativo, p.status,
                      pf.codigo_no_fornecedor, pf.embalagem, pf.fator,
                      pf.ultimo_preco, pf.ultima_compra, pf.preferencial
                 FROM produto_fornecedor pf
                 JOIN produtos p ON p.id = pf.id_produto
                WHERE pf.id_fornecedor = %s AND p.ativo
                -- O preferencial primeiro, depois quem foi comprado mais
                -- recentemente: a pergunta de quem abre isto é "o que a gente
                -- compra deste fornecedor HOJE", não a ordem alfabética.
                ORDER BY pf.preferencial DESC,
                         pf.ultima_compra DESC NULLS LAST,
                         lower(p.nome)""",
            (id_fornecedor,),
        )
        return [dict(r) for r in cur.fetchall()]


@router.post("", status_code=201)
def criar(body: FornecedorCreate,
          ctx: Contexto = Depends(requer_permissao("cadastros.fornecedores"))) -> dict:
    dados = body.model_dump()
    dados["cnpj"] = _so_digitos(dados.get("cnpj"))
    with get_cursor() as cur:
        if dados["cnpj"]:
            cur.execute("SELECT nome FROM fornecedores WHERE cnpj = %s", (dados["cnpj"],))
            existente = cur.fetchone()
            if existente:
                raise HTTPException(
                    status_code=409, detail=f"Este CNPJ já é de {existente['nome']}"
                )
        dados["criado_por"] = ctx.id_usuario
        colunas = ", ".join(dados)
        marcas = ", ".join(["%s"] * len(dados))
        cur.execute(
            f"INSERT INTO fornecedores ({colunas}) VALUES ({marcas}) RETURNING id",
            list(dados.values()),
        )
        novo = cur.fetchone()["id"]
        auditoria.registrar(cur, ctx.id_usuario, "fornecedor", novo, "criar", depois=dados)
    return {"id": novo, "message": "Fornecedor criado"}


@router.put("/{id_fornecedor}")
def atualizar(id_fornecedor: int, body: FornecedorUpdate,
              ctx: Contexto = Depends(requer_permissao("cadastros.fornecedores"))) -> dict:
    dados = body.model_dump(exclude_unset=True)
    if "cnpj" in dados:
        dados["cnpj"] = _so_digitos(dados["cnpj"])
    if not dados:
        raise HTTPException(status_code=400, detail="Nada para atualizar")
    with get_cursor() as cur:
        cur.execute(
            f"SELECT {', '.join(_CAMPOS)} FROM fornecedores WHERE id = %s", (id_fornecedor,)
        )
        antes = cur.fetchone()
        if not antes:
            raise HTTPException(status_code=404, detail="Fornecedor não encontrado")
        if dados.get("cnpj"):
            cur.execute(
                "SELECT nome FROM fornecedores WHERE cnpj = %s AND id <> %s",
                (dados["cnpj"], id_fornecedor),
            )
            outro = cur.fetchone()
            if outro:
                raise HTTPException(status_code=409, detail=f"Este CNPJ já é de {outro['nome']}")
        sets = ", ".join(f"{c} = %s" for c in dados)
        cur.execute(
            f"UPDATE fornecedores SET {sets} WHERE id = %s", [*dados.values(), id_fornecedor]
        )
        auditoria.registrar(cur, ctx.id_usuario, "fornecedor", id_fornecedor, "atualizar",
                            antes=dict(antes), depois=dados)
    return {"message": "Fornecedor atualizado"}


@router.delete("/{id_fornecedor}")
def desativar(id_fornecedor: int,
              ctx: Contexto = Depends(requer_permissao("cadastros.fornecedores"))) -> dict:
    """Desativa; fornecedor com histórico nunca some do sistema."""
    with get_cursor() as cur:
        cur.execute("UPDATE fornecedores SET ativo = false WHERE id = %s", (id_fornecedor,))
        auditoria.registrar(cur, ctx.id_usuario, "fornecedor", id_fornecedor, "desativar")
    return {"message": "Fornecedor desativado"}
