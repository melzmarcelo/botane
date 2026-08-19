"""Notas de entrada — as três portas e um caminho só.

    XML da NF-e ─┐
    digitação   ─┼─▶ nota_entrada ─▶ conciliação ─▶ rateio ─▶ ENTRADA_NF
    Omie        ─┘

A porta muda; o que acontece depois, não. Por isso este router cuida do **ciclo
da nota** (conferir, vincular, lançar, estornar) para as três origens, e o
router do Omie ficou só com o que é do Omie: credencial, sincronização e
catálogo.

A casa opera inteira sem integração nenhuma: o XML chega por e-mail do
fornecedor e a nota do açougue da esquina se digita em um minuto.
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

import auditoria
from database import get_cursor
from seguranca import Contexto, contexto_atual, requer_permissao, unidade_atual
from services import nfe_xml
from services.omie import importador

router = APIRouter(prefix="/notas", tags=["Notas de entrada"])

# 8 MB cobre com folga a NF-e mais comprida que já vi (uns 900 itens).
LIMITE_XML = 8 * 1024 * 1024


class VincularRequest(BaseModel):
    id_produto: int
    fator: float | None = Field(default=None, gt=0)
    aprender: bool = True


class LancarRequest(BaseModel):
    id_local: int | None = None


class ItemManual(BaseModel):
    id_produto: int | None = None
    descricao: str | None = Field(default=None, max_length=200)
    codigo_fornecedor: str | None = Field(default=None, max_length=60)
    quantidade: float = Field(gt=0)
    um: str | None = Field(default=None, max_length=10)
    valor_unitario: float = Field(ge=0)
    valor_desconto: float = Field(default=0, ge=0)
    lote: str | None = Field(default=None, max_length=40)
    validade: date | None = None


class NotaManual(BaseModel):
    id_fornecedor: int | None = None
    numero: str | None = Field(default=None, max_length=20)
    serie: str | None = Field(default=None, max_length=5)
    data_emissao: date | None = None
    data_entrada: date | None = None
    valor_frete: float = Field(default=0, ge=0)
    valor_desconto: float = Field(default=0, ge=0)
    valor_outros: float = Field(default=0, ge=0)
    id_local: int | None = None
    itens: list[ItemManual] = Field(min_length=1)


def _resumo(cur, id_nota: int) -> dict:
    cur.execute(
        """SELECT n.id, n.chave_nfe, n.numero, n.serie, n.nome_emitente, n.data_emissao,
                  n.valor_total, n.status, n.origem, f.nome AS fornecedor,
                  (SELECT count(*) FROM nota_itens i WHERE i.id_nota = n.id) AS itens,
                  (SELECT count(*) FROM nota_itens i
                    WHERE i.id_nota = n.id AND i.id_produto IS NULL AND NOT i.ignorado)
                      AS pendentes
             FROM notas_entrada n
             LEFT JOIN fornecedores f ON f.id = n.id_fornecedor
            WHERE n.id = %s""",
        (id_nota,),
    )
    return dict(cur.fetchone())


# ---------------------------------------------------------------- porta 1: XML


@router.post("/importar-xml")
async def importar_xml(arquivos: list[UploadFile] = File(...),
                       ctx: Contexto = Depends(requer_permissao("compras.notas"))) -> dict:
    """Sobe um ou vários XMLs da NF-e.

    Cada arquivo é independente: um inválido no meio não derruba os outros — o
    caso normal é selecionar a pasta inteira do mês e deixar rodar.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute("SELECT cnpj FROM empresa WHERE id = 1")
        linha = cur.fetchone()
        cnpj_empresa = linha["cnpj"] if linha else None

        resultados = []
        for arquivo in arquivos:
            conteudo = await arquivo.read()
            nome = arquivo.filename or "arquivo.xml"
            if len(conteudo) > LIMITE_XML:
                resultados.append({"arquivo": nome, "status": "erro",
                                   "erro": "Arquivo grande demais para ser uma NF-e."})
                continue
            try:
                nota = nfe_xml.ler(conteudo)
                avisos = nfe_xml.conferir(nota, cnpj_empresa)
                id_nota, nova = importador.gravar_nota(
                    cur, id_unidade, nota, origem="XML",
                    xml=conteudo.decode("utf-8", errors="replace"),
                )
            except nfe_xml.XmlInvalido as e:
                resultados.append({"arquivo": nome, "status": "erro", "erro": e.mensagem})
                continue

            resumo = _resumo(cur, id_nota)
            resultados.append({
                **resumo,
                "arquivo": nome,
                # `status` aqui é o do ARQUIVO (entrou? repetiu? deu erro?); o da
                # nota vem junto com outro nome para não se atropelarem.
                "status_nota": resumo["status"],
                "status": "nova" if nova else "repetida",
                "avisos": avisos if nova else ["Esta nota já tinha sido importada."],
            })
            if nova:
                auditoria.registrar(cur, ctx.id_usuario, "nota", id_nota, "importar_xml",
                                    depois={"arquivo": nome, "chave": nota.get("chave_nfe")},
                                    id_unidade=id_unidade)

    novas = sum(1 for r in resultados if r["status"] == "nova")
    erros = sum(1 for r in resultados if r["status"] == "erro")
    pendentes = sum(r.get("pendentes") or 0 for r in resultados)
    return {
        "resultados": resultados,
        "novas": novas,
        "repetidas": sum(1 for r in resultados if r["status"] == "repetida"),
        "erros": erros,
        "pendentes": pendentes,
        "message": (f"{novas} nota(s) importada(s)"
                    + (f", {pendentes} item(ns) a vincular" if pendentes else "")
                    + (f", {erros} arquivo(s) recusado(s)" if erros else "")),
    }


# ------------------------------------------------------------ porta 2: digitação


@router.post("")
def criar_manual(body: NotaManual,
                 ctx: Contexto = Depends(requer_permissao("compras.notas"))) -> dict:
    """Digita a nota inteira: o cupom do mercado, a compra do hortifrúti.

    O item já pode nascer com o produto escolhido na tela — nesse caso não passa
    pela cascata de de-para, porque quem digitou já disse o que era.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        if body.id_fornecedor:
            cur.execute("SELECT id FROM fornecedores WHERE id = %s", (body.id_fornecedor,))
            if not cur.fetchone():
                raise HTTPException(status_code=400, detail="Fornecedor não encontrado")

        itens, produtos = [], Decimal(0)
        for seq, item in enumerate(body.itens, start=1):
            descricao, um = item.descricao, item.um
            if item.id_produto:
                cur.execute("SELECT nome, um_estoque FROM produtos WHERE id = %s AND ativo",
                            (item.id_produto,))
                produto = cur.fetchone()
                if not produto:
                    raise HTTPException(status_code=400,
                                        detail=f"Item {seq}: produto não encontrado")
                descricao = descricao or produto["nome"]
                um = um or produto["um_estoque"]
            if not descricao:
                raise HTTPException(
                    status_code=400,
                    detail=f"Item {seq}: escolha o produto ou escreva a descrição.",
                )
            total = (Decimal(str(item.quantidade)) * Decimal(str(item.valor_unitario))
                     ).quantize(Decimal("0.01"))
            produtos += total
            itens.append({
                "seq": seq,
                "descricao_fornecedor": descricao[:200],
                "codigo_fornecedor": item.codigo_fornecedor,
                "codigo_barras": None,
                "ncm": None,
                "quantidade": item.quantidade,
                "um_nota": um,
                "valor_unitario": item.valor_unitario,
                "valor_total": total,
                "valor_desconto": item.valor_desconto,
                "lote_nf": item.lote,
                "validade_nf": item.validade,
                "id_produto": item.id_produto,
            })

        hoje = date.today()
        nota = {
            "numero": body.numero,
            "serie": body.serie,
            "data_emissao": body.data_emissao or body.data_entrada or hoje,
            "data_entrada": body.data_entrada or body.data_emissao or hoje,
            "valor_produtos": produtos,
            "valor_frete": body.valor_frete,
            "valor_desconto": body.valor_desconto,
            "valor_outros": body.valor_outros,
            "valor_total": (produtos + Decimal(str(body.valor_frete))
                            + Decimal(str(body.valor_outros))
                            - Decimal(str(body.valor_desconto))),
            "id_local": body.id_local,
            "itens": itens,
        }
        id_nota, nova = importador.gravar_nota(cur, id_unidade, nota, origem="MANUAL",
                                               id_fornecedor=body.id_fornecedor)
        if not nova:
            raise HTTPException(
                status_code=409,
                detail=(f"Já existe uma nota #{body.numero} deste fornecedor (nº {id_nota}). "
                        "Abra a que existe em vez de digitar de novo."),
            )
        resumo = _resumo(cur, id_nota)
        auditoria.registrar(cur, ctx.id_usuario, "nota", id_nota, "digitar",
                            depois={"numero": body.numero, "itens": len(itens),
                                    "valor": float(nota["valor_total"])},
                            id_unidade=id_unidade)
    return resumo | {"message": "Nota registrada — confira e lance no estoque"}


# ---------------------------------------------------------------- consulta


@router.get("")
def listar(status: str | None = None,
           origem: str | None = None,
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
                  AND (%s::varchar IS NULL OR n.origem = %s)
                ORDER BY n.data_emissao DESC NULLS LAST, n.id DESC
                LIMIT %s""",
            (status, status, origem, origem, limite),
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


@router.get("/vinculos")
def listar_vinculos(ctx: Contexto = Depends(requer_permissao("compras.notas"))) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """SELECT c.codigo, c.descricao_externa, c.fator, c.confirmado_em, c.sistema,
                      p.nome AS produto, p.codigo AS codigo_produto, u.nome AS confirmado_por
                 FROM codigos_externos c
                 JOIN produtos p ON p.id = c.id_produto
                 LEFT JOIN usuarios u ON u.id = c.confirmado_por
                ORDER BY c.confirmado_em DESC LIMIT 200"""
        )
        return [dict(r) for r in cur.fetchall()]


@router.delete("/vinculos/{codigo}")
def desvincular(codigo: str,
                ctx: Contexto = Depends(requer_permissao("compras.conciliar"))) -> dict:
    """Esquece um de-para. Serve para quando o vínculo foi feito no produto errado."""
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM codigos_externos WHERE codigo = %s RETURNING id_produto",
            (codigo,),
        )
        achado = cur.fetchone()
        if not achado:
            raise HTTPException(status_code=404, detail="Vínculo não encontrado")
        auditoria.registrar(cur, ctx.id_usuario, "codigo_externo", codigo, "desvincular",
                            antes={"id_produto": achado["id_produto"]})
    return {"message": "Vínculo desfeito — o próximo item volta para a fila"}


@router.get("/{id_nota}")
def obter(id_nota: int,
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
        # O XML e a resposta crua ficam guardados para auditoria, mas pesam
        # centenas de KB — não têm o que fazer no JSON da tela.
        nota.pop("bruto", None)
        nota["tem_xml"] = bool(nota.pop("xml_bruto", None))

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


# ---------------------------------------------------------------- ciclo da nota


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


@router.post("/{id_nota}/lancar")
def lancar(id_nota: int, body: LancarRequest,
           ctx: Contexto = Depends(requer_permissao("compras.lancar"))) -> dict:
    with get_cursor() as cur:
        r = importador.lancar_nota(cur, id_nota, ctx.id_usuario, body.id_local,
                                   ctx.pode("estoque.retroativo"))
        auditoria.registrar(cur, ctx.id_usuario, "nota", id_nota, "lancar", depois=r)
    return r | {"message": f"{r['itens_lancados']} item(ns) lançado(s) no estoque"}


@router.post("/{id_nota}/estornar")
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


@router.delete("/{id_nota}")
def descartar(id_nota: int,
              ctx: Contexto = Depends(requer_permissao("compras.notas"))) -> dict:
    """Descarta uma nota que não deveria estar aqui (não é da casa, foi digitada
    errada, veio duplicada por outro caminho). Só antes de lançar."""
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
