"""Tradução da resposta do Omie para o modelo do Botané.

⚠️ **É o único arquivo que precisa mudar quando a credencial real chegar.** O
formato dos campos aqui foi montado a partir da documentação pública; o nome
exato de cada chave só se confirma batendo na conta do cliente. Todo o resto do
importador (de-para, rateio, conversão, lançamento) é lógica nossa e não depende
disso.

Por isso cada leitura passa por `_pega`, que aceita uma lista de nomes possíveis:
quando o campo vier com outro nome, é uma linha de mudança, não um refactor.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from services.custos import dec


def _pega(origem: dict, *nomes: str, padrao=None):
    for nome in nomes:
        if nome in origem and origem[nome] not in (None, ""):
            return origem[nome]
    return padrao


def _data(valor) -> date | None:
    """O Omie manda dd/mm/aaaa na maior parte dos campos."""
    if not valor:
        return None
    if isinstance(valor, (date, datetime)):
        return valor.date() if isinstance(valor, datetime) else valor
    texto = str(valor).strip()
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def _numero(valor) -> Decimal:
    if valor in (None, ""):
        return Decimal(0)
    if isinstance(valor, str):
        # "1.234,56" (pt-BR) e "1234.56" convivem nas respostas.
        valor = valor.replace(".", "").replace(",", ".") if "," in valor else valor
    return dec(valor)


def _so_digitos(valor) -> str | None:
    if not valor:
        return None
    limpo = "".join(c for c in str(valor) if c.isdigit())
    return limpo or None


def nota_de_entrada(bruto: dict) -> dict:
    """Uma nota do `ListarNotaEnt` / `ConsultarNotaEnt`."""
    cab = _pega(bruto, "nfCabecalho", "cabecalho", padrao={}) or {}
    total = _pega(bruto, "nfTotais", "totais", padrao={}) or {}
    emit = _pega(bruto, "nfEmitente", "emitente", "fornecedor", padrao={}) or {}
    info = _pega(bruto, "nfInfoCadastro", "infoCadastro", padrao={}) or {}

    return {
        "id_omie": str(_pega(bruto, "nCodNotaEnt", "nIdReceb", "nCodNF", padrao="") or "") or None,
        "chave_nfe": _so_digitos(_pega(cab, "cChaveNFe", "chave_nfe") or _pega(bruto, "cChaveNFe")),
        "numero": str(_pega(cab, "nNumero", "numero", padrao="") or "") or None,
        "serie": str(_pega(cab, "cSerie", "serie", padrao="") or "") or None,
        "cnpj_emitente": _so_digitos(_pega(emit, "cnpj_cpf", "cCNPJ", "cnpj")),
        "nome_emitente": _pega(emit, "razao_social", "cRazaoSocial", "nome_fantasia"),
        "data_emissao": _data(_pega(cab, "dDtEmissao", "data_emissao")),
        "data_entrada": _data(_pega(cab, "dDtEntrada", "data_entrada")
                              or _pega(info, "dInc", "data_inclusao")),
        "valor_produtos": _numero(_pega(total, "nValorProdutos", "valor_mercadorias")),
        "valor_frete": _numero(_pega(total, "nValorFrete", "valor_frete")),
        "valor_desconto": _numero(_pega(total, "nValorDesconto", "valor_desconto")),
        "valor_outros": _numero(_pega(total, "nValorIPI", "valor_ipi"))
                        + _numero(_pega(total, "nValorICMSST", "valor_st")),
        "valor_total": _numero(_pega(total, "nValorTotal", "valor_total")),
        "itens": [item_da_nota(i, seq) for seq, i in
                  enumerate(_pega(bruto, "det", "itens", "produtos", padrao=[]) or [], start=1)],
    }


def item_da_nota(bruto: dict, seq: int) -> dict:
    prod = _pega(bruto, "produto", "prod", padrao={}) or bruto
    return {
        "seq": int(_pega(bruto, "nSeqItem", "seq", padrao=seq) or seq),
        "descricao_fornecedor": str(
            _pega(prod, "cDescricao", "descricao", "descr", padrao="(sem descrição)")
        )[:200],
        "codigo_fornecedor": str(_pega(prod, "cCodigo", "codigo", "cCodProd", padrao="") or "")
        or None,
        "codigo_barras": _so_digitos(_pega(prod, "cEAN", "codigo_barras", "cCodigoBarras")),
        "ncm": str(_pega(prod, "cNCM", "ncm", padrao="") or "") or None,
        "quantidade": _numero(_pega(prod, "nQuantidade", "quantidade", "qtde")),
        "um_nota": str(_pega(prod, "cUnidade", "unidade", "und", padrao="") or "").upper() or None,
        "valor_unitario": _numero(_pega(prod, "nValorUnitario", "valor_unitario", "vUnCom")),
        "valor_total": _numero(_pega(prod, "nValorTotal", "valor_total", "vProd")),
        "valor_desconto": _numero(_pega(prod, "nValorDesconto", "valor_desconto")),
        "lote_nf": str(_pega(bruto, "cLote", "lote", padrao="") or "") or None,
        "validade_nf": _data(_pega(bruto, "dValidade", "validade")),
    }


def produto_do_catalogo(bruto: dict) -> dict:
    """Um produto do `ListarProdutos`, para a carga inicial do cadastro."""
    return {
        "codigo_omie": str(_pega(bruto, "codigo_produto", "nCodProd", padrao="") or "") or None,
        "codigo": str(_pega(bruto, "codigo", "cCodigo", padrao="") or "") or None,
        "nome": str(_pega(bruto, "descricao", "cDescricao", padrao="(sem nome)"))[:160],
        "um": str(_pega(bruto, "unidade", "cUnidade", padrao="") or "").upper() or None,
        "ncm": str(_pega(bruto, "ncm", "cNCM", padrao="") or "") or None,
        "codigo_barras": _so_digitos(_pega(bruto, "ean", "codigo_barras", "cEAN")),
        "valor_unitario": _numero(_pega(bruto, "valor_unitario", "nValorUnitario")),
        "inativo": str(_pega(bruto, "inativo", padrao="N")).upper() == "S",
    }


def fornecedor_do_cadastro(bruto: dict) -> dict:
    """Um cadastro do `ListarClientes` — no Omie, fornecedor é cliente com tag."""
    return {
        "codigo_omie": str(_pega(bruto, "codigo_cliente_omie", "nCodCliente", padrao="") or "")
        or None,
        "nome": str(_pega(bruto, "razao_social", "cRazaoSocial", padrao="(sem nome)"))[:160],
        "nome_fantasia": _pega(bruto, "nome_fantasia", "cNomeFantasia"),
        "cnpj": _so_digitos(_pega(bruto, "cnpj_cpf", "cCNPJCPF")),
        "email": _pega(bruto, "email", "cEmail"),
        "telefone": _pega(bruto, "telefone1_numero", "cTelefone"),
        "cidade": _pega(bruto, "cidade", "cCidade"),
        "uf": (_pega(bruto, "estado", "cUF", padrao="") or "")[:2] or None,
    }


def posicao_de_estoque(bruto: dict) -> dict:
    """Uma linha do `ListarPosEstoque` — traz o CMC, o custo médio do Omie."""
    return {
        "codigo_omie": str(_pega(bruto, "cCodigo", "codigo_produto", padrao="") or "") or None,
        "descricao": _pega(bruto, "cDescricao", "descricao"),
        "saldo": _numero(_pega(bruto, "nSaldo", "saldo")),
        "cmc": _numero(_pega(bruto, "nCMC", "cmc", "custo_medio")),
    }


def lista_de(dados: dict, *chaves: str) -> list[Any]:
    """Extrai a lista de registros da resposta, qualquer que seja o nome dela."""
    for chave in chaves:
        valor = dados.get(chave)
        if isinstance(valor, list):
            return valor
    for valor in dados.values():
        if isinstance(valor, list) and valor and isinstance(valor[0], dict):
            return valor
    return []
