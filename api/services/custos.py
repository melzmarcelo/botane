"""Cálculo de custo — o coração do sistema.

**Uma fonte só para o custo do insumo.** Desde a etapa 4 ela é o custo médio do
estoque, com o último preço de compra como reserva para quem ainda não teve
entrada. Tudo que precisa saber quanto custa um insumo pergunta aqui — ficha
técnica, produção e CMV.

Dinheiro em `Decimal`, sempre. `float` em custo unitário de insumo vira
diferença de centavos que reaparece multiplicada por mil no fim do mês.
"""

from decimal import Decimal, InvalidOperation

CASAS_CUSTO = Decimal("0.000001")
CASAS_VALOR = Decimal("0.01")

PROFUNDIDADE_MAXIMA = 12


def dec(valor) -> Decimal:
    if valor is None:
        return Decimal(0)
    if isinstance(valor, Decimal):
        return valor
    try:
        return Decimal(str(valor))
    except InvalidOperation:
        return Decimal(0)


def custo_do_insumo(cur, id_produto: int) -> tuple[Decimal | None, str]:
    """Custo de UMA unidade de estoque do insumo, e de onde ele veio.

    Ordem: **custo médio do estoque** → último preço do fornecedor. Devolve
    (None, "sem_custo") quando ninguém sabe quanto custa — o que a tela precisa
    dizer em vez de mostrar zero.

    O custo médio ganha do preço de tabela porque é o que a casa realmente pagou
    pelo que está na prateleira, frete e desconto já embutidos.
    """
    cur.execute(
        """
        SELECT sum(quantidade * custo_medio) AS valor, sum(quantidade) AS qtd
          FROM estoque_saldos
         WHERE id_produto = %s AND quantidade > 0 AND custo_medio > 0
        """,
        (id_produto,),
    )
    linha = cur.fetchone()
    if linha and linha["qtd"] and dec(linha["qtd"]) > 0:
        # Médio ponderado entre os locais: o mesmo insumo pode estar na câmara
        # fria e no bar com custos diferentes.
        return (dec(linha["valor"]) / dec(linha["qtd"])).quantize(CASAS_CUSTO), "custo_medio"

    cur.execute(
        """
        SELECT pf.ultimo_preco, pf.fator, pf.preferencial
          FROM produto_fornecedor pf
         WHERE pf.id_produto = %s AND pf.ultimo_preco IS NOT NULL
         ORDER BY pf.preferencial DESC, pf.ultima_compra DESC NULLS LAST
         LIMIT 1
        """,
        (id_produto,),
    )
    linha = cur.fetchone()
    if not linha:
        return None, "sem_custo"

    fator = dec(linha["fator"]) or Decimal(1)
    # O preço do fornecedor é pela embalagem dele; o fator traz para a unidade
    # de estoque (caixa de 12 → custo por unidade).
    return (dec(linha["ultimo_preco"]) / fator).quantize(CASAS_CUSTO), "ultima_compra"


def converter(qtd: Decimal, de: str | None, para: str | None, ums: dict) -> Decimal | None:
    """Converte dentro da mesma grandeza (kg↔g, L↔ml). Fora dela, devolve None."""
    if not de or not para or de == para:
        return qtd
    a, b = ums.get(de), ums.get(para)
    if not a or not b or a["grandeza"] != b["grandeza"]:
        return None
    return qtd * dec(a["fator_base"]) / dec(b["fator_base"])


def _carregar_ums(cur) -> dict:
    cur.execute("SELECT sigla, grandeza, fator_base FROM unidades_medida")
    return {r["sigla"]: dict(r) for r in cur.fetchall()}


def custo_da_ficha(cur, id_ficha: int, _visitadas: set[int] | None = None,
                   _ums: dict | None = None, _nivel: int = 0) -> dict:
    """Custo total de uma ficha, item a item, descendo nas sub-fichas.

    Devolve `{custo_total, custo_por_porcao, custo_por_unidade_rendimento,
    itens: [...], itens_sem_custo, completo}`. Nada de exceção quando falta
    preço: o que falta vem marcado, porque a ficha precisa ser útil antes de
    estar completa.
    """
    visitadas = set(_visitadas or ())
    if id_ficha in visitadas or _nivel > PROFUNDIDADE_MAXIMA:
        # Guarda de segurança: a gravação já recusa ciclo, mas dado antigo
        # não pode derrubar a tela.
        return {
            "custo_total": Decimal(0), "custo_por_porcao": Decimal(0),
            "custo_por_unidade_rendimento": Decimal(0), "itens": [],
            "itens_sem_custo": 0, "completo": False, "ciclo": True,
        }
    visitadas.add(id_ficha)
    ums = _ums or _carregar_ums(cur)

    cur.execute(
        """SELECT rendimento_qtd, rendimento_um, porcoes FROM fichas_tecnicas WHERE id = %s""",
        (id_ficha,),
    )
    ficha = cur.fetchone()
    if not ficha:
        raise ValueError("ficha inexistente")

    cur.execute(
        """
        SELECT fi.id, fi.id_insumo, fi.id_subficha, fi.qtd_bruta, fi.qtd_liquida, fi.um,
               fi.fator_correcao, fi.fator_coccao, fi.observacao, fi.ordem,
               p.nome AS insumo, p.um_estoque, p.codigo,
               sp.nome AS subficha_nome, sf.rendimento_qtd AS sub_rendimento,
               sf.rendimento_um AS sub_rendimento_um
          FROM ficha_itens fi
          LEFT JOIN produtos p ON p.id = fi.id_insumo
          LEFT JOIN fichas_tecnicas sf ON sf.id = fi.id_subficha
          LEFT JOIN produtos sp ON sp.id = sf.id_produto
         WHERE fi.id_ficha = %s
         ORDER BY fi.ordem, fi.id
        """,
        (id_ficha,),
    )
    linhas = [dict(r) for r in cur.fetchall()]

    itens, total, sem_custo = [], Decimal(0), 0

    for l in linhas:
        qtd = dec(l["qtd_bruta"])
        detalhe = {
            "id": l["id"],
            "id_insumo": l["id_insumo"],
            "id_subficha": l["id_subficha"],
            "nome": l["insumo"] or l["subficha_nome"] or "—",
            "codigo": l["codigo"],
            "qtd_bruta": qtd,
            "qtd_liquida": dec(l["qtd_liquida"]) if l["qtd_liquida"] is not None else None,
            "um": l["um"],
            "fator_correcao": dec(l["fator_correcao"]),
            "fator_coccao": dec(l["fator_coccao"]),
            "observacao": l["observacao"],
            "ordem": l["ordem"],
            "custo_unitario": None,
            "custo_total": None,
            "origem_custo": "sem_custo",
            "aviso": None,
        }

        if l["id_insumo"]:
            unitario, origem = custo_do_insumo(cur, l["id_insumo"])
            detalhe["origem_custo"] = origem
            # A receita pode estar em grama e o estoque em quilo.
            convertida = converter(qtd, l["um"], l["um_estoque"], ums)
            if convertida is None:
                detalhe["aviso"] = (
                    f"{l['um'] or '?'} não converte para {l['um_estoque'] or '?'}"
                )
            elif unitario is not None:
                detalhe["custo_unitario"] = unitario
                detalhe["custo_total"] = (convertida * unitario).quantize(CASAS_CUSTO)
        else:
            sub = custo_da_ficha(cur, l["id_subficha"], visitadas, ums, _nivel + 1)
            rendimento = dec(l["sub_rendimento"]) or Decimal(1)
            convertida = converter(qtd, l["um"], l["sub_rendimento_um"], ums)
            if sub.get("ciclo"):
                detalhe["aviso"] = "sub-ficha em ciclo"
            elif convertida is None:
                detalhe["aviso"] = (
                    f"{l['um'] or '?'} não converte para {l['sub_rendimento_um'] or '?'}"
                )
            elif sub["completo"]:
                unitario = (sub["custo_total"] / rendimento).quantize(CASAS_CUSTO)
                detalhe["custo_unitario"] = unitario
                detalhe["custo_total"] = (convertida * unitario).quantize(CASAS_CUSTO)
                detalhe["origem_custo"] = "subficha"
            else:
                detalhe["origem_custo"] = "subficha_incompleta"

        if detalhe["custo_total"] is None:
            sem_custo += 1
        else:
            total += detalhe["custo_total"]
        itens.append(detalhe)

    porcoes = dec(ficha["porcoes"]) or Decimal(1)
    rendimento = dec(ficha["rendimento_qtd"]) or Decimal(1)

    return {
        "custo_total": total.quantize(CASAS_CUSTO),
        "custo_por_porcao": (total / porcoes).quantize(CASAS_CUSTO),
        "custo_por_unidade_rendimento": (total / rendimento).quantize(CASAS_CUSTO),
        "itens": itens,
        "itens_sem_custo": sem_custo,
        "completo": sem_custo == 0 and bool(itens),
        "ciclo": False,
    }


def descendentes_da_ficha(cur, id_ficha: int) -> set[int]:
    """Todas as fichas usadas abaixo desta — é o que prova que não há ciclo."""
    cur.execute(
        """
        WITH RECURSIVE abaixo AS (
            SELECT fi.id_subficha AS id FROM ficha_itens fi
             WHERE fi.id_ficha = %s AND fi.id_subficha IS NOT NULL
            UNION
            SELECT fi.id_subficha FROM ficha_itens fi
              JOIN abaixo a ON a.id = fi.id_ficha
             WHERE fi.id_subficha IS NOT NULL
        ) SELECT id FROM abaixo
        """,
        (id_ficha,),
    )
    return {r["id"] for r in cur.fetchall()}
