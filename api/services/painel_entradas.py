"""Entradas por nota: os itens das notas de entrada de um período, e em que pé cada um está.

🔑 **Pedido do dono (26/11/2026):** *"no painel do estoque, vamos criar uma nova visualização …
para ver os itens em notas de entrada. Filtrar um período e ver todos os itens que estão em alguma
nota naquele período, divididos por conciliados, lançados, recebido (quem recebeu) e o número da
nota que o produto está. O usuário gostaria de uma visão dos produtos que estão entrando no estoque
e por qual nota."*

- A data é a de ENTRADA da nota, e a de emissão quando não houver — a régua do relatório de compras
  e da memória do CMV (`coalesce(data_entrada, data_emissao)`).
- As situações são as da NOTA: a conciliar (IMPORTADA — algum item ainda sem produto), conciliada,
  recebida (a mercadoria chegou, falta o recebimento no Omie; migração 168) e lançada.
- ⚠️ Fora: nota cancelada ou não encontrada no Omie (não houve compra) e item marcado como fora do
  estoque (`ignorado`) — nenhum dos dois entra no estoque.
- 🔑 A quantidade é a de ESTOQUE (`quantidade_convertida`, na unidade do produto) quando o item
  tem produto; senão, a da nota, na unidade do fornecedor. O custo é o que entra no estoque:
  valor − desconto + frete e outros rateados (a mesma conta do relatório de compras).
"""

from datetime import date, timedelta
from decimal import Decimal

SITUACOES = {
    "IMPORTADA": "a conciliar",
    "CONCILIADA": "conciliada",
    "RECEBIDA": "recebida",
    "LANCADA": "lançada",
}
TETO_ITENS = 2000

_CUSTO = ("(i.valor_total - i.valor_desconto + i.valor_frete_rateado "
          "+ i.valor_outros_rateado)")


def _f(v) -> float:
    return float(v or 0)


def entradas(cur, id_unidade: int, inicio: date, fim: date, situacoes: list[str] | None = None,
             busca: str | None = None, limite: int = TETO_ITENS) -> dict:
    """Os itens das notas do período, com os totais por situação (sempre do período inteiro)."""
    escolhidas = [s for s in (situacoes or []) if s in SITUACOES] or list(SITUACOES)
    like = f"%{busca.strip()}%" if busca and busca.strip() else None
    base = {"u": id_unidade, "inicio": inicio, "limite": fim + timedelta(days=1),
            "todas": list(SITUACOES), "like": like}
    filtro = """n.id_unidade = %(u)s AND n.status = ANY(%(st)s) AND NOT i.ignorado
              AND coalesce(n.data_entrada, n.data_emissao) >= %(inicio)s
              AND coalesce(n.data_entrada, n.data_emissao) < %(limite)s
              AND (%(like)s::text IS NULL
                   OR p.nome ILIKE %(like)s OR p.codigo ILIKE %(like)s
                   OR i.descricao_fornecedor ILIKE %(like)s OR n.numero ILIKE %(like)s
                   OR coalesce(f.nome, n.nome_emitente) ILIKE %(like)s
                   OR n.recebido_por ILIKE %(like)s)"""
    juncao = """FROM nota_itens i
                JOIN notas_entrada n ON n.id = i.id_nota
                LEFT JOIN produtos p ON p.id = i.id_produto
                LEFT JOIN fornecedores f ON f.id = n.id_fornecedor"""

    # Os totais de cada situação, na mesma busca — é o que as abas mostram ao lado do nome.
    cur.execute(
        f"""SELECT n.status, count(*) AS itens, count(DISTINCT n.id) AS notas,
                   count(DISTINCT i.id_produto) AS produtos,
                   coalesce(sum({_CUSTO}), 0) AS valor
              {juncao}
             WHERE {filtro.replace('%(st)s', '%(todas)s')}
             GROUP BY n.status""", base)
    por = {r["status"]: r for r in cur.fetchall()}
    por_situacao = [{"situacao": s, "nome": n,
                     "itens": por[s]["itens"] if s in por else 0,
                     "notas": por[s]["notas"] if s in por else 0,
                     "produtos": por[s]["produtos"] if s in por else 0,
                     "valor": _f(por[s]["valor"]) if s in por else 0.0}
                    for s, n in SITUACOES.items()]

    cur.execute(
        f"""SELECT i.id, i.id_nota, i.seq, i.id_produto, p.codigo, p.nome AS produto,
                   p.um_estoque, i.descricao_fornecedor, i.quantidade, i.um_nota,
                   i.quantidade_convertida, {_CUSTO} AS custo,
                   n.numero, n.serie, n.status, n.origem, n.recebido_por, n.recebido_em,
                   n.lancada_em, coalesce(n.data_entrada, n.data_emissao) AS data,
                   coalesce(f.nome, n.nome_emitente) AS fornecedor
              {juncao}
             WHERE {filtro}
             ORDER BY coalesce(p.nome, i.descricao_fornecedor), data, n.numero, i.seq
             LIMIT %(lim)s""", base | {"st": escolhidas, "lim": limite + 1})
    linhas = [dict(r) for r in cur.fetchall()]
    cortado = len(linhas) > limite
    itens = []
    for r in linhas[:limite]:
        com_produto = r["id_produto"] is not None and r["quantidade_convertida"] is not None
        itens.append({
            "id": r["id"], "id_nota": r["id_nota"], "id_produto": r["id_produto"],
            "codigo": r["codigo"], "produto": r["produto"],
            "descricao_fornecedor": r["descricao_fornecedor"],
            "quantidade": _f(r["quantidade_convertida"] if com_produto else r["quantidade"]),
            "um": (r["um_estoque"] if com_produto else r["um_nota"]) or "",
            "custo": _f(r["custo"]),
            "nota": (f"{r['numero']}" + (f"/{r['serie']}" if r["serie"] else "")
                     if r["numero"] else "—"),
            "fornecedor": r["fornecedor"], "data": r["data"],
            "situacao": r["status"], "origem": r["origem"],
            "recebido_por": r["recebido_por"], "recebido_em": r["recebido_em"],
            "lancada_em": r["lancada_em"],
        })

    soma = sum((Decimal(str(i["custo"])) for i in itens), Decimal(0))
    return {
        "inicio": inicio, "fim": fim, "situacoes": escolhidas, "busca": busca or None,
        "por_situacao": por_situacao,
        "totais": {"itens": len(itens), "notas": len({i["id_nota"] for i in itens}),
                   "produtos": len({i["id_produto"] for i in itens if i["id_produto"]}),
                   "valor": float(soma)},
        "itens": itens, "cortado": cortado, "limite": limite,
    }
