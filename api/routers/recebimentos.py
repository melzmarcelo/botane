"""Recebimento de notas — registrar que a nota chegou, com foto opcional (migração 162).

🔑 Só registro, pedido do dono de 24/11/2026: a nota que quem recebe perde e quem lança nunca
vê. A lista diz se cada uma já está no sistema (`services/recebimentos.py`).
⚠️ A foto entra por multipart e sai só por rota autenticada: `/arquivos/{nome}` é pública.
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile

import arquivos
import auditoria
import relogio
from database import get_cursor
from paginacao import pagina
from seguranca import Contexto, requer_permissao, unidade_atual
from services import recebimentos as servico

router = APIRouter(prefix="/recebimentos", tags=["recebimento de notas"])

RECEBER, NOTAS = "compras.receber", "compras.notas"
_ver = requer_permissao(RECEBER, NOTAS)
_receber = requer_permissao(RECEBER)


@router.get("")
def listar(resposta: Response,
           situacao: Literal["LANCADA", "NO_SISTEMA", "FALTA"] | None = None,
           de: date | None = None, ate: date | None = None,
           busca: str | None = Query(None, max_length=80),
           limite: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
           ctx: Contexto = Depends(_ver)) -> list[dict]:
    with get_cursor() as cur:
        sql, p = servico.consulta(unidade_atual(cur, ctx), situacao, de, ate, busca)
        return pagina(cur, sql, p, limite=limite, offset=offset, resposta=resposta)


@router.get("/resumo")
def resumo(ctx: Contexto = Depends(_ver)) -> dict:
    with get_cursor() as cur:
        return servico.resumo(cur, unidade_atual(cur, ctx))


@router.post("", status_code=201)
async def registrar(numero_nota: str = Form(..., min_length=1, max_length=30),
                    data_nota: date = Form(...),
                    id_fornecedor: int | None = Form(None),
                    fornecedor_texto: str | None = Form(None, max_length=120),
                    observacao: str | None = Form(None, max_length=300),
                    mesmo_assim: bool = Form(False),
                    foto: UploadFile | None = File(None),
                    ctx: Contexto = Depends(_receber)) -> dict:
    """Registra que a nota chegou. A foto é opcional, até 2 MB (a tela reduz antes de mandar).

    ⚠️ A foto é lida ANTES da transação: ler da rede com uma conexão do pool presa é prendê-la
    pelo tempo do envio.
    """
    if data_nota > relogio.hoje_da_casa():
        raise HTTPException(status_code=422, detail="A data da nota não pode ser no futuro.")
    lida = await arquivos.ler_enviada(foto) if foto and foto.filename else None
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        nome_foto = None
        if lida:
            url = arquivos.gravar(cur, lida[0], lida[1], lida[2], "recebimento")
            nome_foto = url.rsplit("/", 1)[-1]
        r = servico.registrar(cur, id_unidade, ctx.id_usuario, {
            "numero_nota": numero_nota, "data_nota": data_nota, "id_fornecedor": id_fornecedor,
            "fornecedor_texto": fornecedor_texto, "observacao": observacao,
            "mesmo_assim": mesmo_assim}, nome_foto)
        auditoria.registrar(cur, ctx.id_usuario, "recebimento", r["id"], "registrar",
                            depois={"numero_nota": numero_nota, "data_nota": str(data_nota),
                                    "id_fornecedor": id_fornecedor,
                                    "fornecedor_texto": fornecedor_texto, "foto": bool(nome_foto)},
                            id_unidade=id_unidade)
    return r


@router.get("/{id_recebimento}/foto")
def foto(id_recebimento: int, ctx: Contexto = Depends(_ver)) -> Response:
    """A foto da nota — só para quem vê os recebimentos, nunca pela rota pública."""
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute("SELECT foto FROM recebimentos WHERE id = %s AND id_unidade = %s",
                    (id_recebimento, id_unidade))
        linha = cur.fetchone()
    if not linha or not linha["foto"]:
        raise HTTPException(status_code=404, detail="Este registro não tem foto.")
    achado = arquivos.ler(f"{arquivos.PREFIXO_URL}/{linha['foto']}")
    if not achado:
        raise HTTPException(status_code=404, detail="A foto não foi encontrada.")
    conteudo, tipo = achado
    return Response(content=conteudo, media_type=tipo,
                    headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/{id_recebimento}")
def excluir(id_recebimento: int, ctx: Contexto = Depends(_ver)) -> dict:
    """Apaga um registro feito por engano. Quem registrou, ou quem cuida das notas."""
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.travar(cur, id_unidade, id_recebimento)
        if r["recebido_por"] != ctx.id_usuario and not ctx.pode(NOTAS):
            raise HTTPException(status_code=403,
                                detail="Só quem registrou ou quem cuida das notas pode apagar.")
        cur.execute("DELETE FROM recebimentos WHERE id = %s", (id_recebimento,))
        if r["foto"]:
            arquivos.remover(f"{arquivos.PREFIXO_URL}/{r['foto']}", cur)
        auditoria.registrar(cur, ctx.id_usuario, "recebimento", id_recebimento, "excluir",
                            antes={"numero_nota": r["numero_nota"], "data_nota": str(r["data_nota"]),
                                   "id_fornecedor": r["id_fornecedor"],
                                   "fornecedor_texto": r["fornecedor_texto"]},
                            id_unidade=id_unidade)
    return {"id": id_recebimento, "message": "Registro apagado."}
