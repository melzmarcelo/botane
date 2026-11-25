"""Fluxo de caixa: o que entra × o que sai, dia a dia (módulo Financeiro, etapa 4).

🔑 **Pedido do dono (25/11/2026):** *"pode seguir com a etapa 4 do financeiro"*. Do estudo
(`docs/financeiro-estudo.md`): "A receber (vendas por forma, contas a receber) × a pagar, dia a
dia". Nada é gravado: tudo é CALCULADO do que as outras telas já registram.

O que entra, por dia:
- **vendas**: as finalizadoras do cupom (160), com o dinheiro LÍQUIDO (dinheiro − troco). A venda
  sem forma de pagamento entra como "não informado" pelo total: esconder seria um caixa menor que
  o real.
- **contas a receber**: os lotes de cobrança RECEBIDOS, na data da baixa (`recebido_em`).

O que sai, por dia:
- **contas pagas**, pela data do pagamento e pelo valor pago;
- **contas em aberto**, pela data agendada (ou pelo vencimento): a previsão;
- **contas fixas que ainda não nasceram** (167): o mês que cai no período, pelo valor do molde;
- **taxas de cartão estimadas**, quando a loja configurou a taxa de cada forma (161).

⚠️ **Não é dinheiro novo e fica de fora:** venda com pessoa (é consumo a receber; entra quando o
lote é recebido — contar as duas vezes dobraria), consumo interno, venda cancelada, o pagamento
em VALE-presente (o dinheiro entrou quando o vale foi vendido) e o lote recebido em PERMUTA ou
DESCONTO EM FOLHA.
⚠️ **O cartão entra no dia da venda**, não no dia em que a operadora deposita: a casa não
registra o prazo de cada maquininha.
⚠️ **Atrasado vai para HOJE** na previsão: a conta vencida ainda vai sair, e o primeiro dia em
que pode sair é hoje.
🔑 **Previsão de vendas** (opcional): a média do mesmo dia da semana nas quatro semanas
fechadas antes de hoje. Só nos dias que ainda não chegaram.
"""

from datetime import date, timedelta
from decimal import Decimal

import relogio
from services.contas_fixas import mes_da, somar_meses, vencimento_do_mes
from services.venda_pagamentos import GRUPOS

# As formas que entram no caixa, na ordem da tela. O vale não entra (ver acima).
FORMAS_CAIXA = ["CREDITO", "DEBITO", "PIX", "DINHEIRO", "OUTRO", "NAO_INFORMADO"]
ROTULOS = {**{g: GRUPOS[g] for g in FORMAS_CAIXA if g in GRUPOS}, "NAO_INFORMADO": "Não informado"}
SEMANAS_DA_PREVISAO = 4
TETO_DE_DIAS = 400

_ZERO = Decimal(0)
_CENT = Decimal("0.01")

# A venda que é dinheiro da casa: sem pessoa (essa é contas a receber), sem consumo interno.
_VENDA_DO_CAIXA = """v.id_unidade = %(u)s AND NOT v.cancelada AND NOT v.consumo_interno
                     AND v.id_pessoa IS NULL"""


def _cem(v) -> Decimal:
    return Decimal(v or 0).quantize(_CENT)


def _vendas_por_dia(cur, p: dict) -> dict[date, dict[str, Decimal]]:
    """{dia: {forma: valor}} com o dinheiro já líquido do troco e o "não informado"."""
    dias: dict[date, dict[str, Decimal]] = {}
    cur.execute(
        f"""SELECT v.data, vp.grupo, sum(vp.valor) AS valor
              FROM venda_pagamentos vp JOIN vendas v ON v.id = vp.id_venda
             WHERE {_VENDA_DO_CAIXA} AND v.data BETWEEN %(de)s AND %(ate)s
             GROUP BY v.data, vp.grupo""", p)
    for r in cur.fetchall():
        d = dias.setdefault(r["data"], {})
        if r["grupo"] == "TROCO":
            d["DINHEIRO"] = d.get("DINHEIRO", _ZERO) - Decimal(r["valor"])
        elif r["grupo"] in FORMAS_CAIXA:
            d[r["grupo"]] = d.get(r["grupo"], _ZERO) + Decimal(r["valor"])
    cur.execute(
        f"""SELECT v.data, sum(v.valor_total) AS valor, count(*) AS cupons FROM vendas v
             WHERE {_VENDA_DO_CAIXA} AND v.data BETWEEN %(de)s AND %(ate)s
               AND NOT EXISTS (SELECT 1 FROM venda_pagamentos vp WHERE vp.id_venda = v.id)
             GROUP BY v.data""", p)
    for r in cur.fetchall():
        dias.setdefault(r["data"], {})["NAO_INFORMADO"] = Decimal(r["valor"] or 0)
    return dias


def _previsao_por_dia_da_semana(cur, p: dict, hoje: date) -> dict[int, Decimal]:
    """{dia da semana (0 = segunda): média das vendas} nas quatro semanas antes de hoje."""
    desde = hoje - timedelta(days=7 * SEMANAS_DA_PREVISAO)
    cur.execute(
        f"""SELECT v.data, sum(v.valor_total) AS valor FROM vendas v
             WHERE {_VENDA_DO_CAIXA} AND v.data >= %(desde)s AND v.data < %(h)s
             GROUP BY v.data""", {**p, "desde": desde})
    somas = {i: _ZERO for i in range(7)}
    for r in cur.fetchall():
        somas[r["data"].weekday()] += Decimal(r["valor"] or 0)
    # Dia sem venda nenhuma (casa fechada) conta como zero: é o que se espera dele.
    return {i: (s / SEMANAS_DA_PREVISAO).quantize(_CENT) for i, s in somas.items()}


def _fixas_previstas(cur, id_unidade: int, inicio: date, fim: date) -> list[dict]:
    """Os meses das contas fixas ativas que ainda NÃO nasceram e vencem no período.

    ⚠️ Roda depois da geração (`baixar_e_registrar`): o que já devia ter nascido já nasceu e
    está em `contas_pagar`, então aqui não há como contar o mesmo mês duas vezes.
    """
    cur.execute("""SELECT f.*, (SELECT max(c.competencia) FROM contas_pagar c
                                 WHERE c.id_conta_fixa = f.id) AS ultimo_mes
                     FROM contas_fixas f WHERE f.ativo AND f.id_unidade = %s""", (id_unidade,))
    saida = []
    for f in cur.fetchall():
        mes = mes_da(f["inicio"])
        if f["ultimo_mes"]:
            mes = max(mes, somar_meses(f["ultimo_mes"], 1))
        while not f["fim"] or mes <= f["fim"]:
            venc = vencimento_do_mes(mes, f["dia_vencimento"])
            if venc > fim:
                break
            if venc >= inicio:
                saida.append({"id_conta_fixa": f["id"], "descricao": f["descricao"],
                              "vencimento": venc, "valor": Decimal(f["valor"])})
            mes = somar_meses(mes, 1)
    return saida


def fluxo(cur, id_unidade: int, inicio: date, fim: date, previsao: bool = True,
          saldo_inicial: Decimal = _ZERO, hoje: date | None = None) -> dict:
    """O fluxo do período, dia a dia, com o saldo acumulado a partir de `saldo_inicial`."""
    hoje = hoje or relogio.hoje_da_casa()
    p = {"u": id_unidade, "de": inicio, "ate": fim, "h": hoje}

    vendas = _vendas_por_dia(cur, p)

    cur.execute(
        """SELECT recebido_em AS data, sum(total) AS valor, count(*) AS lotes FROM consumo_lotes
            WHERE id_unidade = %(u)s AND status = 'RECEBIDO'
              AND forma_pagamento NOT IN ('PERMUTA', 'FOLHA')
              AND recebido_em BETWEEN %(de)s AND %(ate)s
            GROUP BY recebido_em""", p)
    receber = {r["data"]: Decimal(r["valor"]) for r in cur.fetchall()}

    cur.execute(
        """SELECT pago_em AS data, sum(valor_pago) AS valor, count(*) AS contas FROM contas_pagar
            WHERE id_unidade = %(u)s AND status = 'PAGO' AND pago_em BETWEEN %(de)s AND %(ate)s
            GROUP BY pago_em""", p)
    pago = {r["data"]: (Decimal(r["valor"]), r["contas"]) for r in cur.fetchall()}

    # Em aberto: pela data agendada, senão pelo vencimento; o atrasado cai em hoje.
    cur.execute(
        """SELECT greatest(coalesce(agendado_para, vencimento), %(h)s) AS data,
                  sum(valor) AS valor, count(*) AS contas,
                  coalesce(sum(valor) FILTER (WHERE coalesce(agendado_para, vencimento) < %(h)s), 0)
                      AS atrasado,
                  count(*) FILTER (WHERE coalesce(agendado_para, vencimento) < %(h)s) AS n_atrasado
             FROM contas_pagar
            WHERE id_unidade = %(u)s AND status IN ('A_PAGAR', 'AGENDADO')
              AND greatest(coalesce(agendado_para, vencimento), %(h)s) BETWEEN %(de)s AND %(ate)s
            GROUP BY 1""", p)
    a_pagar, atrasado, n_atrasado = {}, _ZERO, 0
    for r in cur.fetchall():
        a_pagar[r["data"]] = (Decimal(r["valor"]), r["contas"])
        atrasado += Decimal(r["atrasado"])
        n_atrasado += r["n_atrasado"]

    fixas: dict[date, list[dict]] = {}
    for x in _fixas_previstas(cur, id_unidade, inicio, fim):
        fixas.setdefault(x["vencimento"], []).append(x)

    cur.execute("SELECT grupo, taxa_pct FROM forma_pagamento_taxas WHERE id_unidade = %(u)s", p)
    taxas = {r["grupo"]: Decimal(r["taxa_pct"]) for r in cur.fetchall()}

    media_semana = _previsao_por_dia_da_semana(cur, p, hoje) if previsao else {}
    # A taxa da previsão é a média real (pelo peso de cada forma nas vendas): a venda prevista
    # não tem forma.
    taxa_media = None
    if previsao and taxas:
        from services.caixa import taxas as taxas_da_loja
        t = taxas_da_loja(cur, id_unidade)["taxa_media_real"]
        taxa_media = Decimal(str(t)) if t is not None else None

    dias, acumulado = [], Decimal(saldo_inicial)
    tot = {k: _ZERO for k in ("vendas", "vendas_previstas", "receber", "pago", "a_pagar",
                              "fixas", "taxas")}
    por_forma = {g: _ZERO for g in FORMAS_CAIXA}
    d = inicio
    while d <= fim:
        formas = vendas.get(d, {})
        v = sum(formas.values(), _ZERO)
        for g, val in formas.items():
            por_forma[g] += val
        taxa = sum((val * taxas[g] / 100 for g, val in formas.items() if g in taxas), _ZERO)
        prevista = _ZERO
        if previsao and d > hoje:
            prevista = media_semana.get(d.weekday(), _ZERO)
            if taxa_media is not None:
                taxa += prevista * taxa_media / 100
        taxa = taxa.quantize(_CENT)
        rec = receber.get(d, _ZERO)
        pg, n_pg = pago.get(d, (_ZERO, 0))
        ab, n_ab = a_pagar.get(d, (_ZERO, 0))
        fx = sum((x["valor"] for x in fixas.get(d, [])), _ZERO)
        entradas = v + prevista + rec
        saidas = pg + ab + fx + taxa
        acumulado += entradas - saidas
        for k, val in (("vendas", v), ("vendas_previstas", prevista), ("receber", rec),
                       ("pago", pg), ("a_pagar", ab), ("fixas", fx), ("taxas", taxa)):
            tot[k] += val
        dias.append({
            "data": d, "passado": d < hoje, "hoje": d == hoje,
            "vendas": float(_cem(v)),
            "formas": {g: float(_cem(val)) for g, val in formas.items() if val},
            "vendas_previstas": float(prevista), "receber": float(_cem(rec)),
            "pago": float(_cem(pg)), "n_pago": n_pg,
            "a_pagar": float(_cem(ab)), "n_a_pagar": n_ab,
            "atrasado": float(_cem(atrasado)) if d == hoje else 0.0,
            "fixas": float(_cem(fx)),
            "fixas_previstas": [{"descricao": x["descricao"], "valor": float(x["valor"])}
                                for x in fixas.get(d, [])],
            "taxas": float(taxa),
            "entradas": float(_cem(entradas)), "saidas": float(_cem(saidas)),
            "saldo": float(_cem(entradas - saidas)), "acumulado": float(_cem(acumulado)),
        })
        d += timedelta(days=1)

    cur.execute(
        f"""SELECT count(*) AS cupons, coalesce(sum(v.valor_total), 0) AS valor FROM vendas v
             WHERE {_VENDA_DO_CAIXA} AND v.data BETWEEN %(de)s AND %(ate)s
               AND NOT EXISTS (SELECT 1 FROM venda_pagamentos vp WHERE vp.id_venda = v.id)""", p)
    sem_forma = cur.fetchone()

    # O que a casa tem a receber e ainda não tem data: lotes cobrados e consumo sem lote.
    cur.execute("""SELECT count(*) AS lotes, coalesce(sum(total), 0) AS valor FROM consumo_lotes
                    WHERE id_unidade = %(u)s AND status = 'ABERTO'""", p)
    em_cobranca = cur.fetchone()
    from services.receber import em_aberto
    abertos = em_aberto(cur, id_unidade)
    sem_lote = {"pessoas": len(abertos),
                "valor": sum((Decimal(x["total"] or 0) for x in abertos), _ZERO)}

    entradas_tot = tot["vendas"] + tot["vendas_previstas"] + tot["receber"]
    saidas_tot = tot["pago"] + tot["a_pagar"] + tot["fixas"] + tot["taxas"]
    return {
        "hoje": hoje, "de": inicio, "ate": fim, "previsao": previsao,
        "saldo_inicial": float(_cem(saldo_inicial)),
        "dias": dias,
        "totais": {
            **{k: float(_cem(v)) for k, v in tot.items()},
            "entradas": float(_cem(entradas_tot)), "saidas": float(_cem(saidas_tot)),
            "saldo": float(_cem(entradas_tot - saidas_tot)),
            "saldo_final": float(_cem(acumulado)),
        },
        "por_forma": [{"forma": g, "rotulo": ROTULOS[g], "valor": float(_cem(v))}
                      for g, v in por_forma.items() if v],
        "atrasado": {"valor": float(_cem(atrasado)), "contas": n_atrasado},
        "sem_forma": {"cupons": sem_forma["cupons"], "valor": float(_cem(sem_forma["valor"]))},
        "a_receber_sem_data": {
            "em_cobranca": float(_cem(em_cobranca["valor"])), "lotes": em_cobranca["lotes"],
            "sem_lote": float(_cem(sem_lote["valor"])), "pessoas": sem_lote["pessoas"]},
        "taxas_configuradas": bool(taxas),
        "semanas_da_previsao": SEMANAS_DA_PREVISAO,
    }
