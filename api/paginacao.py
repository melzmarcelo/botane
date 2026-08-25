"""O total de uma listagem, no cabeçalho `X-Total`.

A tela precisa saber que existe mais coisa além da página. Sem o total, uma
lista cheia e uma lista CORTADA são indistinguíveis — e quem procura conclui que
o registro não existe quando ele está na página seguinte. Foi o que aconteceu
com as notas: a tela mostrava as 50 mais recentes de 3.670, sem dizer.

O total vem na própria varredura (`count(*) OVER ()` como `_total` em cada
linha), então não custa uma segunda consulta.

⚠️ O cabeçalho precisa estar em `expose_headers` do CORS, senão o navegador o
recebe e **não o entrega** à tela — que passa a achar que o total é o tamanho da
página.
"""


def com_total(linhas: list[dict], resposta, offset: int = 0) -> list[dict]:
    """Tira o `_total` das linhas e o devolve no cabeçalho."""
    total = linhas[0].get("_total", len(linhas)) if linhas else offset
    for linha in linhas:
        linha.pop("_total", None)
    if resposta is not None:
        resposta.headers["X-Total"] = str(total)
    return linhas
