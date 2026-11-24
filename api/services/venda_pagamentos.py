"""Como cada venda foi paga — as finalizadoras do cupom (migração 160).

🔑 **Pedido do dono (24/11/2026):** *"conseguimos a finalizadora da compra, se foi dinheiro,
debito, credito, pix ..."*. Estudo em `docs/pdv-finalizadoras-estudo.md`.

🔑 **O troco é linha à parte** e se desconta do dinheiro só na hora de somar: o que a gaveta
recebeu e o que ficou nela são os dois números da conferência de caixa.
⚠️ **Toda soma filtra a venda cancelada e o consumo interno**, como a receita. O cupom
cancelado guarda os pagamentos para a conferência com o PDV fechar, e não conta.
"""

from datetime import date, timedelta
from decimal import Decimal

GRUPOS = {
    "CREDITO": "Crédito",
    "DEBITO": "Débito",
    "PIX": "Pix",
    "DINHEIRO": "Dinheiro",
    "VALE": "Vale-presente",
    "OUTRO": "Outro",
}
# A ordem da tela e do relatório: cartão primeiro, que é onde está o dinheiro da casa.
ORDEM = list(GRUPOS)

# Releitura do histórico: uma chamada ao PDV por dia. Teto de paciência, não da API.
TETO_DE_DIAS = 120


def gravar(cur, id_unidade: int, id_venda: int, pagamentos: list[dict]) -> int:
    """Troca os pagamentos da venda pelos que vieram. Devolve quantos gravou.

    ⚠️ Apaga e regrava, não acumula: reler o mesmo dia duas vezes não pode dobrar o crédito.
    """
    cur.execute("DELETE FROM venda_pagamentos WHERE id_venda = %s", (id_venda,))
    for p in pagamentos:
        cur.execute(
            """INSERT INTO venda_pagamentos (id_venda, id_unidade, grupo, nome_pdv,
                                             cod_forma_pdv, valor)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (id_venda, id_unidade, p["grupo"], p.get("nome_pdv"), p.get("cod_forma_pdv"),
             p["valor"]))
    return len(pagamentos)


def da_venda(cur, id_venda: int) -> dict:
    """Os pagamentos de uma venda, para a tela dela, com o troco já dito."""
    cur.execute("""SELECT grupo, nome_pdv, valor FROM venda_pagamentos
                    WHERE id_venda = %s ORDER BY id""", (id_venda,))
    linhas = [dict(r) for r in cur.fetchall()]
    troco = sum((l["valor"] for l in linhas if l["grupo"] == "TROCO"), Decimal(0))
    return {
        "pagamentos": [{**l, "rotulo": GRUPOS.get(l["grupo"], l["grupo"])}
                       for l in linhas if l["grupo"] != "TROCO"],
        "troco": troco,
    }


def por_forma(cur, id_unidade: int, inicio: date, fim: date, receita: Decimal) -> dict:
    """O quadro "Por forma de pagamento" do painel de vendas.

    🔑 **Dinheiro é LÍQUIDO** (recebido − troco): é o que ficou na casa, e só assim a soma das
    formas fecha com a receita.
    ⚠️ **O que não fecha vira "Não informado"**: venda da planilha, lançada à mão ou do PDV
    ainda não relida. Esconder a diferença faria o quadro parecer completo sem ser.
    """
    cur.execute(
        """SELECT vp.grupo, sum(vp.valor) AS valor, count(DISTINCT vp.id_venda) AS cupons
             FROM venda_pagamentos vp JOIN vendas v ON v.id = vp.id_venda
            WHERE v.id_unidade = %s AND v.data BETWEEN %s AND %s
              AND NOT v.cancelada AND NOT v.consumo_interno
            GROUP BY vp.grupo""",
        (id_unidade, inicio, fim))
    brutos = {r["grupo"]: r for r in cur.fetchall()}
    troco = Decimal(brutos.get("TROCO", {}).get("valor") or 0)
    cur.execute(
        """SELECT count(*) AS n, coalesce(sum(v.valor_total), 0) AS valor FROM vendas v
            WHERE v.id_unidade = %s AND v.data BETWEEN %s AND %s
              AND NOT v.cancelada AND NOT v.consumo_interno
              AND NOT EXISTS (SELECT 1 FROM venda_pagamentos vp WHERE vp.id_venda = v.id)""",
        (id_unidade, inicio, fim))
    sem = cur.fetchone()

    # 🔑 161: a taxa de cada forma, configurada na loja, estima quanto o cartão levou.
    # ⚠️ Sem taxa configurada não há estimativa (nula), em vez de um "R$ 0" que parece real.
    cur.execute("SELECT grupo, taxa_pct FROM forma_pagamento_taxas WHERE id_unidade = %s",
                (id_unidade,))
    taxas = {r["grupo"]: Decimal(r["taxa_pct"]) for r in cur.fetchall()}

    linhas = []
    for g in ORDEM:
        if g not in brutos:
            continue
        valor = Decimal(brutos[g]["valor"] or 0) - (troco if g == "DINHEIRO" else 0)
        custo = (valor * taxas[g] / 100).quantize(Decimal("0.01")) if g in taxas else None
        linhas.append({"grupo": g, "rotulo": GRUPOS[g], "cupons": brutos[g]["cupons"],
                       "valor": float(valor),
                       "taxa_pct": float(taxas[g]) if g in taxas else None,
                       "custo_taxa": float(custo) if custo is not None else None})
    total = sum(Decimal(str(l["valor"])) for l in linhas)
    custos = [Decimal(str(l["custo_taxa"])) for l in linhas if l["custo_taxa"] is not None]
    for l in linhas:
        l["participacao_pct"] = (round(float(Decimal(str(l["valor"])) / total * 100), 1)
                                 if total else None)
    return {
        "linhas": linhas,
        "total": float(total),
        "custo_taxas": float(sum(custos, Decimal(0))) if custos else None,
        "troco": float(troco),
        "dinheiro_recebido": float(Decimal(brutos.get("DINHEIRO", {}).get("valor") or 0)),
        "sem_pagamento": {"cupons": sem["n"], "valor": float(sem["valor"] or 0)},
        # Fecha com a receita? A diferença pequena é o arredondamento do PDV.
        "diferenca": float(Decimal(str(receita)) - total - Decimal(sem["valor"] or 0)),
    }


def completar(cur, cliente, mapeadores, id_unidade: int, filiais: str,
              inicio: date, fim: date) -> dict:
    """Relê o PDV dia a dia e grava os pagamentos das vendas que JÁ existem.

    🔑 **Não cria venda nem mexe em item, custo ou estoque**: só preenche a forma de
    pagamento do que foi importado antes da migração 160. A venda é achada pelo documento
    (`venda_id` do PDV), a mesma chave da importação.
    ⚠️ Dia a dia (`d/d`): é a única forma do `cupom/get` sem o teto de 100 cupons.
    """
    # ⚠️ O teto corta o FIM, não o começo: quem roda de novo continua de onde parou (a rota
    # começa na primeira venda ainda sem pagamento).
    if (fim - inicio).days + 1 > TETO_DE_DIAS:
        fim = inicio + timedelta(days=TETO_DE_DIAS - 1)
    dias = cupons = completadas = sem_venda = 0
    d = inicio
    while d <= fim:
        bruto = cliente.get(f"/cupom/get/{d.isoformat()}/{d.isoformat()}/{filiais}")
        dias += 1
        for c in mapeadores.lista_de_cupons(bruto):
            cupons += 1
            if not c["documento"] or not c["pagamentos"]:
                continue
            cur.execute("""SELECT id FROM vendas
                            WHERE id_unidade = %s AND origem = 'PDV_LEGAL' AND documento = %s""",
                        (id_unidade, c["documento"]))
            venda = cur.fetchone()
            if not venda:
                sem_venda += 1
                continue
            gravar(cur, id_unidade, venda["id"], c["pagamentos"])
            completadas += 1
        d += timedelta(days=1)
    return {"inicio": inicio, "fim": fim, "dias": dias, "cupons": cupons,
            "completadas": completadas, "sem_venda": sem_venda,
            "message": (f"{completadas} venda(s) com a forma de pagamento, de {cupons} cupom(ns) "
                        f"em {dias} dia(s)"
                        + (f". {sem_venda} cupom(ns) do PDV ainda não importado(s): busque as "
                           "vendas do período" if sem_venda else ""))}
