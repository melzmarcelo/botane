"""O catálogo dos relatórios — um lugar só onde cada um se declara.

Cada relatório diz o **rótulo**, a **permissão** que exige, os **filtros** que
aceita e como **montar** as linhas. Quem lê essa declaração são três: o
endpoint que entrega a planilha, o que entrega o PDF e o diálogo de exportação
na tela.

🔑 **O catálogo dos filtros vem do SERVIDOR, não escrito no front.** É a lição
das três listas de `TIPOS` (`models/produtos.py`, `web/lib/cadastros.ts`,
`models/cadastros.py`): lista repetida diverge, e aqui divergiria **calada** —
a tela ofereceria um filtro que o servidor ignora, o arquivo sairia com mais
linhas do que se pediu, e nada denunciaria.

⚠️ **O vocabulário de multisseleção é o mesmo de `inventario_selecao`**: cada
filtro é opcional, os filtros se combinam com **E**, e vazio quer dizer
"todos". No SQL, cada um entra como `(%(x)s IS NULL OR coluna = ANY(%(x)s))` —
montar o WHERE concatenando texto conforme o que veio preenchido daria uma
consulta diferente por combinação, e o bug moraria na que ninguém testou.

⚠️ **Nem todo relatório filtra pelo banco.** A movimentação do estoque e os
vencimentos são motores cuja consulta prova uma identidade
(`inicial + entradas − saídas = final`); remodelar o SQL deles para aceitar
filtro arriscaria justamente a propriedade que o relatório existe para provar.
Nesses dois o corte é feito **sobre as linhas devolvidas**, e é por isso que a
escolha em id vira nome antes de comparar.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable

from fastapi import HTTPException

import arquivos

from models.produtos import TIPOS
from services import alertas as alertas_motor
from services import cmv as cmv_motor
from services import estoque as estoque_motor
from services import exportacao
from services import relatorios

SITUACOES = [("ativos", "Ativos"), ("inativos", "Inativos"), ("rascunhos", "Rascunhos")]


# ---------------------------------------------------------------------------
# Filtros: o que cada um é, e de onde saem as opções
# ---------------------------------------------------------------------------

def _opcoes_locais(cur, id_unidade: int) -> list[dict]:
    cur.execute("""SELECT id AS valor, nome FROM locais_estoque
                    WHERE id_unidade = %s AND ativo ORDER BY lower(nome)""", (id_unidade,))
    return [dict(r) for r in cur.fetchall()]


def _opcoes_setores(cur, _id_unidade: int) -> list[dict]:
    cur.execute("SELECT id AS valor, nome FROM setores WHERE ativo ORDER BY ordem, lower(nome)")
    return [dict(r) for r in cur.fetchall()]


def _opcoes_categorias(cur, _id_unidade: int) -> list[dict]:
    cur.execute("SELECT id AS valor, nome FROM categorias WHERE ativo ORDER BY lower(nome)")
    return [dict(r) for r in cur.fetchall()]


def _opcoes_tipos_produto(_cur, _id_unidade: int) -> list[dict]:
    return [{"valor": t, "nome": t.replace("_", " ").capitalize()} for t in TIPOS]


def _opcoes_tipos_movimento(_cur, _id_unidade: int) -> list[dict]:
    # ⚠️ Os rótulos saem de `estoque.ROTULOS`, que é o mesmo lugar de onde a
    # tela do razão os lê. Uma lista copiada aqui envelheceria no primeiro tipo
    # novo, e o filtro passaria a esconder movimento sem dizer nada.
    return [{"valor": t, "nome": r} for t, r in sorted(estoque_motor.ROTULOS.items(),
                                                       key=lambda x: x[1])]


def _opcoes_situacao(_cur, _id_unidade: int) -> list[dict]:
    return [{"valor": v, "nome": n} for v, n in SITUACOES]


def _opcoes_classes(_cur, _id_unidade: int) -> list[dict]:
    return [{"valor": c, "nome": f"Classe {c}"} for c in ("A", "B", "C")]


FILTROS: dict[str, dict] = {
    "periodo": {"tipo": "periodo", "rotulo": "Período",
                "ajuda": "o mês corrente, se não escolher"},
    "locais": {"tipo": "multipla", "rotulo": "Locais", "ajuda": "todos os locais",
               "opcoes": _opcoes_locais},
    "setores": {"tipo": "multipla", "rotulo": "Setores", "ajuda": "todos os setores",
                "opcoes": _opcoes_setores},
    "categorias": {"tipo": "multipla", "rotulo": "Categorias",
                   "ajuda": "todas as categorias", "opcoes": _opcoes_categorias},
    "tipos_produto": {"tipo": "multipla", "rotulo": "Tipos de produto",
                      "ajuda": "todos os tipos", "opcoes": _opcoes_tipos_produto},
    "tipos_movimento": {"tipo": "multipla", "rotulo": "Movimentos",
                        "ajuda": "todos os movimentos", "opcoes": _opcoes_tipos_movimento},
    "situacao": {"tipo": "multipla", "rotulo": "Situação",
                 "ajuda": "ativos, inativos e rascunhos", "opcoes": _opcoes_situacao},
    "classes": {"tipo": "multipla", "rotulo": "Classes", "ajuda": "A, B e C",
                "opcoes": _opcoes_classes},
    # ⚠️ Produto NÃO é lista de caixinhas: são 3.226 no cadastro, e uma lista
    # dessas é a mesma mentira do `<select>` paginado. Vai pela busca da casa,
    # que pergunta ao servidor — o front resolve pelo tipo `produtos`.
    "produtos": {"tipo": "produtos", "rotulo": "Produtos",
                 "ajuda": "todos os produtos"},
    "busca": {"tipo": "texto", "rotulo": "Produto contém", "ajuda": "código ou parte do nome"},
    "dias": {"tipo": "numero", "rotulo": "Vencendo em até (dias)",
             "ajuda": "o prazo configurado na loja"},
}


def _lista(valores) -> list | None:
    """Lista vazia e `None` são a mesma coisa: "todos"."""
    if not valores:
        return None
    limpos = [v for v in valores if v is not None and v != ""]
    return limpos or None


def _periodo(f: dict) -> tuple[date, date]:
    hoje = date.today()
    return (f.get("inicio") or hoje.replace(day=1)), (f.get("fim") or hoje)


def _intervalo(inicio: date, fim: date) -> str:
    return f"{inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}"


def _nomes(opcoes: list[dict], escolhidos: list | None) -> set[str] | None:
    """Ids escolhidos → nomes, para o corte que acontece fora do banco."""
    if not escolhidos:
        return None
    return {o["nome"] for o in opcoes if o["valor"] in set(escolhidos)}


# ---------------------------------------------------------------------------
# O papel timbrado: quem emitiu o relatório
# ---------------------------------------------------------------------------

def _cnpj_formatado(bruto: str | None) -> str | None:
    """00000000000100 → "00.000.000/0001-00". Fora de 14 dígitos, devolve como veio.

    ⚠️ O cadastro aceita o CNPJ digitado de qualquer jeito, e num documento que
    vai ao contador ele precisa sair na forma que o contador lê. Quem não tem
    14 dígitos passa direto: um cadastro pela metade não pode virar um número
    inventado no papel.
    """
    if not bruto:
        return None
    d = "".join(c for c in bruto if c.isdigit())
    if len(d) != 14:
        return bruto
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def _junta(*pedacos, sep=" · ") -> str | None:
    """Só o que existe, e nada de separador solto quando o resto falta."""
    vivos = [str(p).strip() for p in pedacos if p and str(p).strip()]
    return sep.join(vivos) or None


def papel_timbrado(cur) -> dict:
    """O cabeçalho da casa para o PDF: nome, documento, endereço, contato, logo.

    ⚠️ **Monta com o que EXISTE.** Hoje a base tem razão social, nome fantasia
    e UF, e mais nada — CNPJ, endereço e logo estão em branco, e vão ficar até
    alguém preencher. Um cabeçalho que reserva a linha do CNPJ e a deixa vazia
    anuncia o que falta em cada página impressa; um que monta só o que tem sai
    limpo hoje e completo depois, sem ninguém tocar em nada.
    """
    cur.execute("SELECT * FROM empresa WHERE id = 1")
    e = cur.fetchone()
    if not e:
        return {}
    e = dict(e)

    # ⚠️ A UF só aparece ATRÁS da cidade. Sozinha ela virava uma linha de
    # endereço escrita "SC" — que é o estado atual da base, e não informa nada
    # a quem recebe o papel. Aqui o par é a informação, não cada metade.
    cidade_uf = (_junta(e.get("cidade"), e.get("uf"), sep="/")
                 if e.get("cidade") else None)
    endereco = _junta(
        _junta(e.get("logradouro"), e.get("numero"), e.get("complemento"), sep=", "),
        e.get("bairro"),
        cidade_uf,
        f"CEP {e['cep']}" if e.get("cep") else None,
    )
    linhas = [
        _junta(
            f"CNPJ {_cnpj_formatado(e.get('cnpj'))}" if e.get("cnpj") else None,
            f"IE {e['inscricao_estadual']}" if e.get("inscricao_estadual") else None,
        ),
        endereco,
        _junta(e.get("telefone"), e.get("email"), e.get("site")),
    ]
    return {
        "nome": e.get("nome_fantasia") or e.get("razao_social") or "",
        "linhas": [l for l in linhas if l],
        # Os BYTES, não um caminho: a logo mora no banco (migração 046), porque
        # o disco do App Platform some a cada deploy.
        "logo": (arquivos.ler(e.get("logo_url")) or (None,))[0],
    }


# ---------------------------------------------------------------------------
# Cada relatório
# ---------------------------------------------------------------------------

@dataclass
class Saida:
    linhas: list[dict]
    colunas: list[tuple[str, str]]
    titulo: str
    resumo: list[tuple[str, object]]
    inicio: date | None = None
    fim: date | None = None
    # ⚠️ Dois relatórios são COMPOSTOS de propósito, e não por sobra de
    # projeto: o do contador leva a apuração e a margem por prato; o da reunião
    # com o fornecedor leva a evolução de preço e o peso por setor. São quadros
    # que se leem juntos — em dois arquivos, quem recebe teria de juntar de
    # novo. Planilha e PDF respeitam os dois igualmente.
    anexos: list[tuple] = field(default_factory=list)


def _saldos(cur, id_unidade: int, f: dict) -> Saida:
    cur.execute(
        """SELECT p.codigo, p.nome AS produto, c.nome AS categoria, l.nome AS local,
                  p.um_estoque, s.quantidade, s.custo_medio,
                  round(s.quantidade * s.custo_medio, 2) AS valor, p.estoque_minimo
             FROM estoque_saldos s
             JOIN produtos p ON p.id = s.id_produto
             JOIN locais_estoque l ON l.id = s.id_local
             LEFT JOIN categorias c ON c.id = p.id_categoria
            WHERE s.id_unidade = %(unidade)s AND p.ativo AND s.quantidade <> 0
              AND (%(locais)s::int[] IS NULL OR s.id_local = ANY(%(locais)s))
              AND (%(setores)s::int[] IS NULL OR p.id_setor = ANY(%(setores)s))
              AND (%(categorias)s::int[] IS NULL OR p.id_categoria = ANY(%(categorias)s))
              AND (%(tipos)s::varchar[] IS NULL OR p.tipo = ANY(%(tipos)s))
              AND (%(produtos)s::int[] IS NULL OR s.id_produto = ANY(%(produtos)s))
            ORDER BY lower(p.nome), l.nome""",
        {"unidade": id_unidade, "locais": _lista(f.get("locais")),
         "setores": _lista(f.get("setores")), "categorias": _lista(f.get("categorias")),
         "tipos": _lista(f.get("tipos_produto")),
         "produtos": _lista(f.get("produtos"))},
    )
    linhas = [dict(r) for r in cur.fetchall()]
    total = sum(float(l["valor"] or 0) for l in linhas)
    return Saida(
        linhas,
        [("codigo", "Código"), ("produto", "Produto"), ("categoria", "Categoria"),
         ("local", "Local"), ("um_estoque", "Unidade"), ("quantidade", "Saldo"),
         ("custo_medio", "Custo médio"), ("valor", "Valor em estoque"),
         ("estoque_minimo", "Estoque mínimo")],
        "Posição de estoque",
        [("Linhas", len(linhas)), ("Valor total em estoque", round(total, 2))],
    )


def _movimentos(cur, id_unidade: int, f: dict) -> Saida:
    """O razão, com os MESMOS filtros da tela.

    Sem eles, filtrar na tela e clicar em baixar dava outro arquivo — e quem
    conferisse os dois acharia que um dos dois está errado.
    """
    inicio, fim = _periodo(f)
    cur.execute(
        """SELECT m.data_movimento, m.tipo, p.codigo, p.nome AS produto, l.nome AS local,
                  m.quantidade, m.custo_unitario, m.custo_total, m.saldo_apos,
                  m.custo_medio_apos, m.documento, pm.nome AS motivo, m.observacao,
                  u.nome AS usuario
             FROM estoque_movimentos m
             JOIN produtos p ON p.id = m.id_produto
             JOIN locais_estoque l ON l.id = m.id_local
             LEFT JOIN perda_motivos pm ON pm.id = m.id_motivo_perda
             LEFT JOIN usuarios u ON u.id = m.id_usuario
            WHERE m.id_unidade = %(unidade)s
              AND m.data_movimento >= %(inicio)s AND m.data_movimento < %(limite)s
              AND (%(tipos)s::varchar[] IS NULL OR m.tipo = ANY(%(tipos)s))
              AND (%(locais)s::int[] IS NULL OR m.id_local = ANY(%(locais)s))
              AND (%(produtos)s::int[] IS NULL OR m.id_produto = ANY(%(produtos)s))
              AND (%(busca)s::varchar IS NULL
                   OR lower(p.nome) LIKE lower('%%' || %(busca)s || '%%')
                   OR lower(p.codigo) LIKE lower('%%' || %(busca)s || '%%'))
            ORDER BY m.id""",
        # ⚠️ `fim` é dia CHEIO: `<= fim` cortaria o que foi lançado às 14h do
        # próprio dia, porque `data_movimento` guarda data e hora.
        {"unidade": id_unidade, "inicio": inicio, "limite": fim + timedelta(days=1),
         "tipos": _lista(f.get("tipos_movimento")), "locais": _lista(f.get("locais")),
         "produtos": _lista(f.get("produtos")), "busca": f.get("busca") or None},
    )
    linhas = [dict(r) for r in cur.fetchall()]
    for l in linhas:
        l["tipo"] = estoque_motor.ROTULOS.get(l["tipo"], l["tipo"])
    return Saida(
        linhas,
        [("data_movimento", "Data"), ("tipo", "Movimento"), ("codigo", "Código"),
         ("produto", "Produto"), ("local", "Local"), ("quantidade", "Quantidade"),
         ("custo_unitario", "Custo unitário"), ("custo_total", "Custo total"),
         ("saldo_apos", "Saldo depois"), ("custo_medio_apos", "Custo médio depois"),
         ("documento", "Documento"), ("motivo", "Motivo"), ("observacao", "Observação"),
         ("usuario", "Quem lançou")],
        f"Razão de estoque — {_intervalo(inicio, fim)}",
        [("Movimentos", len(linhas))],
        inicio, fim,
    )


def _produtos(cur, _id_unidade: int, f: dict) -> Saida:
    situacao = _lista(f.get("situacao"))
    cur.execute(
        """SELECT p.codigo, p.nome AS produto, p.tipo, c.nome AS categoria,
                  s.nome AS setor, p.um_estoque, p.um_compra, p.fator_compra,
                  p.estoque_minimo, p.perecivel, p.validade_dias, p.controla_lote,
                  p.ncm, p.codigo_barras, p.status, p.ativo,
                  (SELECT pp.preco_venda FROM produto_precos pp
                    WHERE pp.id_produto = p.id AND pp.vigente_ate IS NULL
                    ORDER BY pp.vigente_de DESC LIMIT 1) AS preco_venda
             FROM produtos p
             LEFT JOIN categorias c ON c.id = p.id_categoria
             LEFT JOIN setores s ON s.id = p.id_setor
            WHERE (%(tipos)s::varchar[] IS NULL OR p.tipo = ANY(%(tipos)s))
              AND (%(categorias)s::int[] IS NULL OR p.id_categoria = ANY(%(categorias)s))
              AND (%(setores)s::int[] IS NULL OR p.id_setor = ANY(%(setores)s))
              AND (%(situacao)s::varchar[] IS NULL OR
                   ('ativos' = ANY(%(situacao)s) AND p.ativo AND p.status <> 'RASCUNHO') OR
                   ('inativos' = ANY(%(situacao)s) AND NOT p.ativo) OR
                   ('rascunhos' = ANY(%(situacao)s) AND p.status = 'RASCUNHO'))
            ORDER BY lower(p.nome)""",
        {"tipos": _lista(f.get("tipos_produto")),
         "categorias": _lista(f.get("categorias")), "setores": _lista(f.get("setores")),
         "situacao": situacao},
    )
    linhas = [dict(r) for r in cur.fetchall()]
    return Saida(
        linhas,
        [("codigo", "Código"), ("produto", "Produto"), ("tipo", "Tipo"),
         ("categoria", "Categoria"), ("setor", "Setor"), ("um_estoque", "Un. estoque"),
         ("um_compra", "Un. compra"), ("fator_compra", "Fator"),
         ("preco_venda", "Preço de venda"), ("estoque_minimo", "Estoque mínimo"),
         ("perecivel", "Perecível"), ("validade_dias", "Validade (dias)"),
         ("controla_lote", "Controla lote"), ("ncm", "NCM"),
         ("codigo_barras", "Código de barras"), ("status", "Situação"), ("ativo", "Ativo")],
        "Cadastro de produtos",
        [("Produtos", len(linhas))],
    )


def _vencimentos(cur, id_unidade: int, f: dict) -> Saida:
    dias = f.get("dias")
    linhas = alertas_motor.vencimentos(cur, id_unidade, dias)
    # ⚠️ O corte por local é feito AQUI, sobre as linhas, e não no SQL do motor
    # de alertas: é o mesmo motor que alimenta o alerta da tela inicial, e
    # emendar filtro nele para servir a exportação mudaria os dois.
    nomes = _nomes(_opcoes_locais(cur, id_unidade), _lista(f.get("locais")))
    if nomes is not None:
        linhas = [l for l in linhas if l["local"] in nomes]
    return Saida(
        linhas,
        [("validade", "Validade"), ("dias_restantes", "Dias restantes"),
         ("codigo", "Código"), ("produto", "Produto"), ("lote", "Lote"),
         ("local", "Local"), ("quantidade", "Quantidade"), ("um_estoque", "Unidade"),
         ("valor", "Valor")],
        "Lotes a vencer",
        [("Lotes", len(linhas)),
         ("Valor exposto", round(sum(float(l["valor"] or 0) for l in linhas), 2))],
    )


def _cmv(cur, id_unidade: int, f: dict) -> Saida:
    """A apuração aberta linha a linha — é o arquivo que vai para o contador."""
    inicio, fim = _periodo(f)
    a = cmv_motor.apurar(cur, id_unidade, inicio, fim)

    # ⚠️ **Dinheiro sai em CENTAVOS aqui, e é arredondamento de APRESENTAÇÃO.**
    # A apuração encadeia custo unitário de 6 casas, então o CMV real vinha como
    # `56138.035` — e o arquivo do contador dizia "56.138,035", que não é um
    # valor em reais. O CSV já fazia isso calado; o PDF só tornou visível.
    # O número da CONTA continua com toda a precisão: quem arredonda é a linha
    # do relatório, não o motor.
    def reais(v) -> Decimal:
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    linhas = [
        {"linha": "Estoque inicial", "valor": reais(a["estoque_inicial"])},
        {"linha": "(+) Compras", "valor": reais(a["compras"])},
        {"linha": "(−) Estoque final", "valor": reais(-a["estoque_final"])},
        {"linha": "(=) CMV real", "valor": reais(a["cmv_real"])},
        {"linha": "CMV teórico (fichas × vendas)", "valor": reais(a["cmv_teorico"])},
        {"linha": "Variância (real − teórico)", "valor": reais(a["variancia"])},
        {"linha": "  dos quais: perdas", "valor": reais(a["perdas"])},
        {"linha": "  dos quais: consumo interno", "valor": reais(a["consumo_interno"])},
        {"linha": "  dos quais: ajustes de inventário", "valor": reais(a["ajustes"])},
        {"linha": "Receita do período", "valor": reais(a["receita"])},
    ]
    margem = cmv_motor.margem_por_prato(cur, id_unidade, inicio, fim, 500)
    return Saida(
        linhas,
        [("linha", "Composição do CMV"), ("valor", "Valor (R$)")],
        f"CMV — {_intervalo(inicio, fim)}",
        [("Food cost", f"{a['food_cost_pct']:.2f}%" if a["food_cost_pct"] else "—"),
         ("Cobertura de ficha", f"{a['cobertura_ficha_pct']:.1f}%"),
         ("Vendas no período", a["vendas"])],
        inicio, fim,
        anexos=[(margem,
                 [("produto", "Prato"), ("quantidade", "Vendidos"), ("receita", "Receita"),
                  ("custo", "Custo pela ficha"), ("margem", "Margem"),
                  ("food_cost_pct", "Food cost %"), ("sem_custo", "Tem item sem custo")],
                 "Margem por prato", None)],
    )


def _abc(cur, id_unidade: int, f: dict) -> Saida:
    inicio, fim = _periodo(f)
    linhas = cmv_motor.curva_abc(cur, id_unidade, inicio, fim, 500)
    classes = _lista(f.get("classes"))
    if classes:
        linhas = [l for l in linhas if l["classe"] in set(classes)]
    return Saida(
        linhas,
        [("codigo", "Código"), ("produto", "Insumo"), ("quantidade", "Consumo"),
         ("um_estoque", "Unidade"), ("valor", "Valor consumido"),
         ("participacao_pct", "Participação %"), ("acumulada_pct", "Acumulado %"),
         ("classe", "Classe")],
        f"Curva ABC — {_intervalo(inicio, fim)}",
        [("Insumos", len(linhas)),
         ("Valor consumido", round(sum(float(l["valor"] or 0) for l in linhas), 2))],
        inicio, fim,
    )


def _movimentacao(cur, id_unidade: int, f: dict) -> Saida:
    """A movimentação do período, produto a produto — a planilha que se confere.

    Período fechado sai do que foi CONGELADO no fechamento; período aberto sai
    do razão na hora. O resumo diz qual dos dois, porque mandar ao contador um
    número que ainda pode mudar é o erro que este relatório existe para evitar.
    """
    inicio, fim = _periodo(f)
    cur.execute(
        """SELECT id, competencia FROM cmv_fechamentos
            WHERE id_unidade = %s AND inicio = %s AND fim = %s AND status = 'FECHADO'""",
        (id_unidade, inicio, fim),
    )
    fechamento = cur.fetchone()
    if fechamento:
        linhas = cmv_motor.movimentacao_congelada(cur, fechamento["id"])
    else:
        linhas = cmv_motor.movimentacao_por_produto(cur, id_unidade, inicio, fim)

    # ⚠️ O corte sai FORA do motor: a consulta dele prova a identidade
    # `inicial + entradas − saídas = final`, e emendar filtro no SQL arriscaria
    # a propriedade que o relatório existe para demonstrar. As linhas trazem
    # categoria e setor pelo NOME (a cópia congelada também), daí o de-para.
    cats = _nomes(_opcoes_categorias(cur, id_unidade), _lista(f.get("categorias")))
    sets_ = _nomes(_opcoes_setores(cur, id_unidade), _lista(f.get("setores")))
    if cats is not None:
        linhas = [l for l in linhas if l.get("categoria") in cats]
    if sets_ is not None:
        linhas = [l for l in linhas if l.get("setor") in sets_]

    soma = lambda campo: sum(float(l[campo] or 0) for l in linhas)  # noqa: E731
    return Saida(
        linhas,
        [("codigo", "Código"), ("produto", "Produto"), ("um_estoque", "Un."),
         ("categoria", "Categoria"), ("setor", "Setor"),
         ("qtd_inicial", "Estoque inicial (qtd)"), ("valor_inicial", "Estoque inicial (R$)"),
         ("qtd_entradas", "Entradas (qtd)"), ("valor_entradas", "Entradas (R$)"),
         ("qtd_saidas", "Saídas (qtd)"), ("valor_saidas", "Saídas (R$)"),
         ("qtd_final", "Estoque final (qtd)"), ("valor_final", "Estoque final (R$)"),
         ("custo_medio_final", "Custo médio final")],
        f"Movimentação de estoque — {_intervalo(inicio, fim)}",
        [("Situação", "período fechado (congelado)" if fechamento
                      else "período aberto (parcial)"),
         ("Produtos", len(linhas)),
         ("Estoque inicial (R$)", round(soma("valor_inicial"), 2)),
         ("Entradas (R$)", round(soma("valor_entradas"), 2)),
         ("Saídas (R$)", round(soma("valor_saidas"), 2)),
         ("Estoque final (R$)", round(soma("valor_final"), 2))],
        inicio, fim,
    )


def _precos(cur, id_unidade: int, f: dict) -> Saida:
    """A planilha que vai para a reunião com o fornecedor."""
    inicio, fim = _periodo(f)
    linhas = relatorios.evolucao_de_preco(cur, id_unidade, inicio, fim, 500)
    grupos = relatorios.cmv_por_grupo(cur, id_unidade, inicio, fim, "setor")
    return Saida(
        linhas,
        [("codigo", "Código"), ("produto", "Insumo"), ("um_estoque", "Unidade"),
         ("compras", "Compras"), ("quantidade", "Quantidade comprada"),
         ("primeiro", "Primeiro preço"), ("ultimo", "Último preço"),
         ("variacao_pct", "Variação %"), ("impacto", "Impacto R$"),
         ("menor", "Menor preço"), ("fornecedor_mais_barato", "Mais barato com"),
         ("economia_possivel", "Economia possível"),
         ("fornecedor_ultimo", "Última compra com"), ("data_ultimo", "Data da última")],
        f"Evolução de preço — {_intervalo(inicio, fim)}",
        [("Insumos com variação", len(linhas)),
         ("Impacto somado", round(sum(float(l["impacto"] or 0) for l in linhas), 2)),
         ("Economia possível",
          round(sum(float(l["economia_possivel"] or 0) for l in linhas), 2))],
        inicio, fim,
        anexos=[(grupos,
                 [("grupo", "Setor"), ("estoque_inicial", "Estoque inicial"),
                  ("compras", "Compras"), ("estoque_final", "Estoque final"),
                  ("cmv", "CMV"), ("perdas", "Perdas"),
                  ("participacao_pct", "Participação %")],
                 "Onde o custo pesa (por setor)", None)],
    )


@dataclass(frozen=True)
class Relatorio:
    rotulo: str
    descricao: str
    permissao: str
    base: str
    filtros: tuple[str, ...]
    montar: Callable[..., Saida]


RELATORIOS: dict[str, Relatorio] = {
    "saldos": Relatorio(
        "Posição de estoque", "O que existe hoje, por produto e prateleira, com o valor.",
        "estoque.saldos", "estoque",
        ("locais", "setores", "categorias", "tipos_produto", "produtos"), _saldos),
    "movimentos": Relatorio(
        "Razão de estoque", "Cada movimento do período, com saldo e custo médio depois dele.",
        "estoque.saldos", "movimentos",
        ("periodo", "tipos_movimento", "locais", "produtos", "busca"), _movimentos),
    "produtos": Relatorio(
        "Cadastro de produtos", "A ficha de cadastro de cada item, com unidade e preço.",
        "cadastros.produtos", "produtos",
        ("tipos_produto", "categorias", "setores", "situacao"), _produtos),
    "vencimentos": Relatorio(
        "Lotes a vencer", "O que vence, quando, onde e quanto vale.",
        "estoque.saldos", "vencimentos", ("dias", "locais"), _vencimentos),
    "cmv": Relatorio(
        "Apuração do CMV",
        "A conta aberta linha a linha, com a margem por prato junto — o arquivo do contador.",
        "cmv.relatorios", "cmv", ("periodo",), _cmv),
    "abc": Relatorio(
        "Curva ABC de insumos", "Onde o dinheiro do consumo se concentra.",
        "cmv.relatorios", "curva-abc", ("periodo", "classes"), _abc),
    "movimentacao": Relatorio(
        "Movimentação do estoque", "Inicial, entradas, saídas e final de cada produto.",
        "cmv.relatorios", "movimentacao",
        ("periodo", "categorias", "setores"), _movimentacao),
    "precos": Relatorio(
        "Evolução de preço",
        "O que subiu, quanto pesou e com quem sai mais barato, com o peso por setor junto.",
        "cmv.relatorios", "precos", ("periodo",), _precos),
}


def catalogo(cur, id_unidade: int, pode: Callable[[str], bool]) -> list[dict]:
    """Os relatórios que ESTA pessoa pode exportar, com as opções já resolvidas.

    ⚠️ As opções vêm resolvidas de propósito: sem isso o diálogo precisaria de
    quatro requisições a mais só para saber o que oferecer, e a tela piscaria
    quatro vezes antes de deixar escolher.
    """
    saida = []
    for chave, r in RELATORIOS.items():
        if not pode(r.permissao):
            continue
        filtros = []
        for nome in r.filtros:
            d = FILTROS[nome]
            item = {"nome": nome, "tipo": d["tipo"], "rotulo": d["rotulo"],
                    "ajuda": d["ajuda"]}
            if "opcoes" in d:
                item["opcoes"] = d["opcoes"](cur, id_unidade)
            filtros.append(item)
        saida.append({"chave": chave, "rotulo": r.rotulo, "descricao": r.descricao,
                      "filtros": filtros})
    return saida


def montar(cur, chave: str, id_unidade: int, f: dict) -> Saida:
    r = RELATORIOS.get(chave)
    if not r:
        # ⚠️ A frase nomeia os que existem: quem errou o nome quase sempre
        # errou por uma letra, e uma lista responde mais rápido que a memória.
        raise HTTPException(
            status_code=404,
            detail=f"Relatório que não existe: {chave}. "
                   f"Os que existem: {', '.join(sorted(RELATORIOS))}.")
    return r.montar(cur, id_unidade, f)


def limite_do_pdf(quantas: int) -> None:
    """⚠️ O milhar sai de `exportacao.milhar`, não de `f"{n:,}".replace(",", ".")`.

    Aquele truque troca a vírgula do MILHAR e a da FRASE pelo mesmo ponto: a
    mensagem saía "acima de 5.000. porque vira um arquivo…" e "baixe a
    planilha. que não tem teto". Frase de erro quebrada é o que a pessoa lê
    justamente quando já está confusa.
    """
    if quantas > exportacao.MAXIMO_PDF:
        raise HTTPException(
            status_code=400,
            detail=(f"São {exportacao.milhar(str(quantas))} linhas — o PDF para acima de "
                    f"{exportacao.milhar(str(exportacao.MAXIMO_PDF))}, porque vira um "
                    f"arquivo de milhares de páginas que ninguém abre. Estreite o filtro "
                    f"ou baixe a planilha, que não tem teto."))
