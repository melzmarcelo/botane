"""Quem entra numa contagem — a pergunta que o inventário faz antes de existir.

Até aqui a única pergunta era o LOCAL: contava-se um lugar inteiro, ou
escolhia-se produto por produto. Mas contar a despensa inteira é raro. O que a
casa faz é contar a câmara fria, ou só as bebidas, ou só o hortifrúti antes da
feira.

Agora são quatro filtros — **local, setor, categoria e tipo de produto** —, cada
um opcional, e vazio querendo dizer "todos". Eles se combinam com E: setor
`cozinha` + tipo `insumo` traz os insumos da cozinha, não a união dos dois.

⚠️ **A linha é o par produto × local, não o produto.** Sem local escolhido, o
mesmo café pode ter saldo na câmara e no estoque seco: são duas prateleiras
diferentes, contadas separadamente, e o fechamento lança dois ajustes. Tratar
como uma linha só sumiria com o estoque de um dos dois.

⚠️ **A base é o SALDO, não o cadastro.** Entram os pares que têm saldo (ou já
tiveram movimento) no local — produto que nunca passou por ali não vira linha
para alguém escrever zero. A exceção é a lista explícita de produtos, em que
quem pediu sabe o que quer contar.
"""

from fastapi import HTTPException

from models.produtos import TIPOS


def _limpar(valores, permitidos=None) -> list | None:
    """Lista vazia e `None` são a mesma coisa aqui: "todos"."""
    if not valores:
        return None
    limpos = [v for v in valores if v is not None]
    if permitidos is not None:
        desconhecidos = [v for v in limpos if v not in permitidos]
        if desconhecidos:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo de produto que não existe: {', '.join(map(str, desconhecidos))}.",
            )
    return limpos or None


def normalizar(filtros: dict) -> dict:
    """Os quatro filtros em forma canônica — vazio vira `None`."""
    return {
        "locais": _limpar(filtros.get("locais")),
        "setores": _limpar(filtros.get("setores")),
        "categorias": _limpar(filtros.get("categorias")),
        "tipos": _limpar(filtros.get("tipos"), permitidos=set(TIPOS)),
        "produtos": _limpar(filtros.get("produtos")),
    }


def _sql(id_unidade: int, f: dict) -> tuple[str, dict]:
    """A consulta dos pares produto × local que a contagem vai cobrir.

    ⚠️ Cada filtro entra como `(%(x)s IS NULL OR coluna = ANY(%(x)s))`. Montar o
    WHERE concatenando texto conforme o que veio preenchido daria uma consulta
    diferente por combinação — dezesseis caminhos, e o bug moraria no que ninguém
    testou. Assim é uma só, e o plano do banco resolve o nulo na hora.
    """
    params = {
        "u": id_unidade,
        "locais": f["locais"],
        "setores": f["setores"],
        "categorias": f["categorias"],
        "tipos": f["tipos"],
        "produtos": f["produtos"],
    }
    sql = """
        SELECT s.id_produto, s.id_local, s.quantidade, s.custo_medio,
               p.codigo, p.nome AS produto, p.um_estoque, p.tipo,
               l.nome AS local, c.nome AS categoria, se.nome AS setor
          FROM estoque_saldos s
          JOIN produtos p ON p.id = s.id_produto
          JOIN locais_estoque l ON l.id = s.id_local
          LEFT JOIN categorias c ON c.id = p.id_categoria
          LEFT JOIN setores se ON se.id = p.id_setor
         WHERE s.id_unidade = %(u)s
           AND p.controla_estoque AND p.ativo AND l.ativo
           AND (%(locais)s::int[] IS NULL OR s.id_local = ANY(%(locais)s))
           AND (%(setores)s::int[] IS NULL OR p.id_setor = ANY(%(setores)s))
           AND (%(categorias)s::int[] IS NULL OR p.id_categoria = ANY(%(categorias)s))
           AND (%(tipos)s::varchar[] IS NULL OR p.tipo = ANY(%(tipos)s))
           AND (%(produtos)s::int[] IS NULL OR p.id = ANY(%(produtos)s))
         ORDER BY l.nome, lower(p.nome)
    """
    return sql, params


def selecionar(cur, id_unidade: int, filtros: dict) -> list[dict]:
    """Os pares produto × local que entram na contagem."""
    f = normalizar(filtros)
    sql, params = _sql(id_unidade, f)

    # ⚠️ Lista explícita de produtos entra MESMO sem saldo no local: quem
    # nomeou o produto sabe o que quer contar, e "não aparece" seria pior que
    # uma linha com zero. Sem lista, vale o saldo — cadastro inteiro viraria
    # centenas de linhas para escrever zero.
    if f["produtos"] and f["locais"] and len(f["locais"]) == 1:
        cur.execute(
            """SELECT p.id AS id_produto, %(local)s::int AS id_local,
                      coalesce(s.quantidade, 0) AS quantidade,
                      coalesce(s.custo_medio, 0) AS custo_medio,
                      p.codigo, p.nome AS produto, p.um_estoque, p.tipo,
                      l.nome AS local, c.nome AS categoria, se.nome AS setor
                 FROM produtos p
                 JOIN locais_estoque l ON l.id = %(local)s
                 LEFT JOIN estoque_saldos s
                        ON s.id_produto = p.id AND s.id_local = %(local)s
                 LEFT JOIN categorias c ON c.id = p.id_categoria
                 LEFT JOIN setores se ON se.id = p.id_setor
                WHERE p.id = ANY(%(produtos)s) AND p.controla_estoque
                ORDER BY lower(p.nome)""",
            {"local": f["locais"][0], "produtos": f["produtos"]},
        )
    else:
        cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def em_contagem_aberta(cur, pares: list[dict], ignorar: int | None = None) -> list[dict]:
    """Os pares que já estão numa contagem ABERTA — o choque que se recusa.

    ⚠️ Esta guarda substituiu "só um inventário aberto por local", que deixou de
    servir quando a contagem passou a ser um recorte: contar as bebidas e contar
    o hortifrúti do mesmo local ao mesmo tempo é legítimo, e não se atravessam.
    O que não pode é o MESMO produto no MESMO local estar em duas contagens —
    as duas congelaram o saldo e as duas iriam lançar ajuste no fechamento, e a
    segunda desfaria a primeira.
    """
    if not pares:
        return []
    cur.execute(
        """SELECT DISTINCT ii.id_produto, ii.id_local, ii.id_inventario,
                  p.nome AS produto, l.nome AS local
             FROM inventario_itens ii
             JOIN inventarios i ON i.id = ii.id_inventario
             JOIN produtos p ON p.id = ii.id_produto
             LEFT JOIN locais_estoque l ON l.id = ii.id_local
            WHERE i.status = 'ABERTO' AND i.id IS DISTINCT FROM %s
              AND (ii.id_produto, ii.id_local) IN (
                  SELECT unnest(%s::int[]), unnest(%s::int[]))""",
        (ignorar, [p["id_produto"] for p in pares], [p["id_local"] for p in pares]),
    )
    return [dict(r) for r in cur.fetchall()]


def resumo(pares: list[dict]) -> dict:
    """O que a tela mostra antes de abrir: quantos, de onde, e uma amostra.

    ⚠️ Existe para ninguém abrir uma contagem de 2.000 linhas sem querer. Numa
    base real o filtro em branco traz o cadastro inteiro, e descobrir isso
    depois de abrir custa cancelar e recomeçar.
    """
    locais: dict[str, int] = {}
    for p in pares:
        locais[p["local"]] = locais.get(p["local"], 0) + 1
    return {
        "total": len(pares),
        "produtos": len({p["id_produto"] for p in pares}),
        "locais": [{"nome": n, "itens": q} for n, q in sorted(locais.items())],
        "amostra": [
            {"produto": p["produto"], "local": p["local"], "um": p["um_estoque"]}
            for p in pares[:12]
        ],
    }
