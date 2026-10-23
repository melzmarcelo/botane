"""Contas a receber do consumo: o que está em aberto, os lotes de cobrança e a baixa.

🔑 **Pedido do dono (22/10/2026):** sem período para abrir e fechar — o consumo
se lança na data em que aconteceu, e a casa cobra quando quiser: "o usuário 1 vai
consumindo, e de 15 em 15 dias ele faz o pagamento. Dia X geramos um lote com todos
os documentos dele, mandamos o relatório, e assim que receber, fizemos a baixa."

O ciclo de um documento com pessoa:

    em aberto  →  em cobrança (num lote ABERTO)  →  recebido (lote RECEBIDO)

⚠️ **"Em aberto" é a venda SEM lote** (`vendas.id_consumo_lote`), nunca uma conta
de datas — a mesma regra do carimbo da 057. As datas só ESCOLHEM o que entra num
lote; depois disso o que vale é o lote.
⚠️ **Um lote é de UMA pessoa** (decisão do dono). Gerar "para todo mundo" é gerar
vários lotes de uma vez, um por pessoa: cada um tem o seu relatório e a sua baixa,
e quem pagou não espera quem não pagou.
⚠️ **Baixa só do lote INTEIRO** (decisão do dono). O que a pessoa não pagar sai do
lote antes da baixa (`tirar_documento`) e volta a ficar em aberto, para o próximo.
"""

from datetime import date

FORMAS = {
    "PIX": "Pix",
    "DINHEIRO": "Dinheiro",
    "CARTAO": "Cartão",
    "TRANSFERENCIA": "Transferência",
    "FOLHA": "Desconto em folha",
    "PERMUTA": "Permuta",
    "OUTRO": "Outro",
}

SITUACOES = {"ABERTO": "em cobrança", "RECEBIDO": "recebido", "CANCELADO": "cancelado"}

# Um cupom com as somas dos itens — a base de toda conta deste módulo.
# ⚠️ As somas dos ITENS saem desta CTE, nunca do SELECT do cabeçalho: juntar
# `vendas` com `venda_itens` repete o cabeçalho por linha, e um `sum(v.desconto)`
# ali multiplicaria o desconto pelo número de itens.
# ⚠️ O preço cheio NULO cai no cobrado: nulo é "a política não tocou nesta linha".
_CUPOM = """
    SELECT v.id, v.id_pessoa, v.data, v.desconto,
           sum(vi.quantidade * coalesce(vi.valor_unitario_cheio, vi.valor_unitario)) AS cheio,
           sum(vi.valor_total) AS itens_total,
           count(*) AS itens
      FROM vendas v
      JOIN venda_itens vi ON vi.id_venda = v.id
"""


def _filtro_aberto(de: date | None, ate: date | None) -> tuple[str, tuple]:
    """O WHERE do que está em aberto, com o recorte opcional de datas."""
    return ("""WHERE v.id_unidade = %s AND NOT v.cancelada
                 AND v.id_pessoa IS NOT NULL AND v.id_consumo_lote IS NULL
                 AND (%s::date IS NULL OR v.data >= %s)
                 AND (%s::date IS NULL OR v.data <= %s)""",
            (de, de, ate, ate))


def em_aberto(cur, id_unidade: int, de: date | None = None, ate: date | None = None,
              ids_pessoa: list[int] | None = None) -> list[dict]:
    """Quanto cada pessoa deve e ainda não foi cobrada — o relatório de "em aberto".

    ⚠️ **Cupom cancelado fica de fora**: cobrar um cupom cancelado seria cobrar o
    que não foi consumido.
    """
    onde, ps = _filtro_aberto(de, ate)
    ids = ids_pessoa or None
    cur.execute(
        f"""WITH cupom AS ({_CUPOM} {onde}
                   AND (%s::int[] IS NULL OR v.id_pessoa = ANY(%s))
                 GROUP BY v.id)
            SELECT f.id AS id_pessoa, f.nome AS pessoa,
                   f.cupom_base, f.cupom_desconto_pct,
                   count(*) AS cupons,
                   sum(c.itens) AS itens,
                   sum(c.cheio) AS total_cheio,
                   sum(c.itens_total - c.desconto) AS total,
                   sum(c.cheio - c.itens_total + c.desconto) AS desconto,
                   min(c.data) AS desde, max(c.data) AS ate
              FROM cupom c
              JOIN fornecedores f ON f.id = c.id_pessoa
             GROUP BY f.id, f.nome, f.cupom_base, f.cupom_desconto_pct
             ORDER BY sum(c.itens_total - c.desconto) DESC, f.nome""",
        (id_unidade, *ps, ids, ids),
    )
    return [dict(r) for r in cur.fetchall()]


def em_cobranca_por_pessoa(cur, id_unidade: int) -> dict[int, dict]:
    """Quanto cada pessoa tem em lotes ainda não pagos — para a mesma tabela."""
    cur.execute(
        """SELECT id_pessoa, count(*) AS lotes, sum(total) AS total
             FROM consumo_lotes
            WHERE id_unidade = %s AND status = 'ABERTO'
            GROUP BY id_pessoa""",
        (id_unidade,),
    )
    return {r["id_pessoa"]: dict(r) for r in cur.fetchall()}


def _recalcular(cur, id_lote: int) -> dict:
    """Grava no lote o valor dos documentos que estão nele.

    🔑 Só se chama ao CRIAR o lote e ao TIRAR um documento dele — nos dois casos o
    lote ainda não foi pago. Depois da baixa o valor não se mexe: é o que foi
    cobrado, e um documento em lote não se cancela nem ganha item.
    """
    cur.execute(
        f"""WITH cupom AS ({_CUPOM}
                 WHERE v.id_consumo_lote = %s AND NOT v.cancelada
                 GROUP BY v.id)
            SELECT count(*) AS cupons, coalesce(sum(itens), 0) AS itens,
                   coalesce(sum(cheio), 0) AS total_cheio,
                   coalesce(sum(cheio - itens_total + desconto), 0) AS desconto,
                   coalesce(sum(itens_total - desconto), 0) AS total,
                   min(data) AS desde
              FROM cupom""",
        (id_lote,),
    )
    s = dict(cur.fetchone())
    cur.execute(
        """UPDATE consumo_lotes
              SET cupons = %s, itens = %s, total_cheio = round(%s, 2),
                  desconto = round(%s, 2), total = round(%s, 2), desde = %s
            WHERE id = %s""",
        (s["cupons"], s["itens"], s["total_cheio"], s["desconto"], s["total"], s["desde"],
         id_lote),
    )
    return s


def gerar(cur, id_unidade: int, id_usuario: int | None, ate: date,
          ids_pessoa: list[int] | None = None, de: date | None = None,
          ids_venda: list[int] | None = None, observacao: str | None = None) -> list[dict]:
    """Gera os lotes: um por pessoa, com o que ela tem em aberto até `ate`.

    🔑 **Sem pessoas, são TODAS as que têm algo em aberto** no recorte — é o
    "gerar de todo mundo" da quinzena.
    ⚠️ `ids_venda` escolhe documentos a dedo (desmarcar um na tela). Só faz
    sentido com uma pessoa; com várias, quem filtra é a data.
    ⚠️ **Quem impede cobrar duas vezes é o UPDATE**, não uma checagem antes: ele
    só pega linha com `id_consumo_lote IS NULL`, e dois cliques simultâneos
    disputam a mesma linha — o segundo, depois do primeiro, não acha nada. Lote
    que ficou sem documento é apagado antes de sair daqui.
    """
    pessoas = [l["id_pessoa"] for l in em_aberto(cur, id_unidade, de, ate, ids_pessoa)]
    criados: list[dict] = []
    for id_pessoa in pessoas:
        cur.execute(
            """INSERT INTO consumo_lotes (id_unidade, id_pessoa, ate, id_usuario_criou,
                                          observacao)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (id_unidade, id_pessoa, ate, id_usuario, observacao),
        )
        id_lote = cur.fetchone()["id"]
        cur.execute(
            """UPDATE vendas SET id_consumo_lote = %s
                WHERE id_unidade = %s AND id_pessoa = %s AND NOT cancelada
                  AND id_consumo_lote IS NULL
                  AND data <= %s AND (%s::date IS NULL OR data >= %s)
                  AND (%s::int[] IS NULL OR id = ANY(%s))""",
            (id_lote, id_unidade, id_pessoa, ate, de, de, ids_venda, ids_venda),
        )
        if not cur.rowcount:
            cur.execute("DELETE FROM consumo_lotes WHERE id = %s", (id_lote,))
            continue
        s = _recalcular(cur, id_lote)
        criados.append({"id": id_lote, "id_pessoa": id_pessoa, "cupons": s["cupons"],
                        "total": float(s["total"] or 0)})
    return criados


def _travar(cur, id_unidade: int, id_lote: int) -> dict | None:
    cur.execute(
        """SELECT id, id_pessoa, status, total FROM consumo_lotes
            WHERE id = %s AND id_unidade = %s FOR UPDATE""",
        (id_lote, id_unidade),
    )
    linha = cur.fetchone()
    return dict(linha) if linha else None


def receber(cur, id_unidade: int, id_lote: int, id_usuario: int | None,
            recebido_em: date, forma: str, observacao: str | None = None) -> dict:
    """A baixa: o lote inteiro foi pago, nesta data e desta forma."""
    lote = _travar(cur, id_unidade, id_lote)
    if not lote:
        return {"erro": "Lote não encontrado.", "status": 404}
    if lote["status"] != "ABERTO":
        return {"erro": f"Este lote está {SITUACOES[lote['status']]} — só o lote em "
                        "cobrança recebe baixa.", "status": 409}
    if forma not in FORMAS:
        return {"erro": "Forma de pagamento que não existe.", "status": 400}
    cur.execute(
        """UPDATE consumo_lotes
              SET status = 'RECEBIDO', recebido_em = %s, forma_pagamento = %s,
                  observacao_baixa = %s, baixado_em = now(), id_usuario_baixou = %s
            WHERE id = %s""",
        (recebido_em, forma, observacao, id_usuario, id_lote),
    )
    return {"id": id_lote, "total": float(lote["total"] or 0)}


def estornar_baixa(cur, id_unidade: int, id_lote: int) -> dict:
    """Desfaz a baixa: o lote volta a estar em cobrança, com os mesmos documentos.

    🔑 Existe porque a baixa é um clique, e dar baixa no lote errado é o engano
    mais provável da tela. Ao contrário do período, qualquer lote se estorna: os
    lotes não dependem uns dos outros.
    """
    lote = _travar(cur, id_unidade, id_lote)
    if not lote:
        return {"erro": "Lote não encontrado.", "status": 404}
    if lote["status"] != "RECEBIDO":
        return {"erro": "Este lote não está recebido.", "status": 409}
    cur.execute(
        """UPDATE consumo_lotes
              SET status = 'ABERTO', recebido_em = NULL, forma_pagamento = NULL,
                  observacao_baixa = NULL, baixado_em = NULL, id_usuario_baixou = NULL
            WHERE id = %s""",
        (id_lote,),
    )
    return {"id": id_lote}


def cancelar(cur, id_unidade: int, id_lote: int, id_usuario: int | None) -> dict:
    """Desfaz o lote: os documentos voltam a ficar em aberto.

    ⚠️ **Só o lote em cobrança.** O recebido já foi pago — para mexer nele,
    estorna-se a baixa primeiro, e fica registrado quem foi.
    ⚠️ O lote não se apaga: CANCELADO fica no histórico com o valor que tinha, e
    a auditoria guarda quais documentos estavam nele.
    """
    lote = _travar(cur, id_unidade, id_lote)
    if not lote:
        return {"erro": "Lote não encontrado.", "status": 404}
    if lote["status"] != "ABERTO":
        return {"erro": "Só o lote em cobrança se cancela"
                        + (" — estorne a baixa antes." if lote["status"] == "RECEBIDO" else "."),
                "status": 409}
    cur.execute("UPDATE vendas SET id_consumo_lote = NULL WHERE id_consumo_lote = %s "
                "RETURNING id", (id_lote,))
    devolvidas = [r["id"] for r in cur.fetchall()]
    cur.execute(
        """UPDATE consumo_lotes
              SET status = 'CANCELADO', cancelado_em = now(), id_usuario_cancelou = %s
            WHERE id = %s""",
        (id_usuario, id_lote),
    )
    return {"id": id_lote, "vendas": devolvidas}


def tirar_documento(cur, id_unidade: int, id_lote: int, id_venda: int,
                    id_usuario: int | None) -> dict:
    """Tira UM documento do lote em cobrança — ele volta para em aberto.

    🔑 É o caminho do "pagou só uma parte": como a baixa é sempre do lote
    inteiro, o que não foi pago sai do lote antes, e fica para o próximo.
    ⚠️ Tirar o último documento cancela o lote — lote vazio não se cobra.
    """
    lote = _travar(cur, id_unidade, id_lote)
    if not lote:
        return {"erro": "Lote não encontrado.", "status": 404}
    if lote["status"] != "ABERTO":
        return {"erro": "Só se tira documento de lote em cobrança.", "status": 409}
    cur.execute("UPDATE vendas SET id_consumo_lote = NULL "
                "WHERE id = %s AND id_consumo_lote = %s", (id_venda, id_lote))
    if not cur.rowcount:
        return {"erro": "Este documento não está neste lote.", "status": 404}
    s = _recalcular(cur, id_lote)
    if not s["cupons"]:
        cancelar(cur, id_unidade, id_lote, id_usuario)
        return {"id": id_lote, "cancelado": True, "total": 0.0}
    return {"id": id_lote, "cancelado": False, "total": float(s["total"] or 0)}


_LOTE = """
    SELECT l.id, l.id_pessoa, f.nome AS pessoa, l.ate, l.desde, l.status,
           l.cupons, l.itens, l.total_cheio, l.desconto, l.total,
           l.criado_em, uc.nome AS criou, l.observacao,
           l.recebido_em, l.forma_pagamento, l.baixado_em, ub.nome AS baixou,
           l.observacao_baixa, l.cancelado_em, l.id_consumo_periodo
      FROM consumo_lotes l
      JOIN fornecedores f ON f.id = l.id_pessoa
      LEFT JOIN usuarios uc ON uc.id = l.id_usuario_criou
      LEFT JOIN usuarios ub ON ub.id = l.id_usuario_baixou
"""


def lotes(cur, id_unidade: int, status: list[str] | None = None,
          id_pessoa: int | None = None, limite: int = 200) -> list[dict]:
    """Os lotes, o mais novo primeiro."""
    cur.execute(
        f"""{_LOTE}
            WHERE l.id_unidade = %s
              AND (%s::text[] IS NULL OR l.status = ANY(%s))
              AND (%s::int IS NULL OR l.id_pessoa = %s)
            ORDER BY l.criado_em DESC, l.id DESC
            LIMIT %s""",
        (id_unidade, status or None, status or None, id_pessoa, id_pessoa, limite),
    )
    return [dict(r) for r in cur.fetchall()]


def lote(cur, id_unidade: int, id_lote: int) -> dict | None:
    """Um lote desta loja.

    ⚠️ O `id_unidade` no WHERE não é decoração: sem ele, um id chutado leria o
    lote de outra loja, e o relatório mostraria o que aquela gente deve.
    """
    cur.execute(f"{_LOTE} WHERE l.id = %s AND l.id_unidade = %s", (id_lote, id_unidade))
    linha = cur.fetchone()
    return dict(linha) if linha else None


def rotulo(l: dict) -> str:
    """Como o lote se chama no cabeçalho do arquivo e na tela."""
    return f"Lote nº {l['id']} — {l['pessoa']}, até {l['ate']:%d/%m/%Y}"
