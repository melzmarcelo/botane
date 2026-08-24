"""Inventário: contar o que existe e acertar o razão pela diferença.

A contagem não escreve no razão — só ao fechar. E o acerto entra como
movimento de ajuste, com o custo médio do momento: some estoque sem virar
perda anônima, mas com nome e rastro.
"""

from fastapi import APIRouter, Depends, HTTPException

import auditoria
from database import get_cursor
from models.estoque import ContagemRequest, InventarioCreate, InventarioResponse
from seguranca import Contexto, requer_permissao
from services import estoque as motor
from services import custos
from services.custos import dec

router = APIRouter(prefix="/inventarios", tags=["inventário"])

_perm = requer_permissao("estoque.inventario")


def _montar(cur, id_inventario: int) -> dict:
    cur.execute(
        """SELECT i.*, l.nome AS local FROM inventarios i
             JOIN locais_estoque l ON l.id = i.id_local
            WHERE i.id = %s""",
        (id_inventario,),
    )
    inv = cur.fetchone()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventário não encontrado")
    inv = dict(inv)

    cur.execute(
        """SELECT ii.id, ii.id_produto, p.codigo, p.nome AS produto, p.um_estoque,
                  ii.qtd_sistema, ii.qtd_contada, ii.custo_medio, ii.observacao,
                  ii.qtd_informada, ii.um_informada, ii.contado_em, u.nome AS contado_por,
                  c.nome AS categoria,
                  (coalesce(ii.qtd_contada, ii.qtd_sistema) - ii.qtd_sistema) AS diferenca,
                  -- Em que unidades este produto pode ser contado. Vai junto
                  -- para o celular não precisar de uma chamada por produto.
                  coalesce((SELECT json_agg(json_build_object('um', pu.um, 'fator', pu.fator)
                                              ORDER BY pu.fator)
                              FROM produto_unidades pu
                             WHERE pu.id_produto = p.id), '[]'::json) AS unidades
             FROM inventario_itens ii
             JOIN produtos p ON p.id = ii.id_produto
             LEFT JOIN usuarios u ON u.id = ii.contado_por
             LEFT JOIN categorias c ON c.id = p.id_categoria
            WHERE ii.id_inventario = %s
            ORDER BY lower(p.nome)""",
        (id_inventario,),
    )
    itens = [dict(r) for r in cur.fetchall()]

    inv["itens"] = itens
    inv["total_itens"] = len(itens)
    inv["contados"] = sum(1 for i in itens if i["qtd_contada"] is not None)
    inv["diferenca_valor"] = float(
        sum(dec(i["diferenca"]) * dec(i["custo_medio"]) for i in itens)
    )
    return inv


@router.get("", response_model=list[InventarioResponse])
def listar(ctx: Contexto = Depends(_perm)) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """SELECT i.id, i.id_local, l.nome AS local, i.data, i.status, i.observacao,
                      i.criado_em, i.fechado_em,
                      (SELECT count(*) FROM inventario_itens ii WHERE ii.id_inventario = i.id) AS total_itens,
                      (SELECT count(*) FROM inventario_itens ii
                        WHERE ii.id_inventario = i.id AND ii.qtd_contada IS NOT NULL) AS contados
                 FROM inventarios i
                 JOIN locais_estoque l ON l.id = i.id_local
                ORDER BY i.data DESC, i.id DESC LIMIT 100"""
        )
        return [dict(r) for r in cur.fetchall()]


@router.get("/{id_inventario}", response_model=InventarioResponse)
def obter(id_inventario: int, ctx: Contexto = Depends(_perm)) -> dict:
    with get_cursor() as cur:
        return _montar(cur, id_inventario)


@router.post("", status_code=201)
def abrir(body: InventarioCreate, ctx: Contexto = Depends(_perm)) -> dict:
    """Abre a contagem congelando o saldo do sistema de cada item, agora."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT id_unidade FROM locais_estoque WHERE id = %s AND ativo", (body.id_local,)
        )
        local = cur.fetchone()
        if not local:
            raise HTTPException(status_code=404, detail="Local não encontrado")

        cur.execute(
            """SELECT 1 FROM inventarios WHERE id_local = %s AND status = 'ABERTO'""",
            (body.id_local,),
        )
        if cur.fetchone():
            raise HTTPException(
                status_code=409, detail="Já há um inventário aberto neste local."
            )

        cur.execute(
            """INSERT INTO inventarios (id_unidade, id_local, data, observacao, id_usuario)
               VALUES (%s, %s, coalesce(%s, current_date), %s, %s) RETURNING id""",
            (local["id_unidade"], body.id_local, body.data, body.observacao, ctx.id_usuario),
        )
        novo = cur.fetchone()["id"]

        if body.produtos:
            cur.execute(
                """INSERT INTO inventario_itens (id_inventario, id_produto, qtd_sistema, custo_medio)
                   SELECT %s, p.id,
                          coalesce(s.quantidade, 0), coalesce(s.custo_medio, 0)
                     FROM produtos p
                     LEFT JOIN estoque_saldos s
                            ON s.id_produto = p.id AND s.id_local = %s
                    WHERE p.id = ANY(%s) AND p.controla_estoque""",
                (novo, body.id_local, body.produtos),
            )
        else:
            # Sem lista: tudo o que tem saldo ou já se moveu neste local.
            cur.execute(
                """INSERT INTO inventario_itens (id_inventario, id_produto, qtd_sistema, custo_medio)
                   SELECT %s, s.id_produto, s.quantidade, s.custo_medio
                     FROM estoque_saldos s
                     JOIN produtos p ON p.id = s.id_produto
                    WHERE s.id_local = %s AND p.controla_estoque AND p.ativo""",
                (novo, body.id_local),
            )
        auditoria.registrar(cur, ctx.id_usuario, "inventario", novo, "abrir",
                            depois={"local": body.id_local})
        return _montar(cur, novo)


@router.put("/{id_inventario}/contagem")
def contar(id_inventario: int, body: ContagemRequest, ctx: Contexto = Depends(_perm)) -> dict:
    """Grava a contagem. Ainda não mexe no razão — isso é no fechamento."""
    with get_cursor() as cur:
        cur.execute("SELECT status, id_local FROM inventarios WHERE id = %s", (id_inventario,))
        inv = cur.fetchone()
        if not inv:
            raise HTTPException(status_code=404, detail="Inventário não encontrado")
        if inv["status"] != "ABERTO":
            raise HTTPException(status_code=400, detail="Inventário já fechado.")

        ums = custos._carregar_ums(cur)
        for item in body.itens:
            # A pessoa conta na embalagem que está na mão; o sistema guarda na
            # unidade de estoque. A conversão é a MESMA da ficha e da nota.
            convertida, informada, um_informada = item.qtd_contada, None, None
            if item.qtd_contada is not None and item.um:
                cur.execute("SELECT um_estoque, nome FROM produtos WHERE id = %s",
                            (item.id_produto,))
                p = cur.fetchone()
                if not p:
                    raise HTTPException(status_code=404,
                                        detail=f"Produto {item.id_produto} não encontrado")
                convertida, _como = custos.converter_para_estoque(
                    cur, dec(item.qtd_contada), item.id_produto, item.um, p["um_estoque"], ums)
                if convertida is None:
                    raise HTTPException(
                        status_code=400,
                        detail=(f"{p['nome']}: {item.um} não converte para "
                                f"{p['um_estoque'] or '?'}. Cadastre esta unidade de compra "
                                f"no produto."),
                    )
                informada, um_informada = item.qtd_contada, item.um.upper()

            cur.execute(
                """INSERT INTO inventario_itens (id_inventario, id_produto, qtd_sistema,
                                                 custo_medio, qtd_contada, qtd_informada,
                                                 um_informada, observacao, contado_em,
                                                 contado_por)
                   SELECT %s, %s, coalesce(s.quantidade, 0), coalesce(s.custo_medio, 0),
                          %s, %s, %s, %s, now(), %s
                     FROM (SELECT 1) x
                     LEFT JOIN estoque_saldos s
                            ON s.id_produto = %s AND s.id_local = %s
                   ON CONFLICT (id_inventario, id_produto) DO UPDATE
                       SET qtd_contada = EXCLUDED.qtd_contada,
                           qtd_informada = EXCLUDED.qtd_informada,
                           um_informada = EXCLUDED.um_informada,
                           observacao = EXCLUDED.observacao,
                           contado_em = now(),
                           contado_por = EXCLUDED.contado_por""",
                (id_inventario, item.id_produto, convertida, informada, um_informada,
                 item.observacao, ctx.id_usuario, item.id_produto, inv["id_local"]),
            )
        return _montar(cur, id_inventario)


@router.post("/{id_inventario}/fechar")
def fechar(id_inventario: int, ctx: Contexto = Depends(requer_permissao("estoque.ajuste"))) -> dict:
    """Fecha e acerta o razão: cada diferença vira um movimento de ajuste."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT id_unidade, id_local, status FROM inventarios WHERE id = %s", (id_inventario,)
        )
        inv = cur.fetchone()
        if not inv:
            raise HTTPException(status_code=404, detail="Inventário não encontrado")
        if inv["status"] != "ABERTO":
            raise HTTPException(status_code=400, detail="Inventário já fechado.")

        cur.execute(
            """SELECT id_produto, qtd_sistema, qtd_contada FROM inventario_itens
                WHERE id_inventario = %s AND qtd_contada IS NOT NULL""",
            (id_inventario,),
        )
        itens = [dict(r) for r in cur.fetchall()]
        if not itens:
            raise HTTPException(status_code=400, detail="Nenhum item contado.")

        ajustes, valor = 0, 0.0
        for item in itens:
            # O saldo do sistema pode ter mudado depois da abertura: o ajuste
            # olha o saldo de AGORA, senão o inventário desfaz movimento válido.
            cur.execute(
                """SELECT quantidade FROM estoque_saldos
                    WHERE id_unidade = %s AND id_local = %s AND id_produto = %s""",
                (inv["id_unidade"], inv["id_local"], item["id_produto"]),
            )
            linha = cur.fetchone()
            atual = dec(linha["quantidade"]) if linha else dec(0)
            diferenca = dec(item["qtd_contada"]) - atual
            if diferenca == 0:
                continue
            r = motor.lancar(
                cur, id_unidade=inv["id_unidade"], id_local=inv["id_local"],
                id_produto=item["id_produto"],
                tipo="AJUSTE_INVENTARIO_ENTRADA" if diferenca > 0 else "AJUSTE_INVENTARIO_SAIDA",
                quantidade=abs(diferenca), origem_tipo="INVENTARIO", origem_id=id_inventario,
                observacao=f"Inventário #{id_inventario}", id_usuario=ctx.id_usuario,
            )
            ajustes += 1
            valor += float(r["custo_total"]) * (1 if diferenca > 0 else -1)

        cur.execute(
            """UPDATE inventarios SET status = 'FECHADO', fechado_em = now(), fechado_por = %s
                WHERE id = %s""",
            (ctx.id_usuario, id_inventario),
        )
        auditoria.registrar(cur, ctx.id_usuario, "inventario", id_inventario, "fechar",
                            depois={"ajustes": ajustes, "valor": round(valor, 2)})
    return {"message": f"Inventário fechado com {ajustes} ajuste(s)",
            "ajustes": ajustes, "diferenca_valor": round(valor, 2)}


@router.delete("/{id_inventario}")
def cancelar(id_inventario: int, ctx: Contexto = Depends(_perm)) -> dict:
    with get_cursor() as cur:
        cur.execute("SELECT status FROM inventarios WHERE id = %s", (id_inventario,))
        inv = cur.fetchone()
        if not inv:
            raise HTTPException(status_code=404, detail="Inventário não encontrado")
        if inv["status"] == "FECHADO":
            raise HTTPException(
                status_code=400,
                detail="Inventário fechado não se cancela — os ajustes já estão no razão.",
            )
        cur.execute("UPDATE inventarios SET status = 'CANCELADO' WHERE id = %s", (id_inventario,))
        auditoria.registrar(cur, ctx.id_usuario, "inventario", id_inventario, "cancelar")
    return {"message": "Inventário cancelado"}
