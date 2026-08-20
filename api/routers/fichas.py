"""Fichas técnicas.

Duas regras de acesso que valem a pena ler antes de mexer:

1. **Ver a ficha e ver o custo são permissões diferentes.** Sem `fichas.custos`,
   nenhum campo de dinheiro sai daqui — não é só a tela que esconde.
2. **Ficha homologada não se edita.** Alterar receita publicada mudaria o custo
   histórico. Quem quer mudar cria uma nova versão.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

import auditoria
from database import get_cursor
from models.fichas import FichaCreate, FichaResponse, FichaResumo, FichaUpdate, ItemFicha
from seguranca import Contexto, requer_permissao
from services import custos

router = APIRouter(prefix="/fichas", tags=["fichas técnicas"])

# Ver a ficha: qualquer um dos dois níveis serve.
_ver = requer_permissao("fichas.visualizar", "fichas.editar")


def _num(v):
    """Decimal/None → float/None, só na borda da API."""
    return None if v is None else float(v)


def _gravar_itens(cur, id_ficha: int, itens: list[ItemFicha]) -> None:
    cur.execute("DELETE FROM ficha_itens WHERE id_ficha = %s", (id_ficha,))
    for ordem, item in enumerate(itens):
        if bool(item.id_insumo) == bool(item.id_subficha):
            raise HTTPException(
                status_code=400,
                detail="Cada linha da ficha aponta para um insumo OU uma sub-ficha.",
            )
        if item.id_subficha == id_ficha:
            raise HTTPException(status_code=400, detail="Uma ficha não pode usar a si mesma.")

        # Fator de correção: se vieram bruta e líquida, ele é a divisão das duas.
        fc = item.fator_correcao
        if item.qtd_liquida:
            fc = round(item.qtd_bruta / item.qtd_liquida, 4) or 1

        cur.execute(
            """INSERT INTO ficha_itens (id_ficha, id_insumo, id_subficha, qtd_bruta,
                                        qtd_liquida, um, fator_correcao, fator_coccao,
                                        observacao, ordem)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (id_ficha, item.id_insumo, item.id_subficha, item.qtd_bruta, item.qtd_liquida,
             item.um, fc, item.fator_coccao, item.observacao, item.ordem or ordem),
        )

    # Só depois de gravar dá para provar que a árvore continua sem ciclo.
    if id_ficha in custos.descendentes_da_ficha(cur, id_ficha):
        raise HTTPException(
            status_code=400,
            detail="Essa combinação faz a ficha usar a si mesma por dentro de uma sub-ficha.",
        )


def _travar_se_homologada(status: str) -> None:
    if status == "HOMOLOGADA":
        raise HTTPException(
            status_code=400,
            detail="Ficha homologada não é editável — crie uma nova versão para mudar a receita.",
        )


@router.get("", response_model=list[FichaResumo])
def listar(
    id_produto: int | None = None,
    status: str | None = None,
    busca: str | None = Query(default=None, max_length=80),
    ctx: Contexto = Depends(_ver),
) -> list[dict]:
    ve_custo = ctx.pode("fichas.custos")
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT f.id, f.id_produto, p.nome AS produto, p.codigo, f.versao, f.status,
                   f.rendimento_qtd, f.rendimento_um, f.porcoes, f.criado_em AS atualizada_em,
                   (SELECT count(*) FROM ficha_itens i WHERE i.id_ficha = f.id) AS itens
              FROM fichas_tecnicas f
              JOIN produtos p ON p.id = f.id_produto
             WHERE (%s::int IS NULL OR f.id_produto = %s)
               AND (%s::varchar IS NULL OR f.status = %s)
               AND (%s::varchar IS NULL OR lower(p.nome) LIKE lower('%%' || %s || '%%'))
             ORDER BY lower(p.nome), f.versao DESC
            """,
            (id_produto, id_produto, status, status, busca, busca),
        )
        fichas = [dict(r) for r in cur.fetchall()]

        for f in fichas:
            f["rendimento_qtd"] = _num(f["rendimento_qtd"])
            f["porcoes"] = _num(f["porcoes"])
            if ve_custo:
                c = custos.custo_da_ficha(cur, f["id"])
                f["custo_total"] = _num(c["custo_total"])
                f["custo_por_porcao"] = _num(c["custo_por_porcao"])
                f["custo_completo"] = c["completo"]
    return fichas


@router.get("/{id_ficha}", response_model=FichaResponse)
def obter(id_ficha: int, ctx: Contexto = Depends(_ver)) -> dict:
    ve_custo = ctx.pode("fichas.custos")
    with get_cursor() as cur:
        cur.execute(
            """SELECT f.*, p.nome AS produto, p.codigo, u.nome AS homologada_por_nome
                 FROM fichas_tecnicas f
                 JOIN produtos p ON p.id = f.id_produto
                 LEFT JOIN usuarios u ON u.id = f.homologada_por
                WHERE f.id = %s""",
            (id_ficha,),
        )
        f = cur.fetchone()
        if not f:
            raise HTTPException(status_code=404, detail="Ficha não encontrada")
        ficha = dict(f)
        calculo = custos.custo_da_ficha(cur, id_ficha)

    itens = []
    for i in calculo["itens"]:
        item = {
            "id": i["id"],
            "id_insumo": i["id_insumo"],
            "id_subficha": i["id_subficha"],
            "nome": i["nome"],
            "codigo": i["codigo"],
            "qtd_bruta": _num(i["qtd_bruta"]),
            "qtd_liquida": _num(i["qtd_liquida"]),
            "um": i["um"],
            "fator_correcao": _num(i["fator_correcao"]),
            "fator_coccao": _num(i["fator_coccao"]),
            "observacao": i["observacao"],
            "ordem": i["ordem"],
            "aviso": i["aviso"],
            # Quanto isto vira na unidade do ESTOQUE: a receita pede 1 CX e o
            # razão baixa 12 PCT. Sem mostrar, a divergência só aparece no
            # inventário do fim do mês.
            "qtd_estoque": _num(i.get("qtd_estoque")),
            "conversao": i.get("conversao"),
            "um_estoque": i.get("um_estoque"),
        }
        if ve_custo:
            # Sem esta chave o dinheiro nem sai do servidor.
            item["custo_unitario"] = _num(i["custo_unitario"])
            item["custo_total"] = _num(i["custo_total"])
            item["origem_custo"] = i["origem_custo"]
        itens.append(item)

    resposta = {
        "id": ficha["id"],
        "id_produto": ficha["id_produto"],
        "produto": ficha["produto"],
        "codigo": ficha["codigo"],
        "versao": ficha["versao"],
        "status": ficha["status"],
        "rendimento_qtd": _num(ficha["rendimento_qtd"]),
        "rendimento_um": ficha["rendimento_um"],
        "porcoes": _num(ficha["porcoes"]),
        "tempo_preparo_min": ficha["tempo_preparo_min"],
        "modo_preparo": ficha["modo_preparo"],
        "alergenos": ficha["alergenos"],
        "observacao": ficha["observacao"],
        "vigente_de": ficha["vigente_de"],
        "vigente_ate": ficha["vigente_ate"],
        "homologada_em": ficha["homologada_em"],
        "homologada_por": ficha["homologada_por_nome"],
        "criado_em": ficha["criado_em"],
        "itens": itens,
        "ve_custo": ve_custo,
    }
    if ve_custo:
        resposta |= {
            "custo_total": _num(calculo["custo_total"]),
            "custo_por_porcao": _num(calculo["custo_por_porcao"]),
            "custo_por_unidade_rendimento": _num(calculo["custo_por_unidade_rendimento"]),
            "itens_sem_custo": calculo["itens_sem_custo"],
            "custo_completo": calculo["completo"],
        }
    return resposta


@router.post("", status_code=201)
def criar(body: FichaCreate, ctx: Contexto = Depends(requer_permissao("fichas.editar"))) -> dict:
    with get_cursor() as cur:
        cur.execute(
            "SELECT nome, tipo, producao_propria FROM produtos WHERE id = %s", (body.id_produto,)
        )
        produto = cur.fetchone()
        if not produto:
            raise HTTPException(status_code=404, detail="Produto não encontrado")
        if produto["tipo"] not in ("PRODUZIDO", "KIT"):
            raise HTTPException(
                status_code=400,
                detail="Ficha técnica é de produto produzido ou kit. Ajuste o tipo do produto.",
            )

        cur.execute(
            "SELECT coalesce(max(versao), 0) + 1 AS proxima FROM fichas_tecnicas WHERE id_produto = %s",
            (body.id_produto,),
        )
        versao = cur.fetchone()["proxima"]

        cur.execute(
            """INSERT INTO fichas_tecnicas (id_produto, versao, rendimento_qtd, rendimento_um,
                                            porcoes, tempo_preparo_min, modo_preparo, alergenos,
                                            observacao, criado_por)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (body.id_produto, versao, body.rendimento_qtd, body.rendimento_um, body.porcoes,
             body.tempo_preparo_min, body.modo_preparo, body.alergenos, body.observacao,
             ctx.id_usuario),
        )
        nova = cur.fetchone()["id"]
        _gravar_itens(cur, nova, body.itens)

        # Produto com ficha é produto de produção própria — deixa coerente aqui.
        if not produto["producao_propria"]:
            cur.execute(
                "UPDATE produtos SET producao_propria = true WHERE id = %s", (body.id_produto,)
            )
        auditoria.registrar(cur, ctx.id_usuario, "ficha", nova, "criar",
                            depois={"produto": produto["nome"], "versao": versao,
                                    "itens": len(body.itens)})
    return {"id": nova, "versao": versao, "message": "Ficha criada"}


@router.put("/{id_ficha}")
def atualizar(id_ficha: int, body: FichaUpdate,
              ctx: Contexto = Depends(requer_permissao("fichas.editar"))) -> dict:
    dados = body.model_dump(exclude_unset=True)
    itens = dados.pop("itens", None)
    with get_cursor() as cur:
        cur.execute(
            """SELECT status, rendimento_qtd, rendimento_um, porcoes FROM fichas_tecnicas
                WHERE id = %s""",
            (id_ficha,),
        )
        antes = cur.fetchone()
        if not antes:
            raise HTTPException(status_code=404, detail="Ficha não encontrada")
        _travar_se_homologada(antes["status"])

        if dados:
            sets = ", ".join(f"{c} = %s" for c in dados)
            cur.execute(
                f"UPDATE fichas_tecnicas SET {sets} WHERE id = %s", [*dados.values(), id_ficha]
            )
        if itens is not None:
            _gravar_itens(cur, id_ficha, body.itens or [])
        auditoria.registrar(cur, ctx.id_usuario, "ficha", id_ficha, "atualizar",
                            antes=dict(antes), depois=dados)
    return {"message": "Ficha salva"}


@router.post("/{id_ficha}/homologar")
def homologar(id_ficha: int,
              ctx: Contexto = Depends(requer_permissao("fichas.homologar"))) -> dict:
    """Publica a versão. A anterior é encerrada no mesmo instante."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT id_produto, status, versao FROM fichas_tecnicas WHERE id = %s", (id_ficha,)
        )
        f = cur.fetchone()
        if not f:
            raise HTTPException(status_code=404, detail="Ficha não encontrada")
        if f["status"] == "HOMOLOGADA":
            raise HTTPException(status_code=400, detail="Esta versão já está homologada")

        cur.execute("SELECT count(*) AS n FROM ficha_itens WHERE id_ficha = %s", (id_ficha,))
        if not cur.fetchone()["n"]:
            raise HTTPException(status_code=400, detail="Ficha sem itens não pode ser homologada")

        cur.execute(
            """UPDATE fichas_tecnicas
                  SET status = 'ARQUIVADA', vigente_ate = current_date
                WHERE id_produto = %s AND status = 'HOMOLOGADA' AND vigente_ate IS NULL""",
            (f["id_produto"],),
        )
        cur.execute(
            """UPDATE fichas_tecnicas
                  SET status = 'HOMOLOGADA', homologada_por = %s, homologada_em = now(),
                      vigente_de = current_date, vigente_ate = NULL
                WHERE id = %s""",
            (ctx.id_usuario, id_ficha),
        )
        auditoria.registrar(cur, ctx.id_usuario, "ficha", id_ficha, "homologar",
                            depois={"versao": f["versao"]})
    return {"message": "Ficha homologada"}


@router.post("/{id_ficha}/nova-versao", status_code=201)
def nova_versao(id_ficha: int,
                ctx: Contexto = Depends(requer_permissao("fichas.editar"))) -> dict:
    """Copia a ficha para uma versão nova em rascunho — a publicada segue no ar."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM fichas_tecnicas WHERE id = %s", (id_ficha,))
        f = cur.fetchone()
        if not f:
            raise HTTPException(status_code=404, detail="Ficha não encontrada")

        cur.execute(
            "SELECT coalesce(max(versao), 0) + 1 AS proxima FROM fichas_tecnicas WHERE id_produto = %s",
            (f["id_produto"],),
        )
        versao = cur.fetchone()["proxima"]
        cur.execute(
            """INSERT INTO fichas_tecnicas (id_produto, versao, rendimento_qtd, rendimento_um,
                                            porcoes, tempo_preparo_min, modo_preparo, alergenos,
                                            observacao, criado_por)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (f["id_produto"], versao, f["rendimento_qtd"], f["rendimento_um"], f["porcoes"],
             f["tempo_preparo_min"], f["modo_preparo"], f["alergenos"], f["observacao"],
             ctx.id_usuario),
        )
        nova = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO ficha_itens (id_ficha, id_insumo, id_subficha, qtd_bruta, qtd_liquida,
                                        um, fator_correcao, fator_coccao, observacao, ordem)
               SELECT %s, id_insumo, id_subficha, qtd_bruta, qtd_liquida, um, fator_correcao,
                      fator_coccao, observacao, ordem
                 FROM ficha_itens WHERE id_ficha = %s""",
            (nova, id_ficha),
        )
        auditoria.registrar(cur, ctx.id_usuario, "ficha", nova, "nova_versao",
                            antes={"copiada_de": id_ficha}, depois={"versao": versao})
    return {"id": nova, "versao": versao, "message": f"Versão {versao} criada em rascunho"}


@router.delete("/{id_ficha}")
def arquivar(id_ficha: int,
             ctx: Contexto = Depends(requer_permissao("fichas.editar"))) -> dict:
    """Arquiva. Ficha usada por outra não some, senão o custo dela quebraria."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM ficha_itens WHERE id_subficha = %s", (id_ficha,)
        )
        if cur.fetchone()["n"]:
            raise HTTPException(
                status_code=409,
                detail="Esta ficha é usada como sub-ficha em outra. Remova o vínculo antes.",
            )
        cur.execute(
            """UPDATE fichas_tecnicas SET status = 'ARQUIVADA', vigente_ate = current_date
                WHERE id = %s""",
            (id_ficha,),
        )
        auditoria.registrar(cur, ctx.id_usuario, "ficha", id_ficha, "arquivar")
    return {"message": "Ficha arquivada"}
