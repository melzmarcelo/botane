"""Conferência do caixa e taxa de cada forma de pagamento (migração 161).

🔑 Etapas 3 e 4 de `docs/pdv-finalizadoras-estudo.md`, pedido do dono de 24/11/2026.

🔑 **O esperado é conta, não registro**: dinheiro recebido − troco, das finalizadoras do dia.
Reler o dia no PDV muda o esperado, e a conferência acompanha. Só o CONTADO é gravado.
⚠️ **Venda sem forma de pagamento deixa o esperado INCOMPLETO** (lançada à mão, planilha):
a tela diz quantas, em vez de apresentar um esperado menor como se fosse o certo.
"""

from datetime import date, timedelta
from decimal import Decimal

import relogio
from services.venda_pagamentos import GRUPOS

# A janela da taxa média real: três meses dão o peso de cada forma sem pegar sazonalidade velha.
DIAS_DO_MIX = 90


def _cem(v) -> Decimal:
    return Decimal(v or 0).quantize(Decimal("0.01"))


def conferencia(cur, id_unidade: int, inicio: date, fim: date) -> dict:
    """Dia a dia: o dinheiro que devia estar na gaveta, o contado e a diferença."""
    cur.execute(
        """SELECT v.data,
                  coalesce(sum(p.valor) FILTER (WHERE p.grupo = 'DINHEIRO'), 0) AS recebido,
                  coalesce(sum(p.valor) FILTER (WHERE p.grupo = 'TROCO'), 0) AS troco,
                  count(DISTINCT v.id) FILTER (WHERE p.grupo = 'DINHEIRO') AS cupons_dinheiro
             FROM vendas v JOIN venda_pagamentos p ON p.id_venda = v.id
            WHERE v.id_unidade = %s AND v.data BETWEEN %s AND %s
              AND NOT v.cancelada AND NOT v.consumo_interno
            GROUP BY v.data""",
        (id_unidade, inicio, fim))
    pagos = {r["data"]: r for r in cur.fetchall()}
    cur.execute(
        """SELECT v.data, count(*) AS cupons,
                  count(*) FILTER (WHERE NOT EXISTS (
                      SELECT 1 FROM venda_pagamentos p WHERE p.id_venda = v.id)) AS sem_forma
             FROM vendas v
            WHERE v.id_unidade = %s AND v.data BETWEEN %s AND %s
              AND NOT v.cancelada AND NOT v.consumo_interno
            GROUP BY v.data""",
        (id_unidade, inicio, fim))
    vendas = {r["data"]: r for r in cur.fetchall()}
    cur.execute(
        """SELECT c.data, c.contado, c.observacao, c.conferido_em, u.nome AS conferido_por
             FROM caixa_conferencias c LEFT JOIN usuarios u ON u.id = c.conferido_por
            WHERE c.id_unidade = %s AND c.data BETWEEN %s AND %s""",
        (id_unidade, inicio, fim))
    contados = {r["data"]: r for r in cur.fetchall()}

    dias = []
    for d in sorted(set(pagos) | set(vendas) | set(contados), reverse=True):
        p, v, c = pagos.get(d) or {}, vendas.get(d) or {}, contados.get(d)
        esperado = _cem(p.get("recebido")) - _cem(p.get("troco"))
        contado = _cem(c["contado"]) if c else None
        dias.append({
            "data": d,
            "cupons": v.get("cupons", 0),
            "cupons_dinheiro": p.get("cupons_dinheiro", 0),
            "sem_forma": v.get("sem_forma", 0),
            "recebido": float(_cem(p.get("recebido"))),
            "troco": float(_cem(p.get("troco"))),
            "esperado": float(esperado),
            "contado": float(contado) if contado is not None else None,
            # Sobra positiva, falta negativa — como quem conta a gaveta fala.
            "diferenca": float(contado - esperado) if contado is not None else None,
            "observacao": c["observacao"] if c else None,
            "conferido_por": c["conferido_por"] if c else None,
            "conferido_em": c["conferido_em"] if c else None,
        })
    conferidos = [x for x in dias if x["contado"] is not None]
    return {
        "inicio": inicio, "fim": fim, "dias": dias,
        "totais": {
            "esperado": float(sum(Decimal(str(x["esperado"])) for x in dias)),
            "conferidos": len(conferidos),
            "a_conferir": sum(1 for x in dias if x["contado"] is None and x["cupons"]),
            "diferenca": float(sum(Decimal(str(x["diferenca"])) for x in conferidos)),
        },
    }


def gravar_contado(cur, id_unidade: int, dia: date, contado: Decimal, observacao: str | None,
                   id_usuario: int) -> dict:
    """Grava (ou corrige) o contado do dia. Devolve o que havia antes, para a auditoria."""
    cur.execute("""SELECT contado, observacao FROM caixa_conferencias
                    WHERE id_unidade = %s AND data = %s FOR UPDATE""", (id_unidade, dia))
    antes = cur.fetchone()
    cur.execute(
        """INSERT INTO caixa_conferencias (id_unidade, data, contado, observacao, conferido_por)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (id_unidade, data) DO UPDATE
               SET contado = EXCLUDED.contado, observacao = EXCLUDED.observacao,
                   conferido_por = EXCLUDED.conferido_por, conferido_em = now()""",
        (id_unidade, dia, contado, (observacao or "").strip() or None, id_usuario))
    return {"antes": dict(antes) if antes else None}


def taxas(cur, id_unidade: int) -> dict:
    """A taxa de cada forma, e a taxa média REAL pelo peso de cada forma nas vendas.

    🔑 A média é sobre TODA a receita com forma (dinheiro e Pix pesam com a taxa deles, em
    geral zero): é o número que a linha de cartão da Precificação deveria usar, já que ela
    incide sobre o preço de tudo o que se vende.
    """
    cur.execute("SELECT grupo, taxa_pct FROM forma_pagamento_taxas WHERE id_unidade = %s",
                (id_unidade,))
    salvas = {r["grupo"]: Decimal(r["taxa_pct"]) for r in cur.fetchall()}
    desde = relogio.hoje_da_casa() - timedelta(days=DIAS_DO_MIX)
    cur.execute(
        """SELECT p.grupo, sum(p.valor) AS valor
             FROM venda_pagamentos p JOIN vendas v ON v.id = p.id_venda
            WHERE v.id_unidade = %s AND v.data >= %s
              AND NOT v.cancelada AND NOT v.consumo_interno
            GROUP BY p.grupo""",
        (id_unidade, desde))
    mix = {r["grupo"]: Decimal(r["valor"] or 0) for r in cur.fetchall()}
    if "DINHEIRO" in mix:
        mix["DINHEIRO"] -= mix.pop("TROCO", Decimal(0))
    mix.pop("TROCO", None)
    total = sum(mix.values(), Decimal(0))
    linhas = []
    for g, rotulo in GRUPOS.items():
        peso = (mix.get(g, Decimal(0)) / total * 100) if total else None
        linhas.append({"grupo": g, "rotulo": rotulo,
                       "taxa_pct": float(salvas[g]) if g in salvas else None,
                       "peso_pct": round(float(peso), 1) if peso is not None else None})
    media = (sum(mix.get(g, Decimal(0)) * salvas.get(g, Decimal(0)) for g in mix) / total) \
        if total else None
    return {"linhas": linhas, "dias_do_mix": DIAS_DO_MIX,
            "taxa_media_real": round(float(media), 3) if media is not None else None,
            "configuradas": bool(salvas)}


def gravar_taxas(cur, id_unidade: int, itens: list[dict], id_usuario: int) -> None:
    for i in itens:
        if i.get("taxa_pct") is None:
            cur.execute("DELETE FROM forma_pagamento_taxas WHERE id_unidade = %s AND grupo = %s",
                        (id_unidade, i["grupo"]))
            continue
        cur.execute(
            """INSERT INTO forma_pagamento_taxas (id_unidade, grupo, taxa_pct, atualizado_por)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (id_unidade, grupo) DO UPDATE
                   SET taxa_pct = EXCLUDED.taxa_pct, atualizado_por = EXCLUDED.atualizado_por,
                       atualizado_em = now()""",
            (id_unidade, i["grupo"], i["taxa_pct"], id_usuario))
