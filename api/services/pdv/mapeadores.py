"""Traduz o cupom do PDV Legal para a venda do Botané.

⚠️ **Este é o único arquivo que muda quando o PDV Legal muda.** Cada campo é
lido por uma lista de nomes possíveis, como no mapeador do Omie: a plataforma
mistura convenções entre módulos, e um campo que hoje se chama `venda_id` pode
chegar como `vendaId` num endpoint vizinho.

A forma abaixo foi conferida **contra a conta real do cliente** em 26/08/2026,
não contra a documentação — é a lição do Omie, onde quatro campos que a doc
previa vinham vazios. O que se sabe está em `docs/pdv-legal-api.md`.
"""

from datetime import date, datetime
from decimal import Decimal

# O canal, traduzido para o vocabulário da casa. `tipovenda` é uma letra.
#
# ⚠️ Só o `B` foi visto num dia real; os outros vêm da documentação e do bom
# senso. Letra desconhecida vira `None` em vez de virar "BALCAO": inventar canal
# faria o relatório por canal mentir com cara de completo.
CANAIS = {
    "B": "BALCAO",
    "M": "SALAO",
    "D": "DELIVERY",
    "E": "EVENTO",
}


def _pega(origem: dict, *nomes: str, padrao=None):
    for nome in nomes:
        if nome in origem and origem[nome] not in (None, ""):
            return origem[nome]
    return padrao


def _numero(valor) -> Decimal:
    if valor in (None, ""):
        return Decimal(0)
    try:
        return Decimal(str(valor))
    except (ArithmeticError, ValueError):
        return Decimal(0)


def _data(valor) -> date | None:
    """`2026-08-26T00:00:00` → 26/08/2026.

    ⚠️ **`0001-01-01` é o vazio do .NET**, não uma data. Ele aparece em
    `dtestorno` e `dtcancelamento` de tudo o que não foi cancelado; tratá-lo como
    data poria vendas no ano 1 e o CMV de um período que não existe.
    """
    if not valor:
        return None
    texto = str(valor)[:19]
    try:
        d = datetime.fromisoformat(texto).date()
    except ValueError:
        return None
    return None if d.year <= 1 else d


def cupom(bruto: dict) -> dict:
    """Um cupom de venda — o cabeçalho.

    ⚠️ **A data que vale é `dtmovimento`**, a do negócio: ela vem com hora
    zerada e é a que diz em que dia a venda conta para o CMV. `dtrecebimento`
    tem a hora do caixa e viraria outro dia numa casa que fecha depois da
    meia-noite — a mesma armadilha do `toISOString()`.
    """
    return {
        # ⚠️ A identidade é `venda_id`, e é ela que faz reimportar não duplicar.
        # `codcupom` é o número do cupom fiscal e se repete entre filiais.
        "documento": str(_pega(bruto, "venda_id", "vendaId", "VendaId", padrao="") or "")
        or None,
        "cupom": str(_pega(bruto, "codcupom", "codCupom", padrao="") or "") or None,
        "filial": _pega(bruto, "loja_id", "lojaId", "CodFilial"),
        "data": _data(_pega(bruto, "dtmovimento", "dtMovimento"))
        or _data(_pega(bruto, "dtabertura", "dtAbertura")),
        "hora": str(_pega(bruto, "dtrecebimento", "dtabertura", padrao="") or "")[11:19] or None,
        # Cancelado OU estornado: são coisas diferentes lá e a mesma aqui — a
        # venda não conta.
        "cancelada": bool(_pega(bruto, "iscancelado", padrao=False))
        or bool(_pega(bruto, "isestornado", padrao=False)),
        "canal": CANAIS.get(str(_pega(bruto, "tipovenda", padrao="") or "").upper()[:1]),
        "valor_total": _numero(_pega(bruto, "valortotal", "valorTotal")),
        "desconto": _numero(_pega(bruto, "valordesconto", "valorDesconto")),
        "vendedor": (_pega(bruto, "nomeVendedor") or "")[:60] or None,
        "itens": [item(i) for i in (_pega(bruto, "itens", "Itens", padrao=[]) or [])],
        # 🔑 As finalizadoras (migração 160, pedido do dono de 24/11/2026). Vinham em todo
        # cupom e morriam aqui.
        "pagamentos": [p for p in (pagamento(x) for x in
                                   (_pega(bruto, "formaPgtos", "FormaPgtos", padrao=[]) or [])
                                   if isinstance(x, dict)) if p["valor"] > 0],
    }


# 🔑 **O grupo sai da CLASSIFICAÇÃO do PDV** (`codClassificacao`), que é do sistema; o nome
# ("CREDITO") é texto que o cliente edita lá. Conferido na conta real em 24/11/2026:
# 1 Dinheiro, 3 Crédito, 4 Débito, 12 Vale presente, 20 PIX estático, 22 Pagamento eletrônico
# (o "PIX WEB"). ⚠️ 21 não apareceu; pela tabela do PDV é o PIX dinâmico, e entra como PIX.
_GRUPO_DA_CLASSIFICACAO = {1: "DINHEIRO", 3: "CREDITO", 4: "DEBITO", 12: "VALE",
                           20: "PIX", 21: "PIX", 22: "PIX"}


def _grupo(classificacao, codigo_forma, nome: str) -> str:
    """O grupo da casa para uma linha de pagamento.

    ⚠️ **O TROCO vem com a classificação do DINHEIRO** (1) e `codformarecebimentopdv = -1`:
    testá-lo antes, senão o troco somaria como dinheiro recebido.
    ⚠️ Classificação desconhecida tenta o nome e, sem pista, vira OUTRO: aparece na tela como
    "Outro (nome do PDV)", em vez de sumir ou de cair num grupo inventado.
    """
    texto = (nome or "").upper()
    if str(codigo_forma) == "-1" or texto == "TROCO":
        return "TROCO"
    try:
        grupo = _GRUPO_DA_CLASSIFICACAO.get(int(classificacao))
    except (TypeError, ValueError):
        grupo = None
    if grupo:
        return grupo
    for pista, g in (("PIX", "PIX"), ("CRED", "CREDITO"), ("DEB", "DEBITO"),
                     ("DINHEIRO", "DINHEIRO"), ("VALE", "VALE")):
        if pista in texto:
            return g
    return "OUTRO"


def pagamento(bruto: dict) -> dict:
    """Uma linha de `formaPgtos`: quanto foi pago e em quê."""
    nome = str(_pega(bruto, "nome", "nomeExterno", padrao="") or "").strip()
    codigo_forma = _pega(bruto, "codformarecebimentopdv", "codFormaRecebimentoPdv")
    try:
        codigo_forma = int(codigo_forma) if codigo_forma is not None else None
    except (TypeError, ValueError):
        codigo_forma = None
    return {
        "grupo": _grupo(_pega(bruto, "codClassificacao", "codclassificacao"), codigo_forma, nome),
        "nome_pdv": nome[:60] or None,
        "cod_forma_pdv": codigo_forma,
        # ⚠️ Arredondado a centavo AQUI: o float do PDV (17.499999) não pode virar
        # `numeric(14,2)` diferente conforme o banco arredonda.
        "valor": _numero(_pega(bruto, "valortotal", "valorTotal")).quantize(Decimal("0.01")),
    }


def item(bruto: dict) -> dict:
    """Uma linha do cupom.

    ⚠️ **`valortotal` é o total da LINHA**, não o unitário. O unitário sai da
    divisão pela quantidade — e quantidade zero existe (cupom cancelado), então
    a divisão precisa de guarda ou o importador morre com `ZeroDivisionError` no
    meio de um dia de vendas.

    ⚠️ **`valorcusto` NÃO vira o nosso custo.** É o que o PDV acha que custou; o
    CMV teórico do Botané é `quantidade × custo da ficha daqui`. Trocar um pelo
    outro seria conferir a casa contra o cadastro do PDV — exatamente o que não
    se quer. Ele viaja como `custo_pdv` para quem quiser comparar, e nada mais.
    """
    quantidade = _numero(_pega(bruto, "quantidade", "qtd", padrao=0))
    total = _numero(_pega(bruto, "valortotal", "valorTotal"))
    unitario = (total / quantidade) if quantidade else Decimal(0)
    return {
        # O código do produto NO PDV — é a chave do de-para (`codigos_externos`
        # com `sistema = 'PDV_LEGAL'`).
        "codigo": str(_pega(bruto, "codproduto", "codProduto", padrao="") or "") or None,
        # O código do cardápio, que é o que o operador digita. Vai junto porque
        # é por ele que uma pessoa reconhece o item numa conferência.
        "codigo_cardapio": str(_pega(bruto, "codigoVenda", padrao="") or "") or None,
        "descricao": (_pega(bruto, "nomeProduto", "descricao") or "")[:200] or None,
        "quantidade": quantidade,
        "valor_unitario": unitario,
        "valor_total": total,
        "desconto": _numero(_pega(bruto, "valordesconto", "valorDesconto")),
        # ⚠️ Cancelamento por ITEM, além do cupom: um cupom válido pode ter uma
        # linha cancelada dentro, e contá-la infla a receita e o CMV teórico.
        "cancelado": bool(_pega(bruto, "iscancelado", padrao=False)),
        "custo_pdv": _numero(_pega(bruto, "valorcusto", "valorCusto")),
    }


def lista_de_cupons(dados) -> list[dict]:
    """A resposta do `cupom/get` — uma lista, mas nem sempre.

    Alguns endpoints da plataforma devolvem o objeto solto quando é um só. Tratar
    os dois casos aqui evita um `TypeError` no meio da importação de um dia com
    uma venda.
    """
    if isinstance(dados, dict):
        return [cupom(dados)]
    return [cupom(c) for c in (dados or []) if isinstance(c, dict)]
