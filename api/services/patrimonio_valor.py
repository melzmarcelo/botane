"""Patrimônio, etapa 4: o VALOR dos bens — vida útil e depreciação (migração 141).

🔑 **Pedido do dono (28/10/2026):** *"pode seguir com a etapa 4 do patrimônio"* — valor
patrimonial por setor e depreciação (valor de compra e vida útil, dando o valor atual), só
como relatório.

🔑 **Método linear, por mês inteiro** — o da Receita: a cota mensal é o valor de compra
dividido pelos meses da vida útil, e conta-se um mês a cada "aniversário" da compra. Na
data de compra o bem vale o que custou; ao fim da vida útil, zero (sem valor residual).
⚠️ **Calculado, nunca gravado** (ver 141): mudar a vida útil ou a data de compra muda o
relatório de ontem também — é o que se quer, porque o número errado era o de antes.

⚠️ **Quem conta:**
- o "A confirmar" NÃO: ninguém viu se ele existe — somar o valor dele seria inventar ativo;
- o desativado SIM: parado num canto, continua sendo da casa;
- o baixado conta até a data da baixa — o valor "em 31/12" inclui o que saiu em março;
- o comprado DEPOIS da data pedida não conta (ainda não era da casa).
⚠️ **Sem data de compra não há como depreciar**: o bem entra pelo valor de compra, marcado
"sem data" — tirá-lo baixaria o patrimônio sem motivo; depreciá-lo seria chutar a data.
Sem valor de compra, conta como bem e não soma nada (marcado "sem valor").
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import relogio

# 🔑 O padrão da Receita (IN RFB 1.700/2017, anexo III) para máquinas, equipamentos e
# móveis — quase tudo de uma cafeteria. Computador e veículo são 5: troca-se no bem.
VIDA_UTIL_PADRAO = 10
_CENTAVO = Decimal("0.01")


def _meses(de: date, ate: date) -> int:
    """Meses INTEIROS de `de` até `ate`: de 15/01 a 14/02 é zero; a 15/02, um."""
    n = (ate.year - de.year) * 12 + (ate.month - de.month) - (1 if ate.day < de.day else 0)
    return max(n, 0)


def calcular(bem: dict, ate: date) -> dict:
    """A depreciação de UM bem até `ate` — a ficha e o relatório usam esta mesma conta.

    ⚠️ O bem baixado para na data da baixa: depois dela não era mais da casa.
    """
    anos = bem.get("vida_util_anos") or VIDA_UTIL_PADRAO
    valor = bem.get("valor_compra")
    compra = bem.get("data_compra")
    fim = min(ate, bem["data_baixa"]) if bem.get("data_baixa") else ate
    r = {"vida_util": anos, "vida_padrao": not bem.get("vida_util_anos"),
         "sem_valor": valor is None, "sem_data": compra is None,
         "meses": None, "quota_mensal": None, "depreciacao": None, "valor_atual": None,
         "depreciado_pct": None, "depreciado_total": False, "fim_vida": None}
    if valor is None:
        return r
    valor = Decimal(str(valor))
    if compra is None:
        r |= {"depreciacao": 0.0, "valor_atual": float(valor)}
        return r
    vida = anos * 12
    meses = min(_meses(compra, fim), vida)
    acumulada = (valor * meses / vida).quantize(_CENTAVO, ROUND_HALF_UP)
    fim_vida = date(compra.year + anos, compra.month, min(compra.day, 28)) \
        if (compra.month, compra.day) == (2, 29) else compra.replace(year=compra.year + anos)
    r |= {"meses": meses,
          "quota_mensal": float((valor / vida).quantize(_CENTAVO, ROUND_HALF_UP)),
          "depreciacao": float(acumulada), "valor_atual": float(valor - acumulada),
          "depreciado_pct": round(float(acumulada / valor * 100), 1) if valor else 0.0,
          "depreciado_total": meses >= vida, "fim_vida": fim_vida}
    return r


def valor(cur, id_unidade: int, ate: date | None = None,
          setores: list[int] | None = None) -> dict:
    """O valor do patrimônio da loja numa data (hoje, sem data): por setor e bem a bem."""
    ate = ate or relogio.hoje_da_casa()
    cur.execute(
        """SELECT b.id, b.codigo, b.apelido, b.descricao, b.situacao, b.id_setor,
                  s.nome AS setor, l.nome AS local, b.data_compra, b.valor_compra,
                  b.vida_util_anos, b.data_baixa
             FROM bens b
             LEFT JOIN setores s ON s.id = b.id_setor
             LEFT JOIN locais_estoque l ON l.id = b.id_local
            WHERE b.id_unidade = %(u)s AND b.situacao <> 'A_CONFIRMAR'
              AND (b.data_baixa IS NULL OR b.data_baixa > %(ate)s)
              AND (b.data_compra IS NULL OR b.data_compra <= %(ate)s)
              AND (%(setores)s::int[] IS NULL OR b.id_setor = ANY(%(setores)s))
            ORDER BY lower(coalesce(s.nome, 'zzz')), b.codigo""",
        {"u": id_unidade, "ate": ate, "setores": setores or None})
    from services.patrimonio import SITUACOES
    bens = []
    for r in cur.fetchall():
        b = dict(r)
        b["situacao_txt"] = SITUACOES.get(b["situacao"], b["situacao"])
        b["valor_compra"] = float(b["valor_compra"]) if b["valor_compra"] is not None else None
        # Baixado DEPOIS da data pedida: naquela data ainda estava em uso.
        if b["situacao"] == "BAIXADO":
            b["situacao_txt"] = f"Baixado depois ({b['data_baixa']:%d/%m/%Y})"
        b |= calcular(b, ate)
        bens.append(b)

    def somar(lista: list[dict]) -> dict:
        com = [b for b in lista if not b["sem_valor"]]
        compra = sum((Decimal(str(b["valor_compra"])) for b in com), Decimal(0))
        dep = sum((Decimal(str(b["depreciacao"])) for b in com), Decimal(0))
        return {"bens": len(lista), "sem_valor": len(lista) - len(com),
                "sem_data": sum(1 for b in com if b["sem_data"]),
                "depreciados": sum(1 for b in com if b["depreciado_total"]),
                "valor_compra": float(compra), "depreciacao": float(dep),
                "valor_atual": float(compra - dep)}

    grupos: dict = {}
    for b in bens:
        grupos.setdefault((b["setor"] or "Sem setor", b["id_setor"]), []).append(b)
    por_setor = [{"setor": k[0], "id_setor": k[1]} | somar(v) for k, v in grupos.items()]
    return {"data": ate, "vida_util_padrao": VIDA_UTIL_PADRAO, "setores": por_setor,
            "total": somar(bens), "bens": bens}
