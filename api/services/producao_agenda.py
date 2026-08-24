"""Agenda de produção — o PLANO, que é diferente do que já aconteceu.

Até aqui produzir era um só gesto: quem lançava a produção estava dizendo que
ela já tinha acontecido. Falta o passo anterior — "amanhã a gente faz 20 kg de
massa" —, que é onde a cozinha se organiza e onde o estoque mínimo vira ação.

A agenda **não mexe no estoque**. Ela é intenção. Quem mexe é a produção, no
momento em que a linha é confirmada, e aí o razão registra o que sempre
registrou. Uma linha planejada que ninguém cumpriu é informação: mostra o que
ficou para trás.

⚠️ **Só produto PARA_ESTOQUE entra na agenda.** O café passado não se agenda:
ele nasce e morre na venda (ver `producao_da_venda`).
"""

from datetime import date, timedelta

from fastapi import HTTPException

from services import estoque as motor
from services.custos import dec

PLANEJADA, PRODUZIDA, CANCELADA = "PLANEJADA", "PRODUZIDA", "CANCELADA"


def _produto(cur, id_produto: int) -> dict:
    cur.execute(
        """SELECT p.id, p.nome, p.codigo, p.um_estoque, p.ativo, p.producao_propria,
                  p.modo_producao, p.estoque_minimo, p.id_local_padrao,
                  (SELECT f.id FROM fichas_tecnicas f
                    WHERE f.id_produto = p.id AND f.status = 'HOMOLOGADA'
                    ORDER BY f.versao DESC LIMIT 1) AS id_ficha
             FROM produtos p WHERE p.id = %s""",
        (id_produto,),
    )
    p = cur.fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return dict(p)


def agendar(cur, id_unidade: int, id_produto: int, data_prevista: date,
            quantidade: float, id_usuario: int, id_local: int | None = None,
            observacao: str | None = None, origem: str = "MANUAL") -> dict:
    """Põe (ou soma) uma linha no plano do dia.

    Agendar o mesmo produto duas vezes para o mesmo dia SOMA, em vez de criar
    duas linhas: quem agenda de novo está aumentando o lote, não abrindo outra
    produção — e duas linhas separadas virariam duas idas ao fogão.
    """
    p = _produto(cur, id_produto)
    if not p["ativo"]:
        raise HTTPException(status_code=400, detail=f"{p['nome']} está inativo.")
    if not p["id_ficha"]:
        raise HTTPException(
            status_code=400,
            detail=f"{p['nome']} não tem ficha homologada — sem ela não há o que produzir.",
        )
    if p["modo_producao"] == "NA_HORA":
        raise HTTPException(
            status_code=400,
            detail=(f"{p['nome']} é produzido na hora da venda: não se agenda. "
                    "Mude o modo de produção se ele passou a ser feito para estoque."),
        )

    cur.execute(
        """INSERT INTO producao_agenda (id_unidade, id_produto, id_local, data_prevista,
                                        quantidade, origem, observacao, criado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (id_unidade, id_produto, data_prevista) WHERE status = 'PLANEJADA'
           DO UPDATE SET quantidade = producao_agenda.quantidade + EXCLUDED.quantidade,
                         observacao = coalesce(EXCLUDED.observacao, producao_agenda.observacao)
           RETURNING id, quantidade""",
        (id_unidade, id_produto, id_local or p["id_local_padrao"], data_prevista,
         quantidade, origem, observacao, id_usuario),
    )
    linha = cur.fetchone()
    return {"id": linha["id"], "quantidade": float(linha["quantidade"]),
            "produto": p["nome"], "data_prevista": str(data_prevista)}


def listar(cur, id_unidade: int, inicio: date | None = None, fim: date | None = None,
           status: str | None = None) -> list[dict]:
    """O plano do período, com o que já foi cumprido e o que ficou para trás."""
    cur.execute(
        """SELECT a.id, a.id_produto, p.codigo, p.nome AS produto, p.um_estoque,
                  a.data_prevista, a.quantidade, a.status, a.origem, a.observacao,
                  a.id_local, l.nome AS local, a.id_producao,
                  u.nome AS criado_por, a.criado_em, a.produzido_em,
                  pu.nome AS produzido_por,
                  coalesce((SELECT sum(s.quantidade) FROM estoque_saldos s
                             WHERE s.id_produto = p.id AND s.id_unidade = a.id_unidade), 0)
                      AS saldo_atual,
                  p.estoque_minimo,
                  -- Atrasada é a planejada cuja data já passou. É o número que
                  -- diz se a agenda está sendo usada ou só preenchida.
                  (a.status = 'PLANEJADA' AND a.data_prevista < current_date) AS atrasada
             FROM producao_agenda a
             JOIN produtos p ON p.id = a.id_produto
             LEFT JOIN locais_estoque l ON l.id = a.id_local
             LEFT JOIN usuarios u ON u.id = a.criado_por
             LEFT JOIN usuarios pu ON pu.id = a.produzido_por
            WHERE a.id_unidade = %s
              AND (%s::date IS NULL OR a.data_prevista >= %s)
              AND (%s::date IS NULL OR a.data_prevista <= %s)
              AND (%s::varchar IS NULL OR a.status = %s)
            ORDER BY a.data_prevista, lower(p.nome)""",
        (id_unidade, inicio, inicio, fim, fim, status, status),
    )
    return [dict(r) for r in cur.fetchall()]


def produzir_linha(cur, id_agenda: int, id_usuario: int,
                   quantidade: float | None = None,
                   id_local: int | None = None) -> dict:
    """Cumpre a linha: aí sim o estoque se mexe.

    A quantidade pode sair diferente da planejada — a cozinha rendeu mais ou
    menos, e o que vale é o que saiu do fogão. O plano fica registrado como
    era; a produção registra o que foi.
    """
    cur.execute("SELECT * FROM producao_agenda WHERE id = %s", (id_agenda,))
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=404, detail="Linha da agenda não encontrada")
    if linha["status"] != PLANEJADA:
        raise HTTPException(
            status_code=400,
            detail=f"Esta linha já está {linha['status'].lower()}.",
        )

    qtd = dec(quantidade) if quantidade is not None else dec(linha["quantidade"])
    if qtd <= 0:
        raise HTTPException(status_code=400, detail="Quantidade tem de ser maior que zero.")

    r = motor.produzir(
        cur, id_unidade=linha["id_unidade"], id_produto=linha["id_produto"],
        quantidade=float(qtd), id_local=id_local or linha["id_local"],
        id_usuario=id_usuario, observacao=f"Agenda #{id_agenda}",
    )
    cur.execute(
        """UPDATE producao_agenda
              SET status = %s, id_producao = %s, produzido_em = now(), produzido_por = %s,
                  quantidade = %s
            WHERE id = %s""",
        (PRODUZIDA, r["id"], id_usuario, qtd, id_agenda),
    )
    return r | {"id_agenda": id_agenda, "planejado": float(linha["quantidade"]),
                "produzido": float(qtd)}


def cancelar(cur, id_agenda: int, motivo: str | None = None) -> dict:
    cur.execute("SELECT status, observacao FROM producao_agenda WHERE id = %s", (id_agenda,))
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=404, detail="Linha da agenda não encontrada")
    if linha["status"] == PRODUZIDA:
        raise HTTPException(
            status_code=400,
            detail="Esta linha já virou produção — o razão não se desfaz por aqui, estorne.",
        )
    cur.execute(
        """UPDATE producao_agenda SET status = %s,
                  observacao = coalesce(%s, observacao) WHERE id = %s""",
        (CANCELADA, motivo, id_agenda),
    )
    return {"id": id_agenda, "message": "Linha cancelada"}


def sugestoes(cur, id_unidade: int) -> list[dict]:
    """O que está abaixo do mínimo, é produzido para estoque e não tem agenda.

    É a ponte entre o alerta e a ação: o alerta diz "vai faltar", e aqui está
    quanto falta para voltar ao mínimo, pronto para virar uma linha do plano.
    """
    cur.execute(
        """SELECT p.id AS id_produto, p.codigo, p.nome AS produto, p.um_estoque,
                  p.estoque_minimo, p.estoque_maximo,
                  coalesce(sum(s.quantidade), 0) AS saldo,
                  -- Repor até o MÁXIMO quando ele existe: produzir só até o
                  -- mínimo deixa a casa raspando o limite no dia seguinte.
                  greatest(coalesce(p.estoque_maximo, p.estoque_minimo)
                           - coalesce(sum(s.quantidade), 0), 0) AS sugerido
             FROM produtos p
             LEFT JOIN estoque_saldos s
                    ON s.id_produto = p.id AND s.id_unidade = %s
            WHERE p.ativo AND p.producao_propria AND p.modo_producao = 'PARA_ESTOQUE'
              AND p.estoque_minimo IS NOT NULL
              AND EXISTS (SELECT 1 FROM fichas_tecnicas f
                           WHERE f.id_produto = p.id AND f.status = 'HOMOLOGADA')
              AND NOT EXISTS (SELECT 1 FROM producao_agenda a
                               WHERE a.id_produto = p.id AND a.status = 'PLANEJADA'
                                 AND a.data_prevista >= current_date)
            GROUP BY p.id
           HAVING coalesce(sum(s.quantidade), 0) < p.estoque_minimo
            ORDER BY lower(p.nome)""",
        (id_unidade,),
    )
    return [dict(r) for r in cur.fetchall()]


def producao_da_venda(cur, id_unidade: int, id_produto: int, quantidade,
                      id_usuario: int, id_local: int | None = None,
                      documento: str | None = None) -> dict | None:
    """Produz o que é feito NA HORA, disparado pela venda.

    O café passado não fica em estoque: a venda e a produção são o mesmo
    instante. Sem isto, o insumo dele nunca baixaria — a casa venderia mil
    cafés e o pó continuaria inteiro no razão.

    Produz e devolve; a baixa da venda é lançada por quem chamou, para o par
    entrada/saída ficar visível no razão. O saldo volta a zero, que é a
    verdade: o produto não existe parado.
    """
    p = _produto(cur, id_produto)
    if p["modo_producao"] != "NA_HORA" or not p["id_ficha"]:
        return None
    return motor.produzir(
        cur, id_unidade=id_unidade, id_produto=id_produto, quantidade=float(quantidade),
        id_local=id_local or p["id_local_padrao"], id_usuario=id_usuario,
        observacao=f"Venda {documento}" if documento else "Venda",
    )


def resumo(cur, id_unidade: int) -> dict:
    """Os números que a tela inicial e o alerta usam."""
    cur.execute(
        """SELECT count(*) FILTER (WHERE status = 'PLANEJADA'
                                     AND data_prevista = current_date) AS hoje,
                  count(*) FILTER (WHERE status = 'PLANEJADA'
                                     AND data_prevista < current_date) AS atrasadas,
                  count(*) FILTER (WHERE status = 'PLANEJADA'
                                     AND data_prevista > current_date) AS proximas
             FROM producao_agenda WHERE id_unidade = %s""",
        (id_unidade,),
    )
    r = dict(cur.fetchone())
    r["sugestoes"] = len(sugestoes(cur, id_unidade))
    return r


def proximo_dia_util(base: date | None = None) -> date:
    """Amanhã — o dia que a cozinha pensa quando pensa em agenda."""
    return (base or date.today()) + timedelta(days=1)
