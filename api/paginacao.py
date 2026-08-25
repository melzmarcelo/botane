"""O total de uma listagem, no cabeçalho `X-Total`.

A tela precisa saber que existe mais coisa além da página. Sem o total, uma
lista cheia e uma lista CORTADA são indistinguíveis — e quem procura conclui que
o registro não existe quando ele está na página seguinte. Foi o que aconteceu
com as notas: a tela mostrava as 50 mais recentes de 3.670, sem dizer.

⚠️ **O total sai numa consulta SEPARADA, e só quando pode ter mudado.**
A primeira versão usava `count(*) OVER ()` na própria varredura — elegante e
caro: a janela obriga o banco a materializar TODAS as linhas do filtro para
depois cortar em 100. Medido com 400.000 movimentos no razão:

    página de 100, sem o total ......    4 ms
    a mesma, com count(*) OVER () ...  388 ms
    count(*) em consulta separada ...   60 ms

Virar a página não muda o total — o filtro é o mesmo. Então a conta roda no
`offset = 0` (primeira página de um filtro) e mais nada: as páginas seguintes
custam os 4 ms da varredura por índice. Quando o cabeçalho não vem, a tela
guarda o total que já tinha.

⚠️ O cabeçalho precisa estar em `expose_headers` do CORS, senão o navegador o
recebe e **não o entrega** à tela — que passa a achar que o total é o tamanho da
página.
"""


def pagina(cur, sql: str, params: tuple | list, *, limite: int, offset: int,
           resposta=None) -> list[dict]:
    """Roda a consulta paginada e, quando é o caso, o total do mesmo filtro.

    `sql` vem SEM `LIMIT`/`OFFSET` — quem monta a consulta não repete o corte, e
    o total usa exatamente o mesmo texto e os mesmos parâmetros. Uma cópia do
    filtro escrita à mão é uma cópia que diverge no primeiro `WHERE` novo.
    """
    params = tuple(params)
    cur.execute(f"{sql}\nLIMIT %s OFFSET %s", (*params, limite, offset))
    linhas = [dict(r) for r in cur.fetchall()]

    if resposta is not None and offset == 0:
        cur.execute(f"SELECT count(*) AS n FROM (\n{sql}\n) AS _do_filtro", params)
        resposta.headers["X-Total"] = str(cur.fetchone()["n"])
    return linhas


def com_total(linhas: list[dict], resposta, offset: int = 0) -> list[dict]:
    """Tira o `_total` das linhas e o devolve no cabeçalho.

    Forma antiga, para a consulta que já traz `count(*) OVER ()`. Serve às
    listas pequenas e limitadas por natureza, onde a varredura inteira não
    custa nada; para o que cresce, use `pagina`.
    """
    total = linhas[0].get("_total", len(linhas)) if linhas else offset
    for linha in linhas:
        linha.pop("_total", None)
    if resposta is not None:
        resposta.headers["X-Total"] = str(total)
    return linhas
