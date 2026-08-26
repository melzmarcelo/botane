"""O cardápio do PDV Legal, e o de-para que liga item vendido a prato daqui.

Sem isto a venda entra e o **CMV teórico é zero**: a receita aparece, o CMV real
aparece, e a variância — que é o número que interessa — não tem com o que
comparar. Numa primeira importação real, 100 itens de 57 produtos distintos
entraram sem vínculo nenhum.

O vínculo mora em `codigos_externos` com `sistema = 'PDV_LEGAL'`, a mesma tabela
que já servia ao Omie e aos códigos de fornecedor. A chave é o `codigo` do PDV
(que chega no item da venda como `codproduto`), e não a descrição: nome de prato
muda de cardápio para cardápio e o número não.

⚠️ **A cascata só vincula o que é certo**: o de-para que já existe e o nome
IDÊNTICO. Semelhança sugere e para por aí. É a mesma regra da conciliação de
nota, e pela mesma razão: um vínculo errado não fica errado sozinho — ele
contamina o CMV teórico de todo mês em que aquele prato foi vendido, e ninguém
vai procurar ali.

⚠️ **E não se casa código com código.** O `codReferencia` do cardápio e o
`produtos.codigo` daqui são espaços de nome diferentes; ver `_candidato`.
"""

import re
import unicodedata
from difflib import SequenceMatcher

from services.pdv.cliente import ClientePdv

SISTEMA = "PDV_LEGAL"

# Teto de páginas do `getlistaresumida` (100 por página). Cardápio de mil itens
# é cardápio de rede, não de café — e um laço sem teto contra API de terceiro é
# um jeito de descobrir o limite deles do pior jeito.
TETO_DE_PAGINAS = 40

# Abaixo disto nem sugere. Um palpite fraco na tela é pior que nenhum: ele
# convida ao clique, e quem clica não confere.
SCORE_MINIMO = 55.0


def _normalizar(texto: str | None) -> str:
    """Sem acento, sem pontuação, espaços colapsados, minúsculo.

    "PÃO DE QUEIJO C/ REQ." e "pao de queijo c req" viram a mesma coisa — que é
    o que permite o nome idêntico valer como vínculo em vez de só sugestão.
    """
    if not texto:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9 ]", " ", re.sub(r"\s+", " ", sem_acento.lower())).strip()


def baixar(cliente: ClientePdv) -> list[dict]:
    """Todo o cardápio, página a página.

    ⚠️ **A resposta é um ENVELOPE, não uma lista**: `{total_count, total,
    pagina, data}`. Tratá-la como lista devolveria as quatro chaves como se
    fossem quatro produtos — e o importador diria "4 itens" numa conta com 164.
    """
    itens: list[dict] = []
    pagina = 1
    while pagina <= TETO_DE_PAGINAS:
        envelope = cliente.get(f"/produtos/getlistaresumida/{pagina}")
        if isinstance(envelope, list):        # modo simulado, ou API que mudou
            lote, total = envelope, len(envelope)
        else:
            lote = (envelope or {}).get("data") or []
            total = int((envelope or {}).get("total") or 0)
        if not lote:
            break
        itens.extend(lote)
        if len(itens) >= total:
            break
        pagina += 1
    return itens


def _candidato(cur, item: dict, por_nome: dict[str, int]) -> tuple[int | None, str, float]:
    """A cascata: onde este item do cardápio encontra um produto daqui.

    A ordem é da certeza para o palpite, e o palpite não vincula:

    1. **código do PDV** já registrado em `codigos_externos` — o de-para de antes
    2. **nome idêntico**, normalizado
    3. **semelhança** — só sugestão, nunca vínculo

    ⚠️ **NÃO existe passo por código da casa, e isso custou caro para descobrir.**
    A primeira versão casava o `codReferencia` do cardápio ("72", "75", "141")
    com `produtos.codigo` — e os dois são espaços de nome diferentes. Numa base
    com 2.189 insumos importados do Omie, **os 78 vínculos criados assim estavam
    todos errados**: REDBULL virou LIMÃO TAITY, PÃO COM MANTEIGA virou
    MANJERICÃO, BOLO virou ADESIVO VINIL PRETO. Nenhum deles daria erro em lugar
    nenhum — apenas o CMV teórico de todo mês sairia com o custo do insumo
    errado, para sempre, e ninguém iria procurar ali.
    """
    codigo = str(item.get("codigo") or "")
    referencia = str(item.get("codReferencia") or "")
    descricao = item.get("descricao") or ""

    if codigo:
        cur.execute(
            "SELECT id_produto FROM codigos_externos WHERE sistema = %s AND codigo = %s",
            (SISTEMA, codigo),
        )
        achado = cur.fetchone()
        if achado:
            return achado["id_produto"], "ja_vinculado", 100.0

    chave = _normalizar(descricao)
    if chave and chave in por_nome:
        return por_nome[chave], "nome", 100.0

    melhor, melhor_score = None, 0.0
    for nome, id_produto in por_nome.items():
        score = SequenceMatcher(None, chave, nome).ratio() * 100
        if score > melhor_score:
            melhor, melhor_score = id_produto, score
    if melhor and melhor_score >= SCORE_MINIMO:
        return melhor, "semelhanca", round(melhor_score, 2)
    return None, "sem_candidato", 0.0


def importar(cur, cliente: ClientePdv, id_usuario: int,
             criar_ausentes: bool = True) -> dict:
    """Traz o cardápio e liga o que dá para ligar.

    ⚠️ **Semelhança NÃO vincula** — vira uma linha na observação do rascunho
    criado ("parece com X"), para quem for fazer a ficha conferir. Vínculo
    errado não fica errado sozinho: contamina o CMV teórico de todo mês em que
    aquele prato foi vendido, e ninguém vai procurar ali.

    ⚠️ **`criar_ausentes` faz o prato nascer RASCUNHO.** O item do cardápio é um
    PRATO — ele precisa de ficha para virar custo. Criá-lo como rascunho com
    `producao_propria` marcada o põe na fila de "produzido sem ficha", que é
    exatamente a lista que alguém precisa percorrer. Não criar deixaria 164
    itens vendidos sem nada do outro lado.
    """
    itens = baixar(cliente)

    cur.execute("SELECT id, nome FROM produtos WHERE ativo")
    por_nome = {_normalizar(r["nome"]): r["id"] for r in cur.fetchall()}

    resumo = {"itens": len(itens), "vinculados": 0, "ja_vinculados": 0,
              "criados": 0, "sugestoes": 0, "sem_vinculo": 0}

    for item in itens:
        codigo = str(item.get("codigo") or "")
        if not codigo:
            continue
        descricao = (item.get("descricao") or "")[:200]
        id_produto, origem, score = _candidato(cur, item, por_nome)

        if origem == "ja_vinculado":
            resumo["ja_vinculados"] += 1
            continue

        dica = None
        if origem == "semelhanca":
            # Sugestão só: a dica viaja com o rascunho, mas não amarra nada.
            resumo["sugestoes"] += 1
            cur.execute("SELECT nome FROM produtos WHERE id = %s", (id_produto,))
            parecido = (cur.fetchone() or {}).get("nome")
            dica = (f"Parece com “{parecido}” ({score:.0f}%). Confira antes de "
                    "fazer a ficha — o palpite não vinculou nada.")
            id_produto = None

        if not id_produto and criar_ausentes:
            # ⚠️ O código da casa nasce com prefixo: `codigo` é único, e o número
            # do PDV pode colidir com um código que alguém já usou aqui.
            cur.execute(
                """INSERT INTO produtos (codigo, nome, tipo, status, origem,
                                         producao_propria, controla_estoque, observacao,
                                         criado_por)
                   VALUES (%s, %s, 'PRODUZIDO', 'RASCUNHO', 'PDV', true, false, %s, %s)
                   ON CONFLICT DO NOTHING RETURNING id""",
                (f"PDV-{codigo}"[:40], descricao or f"Item {codigo}", dica, id_usuario),
            )
            criado = cur.fetchone()
            if criado:
                id_produto = criado["id"]
                origem = "criado"
                resumo["criados"] += 1

        if not id_produto:
            resumo["sem_vinculo"] += 1
            continue

        cur.execute(
            """INSERT INTO codigos_externos (sistema, codigo, id_produto, descricao_externa,
                                             origem_vinculo, confirmado_por)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (sistema, codigo) DO UPDATE
                   SET descricao_externa = EXCLUDED.descricao_externa""",
            (SISTEMA, codigo, id_produto, descricao, origem.upper()[:20], id_usuario),
        )
        if origem != "criado":
            resumo["vinculados"] += 1

    return resumo


def reconciliar(cur, id_unidade: int) -> dict:
    """Passa o de-para nos itens de venda que ficaram sem produto.

    ⚠️ **Existe pela mesma razão que a reconciliação de nota**: a ordem real é a
    venda chegar antes de o cardápio estar ligado. Sem isto, item que não achou
    produto no dia da importação ficaria pendente para sempre — e o CMV teórico
    daquele mês nunca fecharia, mesmo depois de alguém arrumar o de-para.

    ⚠️ **O custo é recalculado AGORA, não herdado.** `custo_ficha_unitario` é
    congelado no momento do uso; um item que entrou sem produto entrou sem custo,
    e ao ganhar produto precisa do custo de hoje — que é o que o mês passa a
    contar. Isso muda o CMV teórico do período, e é o efeito desejado: antes ele
    estava contando zero.
    """
    from services import cmv as motor

    cur.execute(
        """SELECT vi.id, vi.codigo_pdv, ce.id_produto
             FROM venda_itens vi
             JOIN vendas v ON v.id = vi.id_venda
             JOIN codigos_externos ce ON ce.sistema = %s AND ce.codigo = vi.codigo_pdv
            WHERE v.id_unidade = %s AND vi.id_produto IS NULL AND NOT v.cancelada""",
        (SISTEMA, id_unidade),
    )
    pendentes = [dict(r) for r in cur.fetchall()]

    custos: dict[int, tuple] = {}
    vinculados, com_custo = 0, 0
    for item in pendentes:
        id_produto = item["id_produto"]
        if id_produto not in custos:
            custos[id_produto] = motor.custo_teorico_do_produto(cur, id_produto)
        custo, origem = custos[id_produto]
        cur.execute(
            """UPDATE venda_itens
                  SET id_produto = %s, custo_ficha_unitario = %s, origem_custo = %s
                WHERE id = %s""",
            (id_produto, custo, origem, item["id"]),
        )
        vinculados += 1
        if custo is not None:
            com_custo += 1

    return {"vinculados": vinculados, "com_custo": com_custo,
            "sem_custo": vinculados - com_custo}
