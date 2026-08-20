"""Cadastros de apoio: setores, locais de estoque, categorias e unidades de medida.

Os quatro moram no mesmo arquivo de propósito: são tabelas pequenas, editadas
na mesma tela e sempre lidas juntas. Leitura só exige autenticação (o formulário
de produto precisa das quatro); a escrita exige a chave do módulo.
"""

from fastapi import APIRouter, Depends, HTTPException

import auditoria
from database import get_cursor
from models.cadastros import (
    CategoriaCreate,
    CategoriaResponse,
    CategoriaUpdate,
    GRANDEZAS,
    LocalCreate,
    LocalResponse,
    LocalUpdate,
    SetorCreate,
    SetorResponse,
    SetorUpdate,
    TIPOS_CATEGORIA,
    TIPOS_LOCAL,
    UnidadeMedidaCreate,
    UnidadeMedidaResponse,
    UnidadeMedidaUpdate,
)
from seguranca import Contexto, contexto_atual, requer_permissao

router = APIRouter(tags=["cadastros"])


def _valida(valor: str | None, aceitos: tuple[str, ...], campo: str) -> None:
    if valor is not None and valor not in aceitos:
        raise HTTPException(
            status_code=400, detail=f"{campo} inválido. Use: {', '.join(aceitos)}"
        )


def _sets(dados: dict) -> tuple[str, list]:
    return ", ".join(f"{c} = %s" for c in dados), list(dados.values())


# ================================================================ setores


@router.get("/setores", response_model=list[SetorResponse])
def listar_setores(incluir_inativos: bool = False, ctx: Contexto = Depends(contexto_atual)):
    with get_cursor() as cur:
        cur.execute(
            """SELECT id, nome, cor, ordem, id_unidade, ativo FROM setores
                WHERE (%s OR ativo) ORDER BY ordem, nome""",
            (incluir_inativos,),
        )
        return [dict(r) for r in cur.fetchall()]


@router.post("/setores", status_code=201)
def criar_setor(body: SetorCreate,
                ctx: Contexto = Depends(requer_permissao("cadastros.setores"))) -> dict:
    with get_cursor() as cur:
        _recusar_repetido(
            cur,
            """SELECT 1 FROM setores
                WHERE lower(nome) = lower(%s) AND coalesce(id_unidade, 0) = coalesce(%s, 0)""",
            (body.nome.strip(), body.id_unidade),
            f"Já existe um setor chamado {body.nome.strip()}.",
        )
        cur.execute(
            """INSERT INTO setores (nome, cor, ordem, id_unidade, ativo)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (body.nome.strip(), body.cor, body.ordem, body.id_unidade, body.ativo),
        )
        novo = cur.fetchone()["id"]
        auditoria.registrar(cur, ctx.id_usuario, "setor", novo, "criar", depois=body.model_dump())
    return {"id": novo, "message": "Setor criado"}


@router.put("/setores/{id_setor}")
def atualizar_setor(id_setor: int, body: SetorUpdate,
                    ctx: Contexto = Depends(requer_permissao("cadastros.setores"))) -> dict:
    dados = body.model_dump(exclude_unset=True)
    if not dados:
        raise HTTPException(status_code=400, detail="Nada para atualizar")
    with get_cursor() as cur:
        cur.execute("SELECT nome, cor, ordem, ativo FROM setores WHERE id = %s", (id_setor,))
        antes = cur.fetchone()
        if not antes:
            raise HTTPException(status_code=404, detail="Setor não encontrado")
        sets, valores = _sets(dados)
        cur.execute(f"UPDATE setores SET {sets} WHERE id = %s", [*valores, id_setor])
        auditoria.registrar(cur, ctx.id_usuario, "setor", id_setor, "atualizar",
                            antes=dict(antes), depois=dados)
    return {"message": "Setor atualizado"}


@router.delete("/setores/{id_setor}")
def desativar_setor(id_setor: int,
                    ctx: Contexto = Depends(requer_permissao("cadastros.setores"))) -> dict:
    with get_cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM produtos WHERE id_setor = %s", (id_setor,))
        if cur.fetchone()["n"]:
            # Nunca apaga o que já foi usado: o histórico ficaria sem nome.
            cur.execute("UPDATE setores SET ativo = false WHERE id = %s", (id_setor,))
            auditoria.registrar(cur, ctx.id_usuario, "setor", id_setor, "desativar")
            return {"message": "Setor tem produtos e foi desativado, não excluído"}
        cur.execute("DELETE FROM setores WHERE id = %s", (id_setor,))
        auditoria.registrar(cur, ctx.id_usuario, "setor", id_setor, "excluir")
    return {"message": "Setor excluído"}


# ================================================================ locais


@router.get("/locais", response_model=list[LocalResponse])
def listar_locais(incluir_inativos: bool = False, ctx: Contexto = Depends(contexto_atual)):
    with get_cursor() as cur:
        cur.execute(
            """SELECT id, id_unidade, nome, tipo, principal, ativo FROM locais_estoque
                WHERE (%s OR ativo) ORDER BY principal DESC, nome""",
            (incluir_inativos,),
        )
        linhas = [dict(r) for r in cur.fetchall()]
    return [l for l in linhas if ctx.ve_unidade(l["id_unidade"])]


def _recusar_repetido(cur, sql: str, parametros: tuple, mensagem: str) -> None:
    """Nome repetido é 409 com frase, não 500.

    A unicidade é do banco (é o certo), mas deixar a constraint estourar
    devolvia "Internal Server Error" para quem só digitou duas vezes o mesmo
    nome — e isso acontece no primeiro dia, cadastrando as tabelas de apoio.
    """
    cur.execute(sql, parametros)
    if cur.fetchone():
        raise HTTPException(status_code=409, detail=mensagem)


@router.post("/locais", status_code=201)
def criar_local(body: LocalCreate,
                ctx: Contexto = Depends(requer_permissao("cadastros.locais"))) -> dict:
    _valida(body.tipo, TIPOS_LOCAL, "tipo")
    with get_cursor() as cur:
        id_unidade = body.id_unidade
        if id_unidade is None:
            cur.execute("SELECT id FROM unidades WHERE matriz LIMIT 1")
            linha = cur.fetchone()
            if not linha:
                raise HTTPException(status_code=400, detail="Nenhuma loja cadastrada")
            id_unidade = linha["id"]
        _recusar_repetido(
            cur,
            "SELECT 1 FROM locais_estoque WHERE id_unidade = %s AND lower(nome) = lower(%s)",
            (id_unidade, body.nome.strip()),
            f"Já existe um local chamado {body.nome.strip()}.",
        )
        if body.principal:
            cur.execute(
                "UPDATE locais_estoque SET principal = false WHERE id_unidade = %s", (id_unidade,)
            )
        # O PRIMEIRO local da loja é o principal, marque-se ou não a caixinha.
        # Quem cadastra "Balcão" e vai contar o estoque não tem por que saber o
        # que "principal" quer dizer — e as telas usam o principal como padrão.
        principal = body.principal
        if not principal:
            cur.execute(
                "SELECT 1 FROM locais_estoque WHERE id_unidade = %s AND principal", (id_unidade,)
            )
            principal = cur.fetchone() is None
        cur.execute(
            """INSERT INTO locais_estoque (id_unidade, nome, tipo, principal, ativo)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (id_unidade, body.nome.strip(), body.tipo, principal, body.ativo),
        )
        novo = cur.fetchone()["id"]
        auditoria.registrar(cur, ctx.id_usuario, "local", novo, "criar",
                            depois=body.model_dump(), id_unidade=id_unidade)
    return {"id": novo, "message": "Local criado"}


@router.put("/locais/{id_local}")
def atualizar_local(id_local: int, body: LocalUpdate,
                    ctx: Contexto = Depends(requer_permissao("cadastros.locais"))) -> dict:
    dados = body.model_dump(exclude_unset=True)
    _valida(dados.get("tipo"), TIPOS_LOCAL, "tipo")
    if not dados:
        raise HTTPException(status_code=400, detail="Nada para atualizar")
    with get_cursor() as cur:
        cur.execute(
            "SELECT id_unidade, nome, tipo, principal, ativo FROM locais_estoque WHERE id = %s",
            (id_local,),
        )
        antes = cur.fetchone()
        if not antes:
            raise HTTPException(status_code=404, detail="Local não encontrado")
        if dados.get("principal"):
            cur.execute(
                "UPDATE locais_estoque SET principal = false WHERE id_unidade = %s AND id <> %s",
                (antes["id_unidade"], id_local),
            )
        sets, valores = _sets(dados)
        cur.execute(f"UPDATE locais_estoque SET {sets} WHERE id = %s", [*valores, id_local])
        auditoria.registrar(cur, ctx.id_usuario, "local", id_local, "atualizar",
                            antes=dict(antes), depois=dados)
    return {"message": "Local atualizado"}


@router.delete("/locais/{id_local}")
def desativar_local(id_local: int,
                    ctx: Contexto = Depends(requer_permissao("cadastros.locais"))) -> dict:
    with get_cursor() as cur:
        cur.execute("UPDATE locais_estoque SET ativo = false WHERE id = %s", (id_local,))
        auditoria.registrar(cur, ctx.id_usuario, "local", id_local, "desativar")
    return {"message": "Local desativado"}


# ================================================================ categorias


@router.get("/categorias", response_model=list[CategoriaResponse])
def listar_categorias(incluir_inativas: bool = False, ctx: Contexto = Depends(contexto_atual)):
    """Devolve a árvore achatada, já com o caminho montado e em ordem de leitura."""
    with get_cursor() as cur:
        cur.execute(
            """
            WITH RECURSIVE arvore AS (
                SELECT c.id, c.id_pai, c.nome, c.tipo, c.ordem, c.ativo,
                       c.nome::text AS caminho, 0 AS nivel,
                       lpad(c.ordem::text, 5, '0') || c.nome AS chave
                  FROM categorias c WHERE c.id_pai IS NULL
                UNION ALL
                SELECT f.id, f.id_pai, f.nome, f.tipo, f.ordem, f.ativo,
                       a.caminho || ' › ' || f.nome, a.nivel + 1,
                       a.chave || '/' || lpad(f.ordem::text, 5, '0') || f.nome
                  FROM categorias f JOIN arvore a ON a.id = f.id_pai
            )
            SELECT a.id, a.id_pai, a.nome, a.caminho, a.nivel, a.tipo, a.ordem, a.ativo,
                   (SELECT count(*) FROM produtos p WHERE p.id_categoria = a.id) AS produtos
              FROM arvore a
             WHERE (%s OR a.ativo)
             ORDER BY a.chave
            """,
            (incluir_inativas,),
        )
        return [dict(r) for r in cur.fetchall()]


def _descendentes(cur, id_categoria: int) -> set[int]:
    cur.execute(
        """
        WITH RECURSIVE abaixo AS (
            SELECT id FROM categorias WHERE id_pai = %s
            UNION ALL
            SELECT c.id FROM categorias c JOIN abaixo a ON a.id = c.id_pai
        ) SELECT id FROM abaixo
        """,
        (id_categoria,),
    )
    return {r["id"] for r in cur.fetchall()}


@router.post("/categorias", status_code=201)
def criar_categoria(body: CategoriaCreate,
                    ctx: Contexto = Depends(requer_permissao("cadastros.categorias"))) -> dict:
    _valida(body.tipo, TIPOS_CATEGORIA, "tipo")
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO categorias (nome, id_pai, tipo, ordem, ativo)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (body.nome.strip(), body.id_pai, body.tipo, body.ordem, body.ativo),
        )
        nova = cur.fetchone()["id"]
        auditoria.registrar(cur, ctx.id_usuario, "categoria", nova, "criar",
                            depois=body.model_dump())
    return {"id": nova, "message": "Categoria criada"}


@router.put("/categorias/{id_categoria}")
def atualizar_categoria(id_categoria: int, body: CategoriaUpdate,
                        ctx: Contexto = Depends(requer_permissao("cadastros.categorias"))) -> dict:
    dados = body.model_dump(exclude_unset=True)
    _valida(dados.get("tipo"), TIPOS_CATEGORIA, "tipo")
    if not dados:
        raise HTTPException(status_code=400, detail="Nada para atualizar")
    with get_cursor() as cur:
        cur.execute(
            "SELECT nome, id_pai, tipo, ordem, ativo FROM categorias WHERE id = %s",
            (id_categoria,),
        )
        antes = cur.fetchone()
        if not antes:
            raise HTTPException(status_code=404, detail="Categoria não encontrada")

        novo_pai = dados.get("id_pai")
        if novo_pai is not None:
            # Pai que está abaixo dela criaria um ciclo — e a consulta recursiva
            # da árvore entraria em laço infinito.
            if novo_pai == id_categoria or novo_pai in _descendentes(cur, id_categoria):
                raise HTTPException(
                    status_code=400,
                    detail="Uma categoria não pode ficar dentro dela mesma ou de uma filha",
                )

        sets, valores = _sets(dados)
        cur.execute(f"UPDATE categorias SET {sets} WHERE id = %s", [*valores, id_categoria])
        auditoria.registrar(cur, ctx.id_usuario, "categoria", id_categoria, "atualizar",
                            antes=dict(antes), depois=dados)
    return {"message": "Categoria atualizada"}


@router.delete("/categorias/{id_categoria}")
def excluir_categoria(id_categoria: int,
                      ctx: Contexto = Depends(requer_permissao("cadastros.categorias"))) -> dict:
    with get_cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM categorias WHERE id_pai = %s", (id_categoria,))
        if cur.fetchone()["n"]:
            raise HTTPException(
                status_code=409, detail="Categoria tem subcategorias. Mova ou exclua elas antes."
            )
        cur.execute("SELECT count(*) AS n FROM produtos WHERE id_categoria = %s", (id_categoria,))
        if cur.fetchone()["n"]:
            cur.execute("UPDATE categorias SET ativo = false WHERE id = %s", (id_categoria,))
            auditoria.registrar(cur, ctx.id_usuario, "categoria", id_categoria, "desativar")
            return {"message": "Categoria tem produtos e foi desativada, não excluída"}
        cur.execute("DELETE FROM categorias WHERE id = %s", (id_categoria,))
        auditoria.registrar(cur, ctx.id_usuario, "categoria", id_categoria, "excluir")
    return {"message": "Categoria excluída"}


# ================================================================ unidades de medida


@router.get("/unidades-medida", response_model=list[UnidadeMedidaResponse])
def listar_um(incluir_inativas: bool = False, ctx: Contexto = Depends(contexto_atual)):
    with get_cursor() as cur:
        cur.execute(
            """SELECT sigla, nome, grandeza, fator_base, ativo FROM unidades_medida
                WHERE (%s OR ativo) ORDER BY grandeza, fator_base DESC, sigla""",
            (incluir_inativas,),
        )
        return [dict(r) for r in cur.fetchall()]


@router.post("/unidades-medida", status_code=201)
def criar_um(body: UnidadeMedidaCreate,
             ctx: Contexto = Depends(requer_permissao("cadastros.unidades_medida"))) -> dict:
    _valida(body.grandeza, GRANDEZAS, "grandeza")
    sigla = body.sigla.strip().upper()
    with get_cursor() as cur:
        cur.execute("SELECT 1 FROM unidades_medida WHERE sigla = %s", (sigla,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Já existe unidade com esta sigla")
        cur.execute(
            """INSERT INTO unidades_medida (sigla, nome, grandeza, fator_base, ativo)
               VALUES (%s, %s, %s, %s, %s)""",
            (sigla, body.nome.strip(), body.grandeza, body.fator_base, body.ativo),
        )
        auditoria.registrar(cur, ctx.id_usuario, "unidade_medida", sigla, "criar",
                            depois=body.model_dump())
    return {"sigla": sigla, "message": "Unidade criada"}


@router.put("/unidades-medida/{sigla}")
def atualizar_um(sigla: str, body: UnidadeMedidaUpdate,
                 ctx: Contexto = Depends(requer_permissao("cadastros.unidades_medida"))) -> dict:
    dados = body.model_dump(exclude_unset=True)
    _valida(dados.get("grandeza"), GRANDEZAS, "grandeza")
    if not dados:
        raise HTTPException(status_code=400, detail="Nada para atualizar")
    sigla = sigla.upper()
    with get_cursor() as cur:
        cur.execute(
            "SELECT nome, grandeza, fator_base, ativo FROM unidades_medida WHERE sigla = %s",
            (sigla,),
        )
        antes = cur.fetchone()
        if not antes:
            raise HTTPException(status_code=404, detail="Unidade não encontrada")
        sets, valores = _sets(dados)
        cur.execute(f"UPDATE unidades_medida SET {sets} WHERE sigla = %s", [*valores, sigla])
        auditoria.registrar(cur, ctx.id_usuario, "unidade_medida", sigla, "atualizar",
                            antes=dict(antes), depois=dados)
    return {"message": "Unidade atualizada"}
