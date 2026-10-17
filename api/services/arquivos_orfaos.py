"""Os arquivos guardados que nenhum registro aponta mais — e a limpeza deles, conferida antes.

🔑 **Pedido do dono (17/10/2026)**, na análise do Cardápio Vivo: *"uma varredura que lista os
arquivos sem dono e apaga só depois de você conferir"*. Fotos, vídeos e PDFs moram na tabela
`arquivos` (ver `arquivos.py`), e até a 1.1.108 excluir uma seção deixava o vídeo dela, a mídia
das subdivisões e a dos cartões no banco, sem ninguém apontando para eles.

⚠️ **Quem aponta é descoberto pelo BANCO, não por uma lista escrita aqui**: toda coluna de texto
com `url` no nome. Uma lista à mão esqueceria a próxima coluna de foto que alguém criar — e aí a
varredura chamaria de órfão um arquivo em uso e a limpeza o apagaria. Todas as colunas que
guardam arquivo (`foto_url`, `video_url`, `video_capa_url`, `logo_url`, `arquivo_url`) seguem o
nome; as que têm `url` e guardam outra coisa (o link do Google, o do anúncio) só não casam.
⚠️ **Nada com menos de um dia**: o envio grava o arquivo e aponta para ele na mesma transação,
mas é a margem que impede apagar o que acabou de chegar enquanto alguma coisa ainda o liga.
"""

IDADE_MINIMA = "1 day"


def _referencias(cur) -> str:
    """Um SELECT com o NOME de todo arquivo que alguma coluna `*url*` aponta."""
    cur.execute(
        """SELECT c.table_name, c.column_name
             FROM information_schema.columns c
             JOIN information_schema.tables t
               ON t.table_schema = c.table_schema AND t.table_name = c.table_name
            WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'
              AND c.column_name LIKE '%%url%%'
              AND c.data_type IN ('character varying', 'text')
            ORDER BY 1, 2""")
    partes = [f"""SELECT substring("{r['column_name']}" FROM '/arquivos/([^/?#]+)') AS nome
                    FROM "{r['table_name']}" WHERE "{r['column_name']}" LIKE '%%/arquivos/%%'"""
              for r in cur.fetchall()]
    return " UNION ".join(partes) if partes else "SELECT NULL::text AS nome"


def _sql_orfaos(referencias: str) -> str:
    return f"""SELECT a.nome, a.dono, a.tipo, a.bytes, a.criado_em
                 FROM arquivos a
                WHERE a.criado_em < now() - interval '{IDADE_MINIMA}'
                  AND NOT EXISTS (SELECT 1 FROM ({referencias}) r WHERE r.nome = a.nome)"""


def listar(cur) -> dict:
    """Os órfãos (os maiores primeiro) e quanto ocupam, ao lado do total guardado."""
    ref = _referencias(cur)
    cur.execute(_sql_orfaos(ref) + " ORDER BY a.bytes DESC, a.nome")  # noqa: S608 - nomes do catálogo
    orfaos = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT count(*) AS n, coalesce(sum(bytes), 0) AS bytes FROM arquivos")
    total = dict(cur.fetchone())
    return {
        "orfaos": orfaos,
        "orfaos_n": len(orfaos),
        "orfaos_bytes": sum(int(o["bytes"] or 0) for o in orfaos),
        "total_n": total["n"],
        "total_bytes": int(total["bytes"]),
    }


def apagar(cur, nomes: list[str]) -> dict:
    """Apaga, dos nomes que a tela conferiu, só os que CONTINUAM órfãos agora.

    ⚠️ **A conferência é refeita aqui**: entre a lista e o clique alguém pode ter posto aquela
    foto num prato (não pode, porque o nome é novo a cada envio — mas o custo de conferir é uma
    consulta, e o de errar é uma foto sumida no cardápio).
    """
    if not nomes:
        return {"apagados": 0, "bytes": 0, "message": "Nada a apagar."}
    ref = _referencias(cur)
    cur.execute(
        f"""DELETE FROM arquivos WHERE nome IN (
                SELECT o.nome FROM ({_sql_orfaos(ref)}) o WHERE o.nome = ANY(%s))
            RETURNING bytes""",  # noqa: S608
        (list(nomes),))
    linhas = cur.fetchall()
    apagados, bytes_ = len(linhas), sum(int(r["bytes"] or 0) for r in linhas)
    return {"apagados": apagados, "bytes": bytes_,
            "message": f"{apagados} arquivo(s) sem dono apagado(s)."}
