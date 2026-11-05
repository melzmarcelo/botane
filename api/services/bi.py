"""O Estúdio BI: fontes, ligações e campos numa LISTA BRANCA, e o SQL montado pelo servidor.

🔑 **Pedido do dono (05/11/2026), fase 4 do layout novo:** *"um menu estilo BI, onde o usuário
administrador pode criar relatórios personalizados com suas ligações configuráveis"*.

⚠️ **Nada da requisição vira SQL.** A tela manda NOMES (`vendas`, `itens.valor`,
`produtos.id_categoria`); o texto de cada fonte, campo e coluna de ligação está aqui. Nome que
não está na lista é recusado (422). Os valores (loja, datas) vão sempre como parâmetro.
⚠️ **Só leitura, com teto:** a consulta roda em transação `READ ONLY`, com `statement_timeout`
e `LIMIT`. E toda fonte que tem loja é recortada pela loja ATUAL de quem consulta — o BI não é
um caminho para ver a outra loja.
⚠️ **Somar no grão certo.** Somar o valor do CUPOM com os itens juntos repete o cupom uma vez
por item. Uma medida de soma numa fonte que tem outra fonte "muitos" ligada a ela é recusada,
com a explicação — a contagem distinta continua valendo.
"""

from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException


@dataclass(frozen=True)
class Campo:
    rotulo: str
    tipo: str          # "dim" | "med"
    expr: str
    formato: str = "texto"   # texto | inteiro | reais | numero | data | mes
    soma: bool = False       # medida que SOMA (sensível ao grão); contagem distinta não é


@dataclass(frozen=True)
class Fonte:
    rotulo: str
    tabela: str
    permissoes: tuple[str, ...]
    campos: dict[str, Campo]
    # As colunas que podem LIGAR esta fonte a outra numa ligação manual.
    chaves: tuple[str, ...] = ("id",)
    unidade: str | None = None       # coluna da loja (recorte obrigatório)
    data: str | None = None          # coluna de data (o filtro de período)
    filtro: str | None = None        # o que conta como linha válida
    exige: tuple[str, ...] = ()      # fonte que tem de vir junto (a da loja)
    descricao: str = ""


_MES = "to_char({c}, 'YYYY-MM')"
_DIA_SEMANA = ("(ARRAY['1 seg','2 ter','3 qua','4 qui','5 sex','6 sáb','7 dom'])"
               "[extract(isodow FROM {c})::int]")

FONTES: dict[str, Fonte] = {
    "vendas": Fonte(
        "Vendas", "vendas", ("cmv.painel", "cmv.relatorios"),
        descricao="O cupom: data, canal e valor. Sem as canceladas e o consumo interno.",
        unidade="vendas.id_unidade", data="vendas.data",
        filtro="NOT vendas.cancelada AND NOT vendas.consumo_interno",
        chaves=("id", "id_unidade"),
        campos={
            "mes": Campo("Mês", "dim", _MES.format(c="vendas.data"), "mes"),
            "dia": Campo("Dia", "dim", "vendas.data", "data"),
            "dia_semana": Campo("Dia da semana", "dim", _DIA_SEMANA.format(c="vendas.data")),
            "hora": Campo("Hora", "dim", "lpad(extract(hour FROM vendas.hora)::int::text, 2, '0') || 'h'"),
            "canal": Campo("Canal", "dim", "coalesce(nullif(initcap(vendas.canal), ''), 'Sem canal')"),
            "origem": Campo("Origem do lançamento", "dim", "vendas.origem"),
            "cupons": Campo("Nº de vendas", "med", "COUNT(DISTINCT vendas.id)", "inteiro"),
            "faturado": Campo("Faturado (cupom)", "med", "SUM(vendas.valor_total)", "reais", soma=True),
            "ticket": Campo("Ticket médio", "med",
                            "SUM(vendas.valor_total) / nullif(COUNT(DISTINCT vendas.id), 0)", "reais", soma=True),
        }),
    "itens": Fonte(
        "Itens da venda", "venda_itens", ("cmv.painel", "cmv.relatorios"),
        descricao="Cada produto vendido no cupom: quantidade, valor e custo da ficha.",
        chaves=("id_venda", "id_produto"), exige=("vendas",),
        campos={
            "quantidade": Campo("Quantidade vendida", "med", "SUM(itens.quantidade)", "numero", soma=True),
            "valor": Campo("Faturamento", "med", "SUM(itens.valor_total)", "reais", soma=True),
            "custo": Campo("Custo (ficha)", "med",
                           "SUM(itens.quantidade * coalesce(itens.custo_ficha_unitario, 0))", "reais", soma=True),
            "margem": Campo("Margem (faturamento − custo)", "med",
                            "SUM(itens.valor_total) - SUM(itens.quantidade * coalesce(itens.custo_ficha_unitario, 0))",
                            "reais", soma=True),
        }),
    "produtos": Fonte(
        "Produtos", "produtos", ("cadastros.produtos", "estoque.saldos", "fichas.visualizar", "cmv.painel"),
        descricao="O cadastro: nome, tipo, categoria e setor.",
        chaves=("id", "id_categoria", "id_setor"),
        campos={
            "nome": Campo("Produto", "dim", "produtos.nome"),
            "tipo": Campo("Tipo de produto", "dim", "initcap(replace(produtos.tipo, '_', ' '))"),
            "categoria": Campo("Categoria", "dim",
                               "coalesce((SELECT c.nome FROM categorias c WHERE c.id = produtos.id_categoria), 'Sem categoria')"),
            "setor": Campo("Setor", "dim",
                           "coalesce((SELECT s.nome FROM setores s WHERE s.id = produtos.id_setor), 'Sem setor')"),
            "produtos": Campo("Nº de produtos", "med", "COUNT(DISTINCT produtos.id)", "inteiro"),
        }),
    "lojas": Fonte(
        "Lojas", "unidades", (),
        descricao="A loja, pelo apelido.",
        chaves=("id",),
        campos={"nome": Campo("Loja", "dim", "coalesce(lojas.apelido, lojas.nome)")}),
    "reservas": Fonte(
        "Reservas", "reservas", ("reservas.ver",),
        descricao="As reservas válidas (confirmadas, que vieram ou faltaram).",
        unidade="reservas.id_unidade", data="reservas.data",
        filtro="reservas.status IN ('CONFIRMADA', 'CHEGOU', 'ENCERRADA', 'NAO_COMPARECEU')",
        chaves=("id", "id_cliente", "id_unidade"),
        campos={
            "mes": Campo("Mês da reserva", "dim", _MES.format(c="reservas.data"), "mes"),
            "dia_semana": Campo("Dia da semana", "dim", _DIA_SEMANA.format(c="reservas.data")),
            "objetivo": Campo("Objetivo", "dim", "coalesce(nullif(reservas.objetivo, ''), 'Sem objetivo')"),
            "status": Campo("Situação", "dim", "initcap(replace(reservas.status, '_', ' '))"),
            "reservas": Campo("Nº de reservas", "med", "COUNT(DISTINCT reservas.id)", "inteiro"),
            "pessoas": Campo("Pessoas", "med",
                             "SUM(CASE WHEN reservas.status <> 'NAO_COMPARECEU' THEN reservas.pessoas ELSE 0 END)",
                             "inteiro", soma=True),
        }),
    "clientes": Fonte(
        "Clientes", "reserva_clientes", ("reservas.ver",),
        descricao="A base de clientes da rede: cidade, gênero e origem.",
        chaves=("id",),
        campos={
            "cidade": Campo("Cidade", "dim", "coalesce(nullif(initcap(trim(clientes.cidade)), ''), 'Sem cidade')"),
            "genero": Campo("Gênero", "dim", "initcap(replace(coalesce(clientes.genero, 'NAO_INFORMADO'), '_', ' '))"),
            "origem": Campo("Origem do cadastro", "dim", "coalesce(nullif(clientes.origem, ''), 'Cadastro no Botané')"),
            "clientes": Campo("Nº de clientes", "med", "COUNT(DISTINCT clientes.id)", "inteiro"),
        }),
    "notas": Fonte(
        "Notas de entrada", "notas_entrada", ("compras.notas",),
        descricao="As notas de compra: fornecedor, data de entrada e valor.",
        unidade="notas.id_unidade", data="coalesce(notas.data_entrada, notas.data_emissao)",
        chaves=("id", "id_fornecedor", "id_unidade"),
        campos={
            "mes": Campo("Mês da entrada", "dim", _MES.format(c="coalesce(notas.data_entrada, notas.data_emissao)"), "mes"),
            "emitente": Campo("Emitente da nota", "dim", "coalesce(notas.nome_emitente, 'Sem emitente')"),
            "notas": Campo("Nº de notas", "med", "COUNT(DISTINCT notas.id)", "inteiro"),
            "valor": Campo("Valor das notas", "med", "SUM(notas.valor_total)", "reais", soma=True),
        }),
    "itens_nota": Fonte(
        "Itens da nota", "nota_itens", ("compras.notas",),
        descricao="Cada produto comprado na nota: quantidade e valor.",
        chaves=("id_nota", "id_produto"), exige=("notas",),
        filtro="NOT coalesce(itens_nota.ignorado, false)",
        campos={
            "quantidade": Campo("Quantidade comprada", "med",
                                "SUM(coalesce(itens_nota.quantidade_convertida, itens_nota.quantidade))", "numero", soma=True),
            "valor": Campo("Valor comprado", "med", "SUM(itens_nota.valor_total)", "reais", soma=True),
        }),
    "fornecedores": Fonte(
        "Fornecedores", "fornecedores", ("cadastros.fornecedores", "compras.notas"),
        descricao="O cadastro de fornecedores.",
        chaves=("id",),
        campos={
            "nome": Campo("Fornecedor", "dim", "coalesce(nullif(fornecedores.nome_fantasia, ''), fornecedores.nome)"),
            "cidade": Campo("Cidade do fornecedor", "dim", "coalesce(nullif(fornecedores.cidade, ''), 'Sem cidade')"),
        }),
    "movimentos": Fonte(
        "Movimentos de estoque", "estoque_movimentos", ("estoque.saldos",),
        descricao="O razão do estoque: entradas, saídas e ajustes, com custo.",
        unidade="movimentos.id_unidade", data="(movimentos.data_movimento AT TIME ZONE 'America/Sao_Paulo')::date",
        chaves=("id_produto", "id_unidade"),
        campos={
            "mes": Campo("Mês do movimento", "dim",
                         _MES.format(c="(movimentos.data_movimento AT TIME ZONE 'America/Sao_Paulo')"), "mes"),
            "tipo": Campo("Tipo de movimento", "dim", "initcap(replace(movimentos.tipo, '_', ' '))"),
            "quantidade": Campo("Quantidade movimentada", "med", "SUM(movimentos.quantidade)", "numero", soma=True),
            "custo": Campo("Custo movimentado", "med", "SUM(movimentos.custo_total)", "reais", soma=True),
        }),
}

# (fonte "muitos", coluna, fonte "um", coluna) — as ligações que o sistema conhece e sugere.
RELACOES: list[tuple[str, str, str, str]] = [
    ("itens", "id_venda", "vendas", "id"),
    ("itens", "id_produto", "produtos", "id"),
    ("vendas", "id_unidade", "lojas", "id"),
    ("reservas", "id_cliente", "clientes", "id"),
    ("reservas", "id_unidade", "lojas", "id"),
    ("itens_nota", "id_nota", "notas", "id"),
    ("itens_nota", "id_produto", "produtos", "id"),
    ("notas", "id_fornecedor", "fornecedores", "id"),
    ("notas", "id_unidade", "lojas", "id"),
    ("movimentos", "id_produto", "produtos", "id"),
    ("movimentos", "id_unidade", "lojas", "id"),
]

TIPOS_LIGACAO = {"INNER": "JOIN", "LEFT": "LEFT JOIN"}
LIMITE = 500
TEMPO_MAXIMO = "8s"


def id_relacao(r: tuple[str, str, str, str]) -> str:
    return f"{r[0]}.{r[1]}-{r[2]}.{r[3]}"


def pode_fonte(f: Fonte, pode) -> bool:
    return not f.permissoes or any(pode(p) for p in f.permissoes)


def catalogo(pode) -> dict:
    """O que a tela oferece: as fontes que ESTA pessoa pode usar e as ligações entre elas."""
    fontes = {k: f for k, f in FONTES.items() if pode_fonte(f, pode)}
    return {
        "fontes": [{
            "chave": k, "rotulo": f.rotulo, "descricao": f.descricao, "chaves": list(f.chaves),
            "tem_periodo": bool(f.data), "exige": list(f.exige),
            "campos": [{"chave": f"{k}.{c}", "rotulo": x.rotulo, "tipo": x.tipo, "formato": x.formato}
                       for c, x in f.campos.items()],
        } for k, f in fontes.items()],
        "relacoes": [{"id": id_relacao(r), "a": r[0], "ca": r[1], "b": r[2], "cb": r[3]}
                     for r in RELACOES if r[0] in fontes and r[2] in fontes],
        "limite": LIMITE,
    }


def _erro(msg: str):
    raise HTTPException(status_code=422, detail=msg)


def _campo(nome: str, fontes: list[str]) -> tuple[str, str, Campo]:
    fonte, _, campo = nome.partition(".")
    if fonte not in fontes or fonte not in FONTES or campo not in FONTES[fonte].campos:
        _erro(f"Campo que não existe nas fontes escolhidas: {nome}")
    return fonte, campo, FONTES[fonte].campos[campo]


def montar(d: dict, id_unidade: int, pode) -> tuple[str, dict, list[dict]]:
    """A definição (só nomes) → (SQL, parâmetros, colunas). Valida tudo contra a lista branca."""
    fontes: list[str] = []
    for f in d.get("fontes") or []:
        if f not in FONTES:
            _erro(f"Fonte que não existe: {f}")
        if not pode_fonte(FONTES[f], pode):
            raise HTTPException(status_code=403, detail=f"Sem permissão para a fonte {FONTES[f].rotulo}")
        if f not in fontes:
            fontes.append(f)
    if not fontes:
        _erro("Escolha ao menos uma fonte de dados")
    # A fonte que dá a loja vem junto (itens de venda só existem dentro da venda).
    for f in list(fontes):
        for e in FONTES[f].exige:
            if e not in fontes:
                fontes.append(e)

    dims = [_campo(n, fontes) for n in (d.get("dimensoes") or [])[:2]]
    meds = [_campo(n, fontes) for n in (d.get("medidas") or [])[:6]]
    if any(c.tipo != "dim" for _, _, c in dims) or any(c.tipo != "med" for _, _, c in meds):
        _erro("Dimensão e medida trocadas")
    if not meds:
        _erro("Escolha ao menos uma medida")

    # As ligações: as conhecidas entre as fontes escolhidas, mais as manuais (só por colunas-chave).
    tipos = d.get("tipos") or {}
    ligacoes = []
    for r in RELACOES:
        if r[0] in fontes and r[2] in fontes:
            t = tipos.get(id_relacao(r), "INNER")
            if t == "NENHUMA":
                continue
            ligacoes.append({"a": r[0], "ca": r[1], "b": r[2], "cb": r[3], "tipo": t, "manual": False})
    for m in (d.get("manuais") or [])[:6]:
        a, ca, b, cb = m.get("a"), m.get("ca"), m.get("b"), m.get("cb")
        if a not in fontes or b not in fontes or a == b:
            _erro("Ligação manual entre fontes que não estão escolhidas")
        if ca not in FONTES[a].chaves or cb not in FONTES[b].chaves:
            _erro(f"Ligação manual só por colunas de ligação: {a}.{ca} = {b}.{cb}")
        ligacoes.append({"a": a, "ca": ca, "b": b, "cb": cb, "tipo": m.get("tipo", "INNER"), "manual": True})
    for lg in ligacoes:
        if lg["tipo"] not in TIPOS_LIGACAO:
            _erro(f"Tipo de ligação desconhecido: {lg['tipo']}")

    # O grão: soma numa fonte que tem outra "muitos" apontando para ela repete a linha.
    for f, c, campo in meds:
        if not campo.soma:
            continue
        muitos = [lg["a"] for lg in ligacoes if not lg["manual"] and lg["b"] == f and lg["a"] in fontes]
        if muitos:
            _erro(f"“{campo.rotulo}” soma {FONTES[f].rotulo.lower()}, e com {FONTES[muitos[0]].rotulo.lower()} "
                  f"junto cada linha se repete. Use a medida de {FONTES[muitos[0]].rotulo.lower()} "
                  "(ou tire essa fonte).")

    p: dict = {"u": id_unidade}
    de, ate = d.get("de"), d.get("ate")
    if de:
        p["de"] = date.fromisoformat(str(de))
    if ate:
        p["ate"] = date.fromisoformat(str(ate))

    def condicoes(f: str) -> list[str]:
        x = FONTES[f]
        cs = []
        if x.unidade:
            cs.append(f"{x.unidade} = %(u)s")
        if x.filtro:
            cs.append(x.filtro)
        if x.data and de:
            cs.append(f"{x.data} >= %(de)s")
        if x.data and ate:
            cs.append(f"{x.data} <= %(ate)s")
        return cs

    raiz = fontes[0]
    usadas = [raiz]
    juntas = []
    onde = condicoes(raiz)
    mudou = True
    while mudou:
        mudou = False
        for lg in ligacoes:
            tem_a, tem_b = lg["a"] in usadas, lg["b"] in usadas
            if tem_a == tem_b:
                continue
            nova = lg["b"] if tem_a else lg["a"]
            on = [f"{lg['a']}.{lg['ca']} = {lg['b']}.{lg['cb']}"]
            # ⚠️ Na ligação "manter todos", o recorte da fonte nova vai no ON — no WHERE ele
            # descartaria justamente as linhas sem par, e a ligação viraria "só o que casa".
            if lg["tipo"] == "LEFT":
                on += condicoes(nova)
            else:
                onde += condicoes(nova)
            juntas.append(f"{TIPOS_LIGACAO[lg['tipo']]} {FONTES[nova].tabela} AS {nova} ON {' AND '.join(on)}")
            usadas.append(nova)
            mudou = True
    soltas = [FONTES[f].rotulo for f in fontes if f not in usadas]
    if soltas:
        _erro(f"Sem ligação: {', '.join(soltas)}. Crie uma ligação ou tire a fonte.")

    colunas = ([{"chave": f"d{i}", "rotulo": c.rotulo, "tipo": "dim", "formato": c.formato}
                for i, (_, _, c) in enumerate(dims)]
               + [{"chave": f"m{i}", "rotulo": c.rotulo, "tipo": "med", "formato": c.formato}
                  for i, (_, _, c) in enumerate(meds)])
    sel = ([f"{c.expr} AS d{i}" for i, (_, _, c) in enumerate(dims)]
           + [f"{c.expr} AS m{i}" for i, (_, _, c) in enumerate(meds)])
    # Tempo se lê em ordem; o resto, do maior para o menor na primeira medida.
    temporal = dims and dims[0][2].formato in ("mes", "data")
    ordem = "1" if temporal else (f"{len(dims) + 1} DESC NULLS LAST" if dims else "1")
    sql = (f"SELECT {', '.join(sel)}\n  FROM {FONTES[raiz].tabela} AS {raiz}"
           + "".join(f"\n  {j}" for j in juntas)
           + (f"\n WHERE {' AND '.join(onde)}" if onde else "")
           + (f"\n GROUP BY {', '.join(str(i + 1) for i in range(len(dims)))}" if dims else "")
           + f"\n ORDER BY {ordem}\n LIMIT {LIMITE}")
    return sql, p, colunas


def executar(cur, d: dict, id_unidade: int, pode) -> dict:
    """Roda a definição: só leitura, com tempo máximo. Devolve colunas, linhas e o SQL legível."""
    sql, p, colunas = montar(d, id_unidade, pode)
    # ⚠️ Tem de ser a PRIMEIRA instrução da transação — depois dela o banco recusa qualquer
    # escrita. O que veio antes neste cursor foi só leitura (a loja), então encerra-se aqui.
    cur.connection.rollback()
    cur.execute("SET TRANSACTION READ ONLY")
    cur.execute(f"SET LOCAL statement_timeout = '{TEMPO_MAXIMO}'")
    try:
        cur.execute(sql, p)
    except Exception as e:  # noqa: BLE001 — o motivo vai para a tela, não para o log de erro
        if "statement timeout" in str(e).lower() or "canceling statement" in str(e).lower():
            raise HTTPException(status_code=422, detail="A consulta passou do tempo máximo. Use um período menor ou menos fontes.") from e
        raise
    linhas = [[r[c["chave"]] for c in colunas] for r in cur.fetchall()]
    legivel = cur.mogrify(sql, p)
    return {"colunas": colunas, "linhas": linhas, "limite": LIMITE, "cortado": len(linhas) >= LIMITE,
            "sql": legivel.decode() if isinstance(legivel, bytes) else str(legivel)}
