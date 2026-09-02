"""Modelos do produto — o cadastro central do sistema."""

from datetime import date, datetime

from pydantic import BaseModel, Field

# ⚠️ A ordem é a que aparece nas telas, e os três últimos ficam juntos de
# propósito: são os tipos que entram no custo pela porta dos insumos sem serem
# comida. É o que os grupos do CMV separam.
#
# ⚠️ `UTENSILIO` não é só mais um "não comida": é o único que não é CONSUMIDO.
# Marmita sai com o pedido, detergente acaba — uma taça vive meses e some num
# sábado. Por isso tem grupo próprio no CMV (migração 037) e não entra no de
# limpeza.
#
# ⚠️ Esta tupla é a fonte única: `cmv_grupos`, `inventario_selecao` e o router do
# CMV a importam. Não há CHECK no banco — tipo novo se adiciona aqui.
TIPOS = (
    "INSUMO",
    "REVENDA",
    "PRODUZIDO",
    "KIT",
    "EMBALAGEM",
    "MATERIAL_LIMPEZA",
    "UTENSILIO",
)
STATUS = ("RASCUNHO", "ATIVO", "ARQUIVADO")


class FornecedorDoProduto(BaseModel):
    id_fornecedor: int
    codigo_no_fornecedor: str | None = None
    embalagem: str | None = None
    fator: float = Field(default=1, gt=0)
    ultimo_preco: float | None = None
    preferencial: bool = False


class ProdutoBase(BaseModel):
    nome: str = Field(min_length=2, max_length=160)
    nome_curto: str | None = Field(default=None, max_length=60)
    tipo: str = "INSUMO"
    id_categoria: int | None = None
    id_setor: int | None = None
    producao_propria: bool = False
    controla_estoque: bool = True
    um_estoque: str | None = Field(default=None, max_length=6)
    um_compra: str | None = Field(default=None, max_length=6)
    fator_compra: float = Field(default=1, gt=0)
    # Onde este produto entra quando chega numa nota. O congelado e o seco vêm
    # na mesma folha: um local por NOTA obrigaria a lançar duas vezes.
    id_local_padrao: int | None = None
    # PARA_ESTOQUE: produz, guarda, sai depois (a massa de pizza).
    # NA_HORA: a venda produz e baixa junto (o café passado).
    modo_producao: str = "PARA_ESTOQUE"
    perecivel: bool = False
    validade_dias: int | None = Field(default=None, ge=0, le=3650)
    controla_lote: bool = False
    controla_validade: bool = False
    estoque_minimo: float | None = Field(default=None, ge=0)
    estoque_maximo: float | None = Field(default=None, ge=0)
    ncm: str | None = Field(default=None, max_length=10)
    # ⚠️ Vêm do cadastro do Omie e são COMPLETADOS na sincronização — nunca
    # sobrescritos. Quem corrigiu à mão corrigiu porque o dado de lá estava
    # errado; reimportar não pode desfazer conserto.
    cest: str | None = Field(default=None, max_length=10)
    marca: str | None = Field(default=None, max_length=60)
    # O líquido é o que interessa: o bruto inclui a embalagem, e ninguém cozinha
    # o papelão. É ele que resolve "o pacote entra por UN e a ficha pede KG".
    peso_liquido: float | None = Field(default=None, ge=0)
    peso_bruto: float | None = Field(default=None, ge=0)
    codigo_barras: str | None = Field(default=None, max_length=20)
    codigo_omie: str | None = Field(default=None, max_length=40)
    # ⚠️ Espelho do `codigo_omie` para o PDV Legal. Com os DOIS preenchidos, o
    # cadastro é o mesmo produto nas duas integrações — e isso se lê na tela.
    codigo_pdv: str | None = Field(default=None, max_length=40)
    integrado_pdv: bool = False
    observacao: str | None = None


class UnidadeCompra(BaseModel):
    um: str = Field(min_length=1, max_length=6)
    # Quantas unidades de ESTOQUE vêm em uma desta.
    fator: float = Field(gt=0)
    padrao: bool = False
    observacao: str | None = Field(default=None, max_length=120)


class UnidadesCompraRequest(BaseModel):
    itens: list[UnidadeCompra] = Field(default_factory=list)


class VincularRequest(BaseModel):
    """Qual cadastro SAI. O que fica é o da tela, no caminho da rota.

    ⚠️ O que sai é o que não tem história — movimento, ficha, nota, contagem. O
    servidor confere e recusa nomeando o que trava, porque escolher errado a
    direção é o engano natural: quem olha dois nomes parecidos não tem como
    saber qual dos dois carrega o passado.
    """

    id_sai: int
    # ⚠️ **Fecha o buraco do estoque, e por isso vem LIGADO.** O item do cardápio
    # vendia sem baixar; sem esta saída o resultado seria "comprou 15, vendeu 10,
    # saldo 15", e as 10 faltando apareceriam na primeira contagem como ajuste de
    # inventário — onde a diferença some sem nome. Desligar é para quem prefere
    # deixar a contagem resolver, sabendo disso.
    baixar_vendas: bool = True


class KitItem(BaseModel):
    id_componente: int
    quantidade: float = Field(default=1, gt=0)
    observacao: str | None = Field(default=None, max_length=120)


class KitRequest(BaseModel):
    itens: list[KitItem] = Field(default_factory=list)


class ProdutoCreate(ProdutoBase):
    # Em branco, o sistema gera um sequencial — ninguém precisa inventar código.
    codigo: str | None = Field(default=None, max_length=40)
    status: str = "ATIVO"
    preco_venda: float | None = Field(default=None, ge=0)
    fornecedores: list[FornecedorDoProduto] = []


class ProdutoUpdate(ProdutoBase):
    nome: str | None = Field(default=None, min_length=2, max_length=160)
    codigo: str | None = Field(default=None, max_length=40)
    tipo: str | None = None
    fator_compra: float | None = Field(default=None, gt=0)
    id_local_padrao: int | None = None
    modo_producao: str | None = None
    producao_propria: bool | None = None
    controla_estoque: bool | None = None
    perecivel: bool | None = None
    controla_lote: bool | None = None
    controla_validade: bool | None = None
    status: str | None = None
    ativo: bool | None = None
    preco_venda: float | None = Field(default=None, ge=0)
    fornecedores: list[FornecedorDoProduto] | None = None


class PrecoDaLoja(BaseModel):
    """O preço desta loja. Nulo APAGA o dela e devolve o da casa.

    ⚠️ Nulo não é zero: zero é um preço (de graça), e apagar é outra coisa —
    é dizer "aqui vale o da casa".
    """

    preco_venda: float | None = Field(default=None, ge=0)


class CodigoExterno(BaseModel):
    """Um código de fora que aponta para um produto daqui.

    ⚠️ `sistema` é o ESPAÇO DE NOME, e ele importa: o código que vem na linha
    da nota (o do fornecedor) e o identificador do produto no Omie são coisas
    diferentes que podem ter o mesmo valor. Misturá-los é a família do erro que
    ligou REDBULL a LIMÃO TAITY.
    """

    sistema: str
    codigo: str
    descricao_externa: str | None = None
    fator: float | None = None
    origem_vinculo: str | None = None
    confirmado_em: datetime | None = None
    fornecedor: str | None = None
    confirmado_por: str | None = None


class ProdutoResponse(BaseModel):
    id: int
    codigo: str
    nome: str
    nome_curto: str | None = None
    tipo: str
    id_categoria: int | None = None
    categoria: str | None = None
    id_setor: int | None = None
    setor: str | None = None
    producao_propria: bool
    controla_estoque: bool
    um_estoque: str | None = None
    um_compra: str | None = None
    fator_compra: float
    id_local_padrao: int | None = None
    local_padrao: str | None = None
    modo_producao: str = "PARA_ESTOQUE"
    perecivel: bool
    validade_dias: int | None = None
    controla_lote: bool
    controla_validade: bool
    estoque_minimo: float | None = None
    estoque_maximo: float | None = None
    ncm: str | None = None
    cest: str | None = None
    marca: str | None = None
    peso_liquido: float | None = None
    peso_bruto: float | None = None
    codigo_barras: str | None = None
    # ⚠️ **O código interno do Omie** — o id de lá, que a casa não escolhe. É
    # por ele que o vínculo sobrevive quando alguém troca o `codigo` da casa, e
    # é o nível 2 da cascata de conciliação, antes do EAN. A tela mostra sem
    # deixar editar; a API aceita alteração porque consertar um de-para errado é
    # trabalho de quem administra.
    codigo_omie: str | None = None
    codigo_pdv: str | None = None
    integrado_pdv: bool | None = None
    # Os códigos EXTRAS do cardápio que apontam para este produto: "ENTREGA" tem
    # quatro na conta real, e um campo só perderia três.
    apelidos_pdv: list[str] = []
    # 🔑 **Todos os códigos de fora que apontam para este produto.** É o que
    # responde ao caso do ABACATE: o catálogo do Omie cria um cadastro por
    # fornecedor, e juntá-los só é confiável se dá para VER que aquele cadastro
    # já responde por cinco códigos de lá.
    codigos_externos: list[CodigoExterno] = []
    sincronizado_em: datetime | None = None
    origem: str
    status: str
    observacao: str | None = None
    ativo: bool
    criado_em: datetime | None = None
    preco_venda: float | None = None
    preco_desde: date | None = None
    fornecedores: list[dict] = []
    # 🔑 Os DOIS, para a tela dizer de quem é o número. "R$ 12,00" sem dono não
    # responde se esta loja cobra isso ou se herdou da casa.
    preco_casa: float | None = None
    preco_loja: float | None = None


class ProdutoResumo(BaseModel):
    """O que a lista precisa — sem carregar fornecedor e histórico de preço."""

    id: int
    codigo: str
    nome: str
    tipo: str
    categoria: str | None = None
    setor: str | None = None
    um_estoque: str | None = None
    producao_propria: bool
    controla_estoque: bool
    status: str
    ativo: bool
    preco_venda: float | None = None


class ContagemProdutos(BaseModel):
    total: int
    por_tipo: dict[str, int]
    rascunhos: int
    inativos: int
