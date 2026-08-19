"""CMV — quanto custou o que se vendeu, e onde está a diferença.

    CMV real     = estoque inicial + compras − estoque final
    CMV teórico  = Σ (quantidade vendida × custo da ficha na data da venda)
    variância    = real − teórico

A variância é o número que interessa: ela nomeia o que a soma esconde. Positiva
quer dizer que saiu mais do estoque do que as receitas justificam — perda,
porção fora do padrão ou desvio. Negativa costuma ser prato vendido sem ficha
(ou ficha exagerada).

**O valor do estoque numa data vem do próprio razão**: para cada produto e local,
o último movimento antes do corte já carrega `saldo_apos` e `custo_medio_apos`.
Não se recalcula série nenhuma — é para isso que a fotografia existe.
"""

from datetime import date, timedelta
from decimal import Decimal

from services.custos import dec

# O que é compra de verdade (entra dinheiro novo no estoque). Transferência e
# produção são transformação interna: não entram na conta.
TIPOS_COMPRA = ("ENTRADA_NF", "ENTRADA_MANUAL")


def valor_do_estoque(cur, id_unidade: int, ate: date | None = None) -> Decimal:
    """Valor do estoque no fim do dia `ate` (ou agora, se None)."""
    if ate is None:
        cur.execute(
            """SELECT coalesce(sum(quantidade * custo_medio), 0) AS valor
                 FROM estoque_saldos WHERE id_unidade = %s""",
            (id_unidade,),
        )
        return dec(cur.fetchone()["valor"])

    cur.execute(
        """
        WITH ultimo AS (
            SELECT DISTINCT ON (id_produto, id_local)
                   id_produto, id_local, saldo_apos, custo_medio_apos
              FROM estoque_movimentos
             WHERE id_unidade = %s AND data_movimento < %s
             ORDER BY id_produto, id_local, id DESC
        )
        SELECT coalesce(sum(saldo_apos * custo_medio_apos), 0) AS valor FROM ultimo
        """,
        (id_unidade, ate + timedelta(days=1)),
    )
    return dec(cur.fetchone()["valor"])


def _soma_movimentos(cur, id_unidade: int, inicio: date, fim: date, tipos) -> Decimal:
    cur.execute(
        """SELECT coalesce(sum(abs(custo_total)), 0) AS valor
             FROM estoque_movimentos
            WHERE id_unidade = %s AND tipo = ANY(%s)
              AND data_movimento >= %s AND data_movimento < %s""",
        (id_unidade, list(tipos), inicio, fim + timedelta(days=1)),
    )
    return dec(cur.fetchone()["valor"])


def apurar(cur, id_unidade: int, inicio: date, fim: date) -> dict:
    """A conta do período inteiro, com os pedaços que explicam a variância."""
    estoque_inicial = valor_do_estoque(cur, id_unidade, inicio - timedelta(days=1))
    estoque_final = valor_do_estoque(cur, id_unidade, fim)
    compras = _soma_movimentos(cur, id_unidade, inicio, fim, TIPOS_COMPRA)

    cmv_real = estoque_inicial + compras - estoque_final

    perdas = _soma_movimentos(cur, id_unidade, inicio, fim, ("SAIDA_PERDA",))
    consumo = _soma_movimentos(cur, id_unidade, inicio, fim, ("SAIDA_CONSUMO_INTERNO",))
    cur.execute(
        """SELECT coalesce(sum(custo_total * CASE WHEN quantidade > 0 THEN 1 ELSE -1 END), 0) AS valor
             FROM estoque_movimentos
            WHERE id_unidade = %s AND tipo LIKE 'AJUSTE_INVENTARIO%%'
              AND data_movimento >= %s AND data_movimento < %s""",
        (id_unidade, inicio, fim + timedelta(days=1)),
    )
    ajustes = dec(cur.fetchone()["valor"])

    # Receita e CMV teórico saem das vendas do período.
    cur.execute(
        """SELECT coalesce(sum(vi.valor_total), 0) AS receita,
                  coalesce(sum(vi.quantidade * coalesce(vi.custo_ficha_unitario, 0)), 0) AS teorico,
                  count(*) FILTER (WHERE vi.custo_ficha_unitario IS NULL) AS itens_sem_custo,
                  coalesce(sum(vi.valor_total) FILTER (WHERE vi.custo_ficha_unitario IS NOT NULL), 0)
                      AS receita_com_custo,
                  count(DISTINCT v.id) AS vendas
             FROM venda_itens vi
             JOIN vendas v ON v.id = vi.id_venda
            WHERE v.id_unidade = %s AND NOT v.cancelada
              AND v.data BETWEEN %s AND %s""",
        (id_unidade, inicio, fim),
    )
    v = cur.fetchone()
    receita = dec(v["receita"])
    cmv_teorico = dec(v["teorico"])

    cobertura = (
        (dec(v["receita_com_custo"]) / receita * 100) if receita else Decimal(0)
    )

    return {
        "inicio": inicio,
        "fim": fim,
        "estoque_inicial": estoque_inicial,
        "compras": compras,
        "estoque_final": estoque_final,
        "cmv_real": cmv_real,
        "cmv_teorico": cmv_teorico,
        "variancia": cmv_real - cmv_teorico,
        "perdas": perdas,
        "consumo_interno": consumo,
        "ajustes": ajustes,
        "receita": receita,
        "vendas": v["vendas"],
        "itens_sem_custo": v["itens_sem_custo"],
        # Sem isto o CMV teórico mente por omissão: metade dos pratos sem ficha
        # dá um teórico pela metade e uma variância enorme que não existe.
        "cobertura_ficha_pct": cobertura,
        "food_cost_pct": (cmv_real / receita * 100) if receita else None,
    }


def curva_abc(cur, id_unidade: int, inicio: date, fim: date, limite: int = 50) -> list[dict]:
    """Onde o dinheiro do estoque foi parar no período — 80/95/100."""
    cur.execute(
        """SELECT m.id_produto, p.codigo, p.nome AS produto, p.um_estoque,
                  sum(abs(m.quantidade)) AS quantidade,
                  sum(abs(m.custo_total)) AS valor
             FROM estoque_movimentos m
             JOIN produtos p ON p.id = m.id_produto
            WHERE m.id_unidade = %s AND m.quantidade < 0
              AND m.tipo NOT IN ('TRANSFERENCIA_SAIDA', 'ESTORNO_SAIDA')
              AND m.data_movimento >= %s AND m.data_movimento < %s
            GROUP BY m.id_produto, p.codigo, p.nome, p.um_estoque
            ORDER BY valor DESC
            LIMIT %s""",
        (id_unidade, inicio, fim + timedelta(days=1), limite),
    )
    linhas = [dict(r) for r in cur.fetchall()]
    total = sum(dec(l["valor"]) for l in linhas) or Decimal(1)

    acumulado = Decimal(0)
    for l in linhas:
        valor = dec(l["valor"])
        acumulado += valor
        participacao = valor / total * 100
        acumulada = acumulado / total * 100
        l["valor"] = float(valor)
        l["quantidade"] = float(dec(l["quantidade"]))
        l["participacao_pct"] = float(participacao)
        l["acumulada_pct"] = float(acumulada)
        l["classe"] = "A" if acumulada <= 80 else ("B" if acumulada <= 95 else "C")
    return linhas


def margem_por_prato(cur, id_unidade: int, inicio: date, fim: date, limite: int = 50) -> list[dict]:
    """O que cada prato vendeu, custou e deixou — a base da engenharia de cardápio."""
    cur.execute(
        """SELECT vi.id_produto, coalesce(p.nome, vi.descricao_pdv, 'Sem vínculo') AS produto,
                  p.codigo,
                  sum(vi.quantidade) AS quantidade,
                  sum(vi.valor_total) AS receita,
                  sum(vi.quantidade * coalesce(vi.custo_ficha_unitario, 0)) AS custo,
                  bool_or(vi.custo_ficha_unitario IS NULL) AS sem_custo
             FROM venda_itens vi
             JOIN vendas v ON v.id = vi.id_venda
             LEFT JOIN produtos p ON p.id = vi.id_produto
            WHERE v.id_unidade = %s AND NOT v.cancelada AND v.data BETWEEN %s AND %s
            GROUP BY vi.id_produto, coalesce(p.nome, vi.descricao_pdv, 'Sem vínculo'), p.codigo
            ORDER BY receita DESC
            LIMIT %s""",
        (id_unidade, inicio, fim, limite),
    )
    linhas = []
    for r in cur.fetchall():
        receita, custo = dec(r["receita"]), dec(r["custo"])
        margem = receita - custo
        linhas.append({
            "id_produto": r["id_produto"],
            "produto": r["produto"],
            "codigo": r["codigo"],
            "quantidade": float(dec(r["quantidade"])),
            "receita": float(receita),
            "custo": float(custo),
            "margem": float(margem),
            "margem_pct": float(margem / receita * 100) if receita else None,
            "food_cost_pct": float(custo / receita * 100) if receita else None,
            "sem_custo": r["sem_custo"],
        })
    return linhas


def custo_teorico_do_produto(cur, id_produto: int,
                            _nivel: int = 0) -> tuple[Decimal | None, str]:
    """Quanto uma unidade vendida deste produto deveria custar.

    Três regras, nesta ordem:

    * **Kit/combo**: a soma dos componentes, cada um resolvido por esta mesma
      função — é o que faz o combo do PDV deixar de entrar sem custo.
    * **Produção própria**: pela ficha homologada vigente.
    * **Revenda**: pelo custo médio do estoque, que é o que ela custou mesmo.
    """
    from services import custos  # ciclo de import: só aqui dentro

    cur.execute("SELECT tipo FROM produtos WHERE id = %s", (id_produto,))
    linha = cur.fetchone()
    if linha and linha["tipo"] == "KIT":
        from services import kits

        valor, origem, _detalhe = kits.custo(cur, id_produto, _nivel)
        return valor, origem

    cur.execute(
        """SELECT f.id, f.rendimento_qtd
             FROM fichas_tecnicas f
            WHERE f.id_produto = %s AND f.status = 'HOMOLOGADA' AND f.vigente_ate IS NULL""",
        (id_produto,),
    )
    ficha = cur.fetchone()
    if ficha:
        calculo = custos.custo_da_ficha(cur, ficha["id"])
        if calculo["completo"] or calculo["custo_total"] > 0:
            rendimento = dec(ficha["rendimento_qtd"]) or Decimal(1)
            return (calculo["custo_total"] / rendimento), (
                "ficha" if calculo["completo"] else "ficha_parcial"
            )
        return None, "ficha_sem_custo"

    unitario, origem = custos.custo_do_insumo(cur, id_produto)
    return unitario, origem
