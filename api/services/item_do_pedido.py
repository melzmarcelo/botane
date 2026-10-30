"""A linha do pedido a partir do item do cardápio: a ESCOLHA e os ADICIONAIS.

🔑 **Uma regra só para o site e para a mesa** (estudo `docs/item-de-escolha-estudo.md`,
29/10/2026). Antes, os adicionais existiam só no pedido da mesa e o site os mandava no texto
da observação; o item de escolha (142) chegou aos dois ao mesmo tempo, e duas cópias da
conta de mínimo/máximo divergiriam na primeira mudança.

- **Item de escolha**: o cliente escolhe UMA opção (Chocolate Quente → Branco; Monte sua
  cesta → Cesta Média) pelo id DELA (`catalogo_item_escolhas.id`) — o cardápio público não
  expõe id de produto. O produto da opção vai na linha, com o preço dele.
- **Adicionais** são os do produto que vai na linha. Num grupo que `permite_repetir`, o mesmo
  id repetido na lista conta como quantidade ("2 geleias") e mínimo/máximo contam UNIDADES;
  nos outros, repetido conta uma vez (como sempre foi).
⚠️ **Nenhum preço vem do aparelho**: tudo sai do item que o servidor montou.
"""

from collections import Counter
from decimal import Decimal

from fastapi import HTTPException

from services.custos import dec

_CENTAVO = Decimal("0.01")


def conferir_adicionais(nome: str, grupos: list[dict], ids: list[int]) -> tuple[list[dict], Decimal]:
    """Os adicionais escolhidos, conferidos contra os grupos (mínimo e máximo).

    Devolve a escolha congelada (`id`, `nome`, `preco`, `quantidade`) e o acréscimo ao preço.
    """
    por_id = {o["id"]: (g, o) for g in grupos for o in g["opcoes"]}
    contagem = Counter(ids)
    for i in contagem:
        if i not in por_id:
            raise HTTPException(status_code=409,
                                detail=f"Uma opção de {nome} mudou. Atualize o cardápio.")
    escolhidos = []
    for i, n in contagem.items():
        g, o = por_id[i]
        escolhidos.append((g, o, n if g.get("permite_repetir") else 1))
    for g in grupos:
        n = sum(q for gg, _o, q in escolhidos if gg["id"] == g["id"])
        if n < g["minimo"] or n > g["maximo"]:
            faixa = (f"{g['minimo']}" if g["minimo"] == g["maximo"]
                     else f"de {g['minimo']} a {g['maximo']}")
            raise HTTPException(status_code=422,
                                detail=f"{nome}: em “{g['nome']}”, escolha {faixa}.")
    extras = sum((dec(o["preco"] or 0) * q for _g, o, q in escolhidos), Decimal(0))
    # A ordem do cardápio, não a dos toques: a cozinha lê a mesma lista sempre.
    ordem = {o["id"]: n for n, o in enumerate(o for g in grupos for o in g["opcoes"])}
    escolhidos.sort(key=lambda x: ordem[x[1]["id"]])
    return ([{"id": o["id"], "nome": o["nome"], "preco": o["preco"], "quantidade": q}
             for _g, o, q in escolhidos], extras)


def resolver(item: dict, escolha: int | None, adicionais: list[int]) -> dict:
    """O produto, o nome, o preço unitário (com os adicionais) e os adicionais congelados.

    `item` é o item como o cardápio o mostra: `nome`, `preco`, `id_produto`, `adicionais` e
    `escolhas` (nulo no prato comum; a lista de opções no item de escolha, cada uma com `id`
    da opção e `id_produto`). `escolha` é o id da OPÇÃO.
    """
    nome, preco, grupos, id_produto = item["nome"], item["preco"], item["adicionais"], item["id_produto"]
    if item.get("escolhas") is not None:
        opcao = next((o for o in item["escolhas"] if o["id"] == escolha), None)
        if escolha is None:
            raise HTTPException(status_code=422, detail=f"{nome}: escolha uma das opções.")
        if opcao is None:
            raise HTTPException(status_code=409,
                                detail=f"Uma opção de {nome} mudou. Atualize o cardápio.")
        nome = f"{nome} · {opcao['nome']}"
        preco, grupos, id_produto = opcao["preco"], opcao["adicionais"], opcao["id_produto"]
    elif escolha is not None:
        raise HTTPException(status_code=409, detail=f"{nome} não tem opções a escolher.")
    if preco is None:
        raise HTTPException(status_code=409, detail=f"{nome} está sem preço e não pode ser pedido.")
    congelados, extras = conferir_adicionais(nome, grupos, adicionais)
    return {"id_produto": id_produto, "nome": nome,
            "preco_unitario": (dec(preco) + extras).quantize(_CENTAVO),
            "adicionais": congelados or None}
