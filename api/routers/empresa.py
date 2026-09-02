"""Empresa, lojas e parâmetros de operação.

Leitura é liberada a qualquer autenticado (o cabeçalho do app mostra o nome e a
logo). Escrita exige a chave do módulo — o padrão de leitura x mutação da casa.
"""

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile

import arquivos
import auditoria
from database import get_cursor
from models.empresa import (
    EmpresaResponse,
    EmpresaUpdate,
    ParametrosResponse,
    ParametrosUpdate,
    UnidadeCreate,
    UnidadeResponse,
    UnidadeUpdate,
)
from seguranca import Contexto, contexto_atual, requer_permissao
from services import periodos

router = APIRouter(tags=["empresa"])

_CAMPOS_EMPRESA = list(EmpresaUpdate.model_fields.keys())
_CAMPOS_UNIDADE = list(UnidadeCreate.model_fields.keys())
_CAMPOS_PARAM = list(ParametrosUpdate.model_fields.keys())


# ---------------------------------------------------------------- empresa


@router.get("/empresa", response_model=EmpresaResponse)
def obter_empresa(ctx: Contexto = Depends(contexto_atual)) -> dict:
    with get_cursor() as cur:
        cur.execute(f"SELECT id, {', '.join(_CAMPOS_EMPRESA)} FROM empresa WHERE id = 1")
        e = cur.fetchone()
        if not e:
            raise HTTPException(status_code=404, detail="Empresa não configurada")
    return dict(e)


@router.put("/empresa")
def atualizar_empresa(body: EmpresaUpdate, request: Request,
                      ctx: Contexto = Depends(requer_permissao("admin.empresa"))) -> dict:
    dados = body.model_dump(exclude_unset=True)
    if not dados:
        raise HTTPException(status_code=400, detail="Nada para atualizar")
    with get_cursor() as cur:
        cur.execute(f"SELECT {', '.join(_CAMPOS_EMPRESA)} FROM empresa WHERE id = 1")
        antes = cur.fetchone()
        sets = ", ".join(f"{c} = %s" for c in dados)
        cur.execute(
            f"UPDATE empresa SET {sets}, atualizado_em = now(), atualizado_por = %s WHERE id = 1",
            [*dados.values(), ctx.id_usuario],
        )
        auditoria.registrar(
            cur, ctx.id_usuario, "empresa", 1, "atualizar",
            antes=dict(antes) if antes else None, depois=dados,
            ip=request.client.host if request.client else None,
        )
    return {"message": "Empresa atualizada"}


@router.post("/empresa/logo")
async def enviar_logo(
    arquivo: UploadFile = File(...),
    ctx: Contexto = Depends(requer_permissao("admin.empresa")),
) -> dict:
    """Recebe a imagem, guarda e já grava a URL na empresa.

    🔑 **Gravar a nova, apontar para ela e apagar a antiga é UMA transação.**
    Antes eram três, e entre a segunda e a terceira havia uma janela em que a
    logo antiga já tinha sido apagada e a empresa ainda apontava para ela: a
    logo sumia da barra e do cabeçalho dos PDFs, sem volta e sem nada
    explicando. Ou as três acontecem, ou nenhuma.
    """
    # Os bytes vêm ANTES da transação: ler 2 MB da rede com uma conexão do pool
    # presa é prendê-la pelo tempo do envio, não pelo tempo do banco.
    conteudo, tipo, extensao = await arquivos.ler_enviada(arquivo)

    with get_cursor() as cur:
        cur.execute("SELECT logo_url FROM empresa WHERE id = 1")
        antes = cur.fetchone()
        anterior = antes["logo_url"] if antes else None

        url = arquivos.gravar(cur, conteudo, tipo, extensao, "logo-empresa")
        cur.execute(
            "UPDATE empresa SET logo_url = %s, atualizado_em = now(), atualizado_por = %s WHERE id = 1",
            (url, ctx.id_usuario),
        )
        # Só agora — a empresa já aponta para a nova.
        arquivos.remover(anterior, cur)
        auditoria.registrar(
            cur, ctx.id_usuario, "empresa", 1, "logo",
            antes={"logo_url": anterior}, depois={"logo_url": url},
        )
    return {"logo_url": url, "message": "Logo atualizada"}


@router.delete("/empresa/logo")
def remover_logo(ctx: Contexto = Depends(requer_permissao("admin.empresa"))) -> dict:
    with get_cursor() as cur:
        cur.execute("SELECT logo_url FROM empresa WHERE id = 1")
        atual = cur.fetchone()
        cur.execute(
            "UPDATE empresa SET logo_url = NULL, atualizado_em = now(), atualizado_por = %s WHERE id = 1",
            (ctx.id_usuario,),
        )
        auditoria.registrar(
            cur, ctx.id_usuario, "empresa", 1, "logo_remover",
            antes={"logo_url": atual["logo_url"] if atual else None},
        )
    arquivos.remover(atual["logo_url"] if atual else None)
    return {"message": "Logo removida"}


# ---------------------------------------------------------------- lojas


@router.get("/unidades", response_model=list[UnidadeResponse])
def listar_unidades(incluir_inativas: bool = False,
                    ctx: Contexto = Depends(contexto_atual)) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            f"""SELECT id, {', '.join(_CAMPOS_UNIDADE)} FROM unidades
                 WHERE (%s OR ativo) ORDER BY matriz DESC, nome""",
            (incluir_inativas,),
        )
        linhas = [dict(r) for r in cur.fetchall()]
    # Quem não é de todas as lojas só enxerga as suas.
    return [u for u in linhas if ctx.ve_unidade(u["id"])]


@router.post("/unidades", status_code=201)
def criar_unidade(body: UnidadeCreate,
                  ctx: Contexto = Depends(requer_permissao("admin.unidades"))) -> dict:
    dados = body.model_dump()
    with get_cursor() as cur:
        if dados.get("matriz"):
            cur.execute("UPDATE unidades SET matriz = false WHERE matriz")
        colunas = ", ".join(dados)
        marcas = ", ".join(["%s"] * len(dados))
        cur.execute(
            f"INSERT INTO unidades ({colunas}) VALUES ({marcas}) RETURNING id",
            list(dados.values()),
        )
        nova = cur.fetchone()["id"]
        cur.execute("INSERT INTO parametros (id_unidade) VALUES (%s)", (nova,))
        # 🔑 **A loja nasce com um LOCAL, senão ela nasce inutilizável.** Sem
        # local de estoque nada se movimenta — nem entrada, nem produção, nem
        # inventário —, e a mensagem que aparecia era "Local não encontrado",
        # que não diz o que fazer. Quem abre a segunda loja não deveria
        # descobrir isso na primeira nota.
        # ⚠️ Nasce PRINCIPAL porque estoque, produção e inventário usam o
        # principal como padrão, e loja sem nenhum marcado já custou um 404 com
        # o local à vista na tela (migração 016). O nome é genérico de
        # propósito: é para ser renomeado, não para fingir que se sabe como a
        # casa chama a prateleira dela.
        cur.execute(
            """INSERT INTO locais_estoque (id_unidade, nome, tipo, principal, ativo)
               VALUES (%s, 'Estoque', 'SECO', true, true)""",
            (nova,),
        )
        auditoria.registrar(cur, ctx.id_usuario, "unidade", nova, "criar", depois=dados)
    return {"id": nova, "message": "Loja criada"}


@router.put("/unidades/{id_unidade}")
def atualizar_unidade(id_unidade: int, body: UnidadeUpdate,
                      ctx: Contexto = Depends(requer_permissao("admin.unidades"))) -> dict:
    dados = body.model_dump(exclude_unset=True)
    if not dados:
        raise HTTPException(status_code=400, detail="Nada para atualizar")
    with get_cursor() as cur:
        cur.execute(
            f"SELECT {', '.join(_CAMPOS_UNIDADE)} FROM unidades WHERE id = %s", (id_unidade,)
        )
        antes = cur.fetchone()
        if not antes:
            raise HTTPException(status_code=404, detail="Loja não encontrada")
        if dados.get("matriz"):
            cur.execute("UPDATE unidades SET matriz = false WHERE matriz AND id <> %s", (id_unidade,))
        sets = ", ".join(f"{c} = %s" for c in dados)
        cur.execute(
            f"UPDATE unidades SET {sets} WHERE id = %s", [*dados.values(), id_unidade]
        )
        auditoria.registrar(
            cur, ctx.id_usuario, "unidade", id_unidade, "atualizar",
            antes=dict(antes), depois=dados, id_unidade=id_unidade,
        )
    return {"message": "Loja atualizada"}


# ---------------------------------------------------------------- parâmetros


@router.get("/unidades/{id_unidade}/parametros", response_model=ParametrosResponse)
def obter_parametros(id_unidade: int, ctx: Contexto = Depends(contexto_atual)) -> dict:
    if not ctx.ve_unidade(id_unidade):
        raise HTTPException(status_code=404, detail="Loja não encontrada")
    with get_cursor() as cur:
        cur.execute(
            f"SELECT id_unidade, {', '.join(_CAMPOS_PARAM)} FROM parametros WHERE id_unidade = %s",
            (id_unidade,),
        )
        p = cur.fetchone()
        if not p:
            cur.execute("INSERT INTO parametros (id_unidade) VALUES (%s)", (id_unidade,))
            cur.execute(
                f"SELECT id_unidade, {', '.join(_CAMPOS_PARAM)} FROM parametros WHERE id_unidade = %s",
                (id_unidade,),
            )
            p = cur.fetchone()
    return dict(p)


@router.get("/unidades/{id_unidade}/parametros/previa-fechamento")
def previa_do_fechamento(
    id_unidade: int,
    ciclo: str = Query(default="MENSAL", pattern="^(DIARIO|SEMANAL|MENSAL)$"),
    dia_semana: int = Query(default=7, ge=1, le=7),
    dia_mes: int = Query(default=1, ge=1, le=28),
    ctx: Contexto = Depends(contexto_atual),
) -> dict:
    """Como ficaria o calendário do CMV com esta escolha — antes de salvar.

    ⚠️ Existe para NÃO haver uma segunda aritmética de período em TypeScript. A
    semana que fecha na quarta, o mês que começa no dia 26 e o dia corrido são
    três contas diferentes; escrevê-las de novo no front daria duas versões que
    concordam hoje e divergem no primeiro caso de borda — com o detalhe de que
    a divergência apareceria como um fechamento no período errado, que só se
    desfaz reabrindo.

    Os parâmetros vêm do formulário, não do banco: é uma prévia do que ainda
    não foi salvo.
    """
    if not ctx.ve_unidade(id_unidade):
        raise HTTPException(status_code=404, detail="Loja não encontrada")
    lista = periodos.periodos_ate_hoje(ciclo, 3, dia_semana=dia_semana, dia_mes=dia_mes)
    return {
        "descricao": periodos.descricao_do_ciclo(ciclo, dia_semana=dia_semana,
                                                 dia_mes=dia_mes),
        "periodos": [
            {"inicio": str(i), "fim": str(f), "rotulo": periodos.rotulo(i, f, ciclo)}
            for i, f in lista
        ],
    }


@router.put("/unidades/{id_unidade}/parametros")
def atualizar_parametros(id_unidade: int, body: ParametrosUpdate,
                         ctx: Contexto = Depends(requer_permissao("admin.unidades"))) -> dict:
    dados = body.model_dump(exclude_unset=True)
    if not dados:
        raise HTTPException(status_code=400, detail="Nada para atualizar")
    with get_cursor() as cur:
        cur.execute(
            f"SELECT {', '.join(_CAMPOS_PARAM)} FROM parametros WHERE id_unidade = %s",
            (id_unidade,),
        )
        antes = cur.fetchone()
        if not antes:
            raise HTTPException(status_code=404, detail="Loja sem parâmetros")
        sets = ", ".join(f"{c} = %s" for c in dados)
        cur.execute(
            f"UPDATE parametros SET {sets}, atualizado_em = now() WHERE id_unidade = %s",
            [*dados.values(), id_unidade],
        )
        auditoria.registrar(
            cur, ctx.id_usuario, "parametros", id_unidade, "atualizar",
            antes=dict(antes), depois=dados, id_unidade=id_unidade,
        )
    return {"message": "Parâmetros atualizados"}
