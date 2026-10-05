"""Por onde começar: os produtos VENDIDOS que ainda não sabem o próprio custo.

🔑 **Por que existe (05/10/2026).** No ar havia 446 produtos de produção própria
sem ficha e só 2,67% da receita coberta. A lista de pendências era alfabética e
do cadastro inteiro: quem tinha uma tarde para fazer fichas não tinha como saber
que cinco delas cobrem um terço do faturamento e quatrocentas não cobrem nada.

🔑 **A ordem é a da RECEITA**, e cada linha diz quanto de cobertura ela soma —
é o que transforma "446 pendências" numa fila de trabalho com começo.

⚠️ **Mede o que foi VENDIDO sem custo**, não o cadastro: `venda_itens` com
`custo_ficha_unitario` nulo, que é exatamente o que a apuração conta como
"item sem custo". Produto sem ficha que ninguém vende não entra — ele não
distorce número nenhum.
⚠️ **Só o que tem produto vinculado.** Item vendido sem vínculo é outra fila
(Vendas ▸ sem vínculo) e outra correção; aqui ele só entra no total, para a
cobertura bater com a do painel de CMV.
⚠️ **O custo do item de venda é CONGELADO**: fazer a ficha hoje custeia as
vendas de amanhã, não reescreve as do período. A tela diz isso.
"""
from __future__ import annotations

SEM_FICHA = "sem_ficha"                 # produzido e sem ficha nenhuma
FICHA_SEM_CUSTO = "ficha_sem_custo"     # tem ficha, mas algum ingrediente não tem custo
SEM_CUSTO_DE_COMPRA = "sem_custo"       # comprado pronto e nunca teve custo


def fila(cur, id_unidade: int, dias: int = 30, limite: int = 30,
         ve_valores: bool = False) -> dict:
    """Os produtos vendidos sem custo nos últimos `dias`, do que mais pesa para o que menos."""
    p = {"u": id_unidade, "dias": dias, "limite": limite}
    cur.execute(
        """SELECT coalesce(sum(vi.valor_total), 0) AS receita,
                  coalesce(sum(vi.valor_total)
                           FILTER (WHERE vi.custo_ficha_unitario IS NOT NULL), 0) AS com_custo
             FROM venda_itens vi JOIN vendas v ON v.id = vi.id_venda
            WHERE v.id_unidade = %(u)s AND NOT v.cancelada
              AND v.data >= current_date - %(dias)s""", p)
    total = cur.fetchone()
    receita = float(total["receita"] or 0)
    com_custo = float(total["com_custo"] or 0)

    cur.execute(
        """SELECT pr.id, pr.codigo, pr.nome, pr.tipo, pr.producao_propria,
                  sum(vi.valor_total) AS receita, sum(vi.quantidade) AS quantidade,
                  (SELECT f.status FROM fichas_tecnicas f
                    WHERE f.id_produto = pr.id AND f.vigente_ate IS NULL
                      AND f.status IN ('HOMOLOGADA', 'RASCUNHO')
                    ORDER BY (f.status = 'HOMOLOGADA') DESC, f.versao DESC LIMIT 1) AS ficha,
                  (SELECT f.id FROM fichas_tecnicas f
                    WHERE f.id_produto = pr.id AND f.vigente_ate IS NULL
                      AND f.status IN ('HOMOLOGADA', 'RASCUNHO')
                    ORDER BY (f.status = 'HOMOLOGADA') DESC, f.versao DESC LIMIT 1) AS id_ficha,
                  count(*) OVER () AS produtos
             FROM venda_itens vi
             JOIN vendas v ON v.id = vi.id_venda
             JOIN produtos pr ON pr.id = vi.id_produto
            WHERE v.id_unidade = %(u)s AND NOT v.cancelada
              AND v.data >= current_date - %(dias)s
              AND vi.custo_ficha_unitario IS NULL AND pr.ativo
            GROUP BY pr.id, pr.codigo, pr.nome, pr.tipo, pr.producao_propria
            ORDER BY sum(vi.valor_total) DESC, pr.nome
            LIMIT %(limite)s""", p)
    linhas = [dict(r) for r in cur.fetchall()]

    itens, acumulada = [], com_custo
    for l in linhas:
        valor = float(l["receita"] or 0)
        acumulada += valor
        if l["ficha"]:
            falta = FICHA_SEM_CUSTO
        elif l["producao_propria"] or l["tipo"] == "PRODUZIDO":
            falta = SEM_FICHA
        else:
            falta = SEM_CUSTO_DE_COMPRA
        itens.append({
            "id_produto": l["id"], "codigo": l["codigo"], "nome": l["nome"],
            "falta": falta, "id_ficha": l["id_ficha"],
            "quantidade": float(l["quantidade"] or 0),
            # ⚠️ Dinheiro só para quem vê custo: a cozinha recebe a ORDEM e o peso
            # em percentual, que é o que ela precisa para escolher por onde começar.
            "receita": valor if ve_valores else None,
            "participacao_pct": round(valor / receita * 100, 2) if receita else 0.0,
            # A cobertura que a casa teria resolvendo esta linha e todas as de cima.
            "cobertura_acumulada_pct": round(acumulada / receita * 100, 2) if receita else 0.0,
        })
    return {
        "dias": dias,
        "cobertura_pct": round(com_custo / receita * 100, 2) if receita else None,
        "receita": receita if ve_valores else None,
        "produtos": linhas[0]["produtos"] if linhas else 0,
        "itens": itens,
    }
