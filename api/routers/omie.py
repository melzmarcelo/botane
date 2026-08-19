"""Integração com o Omie: configuração, sincronização e conciliação de notas.

Enquanto não há credencial, tudo roda em **modo simulado** sobre respostas
gravadas em arquivo — o que permite construir, testar e demonstrar o importador
inteiro. Ao configurar a chave, o mesmo código passa a falar com a conta real.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import auditoria
from database import get_cursor
from seguranca import Contexto, contexto_atual, requer_permissao
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


class VincularRequest(BaseModel):
    id_produto: int
    fator: float | None = Field(default=None, gt=0)
    aprender: bool = True


class LancarRequest(BaseModel):
    id_local: int | None = None


def _unidade(cur, ctx: Contexto) -> int:
    if ctx.unidades:
        return sorted(ctx.unidades)[0]
    cur.execute("SELECT id FROM unidades WHERE ativo ORDER BY matriz DESC, id LIMIT 1")
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=400, detail="Nenhuma loja cadastrada")
    return linha["id"]


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
        id_unidade = _unidade(cur, ctx)
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
        id_unidade = _unidade(cur, ctx)
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
        cliente = _cliente(cur, _unidade(cur, ctx))
    return testar(cliente)


# ---------------------------------------------------------------- sincronização


@router.post("/sincronizar")
def sincronizar(dias: int = Query(default=30, ge=1, le=365),
                ctx: Contexto = Depends(requer_permissao("integracao.omie"))) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        cliente = _cliente(cur, id_unidade)
        r = importador.sincronizar(cur, id_unidade, cliente, dias)
        cur.execute(
            """INSERT INTO integracoes (id_unidade, servico, modo, ultima_sincronizacao,
                                        ultimo_status, ultima_mensagem)
               VALUES (%s, %s, %s, now(), 'OK', %s)
               ON CONFLICT (id_unidade, servico) DO UPDATE
                   SET ultima_sincronizacao = now(), ultimo_status = 'OK',
                       ultima_mensagem = EXCLUDED.ultima_mensagem""",
            (id_unidade, SERVICO, cliente.modo,
             f"{r['novas']} nova(s), {r['repetidas']} já existiam"),
        )
        auditoria.registrar(cur, ctx.id_usuario, "integracao", SERVICO, "sincronizar", depois=r,
                            id_unidade=id_unidade)
    return r | {"message": f"{r['novas']} nota(s) nova(s) importada(s)"}


@router.post("/importar-catalogo")
def importar_catalogo(ctx: Contexto = Depends(requer_permissao("integracao.omie"))) -> dict:
    """Traz os produtos do Omie como rascunho — a carga inicial do cadastro."""
    with get_cursor() as cur:
        cliente = _cliente(cur, _unidade(cur, ctx))
        r = importador.importar_catalogo(cur, cliente, ctx.id_usuario)
        auditoria.registrar(cur, ctx.id_usuario, "integracao", SERVICO, "importar_catalogo",
                            depois=r)
    return r | {"message": f"{r['criados']} produto(s) criado(s) em rascunho"}


@router.get("/conferencia")
def conferencia(ctx: Contexto = Depends(requer_permissao("integracao.omie"))) -> list[dict]:
    """Custo médio daqui × CMC do Omie. Divergência = entrada não conciliada."""
    with get_cursor() as cur:
        cliente = _cliente(cur, _unidade(cur, ctx))
        return importador.conferir_estoque(cur, cliente)


# ---------------------------------------------------------------- notas


@router.get("/notas")
def listar_notas(status: str | None = None,
                 limite: int = Query(default=50, ge=1, le=200),
                 ctx: Contexto = Depends(requer_permissao("compras.notas"))) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """SELECT n.id, n.chave_nfe, n.numero, n.serie, n.nome_emitente, n.cnpj_emitente,
                      n.data_emissao, n.data_entrada, n.valor_total, n.status, n.origem,
                      f.nome AS fornecedor,
                      (SELECT count(*) FROM nota_itens i WHERE i.id_nota = n.id) AS itens,
                      (SELECT count(*) FROM nota_itens i
                        WHERE i.id_nota = n.id AND i.id_produto IS NULL AND NOT i.ignorado)
                          AS pendentes
                 FROM notas_entrada n
                 LEFT JOIN fornecedores f ON f.id = n.id_fornecedor
                WHERE (%s::varchar IS NULL OR n.status = %s)
                ORDER BY n.data_emissao DESC NULLS LAST, n.id DESC
                LIMIT %s""",
            (status, status, limite),
        )
        return [dict(r) for r in cur.fetchall()]


@router.get("/notas/{id_nota}")
def obter_nota(id_nota: int,
               ctx: Contexto = Depends(requer_permissao("compras.notas"))) -> dict:
    with get_cursor() as cur:
        cur.execute(
            """SELECT n.*, f.nome AS fornecedor FROM notas_entrada n
                 LEFT JOIN fornecedores f ON f.id = n.id_fornecedor
                WHERE n.id = %s""",
            (id_nota,),
        )
        nota = cur.fetchone()
        if not nota:
            raise HTTPException(status_code=404, detail="Nota não encontrada")
        nota = dict(nota)
        nota.pop("bruto", None)

        cur.execute(
            """SELECT i.*, p.nome AS produto, p.um_estoque, p.codigo AS codigo_produto,
                      s.nome AS sugestao_nome
                 FROM nota_itens i
                 LEFT JOIN produtos p ON p.id = i.id_produto
                 LEFT JOIN produtos s ON s.id = i.sugestao_produto
                WHERE i.id_nota = %s ORDER BY i.seq""",
            (id_nota,),
        )
        nota["itens"] = [dict(r) for r in cur.fetchall()]
    return nota


@router.post("/itens/{id_item}/vincular")
def vincular(id_item: int, body: VincularRequest,
             ctx: Contexto = Depends(requer_permissao("compras.conciliar"))) -> dict:
    with get_cursor() as cur:
        r = importador.vincular_item(cur, id_item, body.id_produto, body.fator,
                                     ctx.id_usuario, body.aprender)
        auditoria.registrar(cur, ctx.id_usuario, "nota_item", id_item, "vincular",
                            depois={"id_produto": body.id_produto, "aprender": body.aprender})
    return r | {"message": "Item vinculado"
                + (" — as próximas notas deste fornecedor entram sozinhas" if body.aprender else "")}


@router.post("/itens/{id_item}/ignorar")
def ignorar(id_item: int,
            ctx: Contexto = Depends(requer_permissao("compras.conciliar"))) -> dict:
    """Item que não se controla em estoque (descartável avulso, serviço)."""
    with get_cursor() as cur:
        cur.execute(
            "UPDATE nota_itens SET ignorado = true, id_produto = NULL WHERE id = %s RETURNING id_nota",
            (id_item,),
        )
        linha = cur.fetchone()
        if not linha:
            raise HTTPException(status_code=404, detail="Item não encontrado")
        r = importador.calcular_nota(cur, linha["id_nota"])
        auditoria.registrar(cur, ctx.id_usuario, "nota_item", id_item, "ignorar")
    return r | {"message": "Item marcado como fora do estoque"}


@router.post("/notas/{id_nota}/lancar")
def lancar(id_nota: int, body: LancarRequest,
           ctx: Contexto = Depends(requer_permissao("compras.lancar"))) -> dict:
    with get_cursor() as cur:
        r = importador.lancar_nota(cur, id_nota, ctx.id_usuario, body.id_local,
                                   ctx.pode("estoque.retroativo"))
        auditoria.registrar(cur, ctx.id_usuario, "nota", id_nota, "lancar", depois=r)
    return r | {"message": f"{r['itens_lancados']} item(ns) lançado(s) no estoque"}


@router.post("/notas/{id_nota}/estornar")
def estornar_nota(id_nota: int,
                  ctx: Contexto = Depends(requer_permissao("estoque.ajuste"))) -> dict:
    """Desfaz o lançamento da nota: cada movimento ganha a contrapartida.

    Nota lançada errada acontece (item vinculado ao produto errado, quantidade
    trocada). O razão não se apaga — o estorno é o caminho.
    """
    from services import estoque as motor

    with get_cursor() as cur:
        cur.execute("SELECT status FROM notas_entrada WHERE id = %s", (id_nota,))
        nota = cur.fetchone()
        if not nota:
            raise HTTPException(status_code=404, detail="Nota não encontrada")
        if nota["status"] != "LANCADA":
            raise HTTPException(status_code=400, detail="Esta nota não está lançada.")

        cur.execute(
            """SELECT m.id FROM estoque_movimentos m
                WHERE m.origem_tipo = 'NOTA' AND m.origem_id = %s
                  AND NOT EXISTS (SELECT 1 FROM estoque_movimentos e WHERE e.id_estorno_de = m.id)
                ORDER BY m.id""",
            (id_nota,),
        )
        movimentos = [r["id"] for r in cur.fetchall()]
        for id_movimento in movimentos:
            motor.estornar(cur, id_movimento, ctx.id_usuario, f"Estorno da nota #{id_nota}")

        cur.execute(
            """UPDATE notas_entrada SET status = 'CONCILIADA', lancada_em = NULL,
                                        lancada_por = NULL
                WHERE id = %s""",
            (id_nota,),
        )
        auditoria.registrar(cur, ctx.id_usuario, "nota", id_nota, "estornar",
                            depois={"movimentos": len(movimentos)})
    return {"estornados": len(movimentos), "message": "Lançamento da nota desfeito"}


@router.delete("/notas/{id_nota}")
def descartar_nota(id_nota: int,
                   ctx: Contexto = Depends(requer_permissao("compras.notas"))) -> dict:
    """Descarta uma nota importada que não deveria estar aqui (não é da casa,
    veio duplicada de outro jeito). Só antes de lançar."""
    with get_cursor() as cur:
        cur.execute("SELECT status FROM notas_entrada WHERE id = %s", (id_nota,))
        nota = cur.fetchone()
        if not nota:
            raise HTTPException(status_code=404, detail="Nota não encontrada")
        if nota["status"] == "LANCADA":
            raise HTTPException(
                status_code=400,
                detail="Nota lançada não se descarta — estorne o lançamento antes.",
            )
        cur.execute("DELETE FROM notas_entrada WHERE id = %s", (id_nota,))
        auditoria.registrar(cur, ctx.id_usuario, "nota", id_nota, "descartar")
    return {"message": "Nota descartada"}


@router.delete("/vinculos/{codigo}")
def desvincular(codigo: str,
                ctx: Contexto = Depends(requer_permissao("compras.conciliar"))) -> dict:
    """Esquece um de-para. Serve para quando o vínculo foi feito no produto errado."""
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM codigos_externos WHERE sistema = %s AND codigo = %s RETURNING id_produto",
            (SERVICO, codigo),
        )
        achado = cur.fetchone()
        if not achado:
            raise HTTPException(status_code=404, detail="Vínculo não encontrado")
        auditoria.registrar(cur, ctx.id_usuario, "codigo_externo", codigo, "desvincular",
                            antes={"id_produto": achado["id_produto"]})
    return {"message": "Vínculo desfeito — o próximo item volta para a fila"}


@router.get("/vinculos")
def listar_vinculos(ctx: Contexto = Depends(requer_permissao("compras.notas"))) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """SELECT c.codigo, c.descricao_externa, c.fator, c.confirmado_em,
                      p.nome AS produto, p.codigo AS codigo_produto, u.nome AS confirmado_por
                 FROM codigos_externos c
                 JOIN produtos p ON p.id = c.id_produto
                 LEFT JOIN usuarios u ON u.id = c.confirmado_por
                WHERE c.sistema = %s
                ORDER BY c.confirmado_em DESC LIMIT 200""",
            (SERVICO,),
        )
        return [dict(r) for r in cur.fetchall()]


@router.get("/pendencias")
def pendencias(ctx: Contexto = Depends(requer_permissao("compras.notas"))) -> list[dict]:
    """Os itens que ainda não acharam produto — a fila de trabalho da conciliação."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT i.id, i.id_nota, n.numero, n.nome_emitente, i.descricao_fornecedor,
                      i.codigo_fornecedor, i.codigo_barras, i.quantidade, i.um_nota,
                      i.valor_unitario, i.sugestao_produto, i.sugestao_score,
                      s.nome AS sugestao_nome
                 FROM nota_itens i
                 JOIN notas_entrada n ON n.id = i.id_nota
                 LEFT JOIN produtos s ON s.id = i.sugestao_produto
                WHERE i.id_produto IS NULL AND NOT i.ignorado AND n.status <> 'CANCELADA'
                ORDER BY n.data_emissao DESC NULLS LAST, i.seq
                LIMIT 200"""
        )
        return [dict(r) for r in cur.fetchall()]
