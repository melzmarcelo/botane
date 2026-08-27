"""Tradução da resposta do Omie para o modelo do Botané.

⚠️ **É o único arquivo que precisa mudar quando a credencial real chegar.** O
formato dos campos aqui foi montado a partir da documentação pública; o nome
exato de cada chave só se confirma batendo na conta do cliente. Todo o resto do
importador (de-para, rateio, conversão, lançamento) é lógica nossa e não depende
disso.

Por isso cada leitura passa por `_pega`, que aceita uma lista de nomes possíveis:
quando o campo vier com outro nome, é uma linha de mudança, não um refactor.
"""

import re
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


# O rodapé de tributos aproximados que a Lei 12.741 manda imprimir no DANFE.
# ⚠️ Ele vem GRUDADO na descrição do produto, e daí para o cadastro: numa conta
# real, 59 produtos se chamavam "MAMÃO FORMOSA Trib. Aprox. (Fed: R$ 3,63. Est:
# R$ 3,24. ). Fonte: IBPT/empresometro.com.br/25.2.E." — nome que não cabe em
# tela nenhuma e que nenhuma busca por "mamão formosa" encontraria inteiro.
# Não é parte do nome de nada: é texto fiscal, e o corte é seguro.
_RODAPE_FISCAL = re.compile(
    r"\s*(trib(\.|\s)*aprox|val(or)?\s*aprox|fonte:\s*ibpt)\b.*$", re.IGNORECASE | re.DOTALL
)


def _nome_limpo(valor, padrao: str) -> str:
    texto = str(valor if valor not in (None, "") else padrao)
    return _RODAPE_FISCAL.sub("", texto).strip() or padrao


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
        "descricao_fornecedor": _nome_limpo(
            _pega(prod, "cDescricao", "descricao", "descr"), "(sem descrição)")[:200],
        "codigo_fornecedor": str(_pega(prod, "cCodigo", "codigo", "cCodProd", padrao="") or "")[:60]
        or None,
        "codigo_barras": (_so_digitos(_pega(prod, "cEAN", "codigo_barras", "cCodigoBarras"))
                          or "")[:20] or None,
        # Dígitos, pelo mesmo motivo do cadastro: é por ele que o item da
        # nota reconhece o produto, e pontuado num lado só nunca casaria.
        "ncm": (_so_digitos(_pega(prod, "cNCM", "ncm")) or "")[:10] or None,
        "quantidade": _numero(_pega(prod, "nQuantidade", "quantidade", "qtde")),
        "um_nota": str(_pega(prod, "cUnidade", "unidade", "und", padrao="") or "").upper()[:6]
        or None,
        "valor_unitario": _numero(_pega(prod, "nValorUnitario", "valor_unitario", "vUnCom")),
        "valor_total": _numero(_pega(prod, "nValorTotal", "valor_total", "vProd")),
        "valor_desconto": _numero(_pega(prod, "nValorDesconto", "valor_desconto")),
        "lote_nf": str(_pega(bruto, "cLote", "lote", padrao="") or "") or None,
        "validade_nf": _data(_pega(bruto, "dValidade", "validade")),
    }


def _acessorias_do_emitente(itens: list[dict], frete_nota, outros_nota) -> None:
    """Reconhece o rateio que o emitente JÁ fez, item a item.

    ⚠️ **O `vTotalItem` do Omie vem com o frete e o IPI/ST embutidos.** Numa
    nota real: `vTotalProdutos` 256,00 + `vFrete` 40,00 = `vTotalNFe` 296,00 —
    e o item, de 2 × 128,00, aparecia com `vTotalItem` **296,00**. Tratando
    isso como mercadoria e rateando o frete de novo por cima, o queijo entrava
    no estoque a 336,00: **13,5% acima da nota**, contaminando custo médio,
    ficha e CMV. Foram R$ 74,44 a mais em 30 notas.

    A regra é a mesma que o XML da NF-e já seguia: **quando o emitente rateou,
    o rateio é dele**. A sobra de cada item (`vTotalItem` menos a mercadoria
    líquida) vira acessória informada, e quem não tem sobra recebe ZERO — senão
    o rateio por valor entraria em cima do que já veio distribuído.

    A sobra mistura frete com IPI/ST; a divisão entre os dois acompanha a
    proporção da NOTA, para as colunas da tela continuarem dizendo a verdade.
    O que importa para o custo é a soma, e ela é exata.
    """
    if not any(dec(i.get("_sobra") or 0) > 0 for i in itens):
        for item in itens:
            item.pop("_sobra", None)
        return
    peso_frete = (frete_nota / (frete_nota + outros_nota)
                  if (frete_nota + outros_nota) > 0 else Decimal(1))
    for item in itens:
        sobra = dec(item.pop("_sobra", 0) or 0)
        frete = (sobra * peso_frete).quantize(Decimal("0.01"))
        item["frete_informado"] = frete
        item["outros_informado"] = sobra - frete


def recebimento_de_nfe(bruto: dict) -> dict:
    """Uma nota do `ListarRecebimentos` / `ConsultarRecebimento`.

    ⚠️ **É este o módulo onde moram as notas de compra de verdade.** O
    `produtos/notaentrada` (mapeado acima) é o lançamento manual de nota do
    Omie: na conta do cliente ele tinha UMA nota, de 2024, enquanto o
    recebimento de NF-e tinha 3.670. Quem só olhasse o primeiro concluiria que
    a casa não compra nada.

    A resposta da LISTA e a do DETALHE têm o mesmo cabeçalho; só o detalhe traz
    `itensRecebimento`. Por isso o mesmo mapeador serve aos dois — a lista vira
    uma nota sem itens, que é exatamente o que se precisa para decidir se vale
    a chamada cara do detalhe.
    """
    cab = _pega(bruto, "cabec", "cabecalho", padrao={}) or {}
    total = _pega(bruto, "totais", padrao={}) or {}
    info = _pega(bruto, "infoAdicionais", "infoCadastro", padrao={}) or {}

    # O Omie manda o número zerado à esquerda ("000034194"), como no DANFE.
    numero = str(_pega(cab, "cNumeroNFe", "cNumero", padrao="") or "").strip()

    frete_nota = _numero(_pega(total, "vFrete", "vTotalFrete", "nValFrete"))
    outros_nota = (_numero(_pega(total, "vTotalIPI", "vIPI"))
                   + _numero(_pega(total, "vTotalICMSST", "vICMSST"))
                   + _numero(_pega(total, "vOutrasDespesas", "vOutro")))
    itens = [item_do_recebimento(i, seq) for seq, i in
             enumerate(_pega(bruto, "itensRecebimento", "itens", padrao=[]) or [], start=1)]
    _acessorias_do_emitente(itens, frete_nota, outros_nota)

    return {
        "id_omie": str(_pega(cab, "nIdReceb", "nCodRecebimento", padrao="") or "") or None,
        "chave_nfe": _so_digitos(_pega(cab, "cChaveNFe", "chave_nfe")),
        "numero": (numero.lstrip("0") or numero) or None,
        "serie": str(_pega(cab, "cSerieNFe", "cSerie", padrao="") or "") or None,
        "cnpj_emitente": _so_digitos(_pega(cab, "cCNPJ_CPF", "cCNPJCPF", "cnpj_cpf")),
        "nome_emitente": _pega(cab, "cRazaoSocial", "cNome"),
        "data_emissao": _data(_pega(cab, "dEmissaoNFe", "dDtEmissao")),
        # Entrada é a data em que a nota foi REGISTRADA — a emissão pode ser de
        # dias antes, e é a chegada que move o estoque.
        "data_entrada": _data(_pega(info, "dRegistro", "dDtRegistro")
                              or _pega(cab, "dEmissaoNFe")),
        "valor_produtos": _numero(_pega(total, "vTotalProdutos", "vProdutos")),
        "valor_frete": _numero(_pega(total, "vFrete", "vTotalFrete", "nValFrete")),
        # ⚠️ Só o desconto que NÃO está nos itens. O `vTotalDescontos` da nota é
        # a SOMA dos `vDesconto` de cada item — descontar os dois tira o mesmo
        # dinheiro duas vezes. Numa nota real, dois cafés de 27,55 com 1,36 de
        # desconto cada entravam a 23,47 em vez de 26,19: 10% a menos.
        "valor_desconto": max(
            _numero(_pega(total, "vTotalDescontos", "vDescontos", "vDesconto"))
            - sum((dec(i["valor_desconto"]) for i in itens), Decimal(0)),
            Decimal(0),
        ),
        "valor_outros": (_numero(_pega(total, "vTotalIPI", "vIPI"))
                         + _numero(_pega(total, "vTotalICMSST", "vICMSST"))
                         + _numero(_pega(total, "vOutrasDespesas", "vOutro"))),
        "valor_total": _numero(_pega(total, "vTotalNFe") or _pega(cab, "nValorNFe")),
        # `cEtapa` é o estágio do recebimento no Omie (a conta real tinha 40 e
        # 80 convivendo). Não filtra nada aqui — a nota entra como IMPORTADA e
        # só vira estoque quando alguém lança —, mas fica à vista no bruto.
        "etapa_omie": str(_pega(cab, "cEtapa", padrao="") or "") or None,
        "itens": itens,
    }


def item_do_recebimento(bruto: dict, seq: int) -> dict:
    """Um item de `itensRecebimento` — os dados úteis moram em `itensCabec`."""
    cab = _pega(bruto, "itensCabec", padrao={}) or bruto
    quantidade = _numero(_pega(cab, "nQtdeNFe", "nQuantidade"))
    preco = _numero(_pega(cab, "nPrecoUnit", "nValorUnitario"))
    desconto = _numero(_pega(cab, "vDesconto", "nValorDesconto"))
    total_item = _numero(_pega(cab, "vTotalItem", "nValorTotal"))
    return {
        "seq": int(_pega(cab, "nSequencia", padrao=seq) or seq),
        "descricao_fornecedor": _nome_limpo(
            _pega(cab, "cDescricaoProduto", "cDescricao"), "(sem descrição)")[:200],
        "codigo_fornecedor": str(_pega(cab, "cCodigoProduto", "cCodigo", padrao="") or "")[:60]
        or None,
        # O id interno do produto no Omie. É por ele que o item reconhece o
        # produto que veio do catálogo — identidade do sistema, não texto.
        "codigo_omie": str(_pega(cab, "nIdProduto", padrao="") or "") or None,
        "codigo_barras": (_so_digitos(_pega(cab, "cEAN", "cCodigoBarras")) or "")[:20] or None,
        "ncm": (_so_digitos(_pega(cab, "cNCM", "ncm")) or "")[:10] or None,
        "quantidade": quantidade,
        # ⚠️ A unidade da nota vem com pontuação de DANFE ("BB.", "CX."). Sem
        # limpar, nenhuma comparação com a unidade do cadastro casaria.
        "um_nota": "".join(
            c for c in str(_pega(cab, "cUnidadeNfe", "cUnidade", padrao="") or "").upper()
            if c.isalnum()
        )[:6] or None,
        "valor_unitario": preco,
        # ⚠️ Mercadoria = quantidade × preço, NÃO o `vTotalItem`: aquele já traz
        # as acessórias que o emitente rateou (ver `_acessorias_do_emitente`).
        "valor_total": quantidade * preco,
        "valor_desconto": desconto,
        # O que sobra entre o total do item e a mercadoria líquida: é o rateio
        # do emitente. Some do dicionário assim que for distribuído.
        "_sobra": max(total_item - (quantidade * preco - desconto), Decimal(0)),
        # Item que alguém já marcou para ignorar no Omie entra ignorado aqui:
        # obrigar a repetir a decisão nas duas telas é como não ter integração.
        "ignorado": str(_pega(cab, "cIgnorarItem", padrao="N")).upper() == "S",
        "lote_nf": None,
        "validade_nf": None,
    }


def produto_do_catalogo(bruto: dict) -> dict:
    """Um produto do `ListarProdutos`, para a carga inicial do cadastro.

    ⚠️ **Todo texto sai aparado no tamanho da coluna.** O mundo real não
    respeita largura de campo: numa conta de verdade o "código" do produto era
    a descrição inteira ("Impermeabilizante 300g Veda Tudo Milagroso", 42
    caracteres) e derrubava a importação dos 2.198 no `varchar(40)`. Aparar
    aqui — na fronteira, onde o dado externo entra — é o que impede um cadastro
    esquisito de um fornecedor de parar a carga da casa inteira.
    """
    return {
        "codigo_omie": str(_pega(bruto, "codigo_produto", "nCodProd", padrao="") or "")[:40]
        or None,
        "codigo": str(_pega(bruto, "codigo", "cCodigo", padrao="") or "")[:40] or None,
        "nome": _nome_limpo(_pega(bruto, "descricao", "cDescricao"), "(sem nome)")[:160],
        "um": str(_pega(bruto, "unidade", "cUnidade", padrao="") or "").upper()[:6] or None,
        # ⚠️ NCM só em DÍGITOS. O Omie devolve pontuado ("0405.10.00") e às
        # vezes com sufixo ("2202.99.00.05", 13 caracteres) — um só desses
        # derrubava a importação inteira no varchar(10). Guardar pontuado
        # também tornaria impossível comparar com o NCM que vem no XML da nota,
        # que vem sem pontos.
        "ncm": (_so_digitos(_pega(bruto, "ncm", "cNCM")) or "")[:10] or None,
        "codigo_barras": (_so_digitos(_pega(bruto, "ean", "codigo_barras", "cEAN")) or "")[:20]
        or None,
        "valor_unitario": _numero(_pega(bruto, "valor_unitario", "nValorUnitario")),
        "inativo": str(_pega(bruto, "inativo", padrao="N")).upper() == "S",

        # ------------------------------------------------- o que passou a vir
        # ⚠️ Cada campo por uma LISTA de nomes possíveis, como todo o resto
        # deste arquivo: o Omie mistura dialetos (`descricao` e `cDescricao`) e
        # o que chega depende do módulo que respondeu.
        "marca": (_pega(bruto, "marca", "cMarca") or "")[:60] or None,
        "cest": (_so_digitos(_pega(bruto, "cest", "cCest", "codigo_cest")) or "")[:10] or None,
        # ⚠️ **O líquido é o que interessa** — o bruto inclui a embalagem, e
        # ninguém cozinha o papelão. Os dois vêm porque o cadastro do Omie às
        # vezes só tem um deles preenchido.
        "peso_liquido": _numero(_pega(bruto, "peso_liq", "peso_liquido", "nPesoLiq")) or None,
        "peso_bruto": _numero(_pega(bruto, "peso_bruto", "nPesoBruto")) or None,
        # A FAMÍLIA do Omie é a classificação que a casa já fez lá. Vira
        # categoria aqui — e é ela que faltava nos 2.189 produtos importados,
        # sem a qual o CMV por grupo e a curva ABC não separam nada.
        "familia": (_pega(bruto, "descricao_familia", "cDescrFamilia", "familia") or "")[:80]
        or None,
        "descricao_detalhada": (_pega(bruto, "descr_detalhada", "cDescrDetalhada") or "")[:2000]
        or None,
        "estoque_minimo": _numero(_pega(bruto, "estoque_minimo", "nEstoqueMinimo")) or None,
        # ⚠️ **O fornecedor do produto é opcional e pode não vir.** O
        # `ListarProdutos` do Omie não promete esse campo, e nas contas em que
        # ele não existe isto simplesmente fica nulo — o vínculo então vem das
        # NOTAS, que é onde ele existe de verdade. Ler aqui não custa nada e
        # aproveita a conta que o tiver preenchido.
        "codigo_fornecedor_omie": str(
            _pega(bruto, "codigo_fornecedor", "nCodFornecedor", "cCodFornecedor", padrao="")
            or ""
        )[:40] or None,
    }


def fornecedor_do_cadastro(bruto: dict) -> dict:
    """Um cadastro do `ListarClientes` — no Omie, fornecedor é cliente com tag."""
    return {
        "codigo_omie": str(_pega(bruto, "codigo_cliente_omie", "nCodCliente", padrao="") or "")[:40]
        or None,
        "nome": str(_pega(bruto, "razao_social", "cRazaoSocial", padrao="(sem nome)"))[:160],
        "nome_fantasia": (_pega(bruto, "nome_fantasia", "cNomeFantasia") or "")[:160] or None,
        "cnpj": (_so_digitos(_pega(bruto, "cnpj_cpf", "cCNPJCPF")) or "")[:20] or None,
        "email": (_pega(bruto, "email", "cEmail") or "")[:160] or None,
        "telefone": (_pega(bruto, "telefone1_numero", "cTelefone") or "")[:30] or None,
        "cidade": (_pega(bruto, "cidade", "cCidade") or "")[:80] or None,
        "uf": (_pega(bruto, "estado", "cUF", padrao="") or "")[:2] or None,
    }


def posicao_de_estoque(bruto: dict) -> dict:
    """Uma linha do `ListarPosEstoque` — traz o CMC, o custo médio do Omie.

    ⚠️ **`nCodProd` é o `codigo_omie`; `cCodigo` NÃO é.** A primeira versão lia
    `cCodigo`, que é o código da CASA registrado no Omie ("104304"), e comparava
    com `produtos.codigo_omie`, que guarda o id de lá ("7302593753"). Nunca
    casava — a conferência voltaria **vazia** mesmo com a chamada funcionando, e
    "nenhuma divergência" é indistinguível de "nenhum produto encontrado".
    Mesma família do erro que ligou REDBULL a LIMÃO TAITY: ler o identificador
    errado não dá erro em lugar nenhum.

    `codigo_da_casa` viaja junto porque é o que se mostra na tela — ninguém
    reconhece um produto por "7302593753".
    """
    return {
        "codigo_omie": str(_pega(bruto, "nCodProd", "codigo_produto", padrao="") or "") or None,
        "codigo_da_casa": str(_pega(bruto, "cCodigo", padrao="") or "") or None,
        "descricao": _pega(bruto, "cDescricao", "descricao"),
        "saldo": _numero(_pega(bruto, "nSaldo", "saldo")),
        "cmc": _numero(_pega(bruto, "nCMC", "cmc", "custo_medio")),
        "preco_unitario": _numero(_pega(bruto, "nPrecoUnitario", padrao=0)),
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
