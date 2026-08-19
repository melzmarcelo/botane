"""Kit / combo — o item de venda que vale por vários produtos.

O PDV manda "Combo executivo" como uma linha só. Aqui essa linha vira a soma
dos componentes, cada um custando pela **sua própria regra**: prato produzido
custa pela ficha vigente, refrigerante de revenda custa pelo médio do estoque.

Por isso o kit aponta para PRODUTO e não para ficha (como o `ficha_itens` faz):
ficha é uma versão, e um combo preso a uma versão continuaria calculando pela
receita velha depois que a cozinha homologasse a nova.
"""

from decimal import Decimal

from fastapi import HTTPException

from services.custos import dec

# O mesmo teto das fichas: o ciclo é recusado na gravação, e isto aqui é o
# cinto de segurança para dado que já esteja no banco.
PROFUNDIDADE_MAXIMA = 6


def componentes(cur, id_kit: int) -> list[dict]:
    cur.execute(
        """SELECT k.id, k.id_componente, k.quantidade, k.observacao, k.ordem,
                  p.codigo, p.nome AS componente, p.tipo, p.um_estoque, p.ativo
             FROM kit_itens k
             JOIN produtos p ON p.id = k.id_componente
            WHERE k.id_kit = %s
            ORDER BY k.ordem, k.id""",
        (id_kit,),
    )
    return [dict(r) for r in cur.fetchall()]


def _caminho_ate(cur, id_origem: int, id_destino: int, visitados=None) -> bool:
    """O componente já contém o kit em algum nível? Então o ciclo existe."""
    if id_origem == id_destino:
        return True
    visitados = visitados or set()
    if id_origem in visitados or len(visitados) > PROFUNDIDADE_MAXIMA:
        return False
    visitados.add(id_origem)
    cur.execute("SELECT id_componente FROM kit_itens WHERE id_kit = %s", (id_origem,))
    for linha in cur.fetchall():
        if _caminho_ate(cur, linha["id_componente"], id_destino, visitados):
            return True
    return False


def gravar(cur, id_kit: int, itens: list[dict]) -> dict:
    """Substitui a composição inteira. Recusa ciclo e componente repetido."""
    cur.execute("SELECT nome, tipo FROM produtos WHERE id = %s", (id_kit,))
    kit = cur.fetchone()
    if not kit:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    if kit["tipo"] != "KIT":
        raise HTTPException(
            status_code=400,
            detail=f"{kit['nome']} não é do tipo KIT — mude o tipo no cadastro do produto.",
        )

    vistos = set()
    for item in itens:
        id_comp = item["id_componente"]
        if id_comp == id_kit:
            raise HTTPException(status_code=400, detail="Um kit não pode conter a si mesmo.")
        if id_comp in vistos:
            raise HTTPException(
                status_code=400,
                detail="Componente repetido — some as quantidades numa linha só.",
            )
        vistos.add(id_comp)

        cur.execute("SELECT nome, ativo FROM produtos WHERE id = %s", (id_comp,))
        comp = cur.fetchone()
        if not comp:
            raise HTTPException(status_code=400, detail=f"Componente {id_comp} não existe.")
        if not comp["ativo"]:
            raise HTTPException(
                status_code=400, detail=f"{comp['nome']} está inativo — não entra em kit.")
        # O ciclo indireto: o componente já leva de volta a este kit?
        if _caminho_ate(cur, id_comp, id_kit):
            raise HTTPException(
                status_code=400,
                detail=f"{comp['nome']} já contém este kit — isso faria um ciclo.",
            )

    cur.execute("DELETE FROM kit_itens WHERE id_kit = %s", (id_kit,))
    for ordem, item in enumerate(itens):
        cur.execute(
            """INSERT INTO kit_itens (id_kit, id_componente, quantidade, observacao, ordem)
               VALUES (%s, %s, %s, %s, %s)""",
            (id_kit, item["id_componente"], item["quantidade"], item.get("observacao"), ordem),
        )
    return {"itens": len(itens)}


def custo(cur, id_kit: int, _nivel: int = 0) -> tuple[Decimal | None, str, list[dict]]:
    """Custo teórico do kit: a soma dos componentes, cada um pela regra dele.

    Devolve (custo, origem, detalhe). `origem` diz o quanto dá para confiar:

    * `kit`          — todos os componentes têm custo conhecido;
    * `kit_parcial`  — algum componente não tem, e o total está incompleto;
    * `kit_vazio`    — ninguém montou a composição ainda.

    O parcial não vira zero nem `None`: o que se sabe entra na conta e a origem
    diz que falta pedaço. Zerar esconderia o buraco no CMV teórico; devolver
    nada jogaria fora o custo do componente que a casa já conhece.
    """
    from services.cmv import custo_teorico_do_produto  # ciclo de import

    if _nivel > PROFUNDIDADE_MAXIMA:
        return None, "kit_profundo", []

    itens = componentes(cur, id_kit)
    if not itens:
        return None, "kit_vazio", []

    total, faltou, detalhe = Decimal(0), False, []
    for item in itens:
        unitario, origem = custo_teorico_do_produto(cur, item["id_componente"], _nivel + 1)
        qtd = dec(item["quantidade"])
        parcial = (dec(unitario) * qtd) if unitario is not None else None
        if parcial is None:
            faltou = True
        else:
            total += parcial
        detalhe.append({
            "id_componente": item["id_componente"],
            "componente": item["componente"],
            "quantidade": float(qtd),
            "custo_unitario": float(unitario) if unitario is not None else None,
            "custo": float(parcial) if parcial is not None else None,
            "origem": origem,
        })
    return total, ("kit_parcial" if faltou else "kit"), detalhe
