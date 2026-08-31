"""Remessas entre lojas — enviar, acompanhar e receber.

⚠️ **A transferência dentro da mesma loja NÃO passa por aqui**: ela continua
imediata, em `/estoque/transferencias`. Este router existe para o caso em que a
mercadoria leva tempo no caminho e alguém confere na chegada.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response

import auditoria
from database import get_cursor
from models.estoque import RecebimentoRequest, RemessaCreate
from paginacao import pagina
from seguranca import Contexto, requer_permissao, unidade_atual
from services import transferencias as servico

router = APIRouter(prefix="/transferencias", tags=["transferências"])

# 🔑 **Ver, enviar e receber são três coisas.** Quem recebe na filial não
# precisa poder despachar mercadoria da casa — se fosse a mesma chave, a
# conferência perderia o sentido, porque remetente e conferente seriam a mesma
# pessoa por definição.
_ver = requer_permissao("estoque.transferencias", "estoque.transferencia_receber")
_enviar = requer_permissao("estoque.transferencias")
_receber = requer_permissao("estoque.transferencia_receber")


def _exigir_loja(cur, ctx: Contexto, id_esperada: int, nome: str, papel: str) -> None:
    """A ação pertence a uma loja, e a loja é a do seletor do topo.

    ⚠️ A frase nomeia a loja e diz o caminho: um 403 seco aqui deixaria a
    pessoa procurando permissão que ela já tem.
    """
    if unidade_atual(cur, ctx) != id_esperada:
        raise HTTPException(
            status_code=403,
            detail=f"{papel}. Troque para {nome} no seletor de loja, no topo da tela.")


def _ve_os_dois_lados(cur, ctx: Contexto, *locais: int) -> None:
    """Quem não enxerga a loja não empurra mercadoria para dentro dela."""
    for id_local in locais:
        cur.execute("SELECT id_unidade FROM locais_estoque WHERE id = %s", (id_local,))
        linha = cur.fetchone()
        if linha and not ctx.ve_unidade(linha["id_unidade"]):
            raise HTTPException(
                status_code=403,
                detail="Sem acesso à loja de um dos locais desta remessa.")


@router.get("")
def listar(resposta: Response,
           status: str | None = Query(None),
           limite: int = Query(50, le=200), offset: int = Query(0, ge=0),
           ctx: Contexto = Depends(_ver)) -> list[dict]:
    with get_cursor() as cur:
        sql, params = servico.consulta_da_lista(
            id_unidade=unidade_atual(cur, ctx), status=status)
        return pagina(cur, sql, params, limite=limite, offset=offset, resposta=resposta)


@router.get("/{id_transferencia}")
def obter(id_transferencia: int, ctx: Contexto = Depends(_ver)) -> dict:
    with get_cursor() as cur:
        r = servico.obter(cur, id_transferencia)
        if not (ctx.ve_unidade(r["id_unidade_origem"])
                or ctx.ve_unidade(r["id_unidade_destino"])):
            raise HTTPException(status_code=403, detail="Sem acesso a esta remessa.")
        return r


@router.post("", status_code=201)
def enviar(body: RemessaCreate, ctx: Contexto = Depends(_enviar)) -> dict:
    with get_cursor() as cur:
        _ve_os_dois_lados(cur, ctx, body.id_local_origem, body.id_local_destino)
        r = servico.enviar(
            cur, id_local_origem=body.id_local_origem, id_local_destino=body.id_local_destino,
            itens=[i.model_dump() for i in body.itens],
            id_usuario=ctx.id_usuario, observacao=body.observacao)
        auditoria.registrar(
            cur, ctx.id_usuario, "transferencia", r["id"], "enviar",
            depois={"de": r["origem"], "para": r["destino"],
                    "itens": len(body.itens)},
            id_unidade=r["id_unidade_origem"])
    return {**r, "message": f"Remessa {r['id']} em trânsito para {r['destino']}."}


@router.post("/{id_transferencia}/receber", status_code=201)
def receber(id_transferencia: int, body: RecebimentoRequest,
            ctx: Contexto = Depends(_receber)) -> dict:
    with get_cursor() as cur:
        r = servico.obter(cur, id_transferencia)
        # 🔑 **Quem recebe é o DESTINO — e a pergunta é a LOJA ATUAL, não a
        # visibilidade.** `ve_unidade` responde "esta pessoa pode olhar aquela
        # loja", e o administrador vê todas: com ele a trava não travava nada, e
        # quem despachou daria entrada na outra sem ninguém ter conferido — que
        # é exatamente o processo que este recebimento existe para impedir. A
        # loja atual é a do seletor do topo, e é ela que diz de onde a pessoa
        # está operando.
        _exigir_loja(cur, ctx, r["id_unidade_destino"], r["loja_destino"],
                     "Quem recebe é a loja de destino")
        conferido = {i.id_item: i.model_dump() for i in body.itens}
        feito = servico.receber(
            cur, id_transferencia=id_transferencia, conferido=conferido,
            id_usuario=ctx.id_usuario, observacao=body.observacao)
        auditoria.registrar(
            cur, ctx.id_usuario, "transferencia", id_transferencia, "receber",
            depois={"itens": feito["itens"], "faltas": feito["faltas"]},
            id_unidade=r["id_unidade_destino"])
    # A frase nomeia a divergência: recebimento que fecha certo não precisa de
    # explicação, o que veio a menos precisa.
    if feito["faltas"]:
        falta = ", ".join(f"{f['produto']} ({f['quantidade']:g} {f['um']})"
                          for f in feito["faltas"])
        return {**feito, "message": f"Remessa recebida. Lançado como perda o que não chegou: {falta}."}
    return {**feito, "message": "Remessa recebida e lançada no estoque."}


@router.post("/{id_transferencia}/cancelar", status_code=201)
def cancelar(id_transferencia: int, ctx: Contexto = Depends(_enviar)) -> dict:
    with get_cursor() as cur:
        r = servico.obter(cur, id_transferencia)
        _exigir_loja(cur, ctx, r["id_unidade_origem"], r["loja_origem"],
                     "Quem cancela é a loja que despachou")
        feito = servico.cancelar(
            cur, id_transferencia=id_transferencia, id_usuario=ctx.id_usuario)
        auditoria.registrar(cur, ctx.id_usuario, "transferencia", id_transferencia,
                            "cancelar", id_unidade=r["id_unidade_origem"])
    # ⚠️ Dizer que nada foi estornado é o ponto: quem cancela espera ter de
    # consertar o razão, e não há nada para consertar.
    return {**feito, "message": "Remessa cancelada. Nada foi lançado no estoque."}
