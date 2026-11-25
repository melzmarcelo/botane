"""Recebimento de notas: o registro de quem recebeu a nota, e se ela chegou ao sistema (162).

🔑 **Pedido do dono (24/11/2026)**: a nota chega com a mercadoria, quem recebe perde o papel e
quem lança no sistema nunca fica sabendo. Aqui se registra número, fornecedor, data e uma foto
opcional — e a lista diz, de cada uma, se a nota já está no sistema.

🔑 **"Já no sistema" é CONTA, não coluna**: a nota pode chegar do Omie dias depois. Casa pelo
número (sem pontuação nem zeros à esquerda, em maiúsculas) e pelo fornecedor; sem fornecedor do
cadastro, pelo nome do emitente.
⚠️ Só registro: nada aqui mexe em estoque, custo ou na nota de entrada.
"""

from datetime import date

from fastapi import HTTPException

SITUACOES = {
    "LANCADA": "Lançada no sistema",
    "NO_SISTEMA": "No sistema, falta lançar",
    "FALTA": "Não chegou ao sistema",
}

# O número da nota sem pontuação, sem zeros à esquerda, em maiúsculas: "000.123" = "123".
_NUMERO = "ltrim(upper(regexp_replace({c}, '[^0-9A-Za-z]', '', 'g')), '0')"

_COLUNAS = f"""
    r.id, r.id_unidade, r.numero_nota, r.id_fornecedor, r.fornecedor_texto, r.data_nota,
    r.observacao, (r.foto IS NOT NULL) AS tem_foto, r.recebido_por, r.registrado_em,
    coalesce(f.nome_fantasia, f.nome, r.fornecedor_texto) AS fornecedor,
    u.nome AS recebido_por_nome,
    n.id AS id_nota, n.status AS status_nota,
    CASE WHEN n.status = 'LANCADA' THEN 'LANCADA'
         WHEN n.id IS NOT NULL THEN 'NO_SISTEMA' ELSE 'FALTA' END AS situacao"""

_JUNTAS = f"""
    FROM recebimentos r
    LEFT JOIN fornecedores f ON f.id = r.id_fornecedor
    LEFT JOIN usuarios u ON u.id = r.recebido_por
    LEFT JOIN LATERAL (
        SELECT ne.id, ne.status FROM notas_entrada ne
         WHERE ne.id_unidade = r.id_unidade
           AND {_NUMERO.format(c='ne.numero')} = {_NUMERO.format(c='r.numero_nota')}
           AND (ne.id_fornecedor = r.id_fornecedor
                OR (r.id_fornecedor IS NULL
                    AND upper(ne.nome_emitente) LIKE '%%' || upper(r.fornecedor_texto) || '%%'))
         ORDER BY (ne.status = 'LANCADA') DESC, ne.id DESC
         LIMIT 1) n ON true"""


def consulta(id_unidade: int, situacao: str | None = None, de: date | None = None,
             ate: date | None = None, busca: str | None = None) -> tuple[str, dict]:
    """A consulta da tela e do relatório — uma só, para os dois não divergirem."""
    termo = (busca or "").strip() or None
    sql = f"""SELECT * FROM (SELECT {_COLUNAS} {_JUNTAS}
                WHERE r.id_unidade = %(u)s
                  AND (%(de)s::date IS NULL OR r.data_nota >= %(de)s)
                  AND (%(ate)s::date IS NULL OR r.data_nota <= %(ate)s)
                  AND (%(busca)s::text IS NULL OR r.numero_nota ILIKE '%%' || %(busca)s || '%%'
                       OR coalesce(f.nome_fantasia, f.nome, r.fornecedor_texto)
                          ILIKE '%%' || %(busca)s || '%%')) x
             WHERE (%(sit)s::text IS NULL OR x.situacao = %(sit)s)
             ORDER BY x.data_nota DESC, x.id DESC"""
    return sql, {"u": id_unidade, "de": de, "ate": ate, "busca": termo, "sit": situacao}


def resumo(cur, id_unidade: int) -> dict:
    """Quantas ainda não chegaram ao sistema — o número que cobra quem lança."""
    sql, p = consulta(id_unidade, "FALTA")
    cur.execute(f"SELECT count(*) AS n FROM ({sql}) y", p)
    return {"faltam": cur.fetchone()["n"]}


def registrar(cur, id_unidade: int, id_usuario: int, dados: dict, foto: str | None) -> dict:
    numero = (dados.get("numero_nota") or "").strip()
    if not numero:
        raise HTTPException(status_code=422, detail="Informe o número da nota.")
    texto = (dados.get("fornecedor_texto") or "").strip() or None
    if dados.get("id_fornecedor"):
        cur.execute("SELECT 1 FROM fornecedores WHERE id = %s", (dados["id_fornecedor"],))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail="Fornecedor não encontrado.")
        texto = None
    elif not texto:
        raise HTTPException(status_code=422, detail="Escolha o fornecedor ou escreva o nome dele.")
    # Avisa a duplicata (a mesma nota registrada duas vezes) sem bloquear de vez: o segundo
    # registro pode ser outra entrega com o mesmo número de outro fornecedor.
    cur.execute(
        f"""SELECT r.id, u.nome FROM recebimentos r LEFT JOIN usuarios u ON u.id = r.recebido_por
             WHERE r.id_unidade = %s
               AND {_NUMERO.format(c='r.numero_nota')} = {_NUMERO.format(c='%s')}
               AND (r.id_fornecedor = %s OR (r.id_fornecedor IS NULL AND %s::int IS NULL
                                              AND upper(r.fornecedor_texto) = upper(%s)))""",
        (id_unidade, numero, dados.get("id_fornecedor"), dados.get("id_fornecedor"), texto or ""))
    repetida = cur.fetchone()
    if repetida and not dados.get("mesmo_assim"):
        raise HTTPException(
            status_code=409,
            detail=f"Esta nota já foi registrada por {repetida['nome'] or 'alguém'} "
                   f"(registro nº {repetida['id']}).")
    cur.execute(
        """INSERT INTO recebimentos (id_unidade, numero_nota, id_fornecedor, fornecedor_texto,
                                     data_nota, observacao, foto, recebido_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (id_unidade, numero[:30], dados.get("id_fornecedor"), texto and texto[:120],
         dados["data_nota"], (dados.get("observacao") or "").strip()[:300] or None, foto,
         id_usuario))
    return {"id": cur.fetchone()["id"], "message": f"Nota {numero} registrada como recebida."}


def travar(cur, id_unidade: int, id_recebimento: int) -> dict:
    cur.execute("""SELECT * FROM recebimentos WHERE id = %s AND id_unidade = %s FOR UPDATE""",
                (id_recebimento, id_unidade))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Registro não encontrado nesta loja.")
    return dict(r)
