"""Fornecedores. Leitura livre a autenticados; escrita com `cadastros.fornecedores`."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response

import auditoria
from database import get_cursor
from paginacao import com_total
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
    limite: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    resposta: Response = None,
    ctx: Contexto = Depends(contexto_atual),
) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            f"""SELECT f.id, {', '.join('f.' + c for c in _CAMPOS)},
                       (SELECT count(*) FROM produto_fornecedor pf
                         WHERE pf.id_fornecedor = f.id) AS produtos,
                       (SELECT max(pf.ultima_compra) FROM produto_fornecedor pf
                         WHERE pf.id_fornecedor = f.id) AS ultima_compra,
                       count(*) OVER () AS _total
                  FROM fornecedores f
                 WHERE (%s OR f.ativo)
                   AND (%s::varchar IS NULL
                        OR lower(f.nome) LIKE lower('%%' || %s || '%%')
                        OR lower(coalesce(f.nome_fantasia, '')) LIKE lower('%%' || %s || '%%')
                        OR coalesce(f.cnpj, '') LIKE '%%' || %s || '%%')
                 ORDER BY f.ativo DESC, lower(f.nome)
                 LIMIT %s OFFSET %s""",
            (incluir_inativos, busca, busca, busca, busca, limite, offset),
        )
        linhas = [dict(r) for r in cur.fetchall()]
    return com_total(linhas, resposta, offset)


@router.get("/{id_fornecedor}", response_model=FornecedorResponse)
def obter(id_fornecedor: int, ctx: Contexto = Depends(contexto_atual)) -> dict:
    with get_cursor() as cur:
        cur.execute(
            f"SELECT id, {', '.join(_CAMPOS)} FROM fornecedores WHERE id = %s", (id_fornecedor,)
        )
        f = cur.fetchone()
        if not f:
            raise HTTPException(status_code=404, detail="Fornecedor não encontrado")
    return dict(f)


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
