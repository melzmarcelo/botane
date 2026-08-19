"""Papéis e o catálogo de permissões."""

from fastapi import APIRouter, Depends, HTTPException, Request

import auditoria
from database import get_cursor
from models.acesso import PapelCreate, PapelResponse, PapelUpdate, PermissaoResponse
from seguranca import Contexto, contexto_atual, requer_permissao

router = APIRouter(tags=["papéis"])


@router.get("/permissoes", response_model=list[PermissaoResponse])
def listar_permissoes(ctx: Contexto = Depends(contexto_atual)) -> list[dict]:
    """Catálogo de chaves. Só autenticação: a tela de papéis e a de usuários usam."""
    with get_cursor() as cur:
        cur.execute("SELECT chave, modulo, descricao, ordem FROM permissoes ORDER BY ordem, chave")
        return [dict(r) for r in cur.fetchall()]


@router.get("/papeis", response_model=list[PapelResponse])
def listar(ctx: Contexto = Depends(contexto_atual)) -> list[dict]:
    """Lido também pela tela de usuários — por isso só exige autenticação."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT p.id, p.nome, p.descricao, p.sistema,
                      COALESCE(array_agg(pp.chave) FILTER (WHERE pp.chave IS NOT NULL), '{}') AS permissoes,
                      (SELECT count(DISTINCT up.id_usuario) FROM usuario_papeis up
                        WHERE up.id_papel = p.id) AS usuarios
                 FROM papeis p
                 LEFT JOIN papel_permissoes pp ON pp.id_papel = p.id
                GROUP BY p.id
                ORDER BY p.sistema DESC, p.nome"""
        )
        return [dict(r) for r in cur.fetchall()]


@router.post("/papeis", status_code=201)
def criar(body: PapelCreate, request: Request,
          ctx: Contexto = Depends(requer_permissao("admin.papeis"))) -> dict:
    with get_cursor() as cur:
        cur.execute("SELECT 1 FROM papeis WHERE lower(nome) = lower(%s)", (body.nome,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Já existe um papel com este nome")
        cur.execute(
            "INSERT INTO papeis (nome, descricao, sistema) VALUES (%s, %s, false) RETURNING id",
            (body.nome.strip(), body.descricao),
        )
        novo = cur.fetchone()["id"]
        for chave in body.permissoes:
            cur.execute(
                "INSERT INTO papel_permissoes (id_papel, chave) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (novo, chave),
            )
        auditoria.registrar(
            cur, ctx.id_usuario, "papel", novo, "criar",
            depois={"nome": body.nome, "permissoes": body.permissoes},
        )
    return {"id": novo, "message": "Papel criado"}


@router.put("/papeis/{id_papel}")
def atualizar(id_papel: int, body: PapelUpdate, request: Request,
              ctx: Contexto = Depends(requer_permissao("admin.papeis"))) -> dict:
    with get_cursor() as cur:
        cur.execute("SELECT id, nome, descricao, sistema FROM papeis WHERE id = %s", (id_papel,))
        antes = cur.fetchone()
        if not antes:
            raise HTTPException(status_code=404, detail="Papel não encontrado")
        if antes["sistema"]:
            # Editar papel de fábrica quebraria na próxima migração, que o redefine.
            raise HTTPException(
                status_code=400,
                detail="Papel de fábrica não é editável. Copie-o e ajuste a cópia.",
            )

        if body.nome or body.descricao is not None:
            cur.execute(
                "UPDATE papeis SET nome = COALESCE(%s, nome), descricao = COALESCE(%s, descricao) WHERE id = %s",
                (body.nome, body.descricao, id_papel),
            )
        if body.permissoes is not None:
            cur.execute("DELETE FROM papel_permissoes WHERE id_papel = %s", (id_papel,))
            for chave in body.permissoes:
                cur.execute(
                    "INSERT INTO papel_permissoes (id_papel, chave) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (id_papel, chave),
                )
        auditoria.registrar(
            cur, ctx.id_usuario, "papel", id_papel, "atualizar",
            antes=dict(antes), depois=body.model_dump(exclude_none=True),
        )
    return {"id": id_papel, "message": "Papel atualizado"}


@router.delete("/papeis/{id_papel}")
def excluir(id_papel: int, ctx: Contexto = Depends(requer_permissao("admin.papeis"))) -> dict:
    with get_cursor() as cur:
        cur.execute("SELECT nome, sistema FROM papeis WHERE id = %s", (id_papel,))
        p = cur.fetchone()
        if not p:
            raise HTTPException(status_code=404, detail="Papel não encontrado")
        if p["sistema"]:
            raise HTTPException(status_code=400, detail="Papel de fábrica não pode ser excluído")
        cur.execute("SELECT count(*) AS n FROM usuario_papeis WHERE id_papel = %s", (id_papel,))
        if cur.fetchone()["n"]:
            raise HTTPException(
                status_code=409, detail="Há usuários com este papel. Troque o papel deles antes."
            )
        cur.execute("DELETE FROM papeis WHERE id = %s", (id_papel,))
        auditoria.registrar(cur, ctx.id_usuario, "papel", id_papel, "excluir", antes=dict(p))
    return {"message": "Papel excluído"}
