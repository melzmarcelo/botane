"""Leitor do XML da NF-e — a entrada que não depende de integração nenhuma.

O fornecedor manda o XML por e-mail, ou o contador baixa do portal da SEFAZ.
Esse arquivo tem **mais** informação que a maioria das APIs: chave, emitente,
itens com EAN e NCM, lote e validade, e o frete já rateado por item quando o
emitente rateou.

O resultado sai no mesmo formato que o mapeador do Omie devolve, e por isso
segue exatamente o mesmo caminho: conciliação → conversão → rateio → razão.

Duas notas sobre robustez:

* **Namespace.** O XML da NF-e vem em `http://www.portalfiscal.inf.br/nfe`, mas
  já apareceu arquivo sem namespace nenhum (reprocessado por sistema de
  terceiro). Lemos sempre pelo nome local da tag.
* **Layout.** A 4.00 usa `dhEmi` (com fuso); a 3.10 usava `dEmi` (só data).
  Cada campo é procurado por uma lista de nomes, como no mapeador do Omie.
"""

from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

ZERO = Decimal("0")


class XmlInvalido(Exception):
    def __init__(self, mensagem: str):
        self.mensagem = mensagem
        super().__init__(mensagem)


# ---------------------------------------------------------------- navegação


def _tag(elemento) -> str:
    """Nome da tag sem o namespace: `{...}infNFe` → `infNFe`."""
    return elemento.tag.rsplit("}", 1)[-1]


def _filhos(pai, nome: str) -> list:
    return [f for f in pai if _tag(f) == nome] if pai is not None else []


def _filho(pai, *nomes):
    for nome in nomes:
        achados = _filhos(pai, nome)
        if achados:
            return achados[0]
    return None


def _texto(pai, *nomes) -> str | None:
    """Texto do primeiro filho encontrado, procurando em profundidade."""
    if pai is None:
        return None
    for nome in nomes:
        for elemento in pai.iter():
            if _tag(elemento) == nome and (elemento.text or "").strip():
                return elemento.text.strip()
    return None


def _direto(pai, *nomes) -> str | None:
    """Como `_texto`, mas só entre os filhos diretos.

    Necessário onde o mesmo nome existe em dois níveis: `vProd` aparece no item
    e no total da nota, e procurar em profundidade pegaria o errado.
    """
    if pai is None:
        return None
    for nome in nomes:
        for filho in _filhos(pai, nome):
            if (filho.text or "").strip():
                return filho.text.strip()
    return None


def _num(valor) -> Decimal:
    if valor is None or valor == "":
        return ZERO
    try:
        return Decimal(str(valor).replace(",", "."))
    except InvalidOperation:
        return ZERO


def _data(valor: str | None) -> str | None:
    """`2026-08-16T10:00:00-03:00` ou `2026-08-16` vira `2026-08-16`."""
    if not valor:
        return None
    valor = valor.strip()
    return valor[:10] if len(valor) >= 10 else None


def _digitos(valor: str | None) -> str | None:
    if not valor:
        return None
    limpo = "".join(c for c in valor if c.isdigit())
    return limpo or None


# ---------------------------------------------------------------- leitura


def _somar(elemento, *nomes) -> Decimal:
    """Soma todas as ocorrências dos nomes dentro do elemento.

    Os impostos que encarecem a compra estão espalhados por grupos diferentes
    conforme o regime (`ICMS10`, `ICMS70`, `ICMSST`...). Somar por nome evita
    ter de conhecer os vinte grupos da tabela.
    """
    total = ZERO
    for filho in elemento.iter():
        if _tag(filho) in nomes:
            total += _num(filho.text)
    return total


def _item(det, seq: int) -> dict:
    prod = _filho(det, "prod")
    if prod is None:
        raise XmlInvalido(f"Item {seq} do XML não tem o grupo <prod>.")

    imposto = _filho(det, "imposto")
    # IPI, ST e FCP-ST entram no custo de aquisição; o ICMS próprio, não — ele
    # já está dentro do valor do produto.
    outros = ZERO
    if imposto is not None:
        outros = _somar(imposto, "vIPI", "vICMSST", "vFCPST", "vFCPSTRet")
    outros += _num(_direto(prod, "vOutro")) + _num(_direto(prod, "vSeg"))

    ean = _direto(prod, "cEAN", "cEANTrib")
    if ean and ean.strip().upper() in ("SEM GTIN", "0"):
        ean = None

    rastro = _filho(prod, "rastro")
    lote = _texto(rastro, "nLote") if rastro is not None else None
    validade = _data(_texto(rastro, "dVal")) if rastro is not None else None

    quantidade = _num(_direto(prod, "qCom")) or _num(_direto(prod, "qTrib"))
    unitario = _num(_direto(prod, "vUnCom")) or _num(_direto(prod, "vUnTrib"))
    total = _num(_direto(prod, "vProd")) or (quantidade * unitario)

    return {
        "seq": seq,
        "descricao_fornecedor": (_direto(prod, "xProd") or f"Item {seq}")[:200],
        "codigo_fornecedor": _direto(prod, "cProd"),
        "codigo_barras": ean,
        "ncm": _direto(prod, "NCM"),
        "quantidade": quantidade,
        "um_nota": _direto(prod, "uCom") or _direto(prod, "uTrib"),
        "valor_unitario": unitario,
        "valor_total": total,
        "valor_desconto": _num(_direto(prod, "vDesc")),
        # O emitente já rateou? Então não se rateia de novo — ver `calcular_nota`.
        # `vFrete` ausente e `vFrete` igual a zero são coisas DIFERENTES: zero é
        # o emitente dizendo "neste item não há frete", e tratá-lo como ausente
        # jogaria o item no rateio e cobraria dele um frete que a nota não pôs.
        "frete_informado": (_num(bruto_frete) if (bruto_frete := _direto(prod, "vFrete"))
                            is not None else None),
        "outros_informado": outros if outros else None,
        "lote_nf": lote,
        "validade_nf": validade,
    }


def ler(conteudo) -> dict:
    """Lê o XML e devolve a nota no formato do importador.

    Levanta `XmlInvalido` com uma frase que a tela possa mostrar: o usuário
    arrasta o arquivo errado o tempo todo (o PDF do DANFE, o recibo do envio) e
    precisa saber qual foi.
    """
    if isinstance(conteudo, bytes):
        # A NF-e é UTF-8 por norma, mas arquivo salvo pelo Windows aparece em
        # latin-1. Errar o acento no nome do fornecedor não vale uma exceção.
        try:
            conteudo = conteudo.decode("utf-8")
        except UnicodeDecodeError:
            conteudo = conteudo.decode("latin-1", errors="replace")
    conteudo = conteudo.lstrip("﻿ \r\n\t")

    try:
        raiz = ElementTree.fromstring(conteudo)
    except ElementTree.ParseError as e:
        raise XmlInvalido(f"Arquivo não é um XML válido ({e}).") from e

    inf = next((e for e in raiz.iter() if _tag(e) == "infNFe"), None)
    if inf is None:
        if _tag(raiz) in ("retEnviNFe", "retConsSitNFe", "procEventoNFe", "evento"):
            raise XmlInvalido(
                "Este XML é o recibo/evento da nota, não a nota. "
                "Procure o arquivo que começa com <nfeProc> ou <NFe>."
            )
        raise XmlInvalido(
            "Não encontrei a NF-e neste arquivo. O esperado é o XML da nota "
            "(<nfeProc> ou <NFe>), não o DANFE em PDF."
        )

    ide = _filho(inf, "ide")
    emit = _filho(inf, "emit")
    dest = _filho(inf, "dest")
    total = _filho(inf, "total")
    icms_tot = _filho(total, "ICMSTot") if total is not None else None

    chave = _digitos((inf.get("Id") or "").replace("NFe", ""))
    if chave and len(chave) != 44:
        chave = None

    itens = [_item(det, i) for i, det in enumerate(_filhos(inf, "det"), start=1)]
    if not itens:
        raise XmlInvalido("A nota não tem itens.")

    # Se ALGUM item traz o valor rateado, o rateio é do emitente e vale para a
    # nota inteira: quem não trouxe recebeu zero. Sem isso, os itens sem a tag
    # cairiam no rateio por valor e o frete seria cobrado duas vezes.
    for campo in ("frete_informado", "outros_informado"):
        if any(i[campo] is not None for i in itens):
            for i in itens:
                i[campo] = i[campo] if i[campo] is not None else ZERO

    soma_produtos = sum((i["valor_total"] for i in itens), ZERO)

    nota = {
        "chave_nfe": chave,
        "numero": _direto(ide, "nNF"),
        "serie": _direto(ide, "serie"),
        "modelo": _direto(ide, "mod"),
        "cnpj_emitente": _direto(emit, "CNPJ", "CPF"),
        "nome_emitente": _direto(emit, "xNome"),
        "cnpj_destinatario": _direto(dest, "CNPJ", "CPF"),
        "nome_destinatario": _direto(dest, "xNome"),
        "data_emissao": _data(_direto(ide, "dhEmi", "dEmi")),
        "data_entrada": _data(_direto(ide, "dhSaiEnt", "dSaiEnt")),
        "valor_produtos": _num(_direto(icms_tot, "vProd")) or soma_produtos,
        "valor_frete": _num(_direto(icms_tot, "vFrete")) + _num(_direto(icms_tot, "vSeg")),
        "valor_desconto": _num(_direto(icms_tot, "vDesc")),
        "valor_outros": (_num(_direto(icms_tot, "vIPI")) + _num(_direto(icms_tot, "vST"))
                         + _num(_direto(icms_tot, "vFCPST")) + _num(_direto(icms_tot, "vOutro"))),
        "valor_total": _num(_direto(icms_tot, "vNF")) or soma_produtos,
        "itens": itens,
    }
    nota["data_entrada"] = nota["data_entrada"] or nota["data_emissao"]
    return nota


def conferir(nota: dict, cnpj_empresa: str | None) -> list[str]:
    """Avisos que valem a pena mostrar, sem impedir a importação.

    Nenhum destes é erro fatal: a casa pode ter mais de um CNPJ, e cupom de
    supermercado é compra legítima. Mas importar a nota de outra empresa por
    engano estraga o custo, e é barato avisar.
    """
    avisos = []
    meu, dele = _digitos(cnpj_empresa), _digitos(nota.get("cnpj_destinatario"))
    if meu and dele and meu != dele:
        avisos.append(
            f"O destinatário desta nota é {nota.get('nome_destinatario') or dele}, "
            "que não é o CNPJ da empresa. Confira se é mesmo uma compra da casa."
        )
    if nota.get("modelo") == "65":
        avisos.append("É um cupom fiscal (NFC-e). Entra igual, só não tem fornecedor formal.")
    if not nota.get("chave_nfe"):
        avisos.append(
            "Sem chave de acesso: não dá para garantir que esta nota não entre duas vezes."
        )
    soma = sum((i["valor_total"] for i in nota["itens"]), ZERO)
    declarado = nota.get("valor_produtos") or ZERO
    if declarado and abs(soma - declarado) > Decimal("0.05"):
        avisos.append(
            f"A soma dos itens ({soma}) não bate com o total de produtos declarado ({declarado})."
        )
    return avisos
