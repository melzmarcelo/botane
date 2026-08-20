"""Integração com o Omie: credencial, sincronização e catálogo.

O ciclo da nota (conferir, vincular, lançar, estornar) mora em `notas.py`, porque
é o mesmo para as notas que vêm do XML e para as digitadas na mão.

Enquanto não há credencial, tudo roda em **modo simulado** sobre respostas
gravadas em arquivo — o que permite construir, testar e demonstrar o importador
inteiro. Ao configurar a chave, o mesmo código passa a falar com a conta real.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import auditoria
from database import get_cursor
from seguranca import Contexto, contexto_atual, requer_permissao, unidade_atual
from services import segredos
from services.omie import importador
from services.omie.cliente import ClienteOmie, testar

router = APIRouter(prefix="/omie", tags=["Omie"])

SERVICO = "OMIE"


class ConfigOmie(BaseModel):
    app_key: str | None = Field(default=None, max_length=120)
    app_secret: str | None = Field(default=None, max_length=200)
    modo: str = "simulado"          # simulado | real
    ativa: bool = False


def _cliente(cur, id_unidade: int) -> ClienteOmie:
    cur.execute(
        "SELECT credenciais, modo, ativa FROM integracoes WHERE id_unidade = %s AND servico = %s",
        (id_unidade, SERVICO),
    )
    linha = cur.fetchone()
    if not linha:
        return ClienteOmie(modo="simulado")
    cred = segredos.decifrar(linha["credenciais"])
    return ClienteOmie(cred.get("app_key"), cred.get("app_secret"), linha["modo"])


# ---------------------------------------------------------------- configuração


@router.get("/config")
def config(ctx: Contexto = Depends(requer_permissao("integracao.omie", "admin.integracoes"))):
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT modo, ativa, credenciais, ultima_sincronizacao, ultimo_status,
                      ultima_mensagem
                 FROM integracoes WHERE id_unidade = %s AND servico = %s""",
            (id_unidade, SERVICO),
        )
        linha = cur.fetchone()
        cur.execute(
            """SELECT chamada, status, registros, mensagem, modo, iniciado_em
                 FROM sync_log WHERE servico LIKE %s ORDER BY iniciado_em DESC LIMIT 10""",
            ("%",),
        )
        historico = [dict(r) for r in cur.fetchall()]

    cred = segredos.decifrar(linha["credenciais"]) if linha else {}
    return {
        "configurada": bool(cred.get("app_key")),
        "modo": linha["modo"] if linha else "simulado",
        "ativa": linha["ativa"] if linha else False,
        # A chave nunca sai daqui em claro — só o suficiente para reconhecê-la.
        "app_key": segredos.mascarar(cred.get("app_key")),
        "app_secret": segredos.mascarar(cred.get("app_secret")),
        "ultima_sincronizacao": linha["ultima_sincronizacao"] if linha else None,
        "ultimo_status": linha["ultimo_status"] if linha else None,
        "ultima_mensagem": linha["ultima_mensagem"] if linha else None,
        "historico": historico,
    }


@router.put("/config")
def salvar_config(body: ConfigOmie,
                  ctx: Contexto = Depends(requer_permissao("admin.integracoes"))) -> dict:
    if body.modo not in ("simulado", "real"):
        raise HTTPException(status_code=400, detail="Modo deve ser 'simulado' ou 'real'.")
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            "SELECT credenciais FROM integracoes WHERE id_unidade = %s AND servico = %s",
            (id_unidade, SERVICO),
        )
        atual = cur.fetchone()
        cred = segredos.decifrar(atual["credenciais"]) if atual else {}
        # Campo em branco mantém o que já estava: a tela mostra mascarado.
        if body.app_key:
            cred["app_key"] = body.app_key.strip()
        if body.app_secret:
            cred["app_secret"] = body.app_secret.strip()
        # A tela mostra a chave mascarada; trocar para "real" não pode exigir
        # redigitar o que já está guardado.
        if body.modo == "real" and not (cred.get("app_key") and cred.get("app_secret")):
            raise HTTPException(
                status_code=400,
                detail="Para o modo real é preciso informar app_key e app_secret.",
            )

        cur.execute(
            """INSERT INTO integracoes (id_unidade, servico, ativa, modo, credenciais)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (id_unidade, servico) DO UPDATE
                   SET ativa = EXCLUDED.ativa, modo = EXCLUDED.modo,
                       credenciais = EXCLUDED.credenciais, atualizado_em = now()""",
            (id_unidade, SERVICO, body.ativa, body.modo, segredos.cifrar(cred)),
        )
        # A auditoria registra a mudança sem registrar o segredo.
        auditoria.registrar(cur, ctx.id_usuario, "integracao", SERVICO, "configurar",
                            depois={"modo": body.modo, "ativa": body.ativa,
                                    "app_key": segredos.mascarar(cred.get("app_key"))},
                            id_unidade=id_unidade)
    return {"message": "Integração salva"}


@router.post("/testar")
def testar_conexao(ctx: Contexto = Depends(requer_permissao("integracao.omie",
                                                            "admin.integracoes"))) -> dict:
    with get_cursor() as cur:
        cliente = _cliente(cur, unidade_atual(cur, ctx))
    return testar(cliente)


# ---------------------------------------------------------------- sincronização


@router.post("/sincronizar")
def sincronizar(dias: int | None = Query(default=None, ge=1, le=365),
                desde: date | None = None,
                ctx: Contexto = Depends(requer_permissao("integracao.omie"))) -> dict:
    """Puxa as notas de entrada do Omie.

    Sem parâmetro nenhum, a janela **se adapta**: vai desde a última
    sincronização, com folga. `desde` faz a carga inicial do histórico; `dias`
    fixa uma janela.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cliente = _cliente(cur, id_unidade)
        r = importador.sincronizar(cur, id_unidade, cliente, dias, desde)
        cur.execute(
            """INSERT INTO integracoes (id_unidade, servico, modo, ultima_sincronizacao,
                                        ultimo_status, ultima_mensagem)
               VALUES (%s, %s, %s, now(), 'OK', %s)
               ON CONFLICT (id_unidade, servico) DO UPDATE
                   SET ultima_sincronizacao = now(), ultimo_status = 'OK',
                       ultima_mensagem = EXCLUDED.ultima_mensagem""",
            (id_unidade, SERVICO, cliente.modo,
             f"{r['novas']} nova(s), {r['repetidas']} já existiam ({r['janela']})"),
        )
        auditoria.registrar(cur, ctx.id_usuario, "integracao", SERVICO, "sincronizar", depois=r,
                            id_unidade=id_unidade)
    return r | {"message": (f"{r['novas']} nota(s) nova(s) importada(s) — "
                           f"{r['janela']}, {r['repetidas']} já existiam")}


@router.post("/importar-catalogo")
def importar_catalogo(ctx: Contexto = Depends(requer_permissao("integracao.omie"))) -> dict:
    """Traz os produtos do Omie como rascunho — a carga inicial do cadastro."""
    with get_cursor() as cur:
        cliente = _cliente(cur, unidade_atual(cur, ctx))
        r = importador.importar_catalogo(cur, cliente, ctx.id_usuario)
        auditoria.registrar(cur, ctx.id_usuario, "integracao", SERVICO, "importar_catalogo",
                            depois=r)
    return r | {"message": f"{r['criados']} produto(s) criado(s) em rascunho"}


@router.get("/conferencia-notas")
def conferencia_notas(
    inicio: date | None = None,
    fim: date | None = None,
    ctx: Contexto = Depends(requer_permissao("integracao.omie")),
) -> dict:
    """Quais notas o Omie tem no período e não existem aqui.

    "0 novas" é ambíguo — pode não haver nada novo, ou a janela pode ter passado
    por cima de uma nota lançada com atraso. Isto responde a pergunta certa:
    **quais** faltam.
    """
    hoje = date.today()
    fim = fim or hoje
    inicio = inicio or (fim - timedelta(days=30))
    if inicio > fim:
        raise HTTPException(status_code=400, detail="O início não pode ser depois do fim.")
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        return importador.conferir_notas(cur, id_unidade, _cliente(cur, id_unidade), inicio, fim)


@router.get("/conferencia")
def conferencia(ctx: Contexto = Depends(requer_permissao("integracao.omie"))) -> list[dict]:
    """Custo médio daqui × CMC do Omie. Divergência = entrada não conciliada."""
    with get_cursor() as cur:
        cliente = _cliente(cur, unidade_atual(cur, ctx))
        return importador.conferir_estoque(cur, cliente)
