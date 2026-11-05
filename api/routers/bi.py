"""O Estúdio BI (migração 149, `services/bi.py`).

🔑 **Pedido do dono (05/11/2026):** relatórios personalizados com ligações configuráveis, criados
pelo administrador e publicados para quem ele escolher.

- Criar, editar, consultar livremente e apagar: `bi.estudio`.
- Ver e rodar um relatório salvo: quem o relatório permite (`visibilidade`). ⚠️ Rodar um relatório
  publicado NÃO exige a permissão de cada fonte: publicar para alguém é a decisão de quem tem
  `bi.estudio` — é para isso que a publicação existe. O recorte de loja continua valendo sempre.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from psycopg2.extras import Json

import auditoria
from database import get_cursor
from models.bi import PeriodoBI, RelatorioBIIn, DefinicaoBI
from routers.exportacoes import _render
from seguranca import Contexto, contexto_atual, requer_permissao, unidade_atual
from services import bi
from services import exportacao_catalogo as catalogo_motor

router = APIRouter(prefix="/bi", tags=["estúdio bi"])
_ESTUDIO = requer_permissao("bi.estudio")


def _ve(cur, ctx: Contexto, r: dict) -> bool:
    if ctx.pode("bi.estudio"):
        return True
    if r["visibilidade"] == "EU":
        return r["criado_por"] == ctx.id_usuario
    if r["visibilidade"] == "TODOS":
        return ctx.pode("relatorios.personalizados")
    cur.execute("SELECT 1 FROM usuario_papeis WHERE id_usuario = %s AND id_papel = ANY(%s)",
                (ctx.id_usuario, r["papeis_vistos"]))
    return cur.fetchone() is not None


def _obter(cur, ctx: Contexto, id_rel: int) -> dict:
    cur.execute("""SELECT r.*, u.nome AS criado_por_nome FROM bi_relatorios r
                     LEFT JOIN usuarios u ON u.id = r.criado_por
                    WHERE r.id = %s AND r.ativo""", (id_rel,))
    r = cur.fetchone()
    # ⚠️ Quem não pode ver recebe 404, não 403: nem a existência do relatório é dele.
    if not r or not _ve(cur, ctx, r):
        raise HTTPException(status_code=404, detail="Relatório personalizado não encontrado")
    return dict(r)


def _resumo(r: dict, ctx: Contexto) -> dict:
    return {"id": r["id"], "nome": r["nome"], "visibilidade": r["visibilidade"],
            "papeis_vistos": r["papeis_vistos"], "no_menu": r["no_menu"],
            "criado_por": r.get("criado_por_nome"), "atualizado_em": r["atualizado_em"],
            "pode_editar": ctx.pode("bi.estudio")}


@router.get("/fontes")
def fontes(ctx: Contexto = Depends(_ESTUDIO)) -> dict:
    """As fontes, os campos e as ligações conhecidas que ESTA pessoa pode usar."""
    return bi.catalogo(ctx.pode)


@router.post("/consultar")
def consultar(body: DefinicaoBI, ctx: Contexto = Depends(_ESTUDIO)) -> dict:
    """A prévia do estúdio: roda a definição sem salvar."""
    with get_cursor() as cur:
        u = unidade_atual(cur, ctx)
        return bi.executar(cur, body.model_dump(mode="json"), u, ctx.pode)


@router.get("/relatorios")
def listar(ctx: Contexto = Depends(contexto_atual)) -> list[dict]:
    with get_cursor() as cur:
        cur.execute("""SELECT r.*, u.nome AS criado_por_nome FROM bi_relatorios r
                         LEFT JOIN usuarios u ON u.id = r.criado_por
                        WHERE r.ativo ORDER BY lower(r.nome)""")
        return [_resumo(dict(r), ctx) for r in cur.fetchall() if _ve(cur, ctx, r)]


@router.get("/relatorios/{id_rel}")
def obter(id_rel: int, ctx: Contexto = Depends(contexto_atual)) -> dict:
    with get_cursor() as cur:
        r = _obter(cur, ctx, id_rel)
    return {**_resumo(r, ctx), "definicao": r["definicao"]}


def _validar_e_gravar(cur, ctx: Contexto, body: RelatorioBIIn, id_rel: int | None) -> int:
    definicao = body.definicao.model_dump(mode="json")
    # Salvar valida igual a rodar: definição que não monta não entra.
    bi.montar(definicao, unidade_atual(cur, ctx), ctx.pode)
    cur.execute("SELECT id FROM bi_relatorios WHERE ativo AND lower(nome) = lower(%s) AND id IS DISTINCT FROM %s",
                (body.nome.strip(), id_rel))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail=f"Já existe um relatório chamado “{body.nome.strip()}”")
    papeis = body.papeis_vistos if body.visibilidade == "PAPEIS" else []
    if body.visibilidade == "PAPEIS" and not papeis:
        raise HTTPException(status_code=422, detail="Escolha ao menos um papel que pode ver o relatório")
    if id_rel is None:
        cur.execute("""INSERT INTO bi_relatorios (nome, definicao, visibilidade, papeis_vistos, no_menu, criado_por)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                    (body.nome.strip(), Json(definicao), body.visibilidade, papeis, body.no_menu, ctx.id_usuario))
        novo = cur.fetchone()["id"]
        auditoria.registrar(cur, ctx.id_usuario, "bi_relatorio", novo, "criar",
                            depois={"nome": body.nome.strip(), "visibilidade": body.visibilidade})
        return novo
    cur.execute("""UPDATE bi_relatorios SET nome = %s, definicao = %s, visibilidade = %s, papeis_vistos = %s,
                          no_menu = %s, atualizado_em = now()
                    WHERE id = %s AND ativo""",
                (body.nome.strip(), Json(definicao), body.visibilidade, papeis, body.no_menu, id_rel))
    if not cur.rowcount:
        raise HTTPException(status_code=404, detail="Relatório personalizado não encontrado")
    auditoria.registrar(cur, ctx.id_usuario, "bi_relatorio", id_rel, "alterar",
                        depois={"nome": body.nome.strip(), "visibilidade": body.visibilidade})
    return id_rel


@router.post("/relatorios")
def criar(body: RelatorioBIIn, ctx: Contexto = Depends(_ESTUDIO)) -> dict:
    with get_cursor() as cur:
        return {"id": _validar_e_gravar(cur, ctx, body, None)}


@router.put("/relatorios/{id_rel}")
def alterar(id_rel: int, body: RelatorioBIIn, ctx: Contexto = Depends(_ESTUDIO)) -> dict:
    with get_cursor() as cur:
        return {"id": _validar_e_gravar(cur, ctx, body, id_rel)}


@router.delete("/relatorios/{id_rel}")
def apagar(id_rel: int, ctx: Contexto = Depends(_ESTUDIO)) -> dict:
    with get_cursor() as cur:
        cur.execute("UPDATE bi_relatorios SET ativo = false, atualizado_em = now() WHERE id = %s AND ativo",
                    (id_rel,))
        if not cur.rowcount:
            raise HTTPException(status_code=404, detail="Relatório personalizado não encontrado")
        auditoria.registrar(cur, ctx.id_usuario, "bi_relatorio", id_rel, "apagar")
    return {"ok": True}


def _rodar(cur, ctx: Contexto, r: dict, de: date | None, ate: date | None) -> dict:
    d = dict(r["definicao"])
    if de:
        d["de"] = de.isoformat()
    if ate:
        d["ate"] = ate.isoformat()
    # Publicado = liberado por quem tem `bi.estudio`: as fontes não pedem a permissão de quem vê.
    return bi.executar(cur, d, unidade_atual(cur, ctx), lambda _chave: True)


@router.post("/relatorios/{id_rel}/executar")
def executar(id_rel: int, body: PeriodoBI | None = None, ctx: Contexto = Depends(contexto_atual)) -> dict:
    with get_cursor() as cur:
        r = _obter(cur, ctx, id_rel)
        res = _rodar(cur, ctx, r, body.de if body else None, body.ate if body else None)
    return {**res, "nome": r["nome"], "visual": r["definicao"].get("visual", "barras")}


@router.get("/relatorios/{id_rel}/exportar")
def exportar(id_rel: int, formato: str = Query("pdf", pattern="^(pdf|csv)$"),
             de: date | None = None, ate: date | None = None,
             ctx: Contexto = Depends(contexto_atual)) -> Response:
    """O relatório personalizado em PDF (Imprimir) ou planilha (Gerar planilha)."""
    with get_cursor() as cur:
        r = _obter(cur, ctx, id_rel)
        res = _rodar(cur, ctx, r, de, ate)
    with get_cursor() as cur:
        timbre = catalogo_motor.papel_timbrado(cur)
        auditoria.registrar(cur, ctx.id_usuario, "exportacao", f"bi:{id_rel}", "exportar",
                            depois={"formato": formato, "linhas": len(res["linhas"])})
    cols = [(c["chave"], c["rotulo"]) for c in res["colunas"]]
    linhas = [dict(zip([c[0] for c in cols], linha)) for linha in res["linhas"]]
    periodo = [("Período", f"{de or r['definicao'].get('de') or 'início'} a {ate or r['definicao'].get('ate') or 'hoje'}")]
    saida = catalogo_motor.Saida(linhas=linhas, colunas=cols, titulo=r["nome"], resumo=periodo)
    return _render(saida, f"bi-{id_rel}", formato, timbre, ctx.nome)
