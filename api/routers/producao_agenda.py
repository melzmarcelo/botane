"""Agenda de produção: o plano do que a cozinha vai fazer.

Produzir já existia — mas só depois do fato. Aqui fica o passo anterior, que é
onde o estoque mínimo vira decisão em vez de susto.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import auditoria
from database import get_cursor
from seguranca import Contexto, requer_permissao, unidade_atual
from services import producao_agenda as motor

router = APIRouter(prefix="/producao-agenda", tags=["produção"])

_ver = requer_permissao("producao.agenda")
_produzir = requer_permissao("estoque.saidas")


class AgendarRequest(BaseModel):
    id_produto: int
    data_prevista: date | None = None
    quantidade: float = Field(gt=0)
    id_local: int | None = None
    observacao: str | None = Field(default=None, max_length=240)


class ProduzirLinhaRequest(BaseModel):
    # A cozinha rendeu mais ou menos que o planejado — o que vale é o que saiu
    # do fogão. Vazio = o planejado.
    quantidade: float | None = Field(default=None, gt=0)
    id_local: int | None = None


class CancelarRequest(BaseModel):
    motivo: str | None = Field(default=None, max_length=240)


@router.get("")
def listar(inicio: date | None = None, fim: date | None = None, status: str | None = None,
           ctx: Contexto = Depends(_ver)) -> dict:
    """O plano do período. Sem datas, mostra de ontem em diante.

    De ONTEM, não de hoje: a linha planejada que ninguém cumpriu é a que mais
    importa ver, e ela está no passado.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        linhas = motor.listar(cur, id_unidade, inicio, fim, status)
        if inicio is None and fim is None:
            linhas = [l for l in linhas
                      if l["status"] != "CANCELADA"
                      and (l["data_prevista"] >= date.today() or l["atrasada"])]
        return {
            "linhas": linhas,
            "resumo": motor.resumo(cur, id_unidade),
            "sugestoes": motor.sugestoes(cur, id_unidade),
        }


@router.post("", status_code=201)
def agendar(body: AgendarRequest, ctx: Contexto = Depends(_ver)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = motor.agendar(
            cur, id_unidade, body.id_produto,
            body.data_prevista or motor.proximo_dia_util(),
            body.quantidade, ctx.id_usuario, body.id_local, body.observacao,
        )
        auditoria.registrar(cur, ctx.id_usuario, "producao_agenda", r["id"], "agendar",
                            depois=r, id_unidade=id_unidade)
    return r | {"message": f"{r['produto']} na agenda de {r['data_prevista']}"}


@router.post("/{id_agenda}/produzir")
def produzir(id_agenda: int, body: ProduzirLinhaRequest,
             ctx: Contexto = Depends(_produzir)) -> dict:
    """Cumpre a linha — é aqui que o estoque se mexe."""
    with get_cursor() as cur:
        r = motor.produzir_linha(cur, id_agenda, ctx.id_usuario, body.quantidade,
                                 body.id_local)
        auditoria.registrar(cur, ctx.id_usuario, "producao_agenda", id_agenda, "produzir",
                            depois={"produzido": r["produzido"],
                                    "planejado": r["planejado"],
                                    "custo": r["custo_total"]})
    return r | {"message": f"{r['produzido']} produzido(s) — a linha saiu da agenda"}


@router.delete("/{id_agenda}")
def cancelar(id_agenda: int, ctx: Contexto = Depends(_ver)) -> dict:
    with get_cursor() as cur:
        r = motor.cancelar(cur, id_agenda)
        auditoria.registrar(cur, ctx.id_usuario, "producao_agenda", id_agenda, "cancelar")
    return r


@router.post("/das-sugestoes", status_code=201)
def agendar_sugestoes(ctx: Contexto = Depends(_ver)) -> dict:
    """Põe na agenda tudo o que está abaixo do mínimo, de uma vez.

    O alerta diz "vai faltar" e para por aí. Este é o botão que transforma o
    aviso em plano, que é o passo que costuma não acontecer.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        pendentes = motor.sugestoes(cur, id_unidade)
        if not pendentes:
            raise HTTPException(status_code=400,
                                detail="Nada abaixo do mínimo esperando agenda.")
        amanha = motor.proximo_dia_util()
        criadas = []
        for s in pendentes:
            criadas.append(motor.agendar(
                cur, id_unidade, s["id_produto"], amanha, float(s["sugerido"]),
                ctx.id_usuario, observacao="veio do alerta de estoque mínimo",
                origem="ALERTA",
            ))
        auditoria.registrar(cur, ctx.id_usuario, "producao_agenda", None, "agendar_sugestoes",
                            depois={"linhas": len(criadas)}, id_unidade=id_unidade)
    return {"criadas": len(criadas), "data": str(amanha), "linhas": criadas,
            "message": f"{len(criadas)} produto(s) na agenda de {amanha.strftime('%d/%m')}"}
