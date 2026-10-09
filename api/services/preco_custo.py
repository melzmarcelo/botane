"""A evolução de PREÇO × CUSTO de um produto — a primeira tela da Precificação.

🔑 **Pedido do dono (05/10/2026):** *"uma tela de preços, exemplo, selecionar um
produto e ver em forma de gráfico de linhas a evolução de preço × custo."*
O estudo inteiro está em `docs/precificacao-estudo.md`; esta é a parte que só
LÊ, e por isso veio primeiro: usa o que o sistema já guarda e não depende de
nenhuma das decisões em aberto da configuração.

**De onde vem cada linha — e o que o sistema NÃO sabe:**

* **Preço de venda** — `produto_precos` (`vigente_de`/`vigente_ate`), com a
  regra de sempre: o da loja manda; sem ele, o da casa (`services/precos.py`).
* **Custo do que tem FICHA** — `venda_itens.custo_ficha_unitario`, o custo
  congelado em cada venda. ⚠️ A ficha não tem série própria (o custo dela é
  calculado na hora, com o preço de hoje dos ingredientes); o congelado é a
  fotografia certa — o que o prato custava no dia em que foi vendido —, mas só
  existe nos dias em que houve venda.
* **Custo do que se REVENDE** — `estoque_movimentos.custo_medio_apos`, o médio
  depois de cada movimento. O razão é a memória do custo.

⚠️ **As séries são em DEGRAU**: preço e custo valem até a próxima mudança. Cada
ponto devolvido é uma data em que ALGO mudou, mais as duas pontas da janela —
ligar os pontos em diagonal inventaria valores no meio.
⚠️ **Sem custo é nulo, nunca zero.** Zero é uma afirmação, e faria a margem sair
em 100%.
"""
from __future__ import annotations

import relogio

from datetime import date, timedelta

from fastapi import HTTPException

FONTE_VENDAS = "vendas"   # o custo congelado em cada venda (produto com ficha)
FONTE_RAZAO = "razao"     # o custo médio do estoque


def _precos(cur, id_produto: int, id_unidade: int) -> list[dict]:
    """Todas as vigências de preço que valem para esta loja (as dela e as da casa)."""
    cur.execute(
        """SELECT id_unidade, preco_venda, vigente_de, vigente_ate
             FROM produto_precos
            WHERE id_produto = %s AND (id_unidade = %s OR id_unidade IS NULL)
            ORDER BY vigente_de, id""",
        (id_produto, id_unidade),
    )
    return [dict(r) for r in cur.fetchall()]


def _preco_em(vigencias: list[dict], dia: date):
    """O preço que valia em `dia`: o da LOJA primeiro, o da casa como reserva."""
    da_loja = da_casa = None
    for v in vigencias:
        if v["vigente_de"] <= dia and (v["vigente_ate"] is None or v["vigente_ate"] >= dia):
            if v["id_unidade"] is None:
                da_casa = v["preco_venda"]
            else:
                da_loja = v["preco_venda"]
    return da_loja if da_loja is not None else da_casa


def _custo_pelas_vendas(cur, id_produto: int, id_unidade: int) -> list[tuple[date, float]]:
    cur.execute(
        """SELECT v.data, sum(vi.custo_ficha_unitario * vi.quantidade)
                          / nullif(sum(vi.quantidade), 0) AS custo
             FROM venda_itens vi JOIN vendas v ON v.id = vi.id_venda
            WHERE vi.id_produto = %s AND v.id_unidade = %s AND NOT v.cancelada
              AND vi.custo_ficha_unitario IS NOT NULL AND vi.quantidade > 0
            GROUP BY v.data ORDER BY v.data""",
        (id_produto, id_unidade),
    )
    return [(r["data"], float(r["custo"])) for r in cur.fetchall() if r["custo"] is not None]


def _custo_pelo_razao(cur, id_produto: int, id_unidade: int) -> list[tuple[date, float]]:
    # ⚠️ O último movimento de cada DIA, na ordem da corrente (migração 104):
    # depois de um reprocessamento, o maior id deixa de ser o fim dela.
    cur.execute(
        """SELECT DISTINCT ON (data_movimento::date)
                  data_movimento::date AS dia, custo_medio_apos AS custo
             FROM estoque_movimentos
            WHERE id_produto = %s AND id_unidade = %s AND custo_medio_apos > 0
            ORDER BY data_movimento::date, coalesce(ordem_cadeia, id) DESC""",
        (id_produto, id_unidade),
    )
    return [(r["dia"], float(r["custo"])) for r in cur.fetchall()]


def _praticado(cur, id_produto: int, id_unidade: int, inicio: date, fim: date) -> dict:
    """O preço médio realmente COBRADO na janela — com desconto e promoção dentro."""
    cur.execute(
        """SELECT sum(vi.valor_total) AS receita, sum(vi.quantidade) AS quantidade
             FROM venda_itens vi JOIN vendas v ON v.id = vi.id_venda
            WHERE vi.id_produto = %s AND v.id_unidade = %s AND NOT v.cancelada
              AND v.data BETWEEN %s AND %s""",
        (id_produto, id_unidade, inicio, fim),
    )
    r = cur.fetchone() or {}
    qtd = float(r.get("quantidade") or 0)
    return {"quantidade": qtd,
            "preco_medio": round(float(r["receita"]) / qtd, 2) if qtd > 0 else None}


def evolucao(cur, id_unidade: int, id_produto: int, meses: int = 12,
             hoje: date | None = None) -> dict:
    """Preço, custo e margem do produto nos últimos `meses`, em degraus."""
    cur.execute(
        """SELECT p.id, p.codigo, p.nome, p.um_estoque,
                  EXISTS (SELECT 1 FROM fichas_tecnicas f
                           WHERE f.id_produto = p.id AND f.vigente_ate IS NULL
                             AND f.status IN ('HOMOLOGADA', 'RASCUNHO')) AS tem_ficha
             FROM produtos p WHERE p.id = %s""",
        (id_produto,),
    )
    produto = cur.fetchone()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    fim = hoje or relogio.hoje_da_casa()
    inicio = fim - timedelta(days=round(meses * 30.44))

    vigencias = _precos(cur, id_produto, id_unidade)
    pelas_vendas = _custo_pelas_vendas(cur, id_produto, id_unidade)
    pelo_razao = _custo_pelo_razao(cur, id_produto, id_unidade)
    # 🔑 Quem tem ficha é custeado pela ficha; quem não tem, pelo estoque. A outra
    # fonte é só a reserva — produto com ficha nova e sem venda ainda mostra o
    # médio do razão em vez de um gráfico vazio.
    if produto["tem_ficha"]:
        custos, fonte = (pelas_vendas, FONTE_VENDAS) if pelas_vendas else (pelo_razao, FONTE_RAZAO)
    else:
        custos, fonte = (pelo_razao, FONTE_RAZAO) if pelo_razao else (pelas_vendas, FONTE_VENDAS)
    if not custos:
        fonte = None

    def custo_em(dia: date):
        valor = None
        for quando, c in custos:        # em ordem de data: o último até `dia`
            if quando > dia:
                break
            valor = c
        return valor

    # As datas em que ALGO mudou dentro da janela, mais as duas pontas.
    datas = {inicio, fim}
    for v in vigencias:
        if inicio <= v["vigente_de"] <= fim:
            datas.add(v["vigente_de"])
        if v["vigente_ate"] is not None and inicio <= v["vigente_ate"] + timedelta(days=1) <= fim:
            datas.add(v["vigente_ate"] + timedelta(days=1))
    datas.update(quando for quando, _c in custos if inicio <= quando <= fim)

    pontos, anterior = [], None
    for dia in sorted(datas):
        preco = _preco_em(vigencias, dia)
        custo = custo_em(dia)
        linha = (float(preco) if preco is not None else None,
                 round(custo, 4) if custo is not None else None)
        # Ponto que não muda nada (e não é ponta) só engorda a resposta.
        if linha == anterior and dia not in (inicio, fim):
            continue
        anterior = linha
        margem = None
        if linha[0] and linha[1] is not None:
            margem = round((linha[0] - linha[1]) / linha[0] * 100, 2)
        pontos.append({"data": dia.isoformat(), "preco": linha[0], "custo": linha[1],
                       "margem_pct": margem})

    # ⚠️ **A janela começa onde o sistema começa a SABER algo.** Produto cadastrado
    # há um mês, visto em doze, teria onze meses de gráfico vazio à esquerda — e o
    # desenho inteiro espremido na beirada.
    while len(pontos) > 1 and pontos[0]["preco"] is None and pontos[0]["custo"] is None:
        pontos.pop(0)
    if pontos:
        inicio = date.fromisoformat(pontos[0]["data"])

    # ⚠️ Mudança é de um preço para OUTRO. O primeiro preço que o produto ganhou
    # não é mudança — contá-lo faria todo produto novo aparecer com "1 mudança".
    mudancas = [p["data"] for i, p in enumerate(pontos)
                if i > 0 and p["preco"] is not None and pontos[i - 1]["preco"] is not None
                and p["preco"] != pontos[i - 1]["preco"]]
    return {
        "produto": {"id": produto["id"], "codigo": produto["codigo"], "nome": produto["nome"],
                    "um_estoque": produto["um_estoque"], "tem_ficha": produto["tem_ficha"]},
        "inicio": inicio.isoformat(), "fim": fim.isoformat(), "meses": meses,
        "fonte_custo": fonte,
        "pontos": pontos,
        "mudancas_de_preco": mudancas,
        "praticado": _praticado(cur, id_produto, id_unidade, inicio, fim),
    }
