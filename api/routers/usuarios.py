"""Usuários e o vínculo deles com papéis (por loja)."""

from fastapi import APIRouter, Depends, HTTPException, Request

import auditoria
from database import get_cursor
from models.acesso import UsuarioCreate, UsuarioResponse, UsuarioUpdate
from seguranca import Contexto, hash_senha, requer_permissao

router = APIRouter(
    prefix="/usuarios",
    tags=["usuários"],
    dependencies=[Depends(requer_permissao("admin.usuarios"))],
)


def _papeis_do_usuario(cur, id_usuario: int) -> list[dict]:
    cur.execute(
        """SELECT up.id_papel, p.nome AS papel, up.id_unidade, un.nome AS unidade
             FROM usuario_papeis up
             JOIN papeis p ON p.id = up.id_papel
             LEFT JOIN unidades un ON un.id = up.id_unidade
            WHERE up.id_usuario = %s
            ORDER BY p.nome""",
        (id_usuario,),
    )
    return [dict(r) for r in cur.fetchall()]


def _gravar_papeis(cur, id_usuario: int, papeis) -> None:
    cur.execute("DELETE FROM usuario_papeis WHERE id_usuario = %s", (id_usuario,))
    for v in papeis:
        cur.execute(
            """INSERT INTO usuario_papeis (id_usuario, id_papel, id_unidade)
               VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
            (id_usuario, v.id_papel, v.id_unidade),
        )


@router.get("", response_model=list[UsuarioResponse])
def listar(incluir_inativos: bool = False) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """SELECT id, nome, email, telefone, ativo, ultimo_acesso,
                      (bloqueado_ate IS NOT NULL AND bloqueado_ate > now()) AS bloqueado
                 FROM usuarios
                WHERE (%s OR ativo)
                ORDER BY ativo DESC, nome""",
            (incluir_inativos,),
        )
        usuarios = [dict(r) for r in cur.fetchall()]
        for u in usuarios:
            u["papeis"] = _papeis_do_usuario(cur, u["id"])
    return usuarios


@router.get("/{id_usuario}", response_model=UsuarioResponse)
def obter(id_usuario: int) -> dict:
    with get_cursor() as cur:
        cur.execute(
            """SELECT id, nome, email, telefone, ativo, ultimo_acesso,
                      (bloqueado_ate IS NOT NULL AND bloqueado_ate > now()) AS bloqueado
                 FROM usuarios WHERE id = %s""",
            (id_usuario,),
        )
        u = cur.fetchone()
        if not u:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        u = dict(u)
        u["papeis"] = _papeis_do_usuario(cur, id_usuario)
    return u


@router.post("", status_code=201)
def criar(body: UsuarioCreate, request: Request,
          ctx: Contexto = Depends(requer_permissao("admin.usuarios"))) -> dict:
    email = body.email.strip().lower()
    with get_cursor() as cur:
        cur.execute("SELECT 1 FROM usuarios WHERE lower(email) = %s", (email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Já existe usuário com este e-mail")
        cur.execute(
            """INSERT INTO usuarios (nome, email, senha_hash, telefone, ativo,
                                     trocar_senha, criado_por)
               VALUES (%s, %s, %s, %s, %s, true, %s) RETURNING id""",
            (body.nome.strip(), email, hash_senha(body.senha), body.telefone,
             body.ativo, ctx.id_usuario),
        )
        novo = cur.fetchone()["id"]
        _gravar_papeis(cur, novo, body.papeis)
        auditoria.registrar(
            cur, ctx.id_usuario, "usuario", novo, "criar",
            depois={"nome": body.nome, "email": email, "ativo": body.ativo},
            ip=request.client.host if request.client else None,
        )
    return {"id": novo, "message": "Usuário criado"}


@router.put("/{id_usuario}")
def atualizar(id_usuario: int, body: UsuarioUpdate, request: Request,
              ctx: Contexto = Depends(requer_permissao("admin.usuarios"))) -> dict:
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, nome, email, telefone, ativo FROM usuarios WHERE id = %s",
            (id_usuario,),
        )
        antes = cur.fetchone()
        if not antes:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        campos, valores = [], []
        for campo in ("nome", "telefone", "ativo"):
            valor = getattr(body, campo)
            if valor is not None:
                campos.append(f"{campo} = %s")
                valores.append(valor)
        if body.email:
            email = body.email.strip().lower()
            cur.execute(
                "SELECT 1 FROM usuarios WHERE lower(email) = %s AND id <> %s",
                (email, id_usuario),
            )
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="E-mail já usado por outro usuário")
            campos.append("email = %s")
            valores.append(email)
        if body.senha:
            campos.append("senha_hash = %s")
            valores.append(hash_senha(body.senha))
            campos.append("trocar_senha = true")

        if campos:
            valores.append(id_usuario)
            cur.execute(f"UPDATE usuarios SET {', '.join(campos)} WHERE id = %s", valores)

        # Desativar derruba as sessões abertas na hora.
        if body.ativo is False:
            cur.execute(
                """UPDATE sessoes SET revogada_em = now()
                    WHERE id_usuario = %s AND revogada_em IS NULL""",
                (id_usuario,),
            )
        if body.papeis is not None:
            _gravar_papeis(cur, id_usuario, body.papeis)

        auditoria.registrar(
            cur, ctx.id_usuario, "usuario", id_usuario, "atualizar",
            antes=dict(antes), depois=body.model_dump(exclude_none=True),
            ip=request.client.host if request.client else None,
        )
    return {"id": id_usuario, "message": "Usuário atualizado"}


@router.post("/{id_usuario}/desbloquear")
def desbloquear(id_usuario: int,
                ctx: Contexto = Depends(requer_permissao("admin.usuarios"))) -> dict:
    with get_cursor() as cur:
        cur.execute(
            "UPDATE usuarios SET bloqueado_ate = NULL, tentativas_login = 0 WHERE id = %s",
            (id_usuario,),
        )
        auditoria.registrar(cur, ctx.id_usuario, "usuario", id_usuario, "desbloquear")
    return {"message": "Usuário desbloqueado"}


@router.delete("/{id_usuario}")
def desativar(id_usuario: int,
              ctx: Contexto = Depends(requer_permissao("admin.usuarios"))) -> dict:
    """Nunca apaga: desativa. Usuário apagado levaria a auditoria junto."""
    if id_usuario == ctx.id_usuario:
        raise HTTPException(status_code=400, detail="Você não pode desativar a si mesmo")
    with get_cursor() as cur:
        cur.execute("UPDATE usuarios SET ativo = false WHERE id = %s", (id_usuario,))
        cur.execute(
            "UPDATE sessoes SET revogada_em = now() WHERE id_usuario = %s AND revogada_em IS NULL",
            (id_usuario,),
        )
        auditoria.registrar(cur, ctx.id_usuario, "usuario", id_usuario, "desativar")
    return {"message": "Usuário desativado"}
