"""Cadastros que parecem ser o mesmo produto — venham de onde vierem.

O sistema recebe produto por três portas: o catálogo do **Omie** (o que a casa
compra), o cardápio do **PDV Legal** (o que a casa vende) e a mão de quem
cadastra. Cada porta tem a sua chave única — ``produtos.codigo_omie``,
``codigos_externos (sistema, codigo)`` — e nenhuma delas impede o mesmo produto
de existir duas vezes.

⚠️ **Nem entre portas, nem dentro de uma.** Entre portas não há chave nenhuma: o
mesmo pacote de café entra como insumo pelo Omie e como item vendido pelo PDV.
E dentro de uma só, a chave garante que o *identificador* não repita, não que o
*produto* não repita — a conta real do cliente tem **cinco** cadastros de
"LARANJA PERA KG", cada um com o seu código no Omie.

⚠️ **O estrago é estoque fantasma e custo partido.** Entre portas: a compra entra
no estoque por um cadastro, a venda não sai por nenhum (o item do cardápio nasce
sem controlar estoque), e a sobra aparece na contagem como "ajuste de
inventário". Dentro de uma: a próxima compra vai para o gêmeo e o custo médio da
laranja passa a existir em cinco lugares — cada ficha puxa o de um deles.

⚠️ **Semelhança SUGERE, nunca funde.** Unir dois produtos que são diferentes de
verdade não tem desfazer. Quem decide é gente; este arquivo mostra o grupo e os
fatos de cada cadastro.
"""

import collections
import re
import unicodedata
from difflib import SequenceMatcher

# Abaixo disto nem mostra. Um palpite fraco numa lista de conferência é pior que
# nenhum: ele convida ao clique, e quem clica não confere.
SCORE_MINIMO = 80.0

# Palavras curtas ("de", "com", "500") não servem de peneira — casariam meio
# cadastro com o outro meio e a varredura viraria força bruta.
TAMANHO_DO_TOKEN = 4

# Teto de grupos devolvidos. Uma lista de conferência com mil linhas não é
# conferida por ninguém.
TETO = 200

# ⚠️ Tokens que NÃO distinguem produto: unidade, embalagem e número. É o que
# separa "LARANJA PERA" de "LARANJA PERA KG" (o mesmo produto) de "MORANGO" e
# "AMORA" (dois produtos com o resto do nome idêntico).
UNIDADES = {
    "kg", "kgs", "g", "gr", "grs", "gs", "ml", "l", "lt", "lts", "litro", "litros",
    "un", "und", "unid", "unids", "unidade", "unidades", "cx", "cxs", "caixa",
    "pct", "pcts", "pacote", "pc", "pcs", "bdj", "bandeja", "fd", "fardo", "dz", "duzia",
    "gf", "garrafa", "lata", "sc", "saco",
}

# Duas grafias do mesmo termo ("panettone" e "panetone") contam como o mesmo
# token. Abaixo disto são palavras diferentes.
PARECENCA_DE_TOKEN = 0.80


def _normalizar(texto: str | None) -> str:
    """Sem acento, sem pontuação, minúsculo — e **número separado de letra**.

    ⚠️ A separação existe porque "500g" e "500 g" são a mesma coisa escrita por
    duas pessoas, e sem ela viram tokens diferentes. Isso importa muito depois:
    a regra de `mesmo_produto` trata número dos dois lados como sinal de
    produtos diferentes, e "500g" contra "500" reprovaria um par idêntico. De
    quebra, "pct1kg" vira "pct 1 kg" e o índice passa a enxergar as palavras.
    """
    if not texto:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    limpo = re.sub(r"[^a-z0-9 ]", " ", sem_acento.lower())
    limpo = re.sub(r"(\d)([a-z])", r"\1 \2", limpo)
    limpo = re.sub(r"([a-z])(\d)", r"\1 \2", limpo)
    return re.sub(r"\s+", " ", limpo).strip()


def _so_ruido(token: str) -> str:
    """Este token distingue um produto do outro, ou é embalagem?"""
    return (
        token.isdigit()
        or token in UNIDADES
        or len(token) <= 3
        or bool(re.fullmatch(r"\d+[a-z]*", token))
    )


def mesmo_produto(a: str, b: str) -> bool:
    """Os dois nomes diferem só em ruído — ou em grafia do MESMO termo?

    ⚠️ **É esta regra que torna a lista utilizável.** Sem ela, "FRUTA MORANGO CG
    PCT1KG CX6KG" e "FRUTA AMORA CG PCT1KG CX6KG" batem 95% de semelhança — o
    nome é quase todo embalagem, e a palavra que muda tudo pesa pouco no texto.
    Com ela, a fruta diferente reprova o par e a laranja com e sem "KG" passa.

    ⚠️ Um token sem par do outro lado só é aceito se for **ruído** (número,
    unidade, fragmento curto). Com par parecido, é variação de grafia:
    "panettone" e "panetone" são o mesmo panetone.
    """
    so_a, so_b = set(a.split()) - set(b.split()), set(b.split()) - set(a.split())

    # ⚠️ **Número dos DOIS lados quer dizer produtos diferentes.** É o que separa
    # "CAKE BOARD N19" de "CAKE BOARD N21", "SUCO 300ML" de "SUCO 250ML" e
    # "DRIP COFFEE 1UNID" de "DRIP COFFEE 10UNID" — em todos, o número É o
    # produto. Um número de um lado só (o "2" de "BURRATA ATACADO 2") continua
    # sendo ruído: ali ele costuma ser a marca de quem cadastrou duas vezes.
    com_digito = (lambda ts: {x for x in ts if any(c.isdigit() for c in x)})
    if com_digito(so_a) and com_digito(so_b):
        return False

    # ⚠️ A parelha por semelhança é só para PALAVRA — "panettone" e "panetone"
    # são o mesmo panetone, mas "1unid" e "10unid" batem 91% e são dez vezes um
    # do outro. Números já foram tratados acima.
    livres = [x for x in so_b if not any(c.isdigit() for c in x)]
    for token in so_a:
        if any(c.isdigit() for c in token):
            continue
        par = max(livres, key=lambda x: SequenceMatcher(None, token, x).ratio(), default=None)
        if par and SequenceMatcher(None, token, par).ratio() >= PARECENCA_DE_TOKEN:
            livres.remove(par)
            continue
        if not _so_ruido(token):
            return False
    return all(_so_ruido(token) for token in livres)


def _origem(p: dict) -> str:
    """De que porta este cadastro entrou.

    ⚠️ "AMBOS" é o caso SAUDÁVEL — um cadastro só, conhecido pelas duas pontas.
    """
    if p["do_pdv"] and p["codigo_omie"]:
        return "AMBOS"
    if p["do_pdv"]:
        return "PDV"
    if p["codigo_omie"]:
        return "OMIE"
    return "CASA"


def _carregar(cur) -> list[dict]:
    cur.execute(
        """SELECT p.id, p.codigo, p.nome, p.tipo, p.status, p.controla_estoque,
                  p.codigo_omie, p.codigo_barras, p.um_estoque,
                  c.nome AS categoria,
                  EXISTS (SELECT 1 FROM codigos_externos ce
                           WHERE ce.id_produto = p.id AND ce.sistema = 'PDV_LEGAL') AS do_pdv,
                  (SELECT count(*) FROM estoque_movimentos m WHERE m.id_produto = p.id) AS movimentos,
                  (SELECT count(*) FROM fichas_tecnicas f WHERE f.id_produto = p.id) AS fichas,
                  (SELECT coalesce(sum(vi.quantidade), 0) FROM venda_itens vi
                     JOIN vendas v ON v.id = vi.id_venda AND NOT v.cancelada
                    WHERE vi.id_produto = p.id) AS vendido
             FROM produtos p
             LEFT JOIN categorias c ON c.id = p.id_categoria
            WHERE p.ativo"""
    )
    return [dict(r) for r in cur.fetchall()]


def _lado(p: dict) -> dict:
    """Os fatos de um cadastro — é por eles que se decide qual fica.

    ⚠️ Movimento, ficha e quantidade vendida não são enfeite: são exatamente o
    que diz qual dos cadastros tem história. O que tem história FICA; o outro é
    que pode ser absorvido, e nunca o contrário.
    """
    return {
        "id": p["id"], "codigo": p["codigo"], "nome": p["nome"],
        "origem": p["_origem"], "tipo": p["tipo"], "status": p["status"],
        "categoria": p["categoria"], "um_estoque": p["um_estoque"],
        "controla_estoque": p["controla_estoque"],
        "codigo_barras": p["codigo_barras"],
        "movimentos": p["movimentos"], "fichas": p["fichas"],
        "vendido": float(p["vendido"] or 0),
        "pode_ser_absorvido": p["movimentos"] == 0 and p["fichas"] == 0,
    }


def _peso_da_historia(p: dict) -> tuple:
    """Quanto passado este cadastro carrega. O maior é o que deve FICAR."""
    return (p["movimentos"], p["fichas"], float(p["vendido"] or 0), -p["id"])


def suspeitos(cur, minimo: float = SCORE_MINIMO, limite: int = TETO,
              so_entre_portas: bool = False) -> dict:
    """Grupos de cadastros que parecem ser o mesmo produto.

    ⚠️ **GRUPO, não par.** Cinco cadastros de "LARANJA PERA KG" dão dez pares —
    dez linhas para conferir a mesma laranja. Agrupados, é uma linha dizendo
    "cinco cadastros", que é a pergunta que alguém realmente tem.

    ⚠️ **O índice invertido não é preciosismo.** Sem ele são 2.800 × 2.800
    comparações de texto; com ele, quarenta e seis mil. A varredura inteira leva
    uns quatro segundos, o que permite que o relatório seja pedido na hora em vez
    de virar uma tabela que envelhece.

    `so_entre_portas` reduz ao caso que só a integração cria: o mesmo produto
    entrando pelo Omie e pelo cardápio. É o mais perigoso — dentro de uma porta
    os dois cadastros ao menos se comportam igual.
    """
    produtos = _carregar(cur)
    for p in produtos:
        p["_n"] = _normalizar(p["nome"])
        p["_origem"] = _origem(p)

    indice: dict[str, list[int]] = collections.defaultdict(list)
    for i, p in enumerate(produtos):
        for token in set(p["_n"].split()):
            if len(token) >= TAMANHO_DO_TOKEN:
                indice[token].append(i)

    # União por vizinhança: quem parece com quem cai no mesmo grupo.
    pai = list(range(len(produtos)))

    def raiz(x: int) -> int:
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    # ⚠️ **Os pares são guardados e só depois viram grupo.** A raiz de um índice
    # MUDA a cada união; anotar o placar "na raiz de agora" faz o número se
    # perder no meio do caminho, e o grupo aparece com o placar de outro par.
    achados: list[tuple[int, int, float]] = []
    for i, p in enumerate(produtos):
        candidatos: set[int] = set()
        for token in set(p["_n"].split()):
            if len(token) >= TAMANHO_DO_TOKEN:
                candidatos.update(indice[token])
        for j in candidatos:
            if j <= i:
                continue
            q = produtos[j]
            if so_entre_portas and (p["_origem"] == q["_origem"]
                                    or "AMBOS" in (p["_origem"], q["_origem"])):
                continue
            score = SequenceMatcher(None, p["_n"], q["_n"]).ratio() * 100
            if score < minimo or not mesmo_produto(p["_n"], q["_n"]):
                continue
            achados.append((i, j, score))
            a, b = raiz(i), raiz(j)
            if a != b:
                pai[a] = b

    ligacoes: dict[int, float] = {}
    for i, _j, score in achados:
        r = raiz(i)
        ligacoes[r] = max(ligacoes.get(r, 0.0), score)

    grupos: dict[int, list[dict]] = collections.defaultdict(list)
    for i, p in enumerate(produtos):
        r = raiz(i)
        if r in ligacoes:
            grupos[r].append(p)

    montados = []
    for r, membros in grupos.items():
        if len(membros) < 2:
            continue
        membros.sort(key=_peso_da_historia, reverse=True)
        montados.append({
            "score": round(ligacoes.get(r, minimo), 1),
            "quantos": len(membros),
            "origens": sorted({m["_origem"] for m in membros}),
            # ⚠️ O primeiro é o que carrega mais passado — a sugestão do que fica.
            # Sugestão, não escolha: a tela põe o botão nos dois lados.
            "cadastros": [_lado(m) for m in membros],
        })

    montados.sort(key=lambda g: (-g["quantos"], -g["score"]))
    return {"minimo": minimo, "total": len(montados), "grupos": montados[:limite]}


# ------------------------------------------------------------------- unificar

# ⚠️ Tudo que o absorvido NÃO pode ter. Cada linha destas é história que não se
# move de cadastro: o razão é append-only, o mês fechado é congelado, e a
# contagem de um inventário registra o que foi contado naquele dia.
_IMPEDIMENTOS = (
    ("estoque_movimentos", "id_produto", "tem movimento no razão, que é append-only"),
    ("estoque_lotes", "id_produto", "tem lote em estoque"),
    ("cmv_movimentacao", "id_produto", "aparece num mês já fechado, que é congelado"),
    ("inventario_itens", "id_produto", "foi contado num inventário"),
    ("producoes", "id_produto", "tem produção registrada"),
    ("producao_agenda", "id_produto", "está na agenda de produção"),
    ("nota_itens", "id_produto", "aparece em nota de entrada"),
    ("fichas_tecnicas", "id_produto", "tem ficha técnica própria"),
    ("ficha_itens", "id_insumo", "é insumo na ficha de outro produto"),
    ("kit_itens", "id_componente", "é componente de um combo"),
    ("kit_itens", "id_kit", "é um combo com composição"),
    ("produto_fornecedor", "id_produto", "tem fornecedor vinculado, com histórico de preço"),
)


def impedimentos(cur, id_produto: int) -> list[str]:
    """O que impede este cadastro de ser absorvido — em português."""
    achados = []
    for tabela, coluna, frase in _IMPEDIMENTOS:
        cur.execute(f"SELECT 1 FROM {tabela} WHERE {coluna} = %s LIMIT 1", (id_produto,))
        if cur.fetchone():
            achados.append(frase)
    return achados


def unificar(cur, id_manter: int, id_absorver: int, id_usuario: int) -> dict:
    """Diz que os dois cadastros são o mesmo produto: um fica, o outro sai.

    O que MUDA de dono: o de-para do PDV, o código do Omie, o EAN e os itens de
    venda. O absorvido vira **inativo** — nunca apagado, porque a auditoria e o
    histórico continuam apontando para ele.

    ⚠️ **Não fabrica movimento de estoque.** As vendas que passaram pelo cadastro
    do cardápio não baixaram estoque (ele não controlava), e continuam sem baixar
    — o razão é append-only e inventar lançamento retroativo seria pior que a
    falta dele. O que a unificação conserta é daqui para a frente: a próxima
    venda sai da prateleira certa.

    ⚠️ **O custo dos itens de venda sem custo é recalculado AGORA.** É a mesma
    regra de `cardapio.reconciliar`: o item entrou contando zero no CMV teórico,
    e ao ganhar um produto com ficha passa a contar o que custa hoje. Item que já
    tinha custo congelado NÃO é tocado — aquele número é o do dia em que a venda
    aconteceu.
    """
    from services import cmv as motor

    if id_manter == id_absorver:
        raise ValueError("Escolha dois cadastros diferentes.")

    cur.execute(
        "SELECT id, codigo, nome, codigo_omie, codigo_barras, observacao FROM produtos "
        " WHERE id = ANY(%s)", ([id_manter, id_absorver],),
    )
    achados = {r["id"]: dict(r) for r in cur.fetchall()}
    if len(achados) != 2:
        raise LookupError("Produto não encontrado.")
    manter, absorver = achados[id_manter], achados[id_absorver]

    travas = impedimentos(cur, id_absorver)
    if travas:
        raise PermissionError(
            f"“{absorver['nome']}” não pode ser absorvido: " + "; ".join(travas)
            + ". Se ele é o cadastro certo, faça a unificação ao contrário."
        )

    # ⚠️ Dois códigos do Omie querem dizer DOIS produtos lá — então não é o mesmo
    # cadastro entrando duas vezes, é o catálogo do fornecedor tendo dois itens.
    # (O caso das cinco laranjas passa: quatro delas não têm movimento, e só a
    # que tem código do Omie diferente é barrada — que é o certo, porque unir
    # duas linhas do catálogo esconderia o problema em vez de resolvê-lo lá.)
    if manter["codigo_omie"] and absorver["codigo_omie"]:
        raise PermissionError(
            "Os dois têm código do Omie, e códigos diferentes são produtos diferentes lá. "
            "Corrija o cadastro no Omie, ou desative um deles à mão."
        )

    movidos = {}

    # O de-para do PDV muda de dono. `(sistema, codigo)` é único no sistema
    # inteiro, então não há como colidir com o que o mantido já tem.
    cur.execute(
        "UPDATE codigos_externos SET id_produto = %s WHERE id_produto = %s",
        (id_manter, id_absorver),
    )
    movidos["vinculos_externos"] = cur.rowcount

    # Código do Omie e EAN só migram para um lado vazio — são colunas únicas.
    for coluna in ("codigo_omie", "codigo_barras"):
        if absorver[coluna] and not manter[coluna]:
            cur.execute(
                f"UPDATE produtos SET {coluna} = NULL WHERE id = %s", (id_absorver,)
            )
            cur.execute(
                f"UPDATE produtos SET {coluna} = %s WHERE id = %s",
                (absorver[coluna], id_manter),
            )
            movidos[coluna] = absorver[coluna]

    cur.execute(
        "SELECT id, custo_ficha_unitario FROM venda_itens WHERE id_produto = %s", (id_absorver,)
    )
    itens = [dict(r) for r in cur.fetchall()]
    custo, origem_custo = motor.custo_teorico_do_produto(cur, id_manter)
    recalculados = 0
    for item in itens:
        if item["custo_ficha_unitario"] is None:
            cur.execute(
                """UPDATE venda_itens
                      SET id_produto = %s, custo_ficha_unitario = %s, origem_custo = %s
                    WHERE id = %s""",
                (id_manter, custo, origem_custo, item["id"]),
            )
            if custo is not None:
                recalculados += 1
        else:
            cur.execute(
                "UPDATE venda_itens SET id_produto = %s WHERE id = %s", (id_manter, item["id"])
            )
    movidos["itens_de_venda"] = len(itens)
    movidos["itens_que_ganharam_custo"] = recalculados

    nota = (f"Unificado em {manter['codigo']} — {manter['nome']}. "
            "Era o mesmo produto com outro cadastro.")
    cur.execute(
        """UPDATE produtos
              SET ativo = false,
                  observacao = trim(both E'\\n' from coalesce(observacao, '') || E'\\n' || %s)
            WHERE id = %s""",
        (nota, id_absorver),
    )

    return {
        "manteve": {"id": id_manter, "codigo": manter["codigo"], "nome": manter["nome"]},
        "absorveu": {"id": id_absorver, "codigo": absorver["codigo"], "nome": absorver["nome"]},
        **movidos,
        "message": (f"“{absorver['nome']}” foi unificado em “{manter['nome']}”"
                    + (f" — {movidos['itens_de_venda']} item(ns) de venda mudaram de dono"
                       if movidos.get("itens_de_venda") else "")
                    + (f", {recalculados} ganharam custo" if recalculados else "")),
    }
