"""Contas a pagar — lançar, agendar, pagar (com comprovante), estornar, cancelar (migração 163).

🔑 Módulo Financeiro, etapa 1 (pedido do dono, 24/11/2026). Três chaves: ver, lançar (inclui
agendar e cancelar) e baixar (pagar, comprovante, estorno). Ver `services/contas_pagar.py`.
⚠️ O comprovante sai só por rota autenticada: `/arquivos/{nome}` é pública.
"""

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile

import arquivos
import auditoria
import relogio
from database import get_cursor
from models.contas_pagar import (
    AgendarRequest,
    CategoriaRequest,
    ContaCreate,
    ContaUpdate,
    EquipeRequest,
    IdsRequest,
    PagarRequest,
)
from paginacao import pagina
from seguranca import Contexto, requer_permissao, unidade_atual
from services import contas_pagar as servico

router = APIRouter(prefix="/contas-pagar", tags=["contas a pagar"])

VER, LANCAR, BAIXAR = "financeiro.pagar_ver", "financeiro.pagar_lancar", "financeiro.pagar_baixar"
_ver = requer_permissao(VER, LANCAR, BAIXAR)
_lancar = requer_permissao(LANCAR)
_baixar = requer_permissao(BAIXAR)
Situacao = Literal["A_PAGAR", "AGENDADO", "PAGO", "CANCELADO"]


def _auditar(cur, ctx, ids, acao, id_unidade, **depois):
    for i in ids:
        auditoria.registrar(cur, ctx.id_usuario, "conta_pagar", i, acao,
                            depois=depois or None, id_unidade=id_unidade)


@router.get("")
def listar(resposta: Response, status: list[Situacao] = Query(["A_PAGAR"]),
           de: date | None = None, ate: date | None = None,
           id_pessoa: int | None = None, id_categoria: int | None = None,
           atrasadas: bool = False, busca: str | None = Query(None, max_length=80),
           limite: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
           ctx: Contexto = Depends(_ver)) -> dict:
    """A lista e os totais do MESMO recorte (a soma é do recorte inteiro, não da página)."""
    with get_cursor() as cur:
        servico.baixar_e_registrar(cur)
        sql, p = servico.consulta(unidade_atual(cur, ctx), list(status), de, ate, id_pessoa,
                                  id_categoria, busca, atrasadas)
        itens = pagina(cur, sql, p, limite=limite, offset=offset, resposta=resposta)
        return {"itens": itens, "totais": servico.totais(cur, sql, p)}


@router.get("/resumo")
def resumo(ctx: Contexto = Depends(_ver)) -> dict:
    with get_cursor() as cur:
        servico.baixar_e_registrar(cur)
        return servico.resumo(cur, unidade_atual(cur, ctx))


@router.get("/painel")
def painel(de: date | None = None, ate: date | None = None,
           ctx: Contexto = Depends(_ver)) -> dict:
    """O painel do Financeiro (etapa 2): o que vem pela frente e o período (o mês, se vazio)."""
    hoje = relogio.hoje_da_casa()
    inicio = de or hoje.replace(day=1)
    fim = ate or (inicio.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    if fim < inicio:
        raise HTTPException(status_code=422, detail="O fim do período vem antes do início.")
    if (fim - inicio).days > 400:
        raise HTTPException(status_code=422, detail="Escolha um período de até um ano.")
    with get_cursor() as cur:
        servico.baixar_e_registrar(cur)
        return servico.painel(cur, unidade_atual(cur, ctx), inicio, fim)


@router.get("/categorias")
def categorias(ctx: Contexto = Depends(_ver)) -> list[dict]:
    with get_cursor() as cur:
        cur.execute("SELECT id, nome, ativo FROM financeiro_categorias ORDER BY ordem, lower(nome)")
        return [dict(r) for r in cur.fetchall()]


@router.post("/categorias", status_code=201)
def criar_categoria(body: CategoriaRequest, ctx: Contexto = Depends(_lancar)) -> dict:
    with get_cursor() as cur:
        cur.execute("SELECT id FROM financeiro_categorias WHERE lower(nome) = lower(%s)",
                    (body.nome.strip(),))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Já existe uma categoria com esse nome.")
        cur.execute("""INSERT INTO financeiro_categorias (nome, ativo, ordem)
                       VALUES (%s, %s, 80) RETURNING id""", (body.nome.strip(), body.ativo))
        novo = cur.fetchone()["id"]
        auditoria.registrar(cur, ctx.id_usuario, "financeiro_categoria", novo, "criar",
                            depois={"nome": body.nome})
    return {"id": novo, "message": f"Categoria {body.nome} criada."}


@router.put("/categorias/{id_categoria}")
def alterar_categoria(id_categoria: int, body: CategoriaRequest,
                      ctx: Contexto = Depends(_lancar)) -> dict:
    with get_cursor() as cur:
        cur.execute("""UPDATE financeiro_categorias SET nome = %s, ativo = %s WHERE id = %s
                       RETURNING id""", (body.nome.strip(), body.ativo, id_categoria))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Categoria não encontrada.")
        auditoria.registrar(cur, ctx.id_usuario, "financeiro_categoria", id_categoria, "alterar",
                            depois={"nome": body.nome, "ativo": body.ativo})
    return {"id": id_categoria, "message": "Categoria salva."}


@router.get("/pessoa/{id_pessoa}/ultimo")
def ultimo_da_pessoa(id_pessoa: int, ctx: Contexto = Depends(_ver)) -> dict:
    """O último valor e função da pessoa, para a equipe do dia vir preenchida."""
    with get_cursor() as cur:
        return servico.ultimo_da_pessoa(cur, unidade_atual(cur, ctx), id_pessoa) or {}


@router.post("", status_code=201)
def lancar(body: ContaCreate, ctx: Contexto = Depends(_lancar)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.lancar(cur, id_unidade, ctx.id_usuario, body.model_dump())
        _auditar(cur, ctx, [r["id"]], "lancar", id_unidade, pessoa=r["pessoa"],
                 valor=str(body.valor), vencimento=str(body.vencimento), descricao=body.descricao)
    return {**r, "message": f"Conta de {r['pessoa']} lançada."}


@router.post("/equipe", status_code=201)
def lancar_equipe(body: EquipeRequest, ctx: Contexto = Depends(_lancar)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.lancar_equipe(cur, id_unidade, ctx.id_usuario, body.model_dump())
        _auditar(cur, ctx, r["ids"], "lancar", id_unidade, lote=r["lote"], data=str(body.data))
    return r


@router.post("/agendar")
def agendar(body: AgendarRequest, ctx: Contexto = Depends(_lancar)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.agendar(cur, id_unidade, ctx.id_usuario, body.ids, body.data, body.forma,
                            body.baixa_automatica)
        _auditar(cur, ctx, r["ids"], "agendar", id_unidade, data=str(body.data), forma=body.forma,
                 baixa_automatica=body.baixa_automatica)
    return r


@router.post("/pagar")
def pagar(body: PagarRequest, ctx: Contexto = Depends(_baixar)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.pagar(cur, id_unidade, ctx.id_usuario, body.ids, body.pago_em, body.forma,
                          body.valor_pago)
        _auditar(cur, ctx, r["ids"], "pagar", id_unidade, pago_em=str(body.pago_em),
                 forma=body.forma,
                 valor_pago=str(body.valor_pago) if body.valor_pago is not None else None)
    return r


@router.post("/estornar")
def estornar(body: IdsRequest, ctx: Contexto = Depends(_baixar)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.estornar(cur, id_unidade, body.ids)
        _auditar(cur, ctx, r["ids"], "estornar", id_unidade)
    return r


@router.post("/cancelar")
def cancelar(body: IdsRequest, ctx: Contexto = Depends(_lancar)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.cancelar(cur, id_unidade, ctx.id_usuario, body.ids)
        _auditar(cur, ctx, r["ids"], "cancelar", id_unidade)
    return r


@router.put("/{id_conta}")
def corrigir(id_conta: int, body: ContaUpdate, ctx: Contexto = Depends(_lancar)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.corrigir(cur, id_unidade, id_conta, body.model_dump())
        auditoria.registrar(cur, ctx.id_usuario, "conta_pagar", id_conta, "corrigir",
                            antes=r["antes"], depois={"valor": str(body.valor),
                                                      "vencimento": str(body.vencimento),
                                                      "descricao": body.descricao},
                            id_unidade=id_unidade)
    return {"id": id_conta, "message": "Conta corrigida."}


@router.post("/comprovante")
async def anexar_comprovante(ids: str = Form(..., max_length=2000),
                             arquivo: UploadFile = File(...),
                             ctx: Contexto = Depends(_baixar)) -> dict:
    """O comprovante (foto ou PDF), num ou em vários pagamentos — "pagar todos" de uma pessoa
    tem um comprovante só. ⚠️ Lido antes da transação; trocar o anexo apaga o anterior."""
    try:
        lista = sorted({int(x) for x in ids.split(",") if x.strip()})
    except ValueError:
        raise HTTPException(status_code=422, detail="Contas inválidas.")
    if not lista:
        raise HTTPException(status_code=422, detail="Diga a que conta é o comprovante.")
    if (arquivo.content_type or "") == arquivos.PDF_TIPO:
        conteudo, tipo, extensao = await arquivos.ler_pdf(arquivo)
    else:
        conteudo, tipo, extensao = await arquivos.ler_enviada(arquivo)
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        linhas = servico._travar(cur, id_unidade, lista)
        url = arquivos.gravar(cur, conteudo, tipo, extensao, "comprovante")
        nome = url.rsplit("/", 1)[-1]
        antigos = {c["comprovante"] for c in linhas.values() if c["comprovante"]}
        cur.execute("UPDATE contas_pagar SET comprovante = %s WHERE id = ANY(%s)", (nome, lista))
        # O anexo antigo só sai se nenhuma outra conta ainda aponta para ele.
        for velho in antigos:
            cur.execute("SELECT 1 FROM contas_pagar WHERE comprovante = %s LIMIT 1", (velho,))
            if not cur.fetchone():
                arquivos.remover(f"{arquivos.PREFIXO_URL}/{velho}", cur)
        _auditar(cur, ctx, lista, "comprovante", id_unidade, tipo=tipo)
    return {"ids": lista, "message": "Comprovante anexado."}


@router.get("/{id_conta}/comprovante")
def comprovante(id_conta: int, ctx: Contexto = Depends(_ver)) -> Response:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute("SELECT comprovante FROM contas_pagar WHERE id = %s AND id_unidade = %s",
                    (id_conta, id_unidade))
        linha = cur.fetchone()
    if not linha or not linha["comprovante"]:
        raise HTTPException(status_code=404, detail="Esta conta não tem comprovante.")
    achado = arquivos.ler(f"{arquivos.PREFIXO_URL}/{linha['comprovante']}")
    if not achado:
        raise HTTPException(status_code=404, detail="O comprovante não foi encontrado.")
    conteudo, tipo = achado
    return Response(content=conteudo, media_type=tipo,
                    headers={"Cache-Control": "private, max-age=3600"})
