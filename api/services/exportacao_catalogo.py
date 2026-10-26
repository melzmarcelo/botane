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

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable

import relogio
from fastapi import HTTPException

import arquivos

from models.produtos import TIPOS
from services import alertas as alertas_motor
from services import cmv as cmv_motor
from services import consumo_pessoa as consumo_motor
from services import receber as receber_motor
from services import estoque as estoque_motor
from services import exportacao
from services import memoria_calculo as memoria
from services import painel_vendas
from services import periodos as periodos_motor
from services import relatorios

SITUACOES = [("ativos", "Ativos"), ("inativos", "Inativos"), ("rascunhos", "Rascunhos")]
# 🔑 As pessoas (20/10/2026): fornecedor ou não, e ativa ou não — os mesmos recortes
# da tela de Pessoas, para o arquivo sair igual ao que se vê.
TIPOS_PESSOA = [("fornecedor", "Fornecedores"),
                ("outra", "Não fornecedores (equipe, sócios, clientes)")]
SITUACOES_PESSOA = [("ativas", "Ativas"), ("inativas", "Inativas")]


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


def _opcoes_tipo_pessoa(_cur, _id_unidade: int) -> list[dict]:
    return [{"valor": v, "nome": n} for v, n in TIPOS_PESSOA]


def _opcoes_situacao_pessoa(_cur, _id_unidade: int) -> list[dict]:
    return [{"valor": v, "nome": n} for v, n in SITUACOES_PESSOA]


def _opcoes_pessoas(cur, id_unidade: int) -> list[dict]:
    """As pessoas que podem aparecer no relatório — não o cadastro inteiro.

    ⚠️ Oferecer as 800 do cadastro faria a lista virar a mentira do `<select>`
    paginado, e escolher quem nunca consumiu devolveria um arquivo vazio.
    🔑 **Quem tem política OU quem tem consumo lançado nesta loja** (26/09/2026,
    pedido do dono: *"permitir filtrar pessoas para emissão do PDF mesmo sem
    política, pois vinculei a uma pessoa sem política e não consigo emitir
    somente para ela"*). Era só quem tinha política — e a tela, que busca no
    cadastro inteiro, mandava para o arquivo uma pessoa que a lista não tinha.
    """
    cur.execute("""SELECT f.id AS valor, f.nome FROM fornecedores f
                    WHERE f.ativo
                      AND (f.cupom_base = 'CUSTO' OR coalesce(f.cupom_desconto_pct, 0) > 0
                           OR EXISTS (SELECT 1 FROM vendas v
                                       WHERE v.id_pessoa = f.id AND v.id_unidade = %s
                                         AND NOT v.cancelada))
                    ORDER BY lower(f.nome)""", (id_unidade,))
    return [dict(r) for r in cur.fetchall()]


def _opcoes_detalhe(_cur, _id_unidade: int) -> list[dict]:
    return [{"valor": "sintetico", "nome": "Sintético — um total por pessoa"},
            {"valor": "documento", "nome": "Por documento — um total por cupom"},
            {"valor": "documento_itens", "nome": "Por documento, com os itens destacados"},
            {"valor": "analitico", "nome": "Analítico — item a item"}]


SITUACOES_CONSUMO = {
    "aberto": "Em aberto — ainda não cobrado",
    "cobranca": "Em cobrança — num lote ainda não pago",
    "recebido": "Recebido — num lote com baixa",
    "todos": "Todos — com ou sem lote",
}


def _opcoes_situacao_consumo(_cur, _id_unidade: int) -> list[dict]:
    """A situação do documento nas contas a receber (22/10/2026).

    🔑 **"Em aberto" vem primeiro e é o padrão**: é o que a casa tem a receber e
    ainda não cobrou, a pergunta mais frequente deste relatório.
    """
    return [{"valor": v, "nome": n} for v, n in SITUACOES_CONSUMO.items()]


# 🔑 Os quatro relatórios de 23/10/2026 (pedido do dono: "mais relatorios e planilhas"):
# compras, perdas e ajustes, margem dos pratos e recebimentos.
SITUACOES_NOTA = {
    "lancada": "Lançadas no estoque",
    "pendente": "Ainda não lançadas (importadas ou conciliadas)",
    "cancelada": "Canceladas",
}
DETALHES_COMPRAS = {
    "nota": "Por nota — uma linha por nota fiscal",
    "fornecedor": "Por fornecedor — quanto se comprou de cada um",
    "produto": "Por produto — quanto, por quanto e de quantos fornecedores",
    "item": "Item a item — cada linha de cada nota",
}
DETALHES_PRODUCAO = {
    "producao": "Produção a produção — cada lote feito",
    "produto": "Por produto — quanto se fez e quanto custou",
}
ORIGENS_PRODUCAO = {
    "cozinha": "Feitas na cozinha (agenda ou à mão)",
    "na_hora": "Na hora, disparadas pela venda (café, suco…)",
}
DETALHES_PERDAS = {
    "motivo": "Por motivo — quanto se perdeu por cada razão",
    "produto": "Por produto — o que mais se perde",
    "movimento": "Movimento a movimento — cada perda e cada ajuste",
}


def _opcoes_situacao_nota(_cur, _id_unidade: int) -> list[dict]:
    return [{"valor": v, "nome": n} for v, n in SITUACOES_NOTA.items()]


def _opcoes_detalhe_compras(_cur, _id_unidade: int) -> list[dict]:
    return [{"valor": v, "nome": n} for v, n in DETALHES_COMPRAS.items()]


def _opcoes_detalhe_perdas(_cur, _id_unidade: int) -> list[dict]:
    return [{"valor": v, "nome": n} for v, n in DETALHES_PERDAS.items()]


def _opcoes_motivos(cur, _id_unidade: int) -> list[dict]:
    """Os motivos de perda do cadastro, mais as três origens que não têm motivo.

    ⚠️ O valor é TEXTO (`m12`, `sem_motivo`, `inventario`, `ajuste`): o motivo do
    cadastro e a origem do ajuste respondem à mesma pergunta — "por que saiu" —, e
    dois filtros para ela fariam escolher duas vezes.
    """
    cur.execute("SELECT id, nome FROM perda_motivos ORDER BY lower(nome)")
    return ([{"valor": f"m{r['id']}", "nome": r["nome"]} for r in cur.fetchall()]
            + [{"valor": "sem_motivo", "nome": "Perda sem motivo informado"},
               {"valor": "inventario", "nome": "Diferença de inventário"},
               {"valor": "ajuste", "nome": "Ajuste de saldo"}])


def _opcoes_detalhe_producao(_cur, _id_unidade: int) -> list[dict]:
    return [{"valor": v, "nome": n} for v, n in DETALHES_PRODUCAO.items()]


def _opcoes_origem_producao(_cur, _id_unidade: int) -> list[dict]:
    return [{"valor": v, "nome": n} for v, n in ORIGENS_PRODUCAO.items()]


def _opcoes_formas(_cur, _id_unidade: int) -> list[dict]:
    return [{"valor": v, "nome": n} for v, n in receber_motor.FORMAS.items()]


def _opcoes_classes(_cur, _id_unidade: int) -> list[dict]:
    return [{"valor": c, "nome": f"Classe {c}"} for c in ("A", "B", "C")]


def _opcoes_periodo_cmv(cur, id_unidade: int) -> list[dict]:
    """Os períodos do CICLO da loja — os mesmos que o painel oferece.

    🔑 **Pedido do dono (16/09/2026):** *"esta vai abrir o filtro do período, e
    não datas como está"*. ⚠️ **Data digitada à mão é onde o engano entra**:
    "17/08 a 23/08" com um dia a mais e o arquivo deixa de bater com o
    fechamento — e nada avisa, porque o número continua saindo.

    ⚠️ **O valor é `inicio|fim`, e o front o desmembra em `inicio` e `fim`.**
    O contrato do servidor não muda: `_periodo(f)` continua lendo as duas
    pontas, e todo o resto do catálogo segue igual. Um parâmetro novo só para
    este relatório criaria uma segunda forma de dizer período.

    ⚠️ **O corrente é truncado em HOJE.** Ele ainda não terminou, e oferecer o
    fim que vai acontecer faria o arquivo prometer dias que não existem.
    """
    hoje = relogio.hoje_da_casa()
    c = periodos_motor.config(cur, id_unidade)
    lista = periodos_motor.periodos_ate_hoje(
        c["ciclo"], 12, dia_semana=c["dia_semana"], dia_mes=c["dia_mes"], hoje=hoje)
    opcoes = []
    for i, f in lista:
        ate = min(f, hoje)
        rotulo = periodos_motor.rotulo(i, f, c["ciclo"])
        if i <= hoje <= f:
            rotulo += " (em curso)"
        opcoes.append({"valor": f"{i}|{ate}", "nome": rotulo})
    return opcoes


# 🔑 **As abas do painel, como conteúdo do arquivo** (pedido do dono,
# 16/09/2026: *"este deve baixar os números do CMV, abaixo do cabeçalho, e os
# dados da aba posicionada"*). O arquivo tem sempre duas partes: a conta do CMV
# e o quadro da aba em que a pessoa está.
# ⚠️ **Os seis eixos da quebra são opções PRÓPRIAS**, e não um segundo filtro:
# a janela precisa dizer exatamente o que vai sair, e "Quebra do CMV" com o eixo
# escondido noutro campo faria escolher duas vezes para uma pergunta só.
ABAS_DO_PAINEL = [
    ("conta", "A conta — só a composição do CMV"),
    ("quebra-loja", "Quebra por loja"),
    ("quebra-local", "Quebra por prateleira"),
    ("quebra-setor", "Quebra por setor"),
    ("quebra-categoria", "Quebra por categoria"),
    ("quebra-grupo", "Quebra por grupo do CMV"),
    ("quebra-produto", "Quebra por produto"),
    ("abc", "Curva ABC de insumos"),
    ("margem", "Margem por prato"),
    ("movimentacao", "Movimentação do estoque"),
    ("precos", "O que subiu de preço"),
    ("memoria", "Memória de cálculo"),
]


def _opcoes_agrupar(_cur, _id_unidade: int) -> list[dict]:
    return [{"valor": v, "nome": n} for v, n in painel_vendas.AGRUPAMENTOS.items()]


def _opcoes_aba(_cur, _id_unidade: int) -> list[dict]:
    return [{"valor": v, "nome": n} for v, n in ABAS_DO_PAINEL]


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
    # 🔑 A saída que não achou saldo sai por um custo PROVISÓRIO, e cada uma
    # delas é uma entrada que ninguém lançou. ⚠️ Vale como filtro do ARQUIVO
    # porque a tela passou a oferecê-lo: filtro que existe num lado só recria a
    # divergência que o razão exportado existe para não ter.
    "provisorio": {"tipo": "sim_nao", "rotulo": "Só custo provisório",
                   "ajuda": "todos os movimentos"},
    "dias": {"tipo": "numero", "rotulo": "Vencendo em até (dias)",
             "ajuda": "o prazo configurado na loja"},
    # ⚠️ Uma DATA, não um período: o inventário valorizado responde "quanto
    # valia o estoque naquele dia", e oferecer duas pontas ali faria escolher um
    # intervalo para uma pergunta que tem uma data só.
    "data": {"tipo": "data", "rotulo": "Na data de", "ajuda": "hoje, se não escolher"},
    "pessoas": {"tipo": "multipla", "rotulo": "Pessoas", "ajuda": "todas",
                "opcoes": _opcoes_pessoas},
    # ⚠️ Escolha múltipla porque é o vocabulário da janela — mas o relatório usa
    # só a PRIMEIRA: sintético e analítico são dois documentos, e um arquivo com
    # os dois faria quem recebe separar de novo.
    "detalhe": {"tipo": "multipla", "rotulo": "Detalhe", "ajuda": "sintético",
                "opcoes": _opcoes_detalhe},
    # 🔑 **Situação + datas, no lugar do ciclo** (22/10/2026, contas a receber).
    # O documento de UM lote sai pela rota do lote (`/exportar/lote-consumo`),
    # que recorta pelo lote e não por data.
    "situacao_consumo": {"tipo": "escolha", "rotulo": "Situação",
                         "ajuda": "em aberto — o que ainda não foi cobrado",
                         "opcoes": _opcoes_situacao_consumo},
    # ⚠️ Sem datas são TODAS — não o mês corrente, como nos outros relatórios: a
    # dívida de agosto ainda não cobrada é justamente a que não pode sumir.
    "periodo_consumo": {"tipo": "periodo", "rotulo": "Datas dos documentos",
                        "ajuda": "todas as datas, se não escolher"},
    # ⚠️ **Mesmo `tipo: periodo`, com OPÇÕES** — e é isso que muda a cara dele na
    # janela: o front, vendo opções num filtro de período, troca os dois campos
    # de data por um seletor dos ciclos e grava `inicio`/`fim` do valor
    # escolhido. O servidor continua lendo as duas pontas, como sempre leu.
    "periodo_cmv": {"tipo": "periodo", "rotulo": "Período",
                    "ajuda": "os períodos do ciclo da loja — o mesmo recorte do painel",
                    "opcoes": _opcoes_periodo_cmv},
    # ⚠️ **Escolha ÚNICA, não múltipla.** `detalhe` (e o antigo `ciclo`) são múltiplas e
    # usam só a primeira, o que sempre foi um remendo do vocabulário da janela;
    # com doze opções isso viraria doze caixinhas para uma escolha só.
    "aba": {"tipo": "escolha", "rotulo": "O que levar junto",
            "ajuda": "a aba em que você está no painel", "opcoes": _opcoes_aba},
    "tipo_pessoa": {"tipo": "multipla", "rotulo": "Tipo", "ajuda": "fornecedores e não fornecedores",
                    "opcoes": _opcoes_tipo_pessoa},
    "situacao_pessoa": {"tipo": "multipla", "rotulo": "Situação", "ajuda": "ativas e inativas",
                        "opcoes": _opcoes_situacao_pessoa},
    "agrupar": {"tipo": "escolha", "rotulo": "Evolução por",
                "ajuda": "dia, semana ou mês", "opcoes": _opcoes_agrupar},
    "busca_pessoa": {"tipo": "texto", "rotulo": "Nome ou CNPJ contém",
                     "ajuda": "parte do nome, do nome fantasia ou do CNPJ"},
    # 🔑 Os de 23/10/2026.
    "situacao_nota": {"tipo": "multipla", "rotulo": "Situação da nota",
                      "ajuda": "lançadas e ainda não lançadas (canceladas ficam de fora)",
                      "opcoes": _opcoes_situacao_nota},
    "busca_fornecedor": {"tipo": "texto", "rotulo": "Fornecedor contém",
                         "ajuda": "parte do nome ou do CNPJ"},
    "detalhe_compras": {"tipo": "escolha", "rotulo": "Como agrupar",
                        "ajuda": "por nota", "opcoes": _opcoes_detalhe_compras},
    "motivos": {"tipo": "multipla", "rotulo": "Motivos", "ajuda": "todos os motivos",
                "opcoes": _opcoes_motivos},
    "detalhe_perdas": {"tipo": "escolha", "rotulo": "Como agrupar",
                       "ajuda": "por motivo", "opcoes": _opcoes_detalhe_perdas},
    "formas": {"tipo": "multipla", "rotulo": "Formas de pagamento", "ajuda": "todas",
               "opcoes": _opcoes_formas},
    "detalhe_producao": {"tipo": "escolha", "rotulo": "Como agrupar",
                         "ajuda": "produção a produção", "opcoes": _opcoes_detalhe_producao},
    # ⚠️ O padrão é só a COZINHA: a produção "na hora" é uma por café vendido, e
    # misturada ela soterra o que a cozinha de fato fez.
    "origem_producao": {"tipo": "multipla", "rotulo": "Quais produções",
                        "ajuda": "só as feitas na cozinha", "opcoes": _opcoes_origem_producao},
}


def _lista(valores) -> list | None:
    """Lista vazia e `None` são a mesma coisa: "todos"."""
    if not valores:
        return None
    limpos = [v for v in valores if v is not None and v != ""]
    return limpos or None


def _periodo(f: dict) -> tuple[date, date]:
    hoje = relogio.hoje_da_casa()
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
                  m.custo_medio_apos,
                  CASE WHEN m.custo_provisorio THEN 'sim' END AS provisorio,
                  m.documento, pm.nome AS motivo, m.observacao,
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
              AND (NOT %(provisorio)s OR m.custo_provisorio)
            ORDER BY m.id""",
        # ⚠️ `fim` é dia CHEIO: `<= fim` cortaria o que foi lançado às 14h do
        # próprio dia, porque `data_movimento` guarda data e hora.
        {"unidade": id_unidade, "inicio": inicio, "limite": fim + timedelta(days=1),
         "tipos": _lista(f.get("tipos_movimento")), "locais": _lista(f.get("locais")),
         "produtos": _lista(f.get("produtos")), "busca": f.get("busca") or None,
         "provisorio": bool(f.get("provisorio"))},
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
         # ⚠️ Vazia quando o custo é firme, e não "não": a coluna é um alerta,
         # e uma coluna com 600 "não" e 3 "sim" esconde os três.
         ("provisorio", "Custo provisório"),
         ("documento", "Documento"), ("motivo", "Motivo"), ("observacao", "Observação"),
         ("usuario", "Quem lançou")],
        f"Razão de estoque — {_intervalo(inicio, fim)}",
        [("Movimentos", len(linhas))],
        inicio, fim,
    )


def _produtos(cur, _id_unidade: int, f: dict) -> Saida:
    # ⚠️ O `_` do nome dizia "não uso a loja" — e passou a usar: o preço de venda
    # é resolvido por loja (o dela, caindo para o da casa). O nome fica como
    # está para não mexer na assinatura que o catálogo inteiro compartilha.
    situacao = _lista(f.get("situacao"))
    # ⚠️ **As colunas largas só quando vão para a PLANILHA.** O PDF usa as de sempre, e a
    # prévia (`_previa`) só conta linhas: buscar as quarenta colunas ali levou a prévia de
    # 1 s para 3,4 s numa base de 50 mil produtos — e a janela de exportação esperando.
    largo = f.get("_formato") != "pdf" and not f.get("_previa")
    extras = """, p.nome_curto, p.estoque_maximo, p.controla_validade, p.controla_estoque,
                  p.producao_propria, p.modo_producao,
                  lp.nome AS local_padrao, lv.nome AS local_venda,
                  p.marca, p.peso_liquido, p.peso_bruto, p.cest,
                  p.codigo_pdv, p.integrado_pdv,
                  p.nome_catalogo, p.informacao_adicional,
                  array_to_string(p.restricoes, ', ') AS restricoes,
                  p.custo_referencia, p.custo_referencia_em, p.custo_referencia_origem,
                  p.observacao, fz.fornecedores""" if largo else ""
    juncoes = """
             LEFT JOIN locais_estoque lp ON lp.id = p.id_local_padrao
             LEFT JOIN locais_estoque lv ON lv.id = p.id_local_venda
             -- Agregado UMA vez, não por linha.
             LEFT JOIN (SELECT pf.id_produto,
                               string_agg(f.nome, ' / ' ORDER BY pf.preferencial DESC,
                                          lower(f.nome)) AS fornecedores
                          FROM produto_fornecedor pf
                          JOIN fornecedores f ON f.id = pf.id_fornecedor
                         GROUP BY pf.id_produto) fz ON fz.id_produto = p.id""" if largo else ""
    cur.execute(
        f"""SELECT p.codigo, p.nome AS produto, p.tipo, c.nome AS categoria,
                  s.nome AS setor, p.um_estoque, p.um_compra, p.fator_compra,
                  p.estoque_minimo, p.perecivel, p.validade_dias, p.controla_lote,
                  p.ncm, p.codigo_barras, p.status, p.ativo,
                  (SELECT pp.preco_venda FROM produto_precos pp
                    WHERE pp.id_produto = p.id AND pp.vigente_ate IS NULL
                      AND (pp.id_unidade = %(uni)s OR pp.id_unidade IS NULL)
                    ORDER BY pp.id_unidade NULLS LAST LIMIT 1) AS preco_venda{extras}
             FROM produtos p
             LEFT JOIN categorias c ON c.id = p.id_categoria
             LEFT JOIN setores s ON s.id = p.id_setor{juncoes}
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
         "situacao": situacao, "uni": _id_unidade},
    )
    linhas = [dict(r) for r in cur.fetchall()]
    # 🔑 **Na planilha, TODOS os campos do cadastro** (pedido do dono, 20/10/2026:
    # "listar todos os campos do cadastro, principalmente na planilha"). O PDF fica
    # com os de sempre: quarenta colunas numa folha deitada viram letra de bula.
    # ⚠️ O custo de referência só sai para quem vê custo (`estoque.saldos`) — a mesma
    # regra do `GET /produtos/{id}`: custo é dado de estoque, não de cadastro.
    # ⚠️ **"Todos os campos" é todos os que a TELA mostra** (pedido do dono, 21/10/2026:
    # "alguns internos não precisamos exportar, exemplo é o código no Omie"). Saíram
    # `codigo_omie` (o id interno do Omie, que só serve ao casamento), `um_omie`,
    # `origem` e as datas de cadastro, revisão e sincronização — nenhum aparece nem se
    # edita no cadastro. O código no PDV fica: aparece em "Códigos" e cruza com o PDV.
    # Campo novo na planilha só se a tela do produto também o mostrar.
    resumidas = [
        ("codigo", "Código"), ("produto", "Produto"), ("tipo", "Tipo"),
        ("categoria", "Categoria"), ("setor", "Setor"), ("um_estoque", "Un. estoque"),
        ("um_compra", "Un. compra"), ("fator_compra", "Fator"),
        ("preco_venda", "Preço de venda"), ("estoque_minimo", "Estoque mínimo"),
        ("perecivel", "Perecível"), ("validade_dias", "Validade (dias)"),
        ("controla_lote", "Controla lote"), ("ncm", "NCM"),
        ("codigo_barras", "Código de barras"), ("status", "Situação"), ("ativo", "Ativo")]
    if not largo:
        colunas = resumidas
    else:
        colunas = [
            ("codigo", "Código"), ("produto", "Produto"), ("nome_curto", "Nome curto"),
            ("tipo", "Tipo"), ("categoria", "Categoria"), ("setor", "Setor"),
            ("status", "Situação"), ("ativo", "Ativo"),
            ("um_estoque", "Un. estoque"), ("um_compra", "Un. compra"),
            ("fator_compra", "Fator de compra"),
            ("preco_venda", "Preço de venda"),
            ("controla_estoque", "Controla estoque"), ("producao_propria", "Produção própria"),
            ("modo_producao", "Modo de produção"),
            ("local_padrao", "Local padrão"), ("local_venda", "Local de venda"),
            ("estoque_minimo", "Estoque mínimo"), ("estoque_maximo", "Estoque máximo"),
            ("perecivel", "Perecível"), ("validade_dias", "Validade (dias)"),
            ("controla_validade", "Controla validade"), ("controla_lote", "Controla lote"),
            ("marca", "Marca"), ("peso_liquido", "Peso líquido"), ("peso_bruto", "Peso bruto"),
            ("ncm", "NCM"), ("cest", "CEST"), ("codigo_barras", "Código de barras"),
            ("codigo_pdv", "Código no PDV"), ("integrado_pdv", "Integrado ao PDV"),
            ("fornecedores", "Fornecedores"),
            ("nome_catalogo", "Nome no cardápio"), ("informacao_adicional", "Informação adicional"),
            ("restricoes", "Restrições"),
        ]
        if f.get("_ve_custo"):
            colunas += [("custo_referencia", "Custo de referência"),
                        ("custo_referencia_em", "Custo de referência em"),
                        ("custo_referencia_origem", "Origem do custo de referência")]
        colunas += [("observacao", "Observação")]
    if not f.get("_ve_custo"):
        for linha in linhas:
            for campo in ("custo_referencia", "custo_referencia_em", "custo_referencia_origem"):
                linha.pop(campo, None)
    return Saida(linhas, colunas, "Cadastro de produtos", [("Produtos", len(linhas))])


def _pessoas(cur, _id_unidade: int, f: dict) -> Saida:
    """O cadastro de pessoas, com os recortes da tela (pedido do dono, 20/10/2026).

    ⚠️ Pessoa é da CASA, não da loja (a tabela não tem `id_unidade`) — por isso a
    loja não entra no filtro.
    """
    tipos = _lista(f.get("tipo_pessoa")) or []
    situacoes = _lista(f.get("situacao_pessoa")) or []
    # Os dois marcados, ou nenhum, é "todos" — igual às caixinhas dos outros relatórios.
    so_fornecedor = None if len(set(tipos)) != 1 else (tipos[0] == "fornecedor")
    so_ativas = None if len(set(situacoes)) != 1 else (situacoes[0] == "ativas")
    busca = (f.get("busca_pessoa") or "").strip() or None
    cur.execute(
        """SELECT f.nome, f.nome_fantasia, f.cnpj, f.fornecedor,
                  f.email, f.telefone, f.whatsapp, f.contato, f.cidade, f.uf,
                  f.prazo_entrega_dias, f.dias_entrega, f.pedido_minimo,
                  f.cupom_base, f.cupom_desconto_pct, f.ativo, f.observacao,
                  (SELECT count(*) FROM produto_fornecedor pf
                    WHERE pf.id_fornecedor = f.id) AS produtos,
                  (SELECT max(pf.ultima_compra) FROM produto_fornecedor pf
                    WHERE pf.id_fornecedor = f.id) AS ultima_compra,
                  (SELECT u.nome FROM usuarios u
                    WHERE u.id_pessoa = f.id AND u.ativo LIMIT 1) AS usuario
             FROM fornecedores f
            WHERE (%(forn)s::bool IS NULL OR f.fornecedor = %(forn)s)
              AND (%(ativas)s::bool IS NULL OR f.ativo = %(ativas)s)
              AND (%(busca)s::varchar IS NULL
                   OR lower(f.nome) LIKE lower('%%' || %(busca)s || '%%')
                   OR lower(coalesce(f.nome_fantasia, '')) LIKE lower('%%' || %(busca)s || '%%')
                   OR coalesce(f.cnpj, '') LIKE '%%' || %(busca)s || '%%')
            ORDER BY f.ativo DESC, lower(f.nome)""",
        {"forn": so_fornecedor, "ativas": so_ativas, "busca": busca},
    )
    linhas = [dict(r) for r in cur.fetchall()]
    for linha in linhas:
        linha["tipo"] = "fornecedor" if linha["fornecedor"] else "não fornecedor"
        desconto = float(linha["cupom_desconto_pct"] or 0)
        linha["politica"] = (("pelo custo" if linha["cupom_base"] == "CUSTO" else "preço de venda")
                             + (f", {desconto:g}% de desconto" if desconto else ""))
    # ⚠️ Mesma regra do cadastro de produtos (21/10/2026): só o que a tela mostra. Saíram
    # `codigo_omie` e `criado_em`. O login fica: aparece na tela de Usuários.
    if f.get("_formato") == "pdf":
        colunas = [("nome", "Nome"), ("tipo", "Tipo"), ("cnpj", "CNPJ"),
                   ("telefone", "Telefone"), ("email", "E-mail"), ("cidade", "Cidade"),
                   ("uf", "UF"), ("ativo", "Ativa")]
    else:
        colunas = [("nome", "Nome"), ("nome_fantasia", "Nome fantasia"), ("tipo", "Tipo"),
                   ("cnpj", "CNPJ"), ("ativo", "Ativa"), ("email", "E-mail"),
                   ("telefone", "Telefone"), ("whatsapp", "WhatsApp"), ("contato", "Contato"),
                   ("cidade", "Cidade"), ("uf", "UF"),
                   ("prazo_entrega_dias", "Prazo de entrega (dias)"),
                   ("dias_entrega", "Dias de entrega"), ("pedido_minimo", "Pedido mínimo"),
                   ("politica", "Política do cupom"),
                   ("produtos", "Produtos"), ("ultima_compra", "Última compra"),
                   ("usuario", "Login no sistema"), ("observacao", "Observação")]
    return Saida(
        linhas, colunas, "Cadastro de pessoas",
        [("Pessoas", len(linhas)),
         ("Fornecedores", sum(1 for x in linhas if x["fornecedor"])),
         ("Não fornecedores", sum(1 for x in linhas if not x["fornecedor"]))],
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
        # As partes do consumo interno, pelo motivo do documento (134) — só com mais de
        # uma, senão a parte repete a linha de cima.
        *([{"linha": f"      {p['rotulo']}", "valor": reais(p["valor"])}
           for p in a.get("consumo_por_motivo", [])]
          if len(a.get("consumo_por_motivo", [])) > 1 else []),
        {"linha": "  dos quais: ajustes de inventário", "valor": reais(a["ajustes"])},
        {"linha": "Receita do período", "valor": reais(a["receita"])},
    ]
    return Saida(
        linhas,
        [("linha", "Composição do CMV"), ("valor", "Valor (R$)")],
        f"CMV — {_intervalo(inicio, fim)}",
        [("Food cost", f"{a['food_cost_pct']:.2f}%" if a["food_cost_pct"] else "—"),
         ("Cobertura de ficha", f"{a['cobertura_ficha_pct']:.1f}%"),
         ("Vendas no período", a["vendas"])],
        inicio, fim,
        anexos=_anexo_da_aba(cur, id_unidade, f, inicio, fim),
    )


def _quadro_da_quebra(grupos: list[dict], titulo: str, rotulo_eixo: str) -> tuple:
    """A quebra do CMV como quadro de arquivo — arredondada para ser lida.

    ⚠️ **Dinheiro em centavos e percentual com uma casa, e isto é apresentação.**
    O motor encadeia custo unitário de seis casas, então a linha saía
    `6094,0000000000` e `92,84221351575725` — num arquivo que vai ao contador
    isso não é um valor em reais nem um percentual, é defeito aparente. O
    número da CONTA continua com toda a precisão: quem arredonda é a linha do
    relatório.
    ⚠️ **Num lugar só**: este mesmo quadro é o anexo do relatório de preços
    desde sempre, e lá saía cru. Duas cópias arredondariam diferente no dia em
    que alguém mexesse numa.
    """
    def cem(v) -> Decimal:
        return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    linhas = [
        {**g,
         **{c: cem(g.get(c)) for c in
            ("estoque_inicial", "compras", "estoque_final", "cmv", "perdas")},
         "participacao_pct": Decimal(str(g.get("participacao_pct") or 0)).quantize(
             Decimal("0.1"), rounding=ROUND_HALF_UP)}
        for g in grupos
    ]
    return (linhas,
            [("grupo", rotulo_eixo), ("estoque_inicial", "Estoque inicial"),
             ("compras", "Compras"), ("estoque_final", "Estoque final"),
             ("cmv", "CMV"), ("perdas", "Perdas"), ("produtos", "Produtos"),
             ("participacao_pct", "Participação %")],
            titulo, None)


def _como_anexo(s: "Saida") -> tuple:
    """Uma `Saida` inteira vira o anexo de outra.

    🔑 **É o que impede a duplicação.** As abas do painel já são relatórios
    deste mesmo catálogo — curva ABC, movimentação, preços, memória. Reescrever
    as consultas aqui daria uma segunda versão de cada uma, e elas divergiriam
    na primeira correção feita só de um lado.
    """
    return (s.linhas, s.colunas, s.titulo, None)


def _anexo_da_aba(cur, id_unidade: int, f: dict, inicio: date, fim: date) -> list[tuple]:
    """O quadro da aba em que a pessoa está, atrás da conta do CMV.

    🔑 **Pedido do dono (16/09/2026):** *"este deve baixar os números do CMV,
    abaixo do cabeçalho, e os dados da aba posicionada"*. Eram cinco botões de
    baixar espalhados pelo painel — um no cabeçalho e um por aba — e cada um
    dava um arquivo diferente sem a conta junto. Agora é um só, e o arquivo
    abre pela conta.

    ⚠️ **A margem por prato continua sendo o padrão**, que é o que este
    relatório sempre levou: quem baixa sem passar pelo painel (a URL direta, o
    catálogo) recebe o arquivo do contador como antes.
    """
    aba = (f.get("aba") or "").strip() or "margem"

    if aba == "conta":
        # ⚠️ Nada atrás da conta, e é uma escolha: a aba "A conta" É a
        # composição, e repeti-la como anexo dobraria o mesmo quadro.
        return []

    if aba.startswith("quebra-"):
        eixo = aba.split("-", 1)[1]
        grupos = relatorios.cmv_por_grupo(cur, id_unidade, inicio, fim, eixo)
        titulo = {v: n for v, n in ABAS_DO_PAINEL}.get(aba, "Quebra do CMV")
        return [_quadro_da_quebra(
            grupos, titulo, titulo.replace("Quebra por ", "").capitalize())]

    if aba == "abc":
        return [_como_anexo(_abc(cur, id_unidade, f))]
    if aba == "movimentacao":
        return [_como_anexo(_movimentacao(cur, id_unidade, f))]
    if aba == "precos":
        # ⚠️ O relatório de preços leva um anexo PRÓPRIO (o peso por setor).
        # Aqui entra só a tabela dele: o anexo do anexo se perderia em silêncio,
        # e a conta do CMV já está na frente do arquivo.
        return [_como_anexo(_precos(cur, id_unidade, f))]
    if aba == "memoria":
        m = _memoria_cmv(cur, id_unidade, f)
        return [_como_anexo(m), *m.anexos]

    margem = cmv_motor.margem_por_prato(cur, id_unidade, inicio, fim, 500)
    return [(margem,
             [("produto", "Prato"), ("quantidade", "Vendidos"), ("receita", "Receita"),
              ("custo", "Custo pela ficha"), ("margem", "Margem"),
              ("food_cost_pct", "Food cost %"), ("sem_custo", "Tem item sem custo")],
             "Margem por prato", None)]


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
        anexos=[_quadro_da_quebra(grupos, "Onde o custo pesa (por setor)", "Setor")],
    )


def _precos_pdv(cur, id_unidade: int, _f: dict) -> Saida:
    """O que está com um preço aqui e outro no caixa — para acertar no PDV."""
    from services.pdv import envio  # só aqui: o catálogo não depende do PDV

    cliente, filial = envio.cliente_e_filial(cur, id_unidade)
    r = envio.diferencas_de_preco(cur, id_unidade, cliente, filial)
    # ⚠️ Dinheiro em CENTAVOS no papel: como `float` a coluna saía "4,0" e "3,0",
    # que não é como se escreve um preço — e é uma lista que alguém digita no PDV.
    centavos = Decimal("0.01")
    linhas = [{**l, **{c: Decimal(str(l[c])).quantize(centavos, ROUND_HALF_UP)
                       for c in ("preco_botane", "preco_pdv", "diferenca")}}
              for l in r["linhas"]]
    resumo: list[tuple[str, object]] = [
        ("Preços conferidos", r["conferidos"]),
        ("Diferentes do PDV", len(linhas)),
        ("A subir no PDV", sum(1 for l in linhas if l["diferenca"] > 0)),
        ("A baixar no PDV", sum(1 for l in linhas if l["diferenca"] < 0)),
    ]
    if r["sem_preco_no_pdv"]:
        # ⚠️ Dito no resumo: sem linha na tabela de lá não há o que comparar, e
        # eles NÃO estão na lista — que não pode passar por "tudo conferido".
        resumo.append(("⚠ Sem preço na tabela do PDV", f"{r['sem_preco_no_pdv']} — fora da lista"))
    if r["simulado"]:
        resumo.append(("⚠ PDV em modo simulado", "sem credencial: os preços de lá são de teste"))
    return Saida(
        linhas,
        [("codigo_pdv", "Código no PDV"), ("produto", "Produto"), ("categoria", "Categoria"),
         ("preco_pdv", "Preço no PDV (hoje)"), ("preco_botane", "Preço certo (Botané)"),
         ("diferenca", "Diferença")],
        "Preços a acertar no PDV",
        resumo,
    )


def _saldos_rede(cur, id_unidade: int, f: dict) -> Saida:
    """O estoque da EMPRESA, somando as lojas — uma linha por produto.

    ⚠️ **As lojas vêm no filtro, resolvidas por quem tem o contexto.** Este
    módulo não conhece `ve_unidade`, e inventar a lista aqui somaria estoque de
    loja que a pessoa não pode consultar — vazando pelo total.
    ⚠️ A prateleira sai da linha, como na tela: aqui a pergunta é quanto a REDE
    tem de cada item.
    """
    lojas = _lista(f.get("_lojas")) or [id_unidade]
    cur.execute(
        """SELECT p.codigo, p.nome AS produto, c.nome AS categoria, p.um_estoque,
                  sum(s.quantidade) AS quantidade,
                  -- 🔑 Ponderado, nunca a média dos médios — e com o MESMO
                  -- recorte da cascata (`quantidade > 0 AND custo_medio > 0`),
                  -- senão o arquivo discorda da ficha como a tela discordava.
                  CASE WHEN sum(s.quantidade) FILTER (
                            WHERE s.quantidade > 0 AND s.custo_medio > 0) > 0
                       THEN round(sum(s.quantidade * s.custo_medio) FILTER (
                                       WHERE s.quantidade > 0 AND s.custo_medio > 0)
                                  / sum(s.quantidade) FILTER (
                                       WHERE s.quantidade > 0 AND s.custo_medio > 0), 6)
                       END AS custo_medio,
                  round(sum(s.quantidade * s.custo_medio), 2) AS valor,
                  p.estoque_minimo,
                  count(DISTINCT s.id_unidade) AS lojas
             FROM estoque_saldos s
             JOIN produtos p ON p.id = s.id_produto
             LEFT JOIN categorias c ON c.id = p.id_categoria
            WHERE s.id_unidade = ANY(%(lojas)s) AND p.ativo
              AND (%(setores)s::int[] IS NULL OR p.id_setor = ANY(%(setores)s))
              AND (%(categorias)s::int[] IS NULL OR p.id_categoria = ANY(%(categorias)s))
              AND (%(tipos)s::varchar[] IS NULL OR p.tipo = ANY(%(tipos)s))
              AND (%(produtos)s::int[] IS NULL OR s.id_produto = ANY(%(produtos)s))
            GROUP BY p.codigo, p.nome, c.nome, p.um_estoque, p.estoque_minimo
           HAVING sum(s.quantidade) <> 0
            ORDER BY lower(p.nome)""",
        {"lojas": lojas, "setores": _lista(f.get("setores")),
         "categorias": _lista(f.get("categorias")),
         "tipos": _lista(f.get("tipos_produto")), "produtos": _lista(f.get("produtos"))},
    )
    linhas = [dict(r) for r in cur.fetchall()]
    total = sum(float(l["valor"] or 0) for l in linhas)
    return Saida(
        linhas,
        [("codigo", "Código"), ("produto", "Produto"), ("categoria", "Categoria"),
         ("um_estoque", "Unidade"), ("quantidade", "Saldo da rede"),
         ("custo_medio", "Custo médio ponderado"), ("valor", "Valor em estoque"),
         ("lojas", "Em quantas lojas"), ("estoque_minimo", "Estoque mínimo")],
        "Posição de estoque da rede",
        [("Produtos", len(linhas)), ("Lojas somadas", len(lojas)),
         ("Valor total em estoque", round(total, 2))],
    )


@dataclass(frozen=True)
class Relatorio:
    rotulo: str
    descricao: str
    permissao: str
    base: str
    filtros: tuple[str, ...]
    montar: Callable[..., Saida]


def _em_reais(linhas: list[dict]) -> list[dict]:
    """Dinheiro em CENTAVOS, custo unitário com as seis casas que ele tem.

    ⚠️ **Arredondamento de APRESENTAÇÃO, e quem arredonda é a linha do
    relatório — nunca o motor.** A composição do estoque encadeia custo unitário
    de 6 casas, e o valor da linha saía como `100,0000000000`: isso não é um
    valor em reais, e num documento que vai para a contabilidade parece defeito.
    O número da CONTA continua com toda a precisão.

    ⚠️ **O custo unitário NÃO vai a centavos.** Ele é um PREÇO (R$ por KG), e
    arredondá-lo faria `quantidade × custo` deixar de reproduzir o valor da
    linha — que é justamente o que o contador refaz na calculadora.
    """
    saida = []
    for l in linhas:
        saida.append({
            **l,
            "valor": Decimal(str(l["valor"])).quantize(Decimal("0.01"), ROUND_HALF_UP),
            "custo_unitario": Decimal(str(l["custo_unitario"])).quantize(
                Decimal("0.000001"), ROUND_HALF_UP),
        })
    return saida


def _fecha(linhas: list[dict], campo: str, autorizado) -> list[tuple]:
    """O rodapé do quadro: o que a coluna soma, e o número da apuração ao lado.

    🔑 **Os dois aparecem de propósito.** O total do quadro soma as linhas
    ARREDONDADAS, porque é ele que fecha com a coluna que alguém confere à mão;
    o número da apuração é o AUTORIZADO, o mesmo do painel e do fechamento. Em
    centenas de linhas os dois podem diferir em centavos, e esconder um dos dois
    seria pior: ou o contador soma a coluna e não bate, ou ele bate com o painel
    e a coluna não soma. Vendo os dois, a diferença tem nome — arredondamento.
    """
    somado = sum((Decimal(str(l[campo] or 0)) for l in linhas), Decimal(0))
    resumo = [("Total do quadro (soma da coluna)",
               somado.quantize(Decimal("0.01"), ROUND_HALF_UP))]
    if autorizado is not None:
        resumo.append(("Linha da apuração",
                       Decimal(str(autorizado)).quantize(Decimal("0.01"), ROUND_HALF_UP)))
    return resumo


def _esta_fechado(cur, id_unidade: int, inicio: date, fim: date) -> bool:
    cur.execute(
        """SELECT 1 FROM cmv_fechamentos
            WHERE id_unidade = %s AND inicio = %s AND fim = %s AND status = 'FECHADO'""",
        (id_unidade, inicio, fim),
    )
    return cur.fetchone() is not None


def _memoria_cmv(cur, id_unidade: int, f: dict) -> Saida:
    """A apuração ABERTA nos documentos que a compõem — a memória de cálculo.

    🔑 **Pedido da contabilidade (02/09/2026).** A apuração dizia o resultado em
    dez linhas e não dizia de ONDE cada linha veio. Perguntado "estes R$ X de
    compras, de quais notas são?", o sistema não tinha resposta.

    O documento tem quatro quadros, e cada um FECHA com a linha que explica:
    o estoque inicial item a item, as compras por nota, o estoque final item a
    item, e a conciliação que leva da soma das notas até a linha "Compras".

    ⚠️ **Os quadros vão como ANEXOS do mesmo arquivo, não em quatro arquivos.**
    Eles só se leem juntos: separados, quem recebe teria de juntar de novo — e o
    contador confere um contra o outro. Mesma razão do relatório do contador.
    """
    inicio, fim = _periodo(f)
    a = cmv_motor.apurar(cur, id_unidade, inicio, fim)
    fora = cmv_motor.tipos_fora_do_cmv(cur)
    vespera = inicio - timedelta(days=1)

    def reais(v) -> Decimal:
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    principal = [
        {"linha": f"Estoque inicial (posição em {vespera.strftime('%d/%m/%Y')})",
         "valor": reais(a["estoque_inicial"]), "quadro": "quadro 1"},
        {"linha": "(+) Compras do período", "valor": reais(a["compras"]),
         "quadro": "quadros 2 e 4"},
        {"linha": f"(−) Estoque final (posição em {fim.strftime('%d/%m/%Y')})",
         "valor": reais(-a["estoque_final"]), "quadro": "quadro 3"},
        {"linha": "(=) CMV real do período", "valor": reais(a["cmv_real"]), "quadro": ""},
    ]

    inicial = _em_reais(memoria.estoque_em(cur, id_unidade, vespera, fora))
    final = _em_reais(memoria.estoque_em(cur, id_unidade, fim, fora))
    notas = memoria.compras_por_nota(cur, id_unidade, inicio, fim, fora)
    concilia = memoria.conciliacao_compras(cur, id_unidade, inicio, fim, fora)

    colunas_estoque = [
        ("codigo", "Código"), ("produto", "Produto"), ("um_estoque", "Un."),
        ("categoria", "Categoria"), ("quantidade", "Quantidade"),
        ("custo_unitario", "Custo unitário"), ("valor", "Valor (R$)"),
    ]
    return Saida(
        principal,
        [("linha", "Composição do CMV"), ("valor", "Valor (R$)"),
         ("quadro", "Aberto em")],
        f"Memória de cálculo do CMV — {_intervalo(inicio, fim)}",
        [("Método de custeio", "custo médio ponderado móvel"),
         ("Produtos no estoque inicial", len(inicial)),
         ("Documentos de compra", len(notas)),
         ("Produtos no estoque final", len(final)),
         # ⚠️ **Período fechado é o que se manda ao contador**: aberto, o número
         # ainda pode mudar depois de o arquivo sair da casa. É a mesma frase do
         # relatório de movimentação, e pela mesma razão — só que aqui ela pesa
         # mais, porque este documento é o que se assina embaixo.
         ("Situação do período",
          "fechado (congelado)" if _esta_fechado(cur, id_unidade, inicio, fim)
          else "aberto — o número ainda pode mudar")],
        inicio, fim,
        anexos=[
            (inicial, colunas_estoque,
             f"Quadro 1 — Estoque inicial, item a item (posição em "
             f"{vespera.strftime('%d/%m/%Y')})",
             _fecha(inicial, "valor", a["estoque_inicial"])),
            (notas,
             [("documento", "Documento"), ("fornecedor", "Fornecedor"),
              ("data_entrada", "Entrada"), ("itens", "Itens"),
              ("valor_da_nota", "Total da nota (R$)"),
              ("valor_frete", "Frete (R$)"), ("valor_outros", "IPI/ST (R$)"),
              ("valor_no_razao", "Entrou no estoque (R$)"),
              ("diferenca", "Diferença (R$)")],
             "Quadro 2 — Compras do período, por documento",
             # ⚠️ Este quadro NÃO fecha com a linha "Compras", e é de propósito:
             # falta a remessa entre lojas, que é compra do destino sem nota. O
             # rodapé manda para o quadro 4 em vez de deixar a diferença solta.
             _fecha(notas, "valor_no_razao", None)
             + [("A linha “Compras” da apuração", "ver o quadro 4")]),
            (final, colunas_estoque,
             f"Quadro 3 — Estoque final, item a item (posição em "
             f"{fim.strftime('%d/%m/%Y')})",
             _fecha(final, "valor", a["estoque_final"])),
            (concilia, [("linha", "Da soma das notas até a linha Compras"),
                        ("valor", "Valor (R$)")],
             "Quadro 4 — Conciliação: por que a soma das notas não é a linha Compras",
             None),
        ],
    )


def _inventario(cur, id_unidade: int, f: dict) -> Saida:
    """O estoque valorizado NUMA DATA — o documento do balanço.

    ⚠️ **Uma data, não um período.** A pergunta é "quanto valia o estoque em
    31/12", e ela tem uma resposta só.

    ⚠️ **Sai do mesmo lugar que a apuração**, inclusive no atalho de hoje: se
    esta lista somasse diferente da linha "Estoque final", o documento estaria
    contradizendo o número que ele existe para compor.
    """
    ate = f.get("data") or relogio.hoje_da_casa()
    # ⚠️ **SEM tirar os tipos fora do CMV.** Aquele filtro é da conta do custo da
    # comida; o inventário do balanço é o que a casa POSSUI, e detergente em
    # estoque é patrimônio igual. Misturar as duas perguntas faria o balanço
    # declarar menos do que existe.
    linhas = _em_reais(memoria.estoque_em(cur, id_unidade, ate, None))
    # ⚠️ **Soma as linhas ARREDONDADAS**, não o valor exato: é o total que a
    # pessoa confere somando a coluna com o dedo, e um rodapé que não fecha com
    # a própria coluna é pior que centavo nenhum de diferença.
    total = sum((Decimal(str(l["valor"])) for l in linhas), Decimal(0))
    return Saida(
        linhas,
        [("codigo", "Código"), ("produto", "Produto"), ("um_estoque", "Un."),
         ("categoria", "Categoria"), ("setor", "Setor"), ("quantidade", "Quantidade"),
         ("custo_unitario", "Custo unitário"), ("valor", "Valor (R$)")],
        f"Inventário valorizado — posição em {ate.strftime('%d/%m/%Y')}",
        [("Método de custeio", "custo médio ponderado móvel"),
         ("Itens com saldo", len(linhas)),
         ("Valor total (R$)", total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
         ("Abrangência", "todos os tipos de produto, inclusive os que ficam fora do CMV")],
        ate, ate,
    )


def _memoria_produto(cur, id_unidade: int, f: dict) -> Saida:
    """Um insumo, movimento a movimento, com a CONTA do custo médio à vista.

    🔑 É a resposta para *"como você chegou nesse custo unitário?"*. O razão já
    guardava o saldo e o médio depois de cada movimento; o que faltava era
    mostrar a aritmética entre um e outro, para o número deixar de aparecer
    pronto e passar a se conferir na calculadora.
    """
    inicio, fim = _periodo(f)
    escolhidos = _lista(f.get("produtos"))
    if not escolhidos:
        return Saida(
            [], [("aviso", "")],
            f"Memória de cálculo por produto — {_intervalo(inicio, fim)}",
            [("Escolha um produto", "esta memória segue UM insumo de cada vez")],
            inicio, fim,
        )

    id_produto = int(escolhidos[0])
    cur.execute("SELECT codigo, nome, um_estoque FROM produtos WHERE id = %s", (id_produto,))
    p = cur.fetchone() or {}
    linhas = memoria.memoria_do_produto(cur, id_unidade, id_produto, inicio, fim)
    abertura, fechamento = linhas[0], linhas[-1]
    return Saida(
        linhas,
        [("data", "Data"), ("movimento", "Movimento"), ("local", "Local"),
         ("documento", "Documento"), ("quantidade", "Quantidade"),
         ("custo_unitario", "Custo unitário"), ("valor", "Valor (R$)"),
         ("saldo_apos", "Saldo depois"), ("custo_medio_apos", "Custo médio depois"),
         ("conta", "Como o custo médio foi obtido")],
        f"Memória de cálculo — {p.get('nome', '')} — {_intervalo(inicio, fim)}",
        [("Produto", f"{p.get('codigo', '')} — {p.get('nome', '')}"),
         ("Unidade de estoque", p.get("um_estoque") or "—"),
         ("Método de custeio", "custo médio ponderado móvel"),
         ("Saldo de abertura", abertura["quantidade"]),
         ("Custo médio de abertura", abertura["custo_medio_apos"]),
         ("Saldo de fechamento", fechamento["quantidade"]),
         ("Custo médio de fechamento", fechamento["custo_medio_apos"])],
        inicio, fim,
    )


def _nome_do_recorte(situacao: str, de: date | None, ate: date | None) -> str:
    """Como o recorte se chama no cabecalho do arquivo.

    ⚠️ O arquivo entregue ao funcionario precisa DIZER do que ele fala. Sem
    isso, dois arquivos diferentes sao indistinguiveis depois de salvos -- e a
    conversa vira "mas eu ja paguei esse".
    """
    nome = SITUACOES_CONSUMO.get(situacao, situacao).split(" — ")[0].lower()
    if de and ate:
        return f"{nome}, de {_intervalo(de, ate)}"
    if ate:
        return f"{nome}, até {ate.strftime('%d/%m/%Y')}"
    if de:
        return f"{nome}, desde {de.strftime('%d/%m/%Y')}"
    return nome


def _consumo_pessoa(cur, id_unidade: int, f: dict) -> Saida:
    """O que cada pessoa consumiu e quanto teve de desconto — o documento da cobrança.

    ⚠️ **A consulta é a MESMA da tela** (`services.consumo_pessoa`). Repetir o
    SQL aqui faria a tela mostrar um valor e o arquivo entregue ao funcionário
    mostrar outro, e a diferença apareceria numa discussão sobre dinheiro.
    """
    pessoas = _lista(f.get("pessoas"))
    # ⚠️ Um documento por arquivo: sintético e analítico respondem perguntas
    # diferentes, e juntá-los faria quem recebe separar de novo.
    detalhe = (_lista(f.get("detalhe")) or ["sintetico"])[0]
    # 🔑 **O LOTE (interno, `_lote`) manda sobre tudo**: é o documento da cobrança
    # mandado à pessoa, e recorta pelo lote, não por data nem situação.
    lote = f.get("_lote")
    if lote:
        filtro = {"id_lote": lote["id"]}
        nome_recorte = receber_motor.rotulo(lote)
        pessoas = None
    else:
        # ⚠️ Não escolher nada e escolher "em aberto" dão o MESMO arquivo, senão o
        # padrão da janela responderia uma pergunta que ninguém fez.
        situacao = f.get("situacao_consumo") or "aberto"
        if situacao not in SITUACOES_CONSUMO:
            situacao = "aberto"
        de, ate = f.get("inicio"), f.get("fim")
        filtro = {"situacao": situacao, "de": de, "ate": ate}
        nome_recorte = _nome_do_recorte(situacao, de, ate)
    linhas = consumo_motor.apurar(
        cur, id_unidade, filtro,
        [int(p) for p in pessoas] if pessoas else None, detalhe)

    # ⚠️ Os totais saem das linhas ANTES de achatar: no "com os itens" cada cupom
    # vira cabeçalho + itens, e somar as linhas achatadas contaria tudo duas vezes.
    cheio = sum(float(l["total_cheio"] or 0) for l in linhas)
    total = sum(float(l["total"] or 0) for l in linhas)
    nomes = {"sintetico": "sintético", "analitico": "analítico",
             "documento": "por documento", "documento_itens": "por documento com itens"}

    if detalhe == "documento":
        colunas = [("data", "Data"), ("documento", "Documento"), ("pessoa", "Pessoa"),
                   ("itens", "Itens"), ("total_cheio", "Valor cheio"),
                   ("desconto", "Desconto"), ("total", "A cobrar")]
    elif detalhe == "documento_itens":
        # 🔑 O cupom é a linha de GRUPO (negrito, com fundo no PDF) e os itens vêm
        # embaixo, recuados — `_estilo` é lido por `exportacao.pdf_de`.
        achatadas = []
        for d in linhas:
            achatadas.append({
                "_estilo": "grupo", "data": d["data"], "documento": d["documento"] or "—",
                "descricao": d["pessoa"], "quantidade": d["itens"],
                "total_cheio": d["total_cheio"], "desconto": d["desconto"],
                "total": d["total"]})
            for i in d["itens_do_documento"]:
                achatadas.append({
                    "_estilo": "item",
                    "descricao": (i["produto"] or "—")
                                 + (f" ({i['produto_codigo']})" if i["produto_codigo"] else ""),
                    "quantidade": i["quantidade"], "unitario": i["unitario"],
                    "total_cheio": i["total_cheio"], "desconto": i["desconto"],
                    "total": i["total"]})
        linhas = achatadas
        colunas = [("data", "Data"), ("documento", "Documento"),
                   ("descricao", "Pessoa / Produto"), ("quantidade", "Qtd"),
                   ("unitario", "Cobrado un."), ("total_cheio", "Cheio"),
                   ("desconto", "Desconto"), ("total", "A cobrar")]
    elif detalhe == "analitico":
        colunas = [("data", "Data"), ("documento", "Documento"), ("pessoa", "Pessoa"),
                   ("produto_codigo", "Código"), ("produto", "Produto"),
                   ("quantidade", "Quantidade"), ("unitario_cheio", "Preço cheio"),
                   ("unitario", "Cobrado"), ("total_cheio", "Total cheio"),
                   ("desconto", "Desconto"), ("total", "Total cobrado")]
    else:
        colunas = [("pessoa", "Pessoa"), ("cupons", "Cupons"), ("itens", "Itens"),
                   ("total_cheio", "Valor cheio"), ("desconto", "Desconto"),
                   ("total", "A cobrar")]

    return Saida(
        linhas, colunas,
        (f"{nome_recorte} — {nomes.get(detalhe, detalhe)}" if lote else
         f"Consumo por pessoa — {nome_recorte} — {nomes.get(detalhe, detalhe)}"),
        [("Valor cheio", round(cheio, 2)),
         ("Desconto", round(cheio - total, 2)),
         ("A cobrar", round(total, 2))]
        + ([("Situação", receber_motor.SITUACOES.get(lote["status"], lote["status"]))]
           + ([("Recebido em", lote["recebido_em"].strftime("%d/%m/%Y")),
               ("Forma", receber_motor.FORMAS.get(lote["forma_pagamento"] or "", "—"))]
              if lote["status"] == "RECEBIDO" else [])
           if lote else []),
    )


def _vendas(cur, id_unidade: int, f: dict) -> Saida:
    """O estudo de vendas — o mesmo recorte da tela, em arquivo.

    🔑 **A conta é a da TELA** (`painel_vendas.painel`): o arquivo baixado tem de
    bater com o painel de onde ele saiu, número a número.
    O quadro da frente são os PRODUTOS, todos (a tela mostra os primeiros); a
    evolução, o dia da semana, a hora, a categoria e o setor vão atrás.
    """
    inicio, fim = _periodo(f)
    p = painel_vendas.painel(
        cur, id_unidade, inicio, fim, (f.get("agrupar") or "dia"),
        _lista(f.get("categorias")), _lista(f.get("setores")), _lista(f.get("produtos")),
        "receita", 5000)
    t, c = p["totais"], p["comparacao"]

    def r2(v):
        return None if v is None else round(v, 2)

    def pct(v):
        return "—" if v is None else f"{v:+.1f}%".replace(".", ",")

    produtos = [{**l, "receita": r2(l["receita"]), "preco_medio": r2(l["preco_medio"])}
                for l in p["produtos"]]
    nome_ag = painel_vendas.AGRUPAMENTOS[p["agrupar"]]
    serie = [{**s, "receita": r2(s["receita"]), "ticket_medio": r2(s["ticket_medio"])}
             for s in p["serie"]]
    semana = [{**s, "receita": r2(s["receita"]), "media_receita": r2(s["media_receita"]),
               "media_cupons": round(s["media_cupons"], 1)} for s in p["por_dia_semana"]]
    horas = [{"hora": f"{h['hora']:02d}h", "cupons": h["cupons"], "receita": r2(h["receita"])}
             for h in p["por_hora"]]
    if p["sem_hora"]:
        horas.append({"hora": "sem hora (digitada)", "cupons": p["sem_hora"]["cupons"],
                      "receita": r2(p["sem_hora"]["receita"])})
    grupo = [("nome", "Nome"), ("cupons", "Cupons"), ("quantidade", "Quantidade"),
             ("receita", "Receita"), ("participacao_pct", "Participação %")]

    resumo = [("Cupons", t["cupons"]), ("Dias com venda", t["dias"]),
              ("Itens", t["itens"]),
              ("Receita bruta dos itens" if p["bruta"] else "Receita líquida", r2(t["receita"])),
              ("Ticket médio", r2(t["ticket_medio"])),
              ("Média por dia", r2(t["media_por_dia"]))]
    if t["desconto"] is not None:
        resumo.insert(3, ("Desconto dos cupons", r2(t["desconto"])))
    resumo.append((f"Contra {c['rotulo']} ({_intervalo(c['inicio'], c['fim'])})",
                   f"receita {pct(c['pct_receita'])} · cupons {pct(c['pct_cupons'])} · "
                   f"ticket {pct(c['pct_ticket'])}"))
    if p["canceladas"]:
        resumo += [("Cupons cancelados (fora das somas)", p["canceladas"]["cupons"]),
                   ("Valor dos cancelados", r2(p["canceladas"]["valor"]))]

    return Saida(
        produtos,
        [("codigo", "Código"), ("produto", "Produto"), ("categoria", "Categoria"),
         ("setor", "Setor"), ("quantidade", "Quantidade"), ("cupons", "Cupons"),
         ("receita", "Receita"), ("preco_medio", "Preço médio"),
         ("participacao_pct", "Participação %")],
        f"Vendas — {_intervalo(inicio, fim)}"
        + (" — recorte (receita bruta dos itens)" if p["bruta"] else ""),
        resumo, inicio, fim,
        anexos=[
            (serie, [("periodo", nome_ag), ("cupons", "Cupons"), ("itens", "Itens"),
                     ("receita", "Receita"), ("ticket_medio", "Ticket médio")],
             f"Evolução por {nome_ag.lower()}", None),
            (semana, [("nome", "Dia da semana"), ("dias", "Dias com venda"),
                      ("cupons", "Cupons"), ("receita", "Receita"),
                      ("media_receita", "Receita média por dia"),
                      ("media_cupons", "Cupons por dia")],
             "Por dia da semana", None),
            (horas, [("hora", "Hora"), ("cupons", "Cupons"), ("receita", "Receita")],
             "Por hora do cupom", None),
            (p["por_categoria"], grupo, "Por categoria", None),
            (p["por_setor"], grupo, "Por setor", None),
        ],
    )


def _situacoes_nota(f: dict) -> list[str]:
    """Situação escolhida → status do banco. Sem escolha: tudo menos cancelada."""
    escolhidas = _lista(f.get("situacao_nota")) or ["lancada", "pendente"]
    status = []
    if "lancada" in escolhidas:
        status.append("LANCADA")
    if "pendente" in escolhidas:
        status += ["IMPORTADA", "CONCILIADA"]
    if "cancelada" in escolhidas:
        status.append("CANCELADA")
    return status or ["LANCADA", "IMPORTADA", "CONCILIADA"]


_ROTULO_STATUS_NOTA = {"LANCADA": "lançada", "IMPORTADA": "importada",
                       "CONCILIADA": "conciliada", "CANCELADA": "cancelada"}


def _compras(cur, id_unidade: int, f: dict) -> Saida:
    """O que se comprou no período: por nota, por fornecedor, por produto ou item a item.

    🔑 **A data é a de ENTRADA da nota (ou a de emissão, se não houver)** — a mesma
    régua de `memoria_calculo.conciliacao_compras`. Com outra, o total deste
    relatório e a linha "Compras" da memória do CMV discordariam por notas na
    virada do mês, e a conversa com o contador começaria pela diferença errada.
    ⚠️ **O custo do item é o que ENTRA no estoque**: valor − desconto + frete e
    outros rateados. É o que o custo médio usa; o valor de tabela da nota sozinho
    faria o fornecedor do frete caro parecer o mais barato.
    """
    inicio, fim = _periodo(f)
    detalhe = f.get("detalhe_compras") or "nota"
    if detalhe not in DETALHES_COMPRAS:
        detalhe = "nota"
    status = _situacoes_nota(f)
    busca = (f.get("busca_fornecedor") or "").strip() or None
    params = {"u": id_unidade, "inicio": inicio, "limite": fim + timedelta(days=1),
              "status": status, "busca": f"%{busca}%" if busca else None,
              "categorias": _lista(f.get("categorias")), "setores": _lista(f.get("setores"))}
    filtro_nota = """n.id_unidade = %(u)s AND n.status = ANY(%(status)s)
              AND coalesce(n.data_entrada, n.data_emissao) >= %(inicio)s
              AND coalesce(n.data_entrada, n.data_emissao) < %(limite)s
              AND (%(busca)s::text IS NULL
                   OR coalesce(fo.nome, n.nome_emitente) ILIKE %(busca)s
                   OR coalesce(n.cnpj_emitente, '') ILIKE %(busca)s)"""
    # ⚠️ Categoria e setor são do PRODUTO: só valem nas visões por item. Na nota e no
    # fornecedor eles cortariam metade de uma nota e o total deixaria de ser o dela.
    filtro_item = """(%(categorias)s::int[] IS NULL OR p.id_categoria = ANY(%(categorias)s))
              AND (%(setores)s::int[] IS NULL OR p.id_setor = ANY(%(setores)s))"""
    custo_item = ("(i.valor_total - i.valor_desconto + i.valor_frete_rateado "
                  "+ i.valor_outros_rateado)")

    if detalhe == "nota":
        cur.execute(
            f"""SELECT coalesce(n.data_entrada, n.data_emissao) AS data,
                       n.numero, n.serie, coalesce(fo.nome, n.nome_emitente) AS fornecedor,
                       n.cnpj_emitente AS cnpj, n.status, n.origem,
                       (SELECT count(*) FROM nota_itens i WHERE i.id_nota = n.id) AS itens,
                       n.valor_produtos, n.valor_desconto, n.valor_frete, n.valor_outros,
                       n.valor_total
                  FROM notas_entrada n
                  LEFT JOIN fornecedores fo ON fo.id = n.id_fornecedor
                 WHERE {filtro_nota}
                 ORDER BY 1, n.numero""", params)
        linhas = [{**dict(r), "status": _ROTULO_STATUS_NOTA.get(r["status"], r["status"]),
                   "nota": (f"{r['numero']}" + (f"/{r['serie']}" if r["serie"] else "")
                            if r["numero"] else "—")}
                  for r in cur.fetchall()]
        colunas = [("data", "Entrada"), ("nota", "Nota"), ("fornecedor", "Fornecedor"),
                   ("cnpj", "CNPJ"), ("status", "Situação"), ("itens", "Itens"),
                   ("valor_produtos", "Produtos"), ("valor_desconto", "Desconto"),
                   ("valor_frete", "Frete"), ("valor_outros", "Outros (IPI, ST)"),
                   ("valor_total", "Total da nota")]
        total = sum((Decimal(str(l["valor_total"] or 0)) for l in linhas), Decimal(0))
        resumo = [("Notas", len(linhas)), ("Total das notas", total),
                  ("Fornecedores", len({l["fornecedor"] for l in linhas}))]
    elif detalhe == "fornecedor":
        cur.execute(
            f"""SELECT coalesce(fo.nome, n.nome_emitente) AS fornecedor,
                       max(n.cnpj_emitente) AS cnpj, count(*) AS notas,
                       sum(n.valor_total) AS total,
                       max(coalesce(n.data_entrada, n.data_emissao)) AS ultima
                  FROM notas_entrada n
                  LEFT JOIN fornecedores fo ON fo.id = n.id_fornecedor
                 WHERE {filtro_nota}
                 GROUP BY 1
                 ORDER BY sum(n.valor_total) DESC""", params)
        linhas = [dict(r) for r in cur.fetchall()]
        total = sum((Decimal(str(l["total"] or 0)) for l in linhas), Decimal(0))
        for l in linhas:
            l["media"] = (Decimal(str(l["total"])) / l["notas"]).quantize(Decimal("0.01"))
            l["participacao"] = (Decimal(str(l["total"] or 0)) * 100 / total
                                 ).quantize(Decimal("0.01")) if total else None
        colunas = [("fornecedor", "Fornecedor"), ("cnpj", "CNPJ"), ("notas", "Notas"),
                   ("total", "Total comprado"), ("participacao", "% do total"),
                   ("media", "Média por nota"), ("ultima", "Última compra")]
        resumo = [("Fornecedores", len(linhas)), ("Notas", sum(l["notas"] for l in linhas)),
                  ("Total das notas", total)]
    elif detalhe == "produto":
        cur.execute(
            f"""SELECT coalesce(p.codigo, '') AS codigo,
                       coalesce(p.nome, i.descricao_fornecedor || ' (sem produto)') AS produto,
                       c.nome AS categoria,
                       coalesce(p.um_estoque, i.um_nota) AS um,
                       sum(coalesce(i.quantidade_convertida, i.quantidade)) AS quantidade,
                       sum({custo_item}) AS custo,
                       min(i.custo_aquisicao_unitario) AS menor_unitario,
                       max(i.custo_aquisicao_unitario) AS maior_unitario,
                       count(DISTINCT n.id) AS notas,
                       count(DISTINCT coalesce(fo.nome, n.nome_emitente)) AS fornecedores
                  FROM nota_itens i
                  JOIN notas_entrada n ON n.id = i.id_nota
                  LEFT JOIN fornecedores fo ON fo.id = n.id_fornecedor
                  LEFT JOIN produtos p ON p.id = i.id_produto
                  LEFT JOIN categorias c ON c.id = p.id_categoria
                 WHERE {filtro_nota} AND {filtro_item}
                 GROUP BY 1, 2, 3, 4
                 ORDER BY sum({custo_item}) DESC""", params)
        linhas = [dict(r) for r in cur.fetchall()]
        for l in linhas:
            q = Decimal(str(l["quantidade"] or 0))
            l["medio"] = (Decimal(str(l["custo"] or 0)) / q).quantize(Decimal("0.000001")) if q else None
        colunas = [("codigo", "Código"), ("produto", "Produto"), ("categoria", "Categoria"),
                   ("quantidade", "Quantidade"), ("um", "Unidade"), ("custo", "Custo total"),
                   ("medio", "Custo médio"), ("menor_unitario", "Menor unitário"),
                   ("maior_unitario", "Maior unitário"), ("notas", "Notas"),
                   ("fornecedores", "Fornecedores")]
        total = sum((Decimal(str(l["custo"] or 0)) for l in linhas), Decimal(0))
        resumo = [("Produtos", len(linhas)), ("Custo total dos itens", total)]
    else:
        cur.execute(
            f"""SELECT coalesce(n.data_entrada, n.data_emissao) AS data,
                       n.numero AS nota, coalesce(fo.nome, n.nome_emitente) AS fornecedor,
                       i.descricao_fornecedor AS na_nota, p.codigo, p.nome AS produto,
                       i.quantidade, i.um_nota, i.valor_unitario, i.valor_total,
                       i.valor_desconto,
                       (i.valor_frete_rateado + i.valor_outros_rateado) AS frete_outros,
                       {custo_item} AS custo,
                       i.quantidade_convertida, p.um_estoque, i.custo_aquisicao_unitario,
                       i.variacao_preco_pct
                  FROM nota_itens i
                  JOIN notas_entrada n ON n.id = i.id_nota
                  LEFT JOIN fornecedores fo ON fo.id = n.id_fornecedor
                  LEFT JOIN produtos p ON p.id = i.id_produto
                 WHERE {filtro_nota} AND {filtro_item}
                 ORDER BY 1, n.numero, i.seq""", params)
        linhas = [dict(r) for r in cur.fetchall()]
        colunas = [("data", "Entrada"), ("nota", "Nota"), ("fornecedor", "Fornecedor"),
                   ("na_nota", "Descrição na nota"), ("codigo", "Código"),
                   ("produto", "Produto"), ("quantidade", "Qtd na nota"), ("um_nota", "Un."),
                   ("valor_unitario", "Unitário"), ("valor_total", "Valor"),
                   ("valor_desconto", "Desconto"), ("frete_outros", "Frete e outros"),
                   ("custo", "Custo"), ("quantidade_convertida", "Qtd em estoque"),
                   ("um_estoque", "Un. estoque"), ("custo_aquisicao_unitario", "Custo un."),
                   ("variacao_preco_pct", "Variação %")]
        total = sum((Decimal(str(l["custo"] or 0)) for l in linhas), Decimal(0))
        resumo = [("Itens", len(linhas)), ("Custo total dos itens", total)]

    escolhidas = ", ".join(SITUACOES_NOTA[s].split(" (")[0].lower()
                           for s in (_lista(f.get("situacao_nota")) or ["lancada", "pendente"])
                           if s in SITUACOES_NOTA)
    resumo.append(("Notas consideradas", escolhidas))
    if busca:
        resumo.append(("Fornecedor contém", busca))
    return Saida(linhas, colunas,
                 f"Compras — {_intervalo(inicio, fim)} — {DETALHES_COMPRAS[detalhe].split(' — ')[0].lower()}",
                 resumo, inicio, fim)


_TIPOS_PERDA = ("SAIDA_PERDA", "AJUSTE_INVENTARIO_SAIDA", "AJUSTE_INVENTARIO_ENTRADA")
_ORIGEM_PERDA = {"ETIQUETA": "etiqueta", "MANUAL": "lançada à mão", "REMESSA": "remessa",
                 "INVENTARIO": "inventário", "AJUSTE_LOTE": "ajuste de saldo"}


def _perdas(cur, id_unidade: int, f: dict) -> Saida:
    """Quanto se perdeu no período, e por quê — perdas, inventário e ajustes de saldo.

    🔑 **A conta é LÍQUIDA**: a sobra de inventário (ajuste de entrada) entra
    negativa, e o estorno de uma perda devolve o que ela tinha tirado. Perda
    estornada não é perda — e contá-la faria o relatório brigar com o razão.
    ⚠️ No razão a quantidade tem sinal e o `custo_total` não: o valor perdido é o
    custo com o sinal da SAÍDA (`-quantidade`), o que já resolve sobra e estorno.
    ⚠️ **O estorno herda o motivo do ORIGINAL** e é datado onde aconteceu: um estorno
    em outubro de uma perda de setembro abate outubro, como no CMV.
    """
    inicio, fim = _periodo(f)
    detalhe = f.get("detalhe_perdas") or "motivo"
    if detalhe not in DETALHES_PERDAS:
        detalhe = "motivo"
    cur.execute(
        """SELECT m.data_movimento, o.tipo, o.origem_tipo, o.id_motivo_perda,
                  pm.nome AS motivo_cadastro, p.codigo, p.nome AS produto, p.um_estoque,
                  c.nome AS categoria, l.nome AS local, u.nome AS usuario,
                  -m.quantidade AS quantidade,
                  CASE WHEN m.quantidade < 0 THEN m.custo_total ELSE -m.custo_total END AS valor,
                  m.id_estorno_de IS NOT NULL AS estorno, coalesce(m.observacao, '') AS observacao
             FROM estoque_movimentos m
             JOIN estoque_movimentos o ON o.id = coalesce(m.id_estorno_de, m.id)
             JOIN produtos p ON p.id = m.id_produto
             LEFT JOIN categorias c ON c.id = p.id_categoria
             LEFT JOIN locais_estoque l ON l.id = m.id_local
             LEFT JOIN perda_motivos pm ON pm.id = o.id_motivo_perda
             LEFT JOIN usuarios u ON u.id = m.id_usuario
            WHERE m.id_unidade = %(u)s AND o.tipo = ANY(%(tipos)s)
              AND m.data_movimento >= %(inicio)s AND m.data_movimento < %(limite)s
              AND (%(locais)s::int[] IS NULL OR m.id_local = ANY(%(locais)s))
              AND (%(setores)s::int[] IS NULL OR p.id_setor = ANY(%(setores)s))
              AND (%(categorias)s::int[] IS NULL OR p.id_categoria = ANY(%(categorias)s))
            ORDER BY m.data_movimento, m.id""",
        {"u": id_unidade, "tipos": list(_TIPOS_PERDA), "inicio": inicio,
         "limite": fim + timedelta(days=1), "locais": _lista(f.get("locais")),
         "setores": _lista(f.get("setores")), "categorias": _lista(f.get("categorias"))})
    movs = []
    for r in cur.fetchall():
        d = dict(r)
        if d["tipo"] == "SAIDA_PERDA":
            chave = f"m{d['id_motivo_perda']}" if d["id_motivo_perda"] else "sem_motivo"
            motivo = d["motivo_cadastro"] or "Perda sem motivo informado"
        elif d["origem_tipo"] == "INVENTARIO":
            chave, motivo = "inventario", "Diferença de inventário"
        else:
            chave, motivo = "ajuste", "Ajuste de saldo"
        d.update(chave=chave, motivo=motivo,
                 origem=_ORIGEM_PERDA.get(d["origem_tipo"], (d["origem_tipo"] or "").lower()))
        movs.append(d)
    motivos = _lista(f.get("motivos"))
    if motivos:
        movs = [m for m in movs if m["chave"] in set(motivos)]

    # ⚠️ `Decimal(0)` como início: soma vazia do Python é o INT 0, sem `.quantize`.
    valores = [Decimal(str(m["valor"] or 0)) for m in movs]
    perdido = sum((v for v in valores if v > 0), Decimal(0))
    sobrou = -sum((v for v in valores if v < 0), Decimal(0))
    liquido = perdido - sobrou

    if detalhe == "motivo":
        grupos: dict[str, dict] = {}
        for m in movs:
            g = grupos.setdefault(m["motivo"], {"motivo": m["motivo"], "movimentos": 0,
                                                "produtos": set(), "valor": Decimal(0)})
            g["movimentos"] += 1
            g["produtos"].add(m["produto"])
            g["valor"] += Decimal(str(m["valor"] or 0))
        linhas = sorted(grupos.values(), key=lambda g: -g["valor"])
        for g in linhas:
            g["produtos"] = len(g["produtos"])
            g["participacao"] = (g["valor"] * 100 / liquido).quantize(Decimal("0.01")) \
                if liquido else None
        colunas = [("motivo", "Motivo"), ("movimentos", "Movimentos"),
                   ("produtos", "Produtos"), ("valor", "Valor perdido"),
                   ("participacao", "% do total")]
    elif detalhe == "produto":
        grupos = {}
        for m in movs:
            g = grupos.setdefault(m["produto"], {
                "codigo": m["codigo"], "produto": m["produto"], "categoria": m["categoria"],
                "um_estoque": m["um_estoque"], "quantidade": Decimal(0), "valor": Decimal(0),
                "_motivos": {}})
            g["quantidade"] += Decimal(str(m["quantidade"] or 0))
            g["valor"] += Decimal(str(m["valor"] or 0))
            g["_motivos"][m["motivo"]] = g["_motivos"].get(m["motivo"], 0) + \
                Decimal(str(m["valor"] or 0))
        linhas = sorted(grupos.values(), key=lambda g: -g["valor"])
        for g in linhas:
            g["principal"] = max(g.pop("_motivos").items(), key=lambda kv: kv[1])[0]
        colunas = [("codigo", "Código"), ("produto", "Produto"), ("categoria", "Categoria"),
                   ("quantidade", "Quantidade perdida"), ("um_estoque", "Unidade"),
                   ("valor", "Valor perdido"), ("principal", "Motivo que mais pesou")]
    else:
        linhas = [{**m, "data": m["data_movimento"],
                   "motivo": m["motivo"] + (" (estorno)" if m["estorno"] else "")}
                  for m in movs]
        colunas = [("data", "Quando"), ("codigo", "Código"), ("produto", "Produto"),
                   ("local", "Local"), ("motivo", "Motivo"), ("origem", "Origem"),
                   ("quantidade", "Quantidade"), ("um_estoque", "Unidade"),
                   ("valor", "Valor"), ("usuario", "Quem"), ("observacao", "Observação")]

    for l in linhas:
        l["valor"] = Decimal(str(l["valor"] or 0)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return Saida(
        linhas, colunas,
        f"Perdas e ajustes — {_intervalo(inicio, fim)} — "
        f"{DETALHES_PERDAS[detalhe].split(' — ')[0].lower()}",
        [("Perdas e faltas", perdido.quantize(Decimal("0.01"))),
         ("Sobras (abatem)", sobrou.quantize(Decimal("0.01"))),
         ("Perda líquida", liquido.quantize(Decimal("0.01"))),
         ("Movimentos", len(movs))],
        inicio, fim)


_SITUACAO_MARGEM = {"prejuizo": "prejuízo", "abaixo": "abaixo da margem",
                    "sem_preco": "sem preço", "sem_custo": "sem custo (sem ficha)",
                    "sem_conta": "taxas + margem passam de 100%", "na_margem": "na margem"}


def _margem(cur, id_unidade: int, f: dict) -> Saida:
    """Cada prato vendido no período: custo, preço, CMV %, lucro e o piso do preço.

    🔑 **É a análise da Precificação, recortada pelo período** (`precificacao.analise`):
    a mesma conta, as mesmas taxas e a mesma margem-alvo da configuração da loja.
    Um segundo cálculo de margem aqui discordaria da tela de preços na primeira
    taxa nova. ⚠️ O custo é o de HOJE (precifica-se para a frente); o volume é o do
    período. A ordem é a da tela: prejuízo e abaixo da margem na frente.
    """
    from services import precificacao

    inicio, fim = _periodo(f)
    r = precificacao.analise(cur, id_unidade, limite=2000, inicio=inicio, fim=fim)
    itens = r["itens"]
    cats = _nomes(_opcoes_categorias(cur, id_unidade), _lista(f.get("categorias")))
    sets_ = _nomes(_opcoes_setores(cur, id_unidade), _lista(f.get("setores")))
    if cats is not None:
        itens = [i for i in itens if i["categoria"] in cats]
    if sets_ is not None:
        itens = [i for i in itens if i["setor"] in sets_]
    linhas = [{**i, "situacao": _SITUACAO_MARGEM.get(i["situacao"], i["situacao"]),
               "lucro_total": (round(i["lucro"] * i["vendido"], 2)
                               if i["lucro"] is not None else None)} for i in itens]
    com_conta = [i for i in itens if i["lucro"] is not None]
    receita = sum(i["receita"] or 0 for i in com_conta)
    custo = sum((i["custo_direto"] or 0) * i["vendido"] for i in com_conta)
    resumo = [("Pratos", len(linhas)),
              ("Abaixo da margem", sum(1 for i in itens if i["situacao"] in ("abaixo", "prejuizo"))),
              ("Com prejuízo", sum(1 for i in itens if i["situacao"] == "prejuizo")),
              ("Sem custo (sem ficha)", sum(1 for i in itens if i["situacao"] == "sem_custo")),
              ("CMV % (pratos com conta)", round(custo / receita * 100, 2) if receita else None),
              ("Lucro no período", round(sum(l["lucro_total"] or 0 for l in linhas), 2))]
    if not r["configurada"]:
        resumo.append(("Atenção", "a precificação desta loja não foi configurada — "
                                  "sem taxas nem margem-alvo, o lucro é só preço − custo"))
    return Saida(
        linhas,
        [("codigo", "Código"), ("nome", "Prato"), ("categoria", "Categoria"),
         ("setor", "Setor"), ("vendido", "Vendido"), ("receita", "Receita"),
         ("custo_direto", "Custo"), ("preco", "Preço"), ("food_cost_pct", "CMV %"),
         ("soma_pct", "Taxas %"), ("lucro", "Lucro un."), ("lucro_pct", "Lucro %"),
         ("lucro_total", "Lucro no período"), ("margem_alvo_pct", "Margem-alvo %"),
         ("sugerido", "Preço mínimo"), ("situacao", "Situação")],
        f"Margem dos pratos — {_intervalo(inicio, fim)}", resumo, inicio, fim)


def _recebimentos(cur, id_unidade: int, f: dict) -> Saida:
    """Os lotes de cobrança RECEBIDOS no período, com o total por forma de pagamento.

    🔑 A data é a do RECEBIMENTO (a que se informou na baixa), não a do lote: é o
    dinheiro que entrou naquele período. O quadro por forma vem como anexo — é o
    que se confere com o extrato e com a folha.
    """
    inicio, fim = _periodo(f)
    formas = _lista(f.get("formas"))
    pessoas = _lista(f.get("pessoas"))
    cur.execute(
        """SELECT l.id AS lote, l.recebido_em, fo.nome AS pessoa, l.desde, l.ate,
                  l.cupons, l.total_cheio, l.desconto, l.total, l.forma_pagamento,
                  ub.nome AS baixou, l.observacao_baixa
             FROM consumo_lotes l
             JOIN fornecedores fo ON fo.id = l.id_pessoa
             LEFT JOIN usuarios ub ON ub.id = l.id_usuario_baixou
            WHERE l.id_unidade = %(u)s AND l.status = 'RECEBIDO'
              AND l.recebido_em BETWEEN %(inicio)s AND %(fim)s
              AND (%(formas)s::text[] IS NULL OR l.forma_pagamento = ANY(%(formas)s))
              AND (%(pessoas)s::int[] IS NULL OR l.id_pessoa = ANY(%(pessoas)s))
            ORDER BY l.recebido_em, lower(fo.nome)""",
        {"u": id_unidade, "inicio": inicio, "fim": fim, "formas": formas,
         "pessoas": [int(p) for p in pessoas] if pessoas else None})
    linhas = []
    for r in cur.fetchall():
        d = dict(r)
        d["forma"] = receber_motor.FORMAS.get(d["forma_pagamento"] or "", "—")
        d["periodo"] = (f"{d['desde']:%d/%m/%Y} a " if d["desde"] else "até ") + f"{d['ate']:%d/%m/%Y}"
        linhas.append(d)
    por_forma: dict[str, dict] = {}
    for l in linhas:
        g = por_forma.setdefault(l["forma"], {"forma": l["forma"], "lotes": 0,
                                              "total": Decimal(0)})
        g["lotes"] += 1
        g["total"] += Decimal(str(l["total"] or 0))
    total = sum((Decimal(str(l["total"] or 0)) for l in linhas), Decimal(0))
    quadro = sorted(por_forma.values(), key=lambda g: -g["total"])
    for g in quadro:
        g["participacao"] = (g["total"] * 100 / total).quantize(Decimal("0.01")) if total else None
    return Saida(
        linhas,
        [("recebido_em", "Recebido em"), ("lote", "Lote"), ("pessoa", "Pessoa"),
         ("periodo", "Documentos de"), ("cupons", "Docs"), ("total_cheio", "Valor cheio"),
         ("desconto", "Desconto"), ("total", "Recebido"), ("forma", "Forma"),
         ("baixou", "Baixa por"), ("observacao_baixa", "Observação")],
        f"Recebimentos do consumo — {_intervalo(inicio, fim)}",
        [("Lotes recebidos", len(linhas)), ("Total recebido", total),
         ("Pessoas", len({l["pessoa"] for l in linhas}))],
        inicio, fim,
        anexos=[(quadro, [("forma", "Forma"), ("lotes", "Lotes"), ("total", "Total"),
                          ("participacao", "% do total")],
                 "Por forma de pagamento", None)] if quadro else [],
    )


def _producoes(cur, id_unidade: int, f: dict) -> Saida:
    """O que a cozinha produziu no período — produção a produção ou por produto.

    🔑 Pedido do dono (lista de relatórios, item 5, 23/10/2026).
    ⚠️ **Produção estornada fica FORA**, e o resumo diz quantas: ela foi desfeita no
    razão, e somá-la faria o relatório afirmar uma produção que o estoque não tem.
    "Estornada" sai do RAZÃO (a entrada do produzido tem contrário), a mesma régua
    de `estoque.estornar_producao` — não há coluna que diga isso na produção.
    ⚠️ A origem "na hora" é a que a VENDA disparou (`producoes.id_venda`).
    """
    inicio, fim = _periodo(f)
    detalhe = f.get("detalhe_producao") or "producao"
    if detalhe not in DETALHES_PRODUCAO:
        detalhe = "producao"
    origens = set(_lista(f.get("origem_producao")) or ["cozinha"])
    cur.execute(
        """SELECT pr.id, pr.data, p.codigo, p.nome AS produto, p.um_estoque,
                  c.nome AS categoria, pr.quantidade, pr.custo_total, pr.custo_unitario,
                  pr.versao_ficha, fm.nome AS modo, l.nome AS local, u.nome AS usuario,
                  pr.observacao, pr.id_venda IS NOT NULL AS na_hora,
                  EXISTS (SELECT 1 FROM producao_agenda a WHERE a.id_producao = pr.id)
                      AS da_agenda,
                  NOT EXISTS (SELECT 1 FROM estoque_movimentos m
                               WHERE m.origem_tipo = 'PRODUCAO' AND m.origem_id = pr.id
                                 AND m.tipo = 'ENTRADA_PRODUCAO'
                                 AND NOT EXISTS (SELECT 1 FROM estoque_movimentos e
                                                  WHERE e.id_estorno_de = m.id))
                      AS estornada
             FROM producoes pr
             JOIN produtos p ON p.id = pr.id_produto
             LEFT JOIN categorias c ON c.id = p.id_categoria
             LEFT JOIN locais_estoque l ON l.id = pr.id_local
             LEFT JOIN usuarios u ON u.id = pr.id_usuario
             LEFT JOIN ficha_modos fm ON fm.id = pr.id_modo
            WHERE pr.id_unidade = %(u)s
              AND pr.data >= %(inicio)s AND pr.data < %(limite)s
              AND (%(setores)s::int[] IS NULL OR p.id_setor = ANY(%(setores)s))
              AND (%(categorias)s::int[] IS NULL OR p.id_categoria = ANY(%(categorias)s))
            ORDER BY pr.data, pr.id""",
        {"u": id_unidade, "inicio": inicio, "limite": fim + timedelta(days=1),
         "setores": _lista(f.get("setores")), "categorias": _lista(f.get("categorias"))})
    todas = [dict(r) for r in cur.fetchall()]
    todas = [r for r in todas
             if ("na_hora" if r["na_hora"] else "cozinha") in origens]
    estornadas = sum(1 for r in todas if r["estornada"])
    vivas = [r for r in todas if not r["estornada"]]
    for r in vivas:
        r["origem"] = ("na hora (venda)" if r["na_hora"]
                       else "agenda" if r["da_agenda"] else "à mão")

    if detalhe == "produto":
        grupos: dict[str, dict] = {}
        for r in vivas:
            g = grupos.setdefault(r["produto"], {
                "codigo": r["codigo"], "produto": r["produto"], "categoria": r["categoria"],
                "um_estoque": r["um_estoque"], "producoes": 0, "quantidade": Decimal(0),
                "custo_total": Decimal(0), "menor": None, "maior": None})
            g["producoes"] += 1
            g["quantidade"] += Decimal(str(r["quantidade"]))
            g["custo_total"] += Decimal(str(r["custo_total"] or 0))
            cu = Decimal(str(r["custo_unitario"] or 0))
            g["menor"] = cu if g["menor"] is None else min(g["menor"], cu)
            g["maior"] = cu if g["maior"] is None else max(g["maior"], cu)
        linhas = sorted(grupos.values(), key=lambda g: -g["custo_total"])
        for g in linhas:
            g["medio"] = (g["custo_total"] / g["quantidade"]).quantize(Decimal("0.000001")) \
                if g["quantidade"] else None
        colunas = [("codigo", "Código"), ("produto", "Produto"), ("categoria", "Categoria"),
                   ("producoes", "Produções"), ("quantidade", "Quantidade"),
                   ("um_estoque", "Unidade"), ("custo_total", "Custo total"),
                   ("medio", "Custo médio un."), ("menor", "Menor custo un."),
                   ("maior", "Maior custo un.")]
    else:
        linhas = vivas
        colunas = [("data", "Quando"), ("codigo", "Código"), ("produto", "Produto"),
                   ("quantidade", "Quantidade"), ("um_estoque", "Unidade"),
                   ("modo", "Modo"), ("versao_ficha", "Ficha v."), ("local", "Local"),
                   ("custo_total", "Custo total"), ("custo_unitario", "Custo un."),
                   ("origem", "Origem"), ("usuario", "Quem"), ("observacao", "Observação")]
    custo = sum((Decimal(str(r["custo_total"] or 0)) for r in vivas), Decimal(0))
    resumo = [("Produções", len(vivas)), ("Produtos", len({r["produto"] for r in vivas})),
              ("Custo produzido", custo),
              ("Quais", ", ".join(ORIGENS_PRODUCAO[o].split(" (")[0].lower()
                                  for o in ORIGENS_PRODUCAO if o in origens))]
    if estornadas:
        resumo.append(("Estornadas (fora da conta)", estornadas))
    return Saida(linhas, colunas,
                 f"Produção — {_intervalo(inicio, fim)} — "
                 f"{DETALHES_PRODUCAO[detalhe].split(' — ')[0].lower()}",
                 resumo, inicio, fim)


def _agenda_producao(cur, id_unidade: int, f: dict) -> Saida:
    """A agenda de produção de UM dia, para a bancada — e o que separar para ela.

    🔑 Pedido do dono (lista de relatórios, item 5, 23/10/2026). Entra o PLANEJADO do
    dia e o ATRASADO (planejado de dias antes, ainda não feito): é a lista de tarefas,
    e a tarefa esquecida é a que mais precisa estar no papel.
    🔑 **O anexo "O que separar"** soma os insumos de todas as linhas — a MESMA conta
    da folha da produção (`estoque.previsao_producao`), com o saldo de agora. Sem
    custo: o papel é da cozinha.
    ⚠️ Linha cuja previsão falha (produto sem ficha) não derruba o papel: ela vai à
    lista, e o resumo diz quantas ficaram sem insumos calculados.
    """
    from services import producao_agenda as agenda_motor

    hoje = relogio.hoje_da_casa()
    dia = f.get("data") or hoje
    # ⚠️ Atrasada é em relação a HOJE, não ao dia escolhido: a folha de sexta,
    # impressa na terça, não chama de atrasado o que está marcado para quarta.
    # O atrasado entra só na folha de HOJE — é nela que ele vira tarefa.
    linhas_ag = [l for l in agenda_motor.listar(cur, id_unidade, None, dia, "PLANEJADA")
                 if l["data_prevista"] == dia or (dia == hoje and l["data_prevista"] < hoje)]
    separar: dict[tuple, dict] = {}
    sem_previsao = 0
    linhas = []
    for l in linhas_ag:
        try:
            prev = estoque_motor.previsao_producao(cur, id_unidade, l["id_produto"],
                                                   l["quantidade"], l["id_local"], None,
                                                   l.get("id_modo"))
        except HTTPException:
            prev, sem_previsao = None, sem_previsao + 1
        for i in (prev or {}).get("itens") or []:
            g = separar.setdefault((i["codigo"], i["produto"]), {
                "codigo": i["codigo"], "insumo": i["produto"], "um": i["um_estoque"],
                "necessario": Decimal(0), "saldo": Decimal(str(i["saldo_total"] or 0)),
                "preparo": "sim" if i["preparo"] else ""})
            g["necessario"] += Decimal(str(i["necessario"] or 0))
        linhas.append({
            "data_prevista": l["data_prevista"],
            "situacao": "ATRASADA" if l["data_prevista"] < hoje else "",
            "codigo": l["codigo"], "produto": l["produto"], "quantidade": l["quantidade"],
            "um_estoque": l["um_estoque"], "modo": l.get("modo"), "local": l["local"],
            "observacao": l["observacao"], "feito": "[   ]"})
    lista_sep = sorted(separar.values(), key=lambda g: g["insumo"].casefold())
    for g in lista_sep:
        falta = g["necessario"] - g["saldo"]
        g["falta"] = falta if falta > 0 else None
    resumo = [("Dia", dia), ("Produções planejadas", len(linhas)),
              ("Atrasadas", sum(1 for l in linhas if l["situacao"])),
              ("Insumos a separar", len(lista_sep)),
              ("Insumos em falta", sum(1 for g in lista_sep if g["falta"]))]
    if sem_previsao:
        resumo.append(("Sem insumos calculados (sem ficha)", sem_previsao))
    return Saida(
        linhas,
        [("feito", "Feito"), ("produto", "Produto"), ("quantidade", "Quantidade"),
         ("um_estoque", "Un."), ("modo", "Modo"), ("local", "Local"),
         ("situacao", "Situação"), ("data_prevista", "Previsto para"),
         ("observacao", "Observação")],
        f"Agenda de produção — {dia:%d/%m/%Y}", resumo, dia, dia,
        anexos=[(lista_sep, [("insumo", "Insumo"), ("preparo", "Preparo"),
                             ("necessario", "Separar"), ("um", "Un."),
                             ("saldo", "Tem no estoque"), ("falta", "Falta")],
                 "O que separar", None)] if lista_sep else [])


_MOTIVOS_VENDA = {"CONSUMO_INTERNO": "consumo interno", "PERDA": "perda", "PREMIO": "prêmio",
                  "BRINDE": "brinde/aniversário", "OUTROS": "outros"}
_ORIGENS_VENDA = {"PDV_LEGAL": "PDV Legal", "PDV": "PDV", "PLANILHA": "planilha",
                  "MANUAL": "lançada à mão"}
_CANAIS_VENDA = {"BALCAO": "balcão", "SALAO": "salão", "DELIVERY": "delivery",
                 "EVENTO": "evento"}


def _opcoes_origem_venda(cur, id_unidade: int) -> list[dict]:
    """As origens que EXISTEM nas vendas desta loja — não uma lista fixa."""
    cur.execute("SELECT DISTINCT origem FROM vendas WHERE id_unidade = %s ORDER BY 1",
                (id_unidade,))
    return [{"valor": r["origem"], "nome": _ORIGENS_VENDA.get(r["origem"], r["origem"])}
            for r in cur.fetchall()]


# ⚠️ Declarado aqui, e não no dicionário lá em cima: as opções saem de uma função
# deste bloco, e o dicionário é montado antes dela existir.
FILTROS["origem_venda"] = {"tipo": "multipla", "rotulo": "Origem",
                           "ajuda": "todas as origens", "opcoes": _opcoes_origem_venda}


def _vendas_documentos(cur, id_unidade: int, f: dict) -> Saida:
    """As vendas do período, documento a documento — para conferir com o caixa e o PDV.

    🔑 Pedido do dono (lista de relatórios, item 7, 23/10/2026). O Estudo de vendas é
    agregado; este é a fita: cada cupom com hora, origem, canal, pessoa e total.
    ⚠️ **A cancelada APARECE, marcada, e fica fora dos totais**: o PDV conta o cupom
    cancelado, e a conferência que a escondesse não fecharia a numeração.
    Dois quadros atrás: por dia (quando o período tem mais de um) e por origem e canal.
    """
    inicio, fim = _periodo(f)
    origens = _lista(f.get("origem_venda"))
    cur.execute(
        """SELECT v.id, v.data, v.hora, v.documento, v.origem, v.canal, v.mesa,
                  fo.nome AS pessoa, v.desconto, v.valor_total, v.cancelada,
                  v.consumo_interno, v.motivo,
                  (SELECT count(*) FROM venda_itens vi WHERE vi.id_venda = v.id) AS itens
             FROM vendas v
             LEFT JOIN fornecedores fo ON fo.id = v.id_pessoa
            WHERE v.id_unidade = %(u)s AND v.data BETWEEN %(inicio)s AND %(fim)s
              AND (%(origens)s::text[] IS NULL OR v.origem = ANY(%(origens)s))
            ORDER BY v.data, v.hora NULLS FIRST, v.documento, v.id""",
        {"u": id_unidade, "inicio": inicio, "fim": fim, "origens": origens})
    linhas = []
    for r in cur.fetchall():
        d = dict(r)
        d["origem_txt"] = _ORIGENS_VENDA.get(d["origem"], d["origem"])
        d["canal_txt"] = _CANAIS_VENDA.get((d["canal"] or "").upper(), d["canal"] or "")
        # O motivo (134) diz que tipo de "não é venda" o documento é.
        d["situacao"] = ("cancelada" if d["cancelada"]
                         else _MOTIVOS_VENDA.get(d["motivo"] or "CONSUMO_INTERNO",
                                                 "consumo interno")
                         if d["consumo_interno"] else "")
        d["hora"] = str(d["hora"])[:5] if d["hora"] else None
        linhas.append(d)
    validas = [l for l in linhas if not l["cancelada"]]
    total = sum((Decimal(str(l["valor_total"] or 0)) for l in validas), Decimal(0))
    canceladas = [l for l in linhas if l["cancelada"]]

    def quadro(chave_de) -> list[dict]:
        g: dict = {}
        for l in validas:
            k = chave_de(l)
            x = g.setdefault(k, {"chave": k, "documentos": 0, "total": Decimal(0)})
            x["documentos"] += 1
            x["total"] += Decimal(str(l["valor_total"] or 0))
        saida = list(g.values())
        for x in saida:
            x["ticket"] = (x["total"] / x["documentos"]).quantize(Decimal("0.01"))
        return saida

    anexos = []
    if inicio != fim:
        anexos.append((sorted(quadro(lambda l: l["data"]), key=lambda x: x["chave"]),
                       [("chave", "Dia"), ("documentos", "Documentos"), ("total", "Total"),
                        ("ticket", "Ticket médio")], "Por dia", None))
    anexos.append((sorted(quadro(lambda l: f"{l['origem_txt']}"
                                 + (f" · {l['canal_txt']}" if l["canal_txt"] else "")),
                          key=lambda x: -x["total"]),
                   [("chave", "Origem e canal"), ("documentos", "Documentos"),
                    ("total", "Total"), ("ticket", "Ticket médio")],
                   "Por origem e canal", None))
    return Saida(
        linhas,
        [("data", "Data"), ("hora", "Hora"), ("documento", "Documento"),
         ("origem_txt", "Origem"), ("canal_txt", "Canal"), ("mesa", "Mesa"),
         ("pessoa", "Pessoa"), ("itens", "Itens"), ("desconto", "Desconto"),
         ("valor_total", "Total"), ("situacao", "Situação")],
        f"Vendas documento a documento — {_intervalo(inicio, fim)}",
        [("Documentos válidos", len(validas)), ("Total vendido", total),
         ("Ticket médio", (total / len(validas)).quantize(Decimal("0.01")) if validas else None),
         ("Canceladas (fora da conta)", len(canceladas)),
         ("Valor das canceladas",
          sum((Decimal(str(l["valor_total"] or 0)) for l in canceladas), Decimal(0)))],
        inicio, fim, anexos=anexos)


# ---------------------------------------------------------------------------
# A terceira leva (23/10/2026, itens 8 e 9): reservas do dia e pedidos do cardápio
# ---------------------------------------------------------------------------

SITUACOES_RESERVA = {"PENDENTE": "aguardando confirmação", "CONFIRMADA": "confirmada",
                     "CHEGOU": "chegou", "ENCERRADA": "encerrada",
                     "NAO_COMPARECEU": "não compareceu", "CANCELADA": "cancelada"}
SITUACOES_PEDIDO = {"NOVO": "novo", "CONFIRMADO": "confirmado", "ENTREGUE": "entregue",
                    "RECUSADO": "recusado", "CANCELADO": "cancelado"}
DETALHES_PEDIDOS = {"pedido": "Pedido a pedido", "produto": "Por produto (o que mais sai)"}
_MODOS_PEDIDO = {"RETIRADA": "retirada", "ENTREGA": "entrega", "MESA": "na mesa"}
_ORIGENS_PEDIDO = {"SITE": "site", "CARDAPIO": "cardápio da mesa"}

FILTROS["situacao_reserva"] = {
    "tipo": "multipla", "rotulo": "Situação",
    # ⚠️ Sem escolha, ficam de fora só as CANCELADAS: a folha é de quem vem, e
    # a cancelada na lista da recepção vira mesa guardada para ninguém.
    "ajuda": "todas menos as canceladas",
    "opcoes": lambda _c, _u: [{"valor": v, "nome": n} for v, n in SITUACOES_RESERVA.items()]}
FILTROS["situacao_pedido"] = {
    "tipo": "multipla", "rotulo": "Situação",
    "ajuda": "todas (recusados e cancelados aparecem, fora dos totais)",
    "opcoes": lambda _c, _u: [{"valor": v, "nome": n} for v, n in SITUACOES_PEDIDO.items()]}
FILTROS["detalhe_pedidos"] = {
    "tipo": "escolha", "rotulo": "Como agrupar", "ajuda": "pedido a pedido",
    "opcoes": lambda _c, _u: [{"valor": v, "nome": n} for v, n in DETALHES_PEDIDOS.items()]}


def _reservas_dia(cur, id_unidade: int, f: dict) -> Saida:
    """As reservas de UM dia, para a recepção: hora, nome, pessoas, mesa.

    🔑 Pedido do dono (lista de relatórios, item 8, 23/10/2026). É o papel do balcão:
    a coluna "Chegou" vai em branco para marcar a caneta.
    ⚠️ As mesas saem JUNTAS numa célula ("3 + 4"): a reserva que junta mesas é uma
    linha só — duas linhas fariam a recepção contar o grupo duas vezes.
    ⚠️ A observação interna ENTRA: o papel não sai da casa, e é nela que está o
    "aniversário, trazer o bolo às 21h".
    """
    dia = f.get("data") or relogio.hoje_da_casa()
    situacoes = _lista(f.get("situacao_reserva"))
    cur.execute(
        """SELECT r.id, r.hora, r.nome, r.telefone, r.pessoas, r.status, r.origem,
                  r.objetivo, r.observacao_cliente, r.observacao_interna,
                  string_agg(m.nome, ' + ' ORDER BY m.nome) AS mesas,
                  string_agg(DISTINCT s.nome, ', ') AS salao
             FROM reservas r
             LEFT JOIN reserva_mesas rm ON rm.id_reserva = r.id
             LEFT JOIN mesas m ON m.id = rm.id_mesa
             LEFT JOIN saloes s ON s.id = m.id_salao
            WHERE r.id_unidade = %(u)s AND r.data = %(dia)s
              AND (CASE WHEN %(sit)s::text[] IS NULL THEN r.status <> 'CANCELADA'
                        ELSE r.status = ANY(%(sit)s) END)
            GROUP BY r.id
            ORDER BY r.hora, r.nome, r.id""",
        {"u": id_unidade, "dia": dia, "sit": situacoes})
    linhas = []
    for r in cur.fetchall():
        d = dict(r)
        d["hora"] = str(d["hora"])[:5]
        d["situacao"] = SITUACOES_RESERVA.get(d["status"], d["status"])
        d["origem_txt"] = "site" if d["origem"] == "SITE" else "balcão"
        d["observacao"] = _junta(d["objetivo"], d["observacao_cliente"],
                                 d["observacao_interna"], sep=" — ")
        d["chegou"] = "[   ]"
        linhas.append(d)

    # Quem conta para a casa: a reserva que ainda vem ou já veio.
    contam = [l for l in linhas if l["status"] not in ("CANCELADA", "NAO_COMPARECEU")]
    por_hora: dict[str, dict] = {}
    for l in contam:
        g = por_hora.setdefault(l["hora"], {"hora": l["hora"], "reservas": 0, "pessoas": 0})
        g["reservas"] += 1
        g["pessoas"] += l["pessoas"]
    resumo = [("Dia", dia), ("Reservas", len(contam)),
              ("Pessoas esperadas", sum(l["pessoas"] for l in contam)),
              ("Aguardando confirmação", sum(1 for l in linhas if l["status"] == "PENDENTE")),
              ("Sem mesa definida", sum(1 for l in contam if not l["mesas"]))]
    return Saida(
        linhas,
        [("chegou", "Chegou"), ("hora", "Hora"), ("nome", "Nome"), ("pessoas", "Pessoas"),
         ("mesas", "Mesa"), ("salao", "Salão"), ("telefone", "Telefone"),
         ("situacao", "Situação"), ("origem_txt", "Origem"), ("observacao", "Observação")],
        f"Reservas do dia — {dia:%d/%m/%Y}", resumo, dia, dia,
        anexos=[(sorted(por_hora.values(), key=lambda g: g["hora"]),
                 [("hora", "Hora"), ("reservas", "Reservas"), ("pessoas", "Pessoas")],
                 "Por horário", None)] if len(por_hora) > 1 else [])


def _pedidos(cur, id_unidade: int, f: dict) -> Saida:
    """Os pedidos do cardápio (site e mesa) no período: quantos, quanto e o que mais sai.

    🔑 Pedido do dono (lista de relatórios, item 9, 23/10/2026).
    ⚠️ **O período é o "para quando"**, não a hora do envio — é o mesmo "Para o dia"
    da tela de Pedidos: o bolo encomendado na segunda para sábado é pedido de sábado.
    ⚠️ Recusado e cancelado APARECEM, marcados, e ficam fora dos totais (a mesma regra
    da lista de vendas): a conferência que os escondesse não fecharia a numeração.
    """
    from config import FUSO_DA_CASA

    inicio, fim = _periodo(f)
    situacoes = _lista(f.get("situacao_pedido"))
    detalhe = f.get("detalhe_pedidos") or "pedido"
    if detalhe not in DETALHES_PEDIDOS:
        detalhe = "pedido"
    params = {"u": id_unidade, "inicio": inicio, "fim": fim, "sit": situacoes,
              "fuso": FUSO_DA_CASA}
    onde = """p.id_unidade = %(u)s
              AND (p.para_quando AT TIME ZONE %(fuso)s)::date BETWEEN %(inicio)s AND %(fim)s
              AND (%(sit)s::text[] IS NULL OR p.situacao = ANY(%(sit)s))"""
    cur.execute(
        f"""SELECT p.id, p.numero, p.nome, p.telefone, p.modo, p.origem, p.situacao,
                   (p.para_quando AT TIME ZONE %(fuso)s) AS quando,
                   coalesce(m.nome, p.mesa_nome) AS mesa, p.subtotal, p.taxa_entrega,
                   p.total, p.cupom_pdv, p.lancado_pdv_em, p.motivo,
                   (SELECT count(*) FROM pedido_itens i WHERE i.id_pedido = p.id) AS itens
              FROM pedidos p
              LEFT JOIN mesas m ON m.id = p.id_mesa
             WHERE {onde}
             ORDER BY p.para_quando, p.numero""", params)
    pedidos = []
    for r in cur.fetchall():
        d = dict(r)
        d["data"] = d["quando"].date()
        d["hora"] = d["quando"].strftime("%H:%M")
        d["situacao_txt"] = SITUACOES_PEDIDO.get(d["situacao"], d["situacao"])
        d["modo_txt"] = (f"mesa {d['mesa']}" if d["modo"] == "MESA" and d["mesa"]
                         else _MODOS_PEDIDO.get(d["modo"], d["modo"]))
        d["origem_txt"] = _ORIGENS_PEDIDO.get(d["origem"], d["origem"])
        d["no_pdv"] = "sim" if d["lancado_pdv_em"] else ""
        d["fora"] = d["situacao"] in ("RECUSADO", "CANCELADO")
        pedidos.append(d)
    validos = [p for p in pedidos if not p["fora"]]
    fora = [p for p in pedidos if p["fora"]]
    total = sum((Decimal(str(p["total"] or 0)) for p in validos), Decimal(0))

    # Situação: um quadro com TODAS (as de fora inclusive), para fechar a contagem.
    por_sit: dict[str, dict] = {}
    for p in pedidos:
        g = por_sit.setdefault(p["situacao"], {"chave": p["situacao_txt"], "pedidos": 0,
                                               "total": Decimal(0)})
        g["pedidos"] += 1
        g["total"] += Decimal(str(p["total"] or 0))
    ordem_sit = list(SITUACOES_PEDIDO)
    quadro_sit = [por_sit[s] for s in ordem_sit if s in por_sit]
    por_modo: dict[str, dict] = {}
    for p in validos:
        k = f"{p['origem_txt']} · {_MODOS_PEDIDO.get(p['modo'], p['modo'])}"
        g = por_modo.setdefault(k, {"chave": k, "pedidos": 0, "total": Decimal(0)})
        g["pedidos"] += 1
        g["total"] += Decimal(str(p["total"] or 0))
    cols_quadro = [("chave", "Situação"), ("pedidos", "Pedidos"), ("total", "Total")]
    anexos = [(quadro_sit, cols_quadro, "Por situação", None),
              (sorted(por_modo.values(), key=lambda g: -g["total"]),
               [("chave", "Origem e modo"), ("pedidos", "Pedidos"), ("total", "Total")],
               "Por origem e modo", None)]
    if inicio != fim:
        por_dia: dict = {}
        for p in validos:
            g = por_dia.setdefault(p["data"], {"chave": p["data"], "pedidos": 0,
                                               "total": Decimal(0)})
            g["pedidos"] += 1
            g["total"] += Decimal(str(p["total"] or 0))
        anexos.append((sorted(por_dia.values(), key=lambda g: g["chave"]),
                       [("chave", "Dia"), ("pedidos", "Pedidos"), ("total", "Total")],
                       "Por dia", None))

    resumo = [("Pedidos válidos", len(validos)), ("Total dos pedidos", total),
              ("Ticket médio",
               (total / len(validos)).quantize(Decimal("0.01")) if validos else None),
              ("Taxas de entrega",
               sum((Decimal(str(p["taxa_entrega"] or 0)) for p in validos), Decimal(0))),
              ("Ainda não lançados no PDV",
               sum(1 for p in validos if not p["lancado_pdv_em"])),
              ("Recusados e cancelados (fora da conta)", len(fora))]

    if detalhe == "produto":
        # ⚠️ Pelo NOME congelado no item, agrupado por produto: o nome do item é o do
        # dia do envio, e o produto renomeado depois não pode virar duas linhas.
        cur.execute(
            f"""SELECT i.id_produto, pr.codigo, max(i.nome) AS produto,
                       sum(i.quantidade) AS quantidade, sum(i.total) AS total,
                       count(DISTINCT p.id) AS pedidos
                  FROM pedido_itens i
                  JOIN pedidos p ON p.id = i.id_pedido
                  JOIN produtos pr ON pr.id = i.id_produto
                 WHERE {onde} AND p.situacao NOT IN ('RECUSADO', 'CANCELADO')
                 GROUP BY i.id_produto, pr.codigo
                 ORDER BY sum(i.total) DESC, max(i.nome)""", params)
        linhas = [dict(r) for r in cur.fetchall()]
        soma_itens = sum((Decimal(str(l["total"] or 0)) for l in linhas), Decimal(0))
        for l in linhas:
            l["participacao"] = ((Decimal(str(l["total"] or 0)) * 100 / soma_itens)
                                 .quantize(Decimal("0.1")) if soma_itens else None)
        return Saida(
            linhas,
            [("codigo", "Código"), ("produto", "Produto"), ("quantidade", "Quantidade"),
             ("pedidos", "Em quantos pedidos"), ("total", "Total"),
             ("participacao", "% do total")],
            f"Pedidos do cardápio por produto — {_intervalo(inicio, fim)}",
            resumo + [("Produtos diferentes", len(linhas))], inicio, fim, anexos=anexos)

    return Saida(
        pedidos,
        [("numero", "Nº"), ("data", "Data"), ("hora", "Hora"), ("nome", "Cliente"),
         ("telefone", "Telefone"), ("origem_txt", "Origem"), ("modo_txt", "Modo"),
         ("itens", "Itens"), ("taxa_entrega", "Taxa"), ("total", "Total"),
         ("situacao_txt", "Situação"), ("no_pdv", "No PDV"), ("cupom_pdv", "Cupom")],
        f"Pedidos do cardápio — {_intervalo(inicio, fim)}", resumo, inicio, fim,
        anexos=anexos)


# ---------------------------------------------------------------------------
# A quarta leva (23/10/2026, itens 10, 11 e 12): fidelidade, acessos e auditoria
# ---------------------------------------------------------------------------

RECORTES_FIDELIDADE = {"todos": "Todos os participantes", "com_premio": "Com prêmio a usar",
                       "vencendo": "Com prêmio vencendo em 7 dias",
                       "vencidos": "Com prêmio vencido sem uso"}
DETALHES_ACESSOS = {"usuarios": "Por usuário (papéis e último acesso)",
                    "papeis": "Por papel (o que cada papel pode fazer)"}


def _opcoes_usuarios(cur, _id_unidade: int) -> list[dict]:
    cur.execute("SELECT id, nome FROM usuarios ORDER BY lower(nome)")
    return [{"valor": r["id"], "nome": r["nome"]} for r in cur.fetchall()]


def _opcoes_entidades(cur, _id_unidade: int) -> list[dict]:
    # ⚠️ As que EXISTEM no registro, não uma lista escrita: entidade nova entra sozinha.
    cur.execute("SELECT DISTINCT entidade FROM auditoria ORDER BY 1")
    return [{"valor": r["entidade"], "nome": r["entidade"]} for r in cur.fetchall()]


FILTROS["recorte_fidelidade"] = {
    "tipo": "escolha", "rotulo": "Quem entra", "ajuda": "todos os participantes",
    "opcoes": lambda _c, _u: [{"valor": v, "nome": n} for v, n in RECORTES_FIDELIDADE.items()]}
FILTROS["periodo_premios"] = {"tipo": "periodo", "rotulo": "Prêmios emitidos entre",
                              "ajuda": "o mês corrente, se não escolher"}
FILTROS["detalhe_acessos"] = {
    "tipo": "escolha", "rotulo": "Como mostrar", "ajuda": "por usuário",
    "opcoes": lambda _c, _u: [{"valor": v, "nome": n} for v, n in DETALHES_ACESSOS.items()]}
FILTROS["usuarios"] = {"tipo": "multipla", "rotulo": "Quem fez", "ajuda": "todos",
                       "opcoes": _opcoes_usuarios}
FILTROS["entidades"] = {"tipo": "multipla", "rotulo": "O que foi mexido", "ajuda": "tudo",
                        "opcoes": _opcoes_entidades}


def _fidelidade(cur, _id_unidade: int, f: dict) -> Saida:
    """Os participantes da fidelidade com o cartão de cada um, e os prêmios do período.

    🔑 Pedido do dono (lista de relatórios, item 10, 23/10/2026).
    ⚠️ **O programa é da REDE** (091): a lista não recorta por loja, igual ao painel.
    🔑 A consulta é a MESMA do painel (`fidelidade.consulta_participantes`): número
    diferente entre a tela e o papel seria a primeira pergunta de quem confere.
    """
    from services import fidelidade as fid

    recorte = f.get("recorte_fidelidade") or "todos"
    if recorte not in RECORTES_FIDELIDADE:
        recorte = "todos"
    sql, params = fid.consulta_participantes(None, None if recorte == "todos" else recorte)
    # ⚠️ A config ANTES da consulta: `config` usa o mesmo cursor, e chamada entre o
    # execute e o fetchall troca o resultado — a lista saía vazia.
    visitas_cartao = fid.config(cur)["visitas"]
    cur.execute(sql, params)
    linhas = []
    for r in cur.fetchall():
        d = dict(r)
        d["faltam"] = max(visitas_cartao - int(d["no_cartao"] or 0), 0)
        linhas.append(d)

    inicio, fim = (f.get("inicio") or relogio.hoje_da_casa().replace(day=1),
                   f.get("fim") or relogio.hoje_da_casa())
    hoje = relogio.hoje_da_casa()
    cur.execute(
        """SELECT p.codigo, c.nome AS cliente, p.premio, p.emitido_em::date AS emitido,
                  p.vence_em, p.usado_em::date AS usado, u.nome AS entregue_por,
                  un.nome AS loja_uso
             FROM fidelidade_premios p
             JOIN reserva_clientes c ON c.id = p.id_cliente
             LEFT JOIN usuarios u ON u.id = p.usado_por
             LEFT JOIN unidades un ON un.id = p.id_unidade_uso
            WHERE p.emitido_em::date BETWEEN %s AND %s
            ORDER BY p.emitido_em, p.codigo""", (inicio, fim))
    premios = []
    for r in cur.fetchall():
        d = dict(r)
        d["situacao"] = ("usado" if d["usado"] else "vencido" if d["vence_em"] < hoje
                         else "a usar")
        premios.append(d)
    resumo = [("Participantes", len(linhas)),
              ("Visitas para um prêmio", visitas_cartao),
              ("Com prêmio a usar", sum(1 for l in linhas if l["disponiveis"])),
              ("Com prêmio vencido sem uso", sum(1 for l in linhas if l["vencidos"])),
              (f"Prêmios emitidos de {_intervalo(inicio, fim)}", len(premios)),
              ("… já usados", sum(1 for p in premios if p["situacao"] == "usado")),
              ("… vencidos sem uso", sum(1 for p in premios if p["situacao"] == "vencido"))]
    return Saida(
        linhas,
        [("nome", "Participante"), ("telefone", "Telefone"), ("no_cartao", "Selos no cartão"),
         ("faltam", "Faltam"), ("visitas", "Visitas"), ("ultima_visita", "Última visita"),
         ("disponiveis", "Prêmios a usar"), ("proximo_vencimento", "Vence em"),
         ("vencidos", "Vencidos"), ("usados", "Usados")],
        f"Fidelidade — {RECORTES_FIDELIDADE[recorte].lower()}", resumo, inicio, fim,
        anexos=[(premios, [("codigo", "Código"), ("cliente", "Cliente"), ("premio", "Prêmio"),
                           ("emitido", "Emitido"), ("vence_em", "Vence"),
                           ("situacao", "Situação"), ("usado", "Usado em"),
                           ("entregue_por", "Entregue por"), ("loja_uso", "Loja")],
                 f"Prêmios emitidos de {_intervalo(inicio, fim)}", None)] if premios else [])


def _acessos(cur, _id_unidade: int, f: dict) -> Saida:
    """Quem entra no sistema e o que pode fazer — para revisar os acessos de vez em quando.

    🔑 Pedido do dono (lista de relatórios, item 11, 23/10/2026). Duas visões: por
    usuário (papéis, loja, último acesso, bloqueio) e por papel (cada permissão dele,
    agrupada pelo módulo).
    ⚠️ Nada de senha ou hash: só o que a tela de Usuários já mostra.
    """
    detalhe = f.get("detalhe_acessos") or "usuarios"
    if detalhe not in DETALHES_ACESSOS:
        detalhe = "usuarios"
    cur.execute(
        """SELECT p.id, p.nome, p.descricao, p.sistema,
                  (SELECT count(*) FROM papel_permissoes pp WHERE pp.id_papel = p.id) AS permissoes,
                  (SELECT count(DISTINCT up.id_usuario) FROM usuario_papeis up
                     JOIN usuarios u ON u.id = up.id_usuario AND u.ativo
                    WHERE up.id_papel = p.id) AS usuarios
             FROM papeis p ORDER BY lower(p.nome)""")
    papeis = [dict(r) for r in cur.fetchall()]
    for p in papeis:
        p["de_sistema"] = "sim" if p["sistema"] else ""
    quadro_papeis = (papeis, [("nome", "Papel"), ("de_sistema", "Do sistema"),
                              ("usuarios", "Usuários ativos"), ("permissoes", "Permissões"),
                              ("descricao", "Descrição")], "Papéis", None)

    if detalhe == "papeis":
        cur.execute(
            """SELECT pa.nome AS papel, pe.modulo, pe.descricao, pe.chave
                 FROM papel_permissoes pp
                 JOIN papeis pa ON pa.id = pp.id_papel
                 JOIN permissoes pe ON pe.chave = pp.chave
                ORDER BY lower(pa.nome), pe.ordem, pe.chave""")
        linhas = [dict(r) for r in cur.fetchall()]
        return Saida(
            linhas,
            [("papel", "Papel"), ("modulo", "Módulo"), ("descricao", "O que pode"),
             ("chave", "Chave")],
            "Acessos por papel", [("Papéis", len(papeis)), ("Permissões concedidas", len(linhas))],
            anexos=[quadro_papeis])

    agora = relogio.agora_da_casa()
    cur.execute(
        """SELECT u.id, u.nome, u.email, u.ativo, u.ultimo_acesso, u.bloqueado_ate,
                  u.trocar_senha,
                  string_agg(pa.nome || coalesce(' (' || un.nome || ')', ''), ', '
                             ORDER BY pa.nome) AS papeis
             FROM usuarios u
             LEFT JOIN usuario_papeis up ON up.id_usuario = u.id
             LEFT JOIN papeis pa ON pa.id = up.id_papel
             LEFT JOIN unidades un ON un.id = up.id_unidade
            GROUP BY u.id
            ORDER BY u.ativo DESC, lower(u.nome)""")
    linhas = []
    for r in cur.fetchall():
        d = dict(r)
        d["situacao"] = "ativo" if d["ativo"] else "inativo"
        bloqueado = d["bloqueado_ate"] and d["bloqueado_ate"] > agora
        d["observacao"] = _junta("bloqueado por tentativas" if bloqueado else None,
                                 "vai trocar a senha" if d["trocar_senha"] else None,
                                 "sem papel" if not d["papeis"] else None)
        # A sessão do banco já está no fuso da casa (regra 6): a hora vem certa.
        d["ultimo"] = (d["ultimo_acesso"].strftime("%d/%m/%Y %H:%M")
                       if d["ultimo_acesso"] else "nunca entrou")
        linhas.append(d)
    ativos = [l for l in linhas if l["ativo"]]
    return Saida(
        linhas,
        [("nome", "Usuário"), ("email", "E-mail"), ("situacao", "Situação"),
         ("papeis", "Papéis (loja)"), ("ultimo", "Último acesso"),
         ("observacao", "Observação")],
        "Usuários e acessos",
        [("Usuários ativos", len(ativos)), ("Inativos", len(linhas) - len(ativos)),
         ("Ativos que nunca entraram", sum(1 for l in ativos if not l["ultimo_acesso"])),
         ("Ativos sem papel", sum(1 for l in ativos if not l["papeis"]))],
        anexos=[quadro_papeis])


def _mudou(antes, depois) -> str:
    """O que mudou, numa linha: "campo: velho → novo"; criação e exclusão, os campos."""
    def curto(v) -> str:
        t = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
        return t if len(t) <= 60 else t[:57] + "…"

    a = antes if isinstance(antes, dict) else {}
    d = depois if isinstance(depois, dict) else {}
    partes = []
    for k in list(dict.fromkeys([*a, *d])):
        if k in a and k in d:
            if a[k] != d[k]:
                partes.append(f"{k}: {curto(a[k])} → {curto(d[k])}")
        elif k in d:
            partes.append(f"{k}={curto(d[k])}")
        else:
            partes.append(f"{k} (era {curto(a[k])})")
    # " · " e não ";": o ponto e vírgula é o separador da planilha da casa.
    texto = " · ".join(partes)
    return texto if len(texto) <= 400 else texto[:397] + "…"


def _auditoria(cur, _id_unidade: int, f: dict) -> Saida:
    """O registro de quem fez o quê, no período — com o que mudou escrito por extenso.

    🔑 Pedido do dono (lista de relatórios, item 12, 23/10/2026). Para quando aparece
    uma dúvida ("quem mudou o preço do pão?").
    ⚠️ **A origem diz POR ONDE**: "tela" (nula, migração 077) ou "claude" (chave de
    máquina). É a coluna que responde "o que o Claude fez ontem?".
    ⚠️ Credencial nunca chega aqui: `auditoria._limpar` já a tira na gravação.
    """
    inicio, fim = _periodo(f)
    usuarios = _lista(f.get("usuarios"))
    entidades = _lista(f.get("entidades"))
    cur.execute(
        """SELECT a.em, a.entidade, a.id_entidade, a.acao, a.antes, a.depois, a.origem,
                  u.nome AS usuario, un.nome AS loja
             FROM auditoria a
             LEFT JOIN usuarios u ON u.id = a.id_usuario
             LEFT JOIN unidades un ON un.id = a.id_unidade
            WHERE a.em >= %(inicio)s::date AND a.em < %(fim)s::date + 1
              AND (%(usuarios)s::int[] IS NULL OR a.id_usuario = ANY(%(usuarios)s))
              AND (%(entidades)s::text[] IS NULL OR a.entidade = ANY(%(entidades)s))
            ORDER BY a.em, a.id""",
        {"inicio": inicio, "fim": fim, "entidades": entidades,
         "usuarios": [int(u) for u in usuarios] if usuarios else None})
    linhas = []
    por_pessoa: dict[str, dict] = {}
    por_entidade: dict[str, dict] = {}
    for r in cur.fetchall():
        d = dict(r)
        d["quando"] = d["em"].strftime("%d/%m/%Y %H:%M:%S")
        d["usuario"] = d["usuario"] or "(sistema)"
        d["origem_txt"] = d["origem"] or "tela"
        d["mudou"] = _mudou(d["antes"], d["depois"])
        linhas.append(d)
        g = por_pessoa.setdefault(d["usuario"], {"chave": d["usuario"], "eventos": 0})
        g["eventos"] += 1
        g = por_entidade.setdefault(d["entidade"], {"chave": d["entidade"], "eventos": 0})
        g["eventos"] += 1
    return Saida(
        linhas,
        [("quando", "Quando"), ("usuario", "Quem"), ("origem_txt", "Por onde"),
         ("entidade", "O quê"), ("id_entidade", "Id"), ("acao", "Ação"),
         ("loja", "Loja"), ("mudou", "O que mudou")],
        f"Auditoria — {_intervalo(inicio, fim)}",
        [("Eventos", len(linhas)), ("Pessoas", len(por_pessoa)),
         ("Pelo Claude", sum(1 for l in linhas if l["origem"] == "claude"))],
        inicio, fim,
        anexos=[(sorted(por_pessoa.values(), key=lambda g: -g["eventos"]),
                 [("chave", "Quem"), ("eventos", "Eventos")], "Por pessoa", None),
                (sorted(por_entidade.values(), key=lambda g: -g["eventos"]),
                 [("chave", "O quê"), ("eventos", "Eventos")], "Por assunto", None)]
        if linhas else [])


# ---------------------------------------------------------------------------
# As etiquetas emitidas (23/10/2026, pedido do dono, fora da lista de 12)
# ---------------------------------------------------------------------------

# ⚠️ Textos CURTOS de propósito: a linha tem quinze colunas, e no PDF a largura de
# cada uma é proporcional ao texto — a situação longa espremia o código da etiqueta.
SITUACOES_ETIQUETA = {"vigente": "no prazo", "vencida": "VENCIDA", "USADA": "usada",
                      "DESCARTADA": "descartada", "SUBSTITUIDA": "substituída"}
_CONSERVACAO_CURTA = {"REFRIGERADO": "refrig.", "CONGELADO": "congel.", "AMBIENTE": "ambiente"}
FILTROS["situacao_etiqueta"] = {
    "tipo": "multipla", "rotulo": "Situação", "ajuda": "todas",
    "opcoes": lambda _c, _u: [{"valor": v, "nome": n} for v, n in SITUACOES_ETIQUETA.items()]}
FILTROS["eventos_etiqueta"] = {
    "tipo": "multipla", "rotulo": "Evento", "ajuda": "produzido, aberto e descongelado",
    "opcoes": lambda _c, _u: [{"valor": v, "nome": n} for v, n in
                              (("PRODUCAO", "Produzido"), ("ABERTURA", "Aberto"),
                               ("DESCONGELAMENTO", "Descongelado"))]}
FILTROS["busca_etiqueta"] = {"tipo": "texto", "rotulo": "Produto, código ou lote contém",
                             "ajuda": "todas as etiquetas"}
FILTROS["periodo_etiqueta"] = {"tipo": "periodo", "rotulo": "Emitidas entre",
                               "ajuda": "o mês corrente, se não escolher"}


def _etiquetas(cur, id_unidade: int, f: dict) -> Saida:
    """Todas as etiquetas emitidas no período, LINHA A LINHA — o papel da conferência.

    🔑 Pedido do dono (23/10/2026): *"listar todas as etiquetas emitidas … linha a linha,
    não quadrado para colar, e sim um pdf para conferência"*. A folha de etiquetas (os
    quadrados) é a rota de impressão; isto é a LISTA delas, para conferir a câmara fria.
    ⚠️ O período é o da EMISSÃO (`feito_em`): "o que se etiquetou na semana". A
    situação "vencida" é a ativa que passou do prazo AGORA — o banco não a guarda,
    porque ela muda sozinha com o relógio.
    ⚠️ "Resta" é a `quantidade` (migração 107: o que sobrou no pote); "Inicial", a de
    nascença. A diferença é o que saiu por uso parcial.
    """
    from services import etiquetas as etq

    inicio, fim = (f.get("inicio") or relogio.hoje_da_casa().replace(day=1),
                   f.get("fim") or relogio.hoje_da_casa())
    situacoes = _lista(f.get("situacao_etiqueta"))
    eventos = _lista(f.get("eventos_etiqueta"))
    locais = [int(x) for x in _lista(f.get("locais")) or []] or None
    busca = (f.get("busca_etiqueta") or "").strip()
    cur.execute(
        """SELECT e.codigo, p.codigo AS cod_produto, p.nome AS produto, e.evento,
                  e.conservacao, e.feito_em, e.vence_em, e.status, e.quantidade,
                  coalesce(e.quantidade_inicial, e.quantidade) AS inicial, e.um,
                  l.nome AS local, e.lote, e.responsavel, e.baixada_em, e.motivo,
                  e.impressoes, (e.status = 'ATIVA' AND e.vence_em < now()) AS vencida
             FROM etiquetas e
             JOIN produtos p ON p.id = e.id_produto
             LEFT JOIN locais_estoque l ON l.id = e.id_local
            WHERE e.id_unidade = %(u)s
              AND e.feito_em::date BETWEEN %(inicio)s AND %(fim)s
              AND (%(eventos)s::text[] IS NULL OR e.evento = ANY(%(eventos)s))
              AND (%(locais)s::int[] IS NULL OR e.id_local = ANY(%(locais)s))
              AND (%(busca)s = '' OR p.nome ILIKE '%%' || %(busca)s || '%%'
                   OR p.codigo ILIKE '%%' || %(busca)s || '%%'
                   OR e.codigo ILIKE '%%' || %(busca)s || '%%'
                   OR e.lote ILIKE '%%' || %(busca)s || '%%')
            ORDER BY e.feito_em, e.id""",
        {"u": id_unidade, "inicio": inicio, "fim": fim, "eventos": eventos,
         "locais": locais, "busca": busca})
    linhas = []
    for r in cur.fetchall():
        d = dict(r)
        chave = (("vencida" if d["vencida"] else "vigente") if d["status"] == "ATIVA"
                 else d["status"])
        if situacoes and chave not in situacoes:
            continue
        d["situacao"] = SITUACOES_ETIQUETA.get(chave, chave)
        # ⚠️ Evento e conservação numa célula: a linha já tem quinze colunas, e no papel
        # deitado cada coluna a mais aperta o nome do produto.
        d["evento_txt"] = (f"{etq.EVENTOS.get(d['evento'], d['evento'])} · "
                           f"{_CONSERVACAO_CURTA.get(d['conservacao'], d['conservacao'])}")
        d["feito"] = d["feito_em"].strftime("%d/%m/%y %H:%M")
        d["vence"] = d["vence_em"].strftime("%d/%m/%y %H:%M")
        d["baixada"] = d["baixada_em"].strftime("%d/%m/%y %H:%M") if d["baixada_em"] else None
        d["confere"] = "[   ]"
        d["_chave"] = chave
        linhas.append(d)

    por_sit: dict[str, dict] = {}
    for l in linhas:
        g = por_sit.setdefault(l["_chave"], {"chave": l["situacao"], "etiquetas": 0})
        g["etiquetas"] += 1
    por_produto: dict[str, dict] = {}
    for l in linhas:
        g = por_produto.setdefault(l["produto"], {"chave": l["produto"], "etiquetas": 0,
                                                  "ativas": 0})
        g["etiquetas"] += 1
        g["ativas"] += 1 if l["status"] == "ATIVA" else 0
    resumo = [("Emitidas no período", len(linhas)),
              ("Ativas no prazo", sum(1 for l in linhas if l["_chave"] == "vigente")),
              ("Ativas VENCIDAS", sum(1 for l in linhas if l["_chave"] == "vencida")),
              ("Usadas", sum(1 for l in linhas if l["_chave"] == "USADA")),
              ("Descartadas", sum(1 for l in linhas if l["_chave"] == "DESCARTADA"))]
    return Saida(
        linhas,
        [("confere", "OK"), ("codigo", "Etiqueta"), ("produto", "Produto"),
         ("evento_txt", "Evento"), ("feito", "Feita em"),
         ("vence", "Vence em"), ("situacao", "Situação"), ("inicial", "Inicial"),
         ("quantidade", "Resta"), ("um", "Un."), ("local", "Local"), ("lote", "Lote"),
         ("responsavel", "Responsável"), ("baixada", "Baixada em"), ("motivo", "Motivo")],
        f"Etiquetas emitidas — {_intervalo(inicio, fim)}", resumo, inicio, fim,
        anexos=[([por_sit[k] for k in SITUACOES_ETIQUETA if k in por_sit],
                 [("chave", "Situação"), ("etiquetas", "Etiquetas")], "Por situação", None),
                (sorted(por_produto.values(), key=lambda g: (-g["etiquetas"], g["chave"])),
                 [("chave", "Produto"), ("etiquetas", "Etiquetas"), ("ativas", "Ativas")],
                 "Por produto", None)] if linhas else [])


RELATORIOS: dict[str, Relatorio] = {
    "saldos": Relatorio(
        "Posição de estoque", "O que existe hoje, por produto e prateleira, com o valor.",
        "estoque.saldos", "estoque",
        ("locais", "setores", "categorias", "tipos_produto", "produtos"), _saldos),
    "saldos-rede": Relatorio(
        "Posição de estoque da rede",
        "O mesmo, somando as lojas: uma linha por produto, com o custo médio ponderado.",
        "estoque.saldos", "estoque",
        ("setores", "categorias", "tipos_produto", "produtos"), _saldos_rede),
    "movimentos": Relatorio(
        "Razão de estoque", "Cada movimento do período, com saldo e custo médio depois dele.",
        "estoque.saldos", "movimentos",
        ("periodo", "tipos_movimento", "locais", "produtos", "busca", "provisorio"),
        _movimentos),
    "produtos": Relatorio(
        "Cadastro de produtos",
        "A ficha de cadastro de cada item. A planilha leva todos os campos; o PDF, os principais.",
        "cadastros.produtos", "produtos",
        ("tipos_produto", "categorias", "setores", "situacao"), _produtos),
    "pessoas": Relatorio(
        "Cadastro de pessoas",
        "Fornecedores, equipe e quem consome: contato, política do cupom e compras. "
        "A planilha leva todos os campos; o PDF, os principais.",
        "cadastros.fornecedores", "pessoas",
        ("tipo_pessoa", "situacao_pessoa", "busca_pessoa"), _pessoas),
    "vencimentos": Relatorio(
        "Lotes a vencer", "O que vence, quando, onde e quanto vale.",
        "estoque.saldos", "vencimentos", ("dias", "locais"), _vencimentos),
    "cmv": Relatorio(
        "Apuração do CMV",
        "A conta aberta linha a linha, com o quadro da aba do painel junto.",
        "cmv.relatorios", "cmv", ("periodo_cmv", "aba"), _cmv),
    "abc": Relatorio(
        "Curva ABC de insumos", "Onde o dinheiro do consumo se concentra.",
        "cmv.relatorios", "curva-abc", ("periodo", "classes"), _abc),
    "movimentacao": Relatorio(
        "Movimentação do estoque", "Inicial, entradas, saídas e final de cada produto.",
        "cmv.relatorios", "movimentacao",
        ("periodo", "categorias", "setores"), _movimentacao),
    "memoria-cmv": Relatorio(
        "Memória de cálculo do CMV",
        "A apuração aberta nos documentos: estoque inicial e final item a item, "
        "as compras por nota e a conciliação com o total das notas.",
        "cmv.relatorios", "cmv", ("periodo",), _memoria_cmv),
    # ⚠️ A chave é `inventario-valorizado`, não `inventario`: já existe a rota
    # `/exportar/inventario/{id}` — a folha de CONTAGEM. Dois endereços parecidos
    # para documentos diferentes é a divergência que só aparece no dia em que
    # alguém baixa o errado e manda ao contador.
    "inventario-valorizado": Relatorio(
        "Inventário valorizado",
        "O estoque numa data: item, quantidade, custo unitário e valor — o documento do balanço.",
        "estoque.saldos", "estoque",
        ("data", "categorias", "setores", "tipos_produto", "produtos"), _inventario),
    "memoria-produto": Relatorio(
        "Memória de cálculo por produto",
        "Um insumo movimento a movimento, com a conta do custo médio escrita em cada linha.",
        "estoque.saldos", "movimentos", ("periodo", "produtos"), _memoria_produto),
    # 🔑 O estudo de vendas (21/10/2026, pedido do dono): o recorte do painel de
    # vendas, com os produtos na frente e os quadros do painel atrás.
    "vendas": Relatorio(
        "Estudo de vendas",
        "O período escolhido: totais e a comparação com o anterior, os produtos, a "
        "evolução, o dia da semana, a hora, a categoria e o setor.",
        "cmv.relatorios", "vendas",
        ("periodo", "agrupar", "categorias", "setores", "produtos"), _vendas),
    "consumo-pessoa": Relatorio(
        "Consumo por pessoa",
        "O que cada um consumiu, quanto custaria e quanto está sendo cobrado — "
        "o documento para cobrar o funcionário.",
        "cmv.relatorios", "vendas",
        ("situacao_consumo", "periodo_consumo", "pessoas", "detalhe"), _consumo_pessoa),
    "precos": Relatorio(
        "Evolução de preço",
        "O que subiu, quanto pesou e com quem sai mais barato, com o peso por setor junto.",
        "cmv.relatorios", "precos", ("periodo",), _precos),
    # 🔑 **O que mudou de preço aqui e ainda não mudou no caixa** (08/10/2026,
    # pedido do dono). Só leitura do PDV — funciona com o envio desligado, que é
    # justamente quando a lista importa.
    "precos-pdv": Relatorio(
        "Preços a acertar no PDV",
        "Os produtos com um preço aqui e outro na tabela do PDV: o código de lá, o "
        "preço que está no caixa e o que deveria estar.",
        "precificacao.analisar", "precos-pdv", (), _precos_pdv),
    # 🔑 Os quatro de 23/10/2026 (pedido do dono: "mais relatorios e planilhas").
    "compras": Relatorio(
        "Compras",
        "O que se comprou no período: por nota, por fornecedor, por produto ou item a item.",
        "compras.notas", "compras",
        ("periodo", "detalhe_compras", "situacao_nota", "busca_fornecedor",
         "categorias", "setores"), _compras),
    "perdas": Relatorio(
        "Perdas e ajustes",
        "Quanto se perdeu e por quê: perdas por motivo, diferenças de inventário e "
        "ajustes de saldo — com as sobras abatendo.",
        "estoque.saldos", "perdas",
        ("periodo", "detalhe_perdas", "motivos", "locais", "setores", "categorias"),
        _perdas),
    "margem": Relatorio(
        "Margem dos pratos",
        "Cada prato vendido no período: custo, preço, CMV %, lucro e o preço mínimo "
        "para a margem da casa.",
        "precificacao.analisar", "margem-pratos", ("periodo", "categorias", "setores"),
        _margem),
    "recebimentos": Relatorio(
        "Recebimentos do consumo",
        "Os lotes de cobrança recebidos no período, com o total por forma de pagamento.",
        "consumo.periodos", "recebimentos", ("periodo", "formas", "pessoas"),
        _recebimentos),
    # 🔑 A segunda leva (23/10/2026, itens 5 e 7; o 4, o livro de fichas, é rota própria
    # em `routers/exportacoes.py` porque cada ficha é um documento inteiro).
    "producao": Relatorio(
        "Produção",
        "O que a cozinha produziu no período, produção a produção ou por produto, com o custo.",
        "estoque.saldos", "producao",
        ("periodo", "detalhe_producao", "origem_producao", "categorias", "setores"),
        _producoes),
    "agenda-producao": Relatorio(
        "Agenda de produção do dia",
        "O planejado do dia (e o atrasado), para a bancada — com o que separar de insumos.",
        "producao.agenda", "agenda-producao", ("data",), _agenda_producao),
    "vendas-documentos": Relatorio(
        "Vendas documento a documento",
        "Cada cupom do período com hora, origem, canal, pessoa e total — para conferir "
        "com o caixa e o PDV.",
        "cmv.relatorios", "vendas-documentos", ("periodo", "origem_venda"),
        _vendas_documentos),
    # 🔑 A terceira leva (23/10/2026, itens 8 e 9).
    "reservas-dia": Relatorio(
        "Reservas do dia",
        "Quem vem, a que horas, quantas pessoas e em que mesa — a folha da recepção.",
        "reservas.ver", "reservas-do-dia", ("data", "situacao_reserva"), _reservas_dia),
    "pedidos": Relatorio(
        "Pedidos do cardápio",
        "Os pedidos do site e da mesa no período: pedido a pedido ou o que mais sai, "
        "com os totais por situação e por modo.",
        "pedidos.ver", "pedidos", ("periodo", "situacao_pedido", "detalhe_pedidos"),
        _pedidos),
    # 🔑 A quarta leva (23/10/2026, itens 10, 11 e 12).
    "fidelidade": Relatorio(
        "Fidelidade",
        "Os participantes com os selos do cartão e os prêmios, e os prêmios emitidos no "
        "período: usados, vencidos e a usar.",
        "fidelidade.operar", "fidelidade", ("recorte_fidelidade", "periodo_premios"),
        _fidelidade),
    "acessos": Relatorio(
        "Usuários e acessos",
        "Quem entra no sistema, com que papel e quando entrou pela última vez — ou o que "
        "cada papel pode fazer.",
        "admin.usuarios", "acessos", ("detalhe_acessos",), _acessos),
    "auditoria": Relatorio(
        "Auditoria",
        "Quem fez o quê no período, por onde (tela ou Claude) e o que mudou.",
        "admin.auditoria", "auditoria", ("periodo", "usuarios", "entidades"), _auditoria),
    # 🔑 A lista das etiquetas para conferência (23/10/2026, pedido do dono).
    "etiquetas": Relatorio(
        "Etiquetas emitidas",
        "Cada etiqueta emitida no período, linha a linha: produto, evento, feita e vence, "
        "situação, quanto resta, local, lote e responsável — para conferir.",
        "etiquetas.imprimir", "etiquetas",
        ("periodo_etiqueta", "situacao_etiqueta", "eventos_etiqueta", "locais",
         "busca_etiqueta"), _etiquetas),
}


def catalogo(cur, id_unidade: int, pode: Callable[[str], bool]) -> list[dict]:
    """Os relatórios que ESTA pessoa pode exportar, com as opções já resolvidas.

    ⚠️ As opções vêm resolvidas de propósito: sem isso o diálogo precisaria de
    quatro requisições a mais só para saber o que oferecer, e a tela piscaria
    quatro vezes antes de deixar escolher.
    """
    # ⚠️ **Sem segunda loja, o relatório da rede é o de sempre com uma coluna a
    # mais** — oferecer os dois lado a lado faria escolher entre duas versões da
    # mesma coisa. Mesma regra do item de menu da remessa e da visão da rede.
    cur.execute("SELECT count(*) AS n FROM unidades WHERE ativo")
    varias_lojas = cur.fetchone()["n"] > 1

    saida = []
    for chave, r in RELATORIOS.items():
        if not pode(r.permissao):
            continue
        if chave == "saldos-rede" and not varias_lojas:
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
