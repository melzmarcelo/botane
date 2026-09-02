"""Modelos do estoque."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class SaldoResponse(BaseModel):
    id_produto: int
    codigo: str
    produto: str
    um_estoque: str | None = None
    id_local: int
    local: str
    quantidade: float
    custo_medio: float
    valor: float
    estoque_minimo: float | None = None
    abaixo_do_minimo: bool = False
    # 🔑 **Já despachado desta prateleira e ainda não recebido do outro lado.**
    # Continua dentro de `quantidade` — é isso que mantém o valor com dono
    # enquanto a mercadoria está no caminho —, mas quem olha o saldo para
    # despachar de novo precisa saber que parte dele já está na estrada.
    em_transito: float = 0
    atualizado_em: datetime | None = None


class SaldoDoLocal(BaseModel):
    id_local: int
    local: str
    setor: str | None = None
    quantidade: float
    valor: float


class SaldoAgrupadoResponse(BaseModel):
    """O saldo de um produto somando os LOCAIS de uma loja.

    🔑 **O processo da casa põe o mesmo produto em vários locais**: o açúcar
    entra no Estoque Central e de manhã cada setor leva um pacote para o seu
    canto. A lista por prateleira responde "onde está"; esta responde "quanto a
    loja tem", que é a pergunta de quem vai comprar.
    """

    id_produto: int
    codigo: str
    produto: str
    um_estoque: str | None = None
    quantidade: float
    valor: float
    # Ponderado, nunca a média dos médios — o mesmo da visão de empresa.
    custo_medio: float | None = None
    estoque_minimo: float | None = None
    abaixo_do_minimo: bool = False
    # Onde ele está, com o setor de cada prateleira quando ela tem um.
    por_local: list[SaldoDoLocal] = []


class SaldoDaLoja(BaseModel):
    id_unidade: int
    loja: str
    quantidade: float
    valor: float


class SaldoRedeResponse(BaseModel):
    """O saldo de um produto somando as lojas — a visão de EMPRESA.

    🔑 **Uma linha por produto, não por prateleira.** A tela da rede já dizia
    quanto vale o estoque da empresa; não dizia **de quê**. Para conferir um
    item era preciso trocar de loja e somar de cabeça — que é exatamente a conta
    que a visão consolidada existe para evitar.
    """

    id_produto: int
    codigo: str
    produto: str
    um_estoque: str | None = None
    quantidade: float
    valor: float
    # ⚠️ **Ponderado, nunca a média dos médios.** A matriz com 10 kg a R$ 40 e a
    # filial com 1 kg a R$ 52 dão R$ 41,09 na rede — não R$ 46. A média simples
    # daria o mesmo peso ao estoque grande e ao pequeno.
    # ⚠️ **E ele é NULO quando a rede tem zero daquele item**, porque é uma
    # divisão pela quantidade. Não é detalhe de tipagem: com "só com saldo"
    # desmarcado a lista traz esses produtos, e um `float` obrigatório fazia a
    # resposta INTEIRA morrer em 500 — a tela ficava vazia sem dizer por quê.
    # Zero também não serve: "não custa nada" e "não há nada para custar" se
    # leem igual, e só o primeiro é um custo. A tela mostra traço.
    custo_medio: float | None = None
    estoque_minimo: float | None = None
    abaixo_do_minimo: bool = False
    # Onde ele está. Só as lojas que a pessoa enxerga entram na soma.
    por_loja: list[SaldoDaLoja] = []


class SaldoRedeForaResponse(BaseModel):
    """Quanto a lista consolidada deixou de fora por o produto estar INATIVO.

    🔑 **Sem isto os dois números da empresa não fecham, e nada diz por quê.**
    O painel da rede conta `estoque_saldos` inteiro — é o que o CMV precisa:
    tirar o inativo do estoque final inflaria o custo. A lista de saldos filtra
    por ativo desde sempre, aqui e na visão de uma loja só. As duas regras estão
    certas, mas agora existe uma tela que promete EXPLICAR aquele total, e quem
    soma a coluna e compara com o painel conclui que um dos dois mente.

    ⚠️ **Segue os MESMOS filtros da lista.** Um número que responde por outro
    recorte é pior que número nenhum: diria "e mais R$ 24 mil" enquanto a tela
    mostra um produto só.
    """

    produtos: int
    valor: float


class MovimentoResponse(BaseModel):
    id: int
    data_movimento: datetime
    tipo: str
    rotulo: str
    id_produto: int
    produto: str
    codigo: str
    local: str
    quantidade: float
    custo_unitario: float
    custo_total: float
    # NOTA, PRODUCAO, VENDA, AJUSTE_LOTE… — o que originou o movimento.
    origem_tipo: str | None = None
    origem_id: int | None = None
    saldo_apos: float
    custo_medio_apos: float
    custo_provisorio: bool
    documento: str | None = None
    motivo: str | None = None
    observacao: str | None = None
    usuario: str | None = None
    estornado: bool = False
    id_estorno_de: int | None = None


class EntradaRequest(BaseModel):
    id_produto: int
    quantidade: float = Field(gt=0)
    custo_unitario: float = Field(ge=0)
    id_local: int | None = None
    data_movimento: datetime | None = None
    documento: str | None = Field(default=None, max_length=60)
    observacao: str | None = None
    lote: str | None = Field(default=None, max_length=40)
    validade: date | None = None


class SaidaRequest(BaseModel):
    id_produto: int
    quantidade: float = Field(gt=0)
    tipo: str = "SAIDA_CONSUMO_INTERNO"   # ou SAIDA_PERDA, SAIDA_VENDA
    id_local: int | None = None
    id_motivo_perda: int | None = None
    data_movimento: datetime | None = None
    observacao: str | None = None
    lote: str | None = None
    validade: date | None = None


class TransferenciaRequest(BaseModel):
    id_produto: int
    quantidade: float = Field(gt=0)
    id_local_origem: int
    id_local_destino: int
    observacao: str | None = None


class EstornoRequest(BaseModel):
    motivo: str | None = None


class ProducaoRequest(BaseModel):
    id_produto: int
    quantidade: float = Field(gt=0)
    id_local: int | None = None
    observacao: str | None = None


class InventarioCreate(BaseModel):
    """Os quatro filtros combinam com E, e vazio quer dizer "todos"."""

    nome: str | None = Field(default=None, max_length=80)
    data: date | None = None
    observacao: str | None = None
    # ⚠️ **Cega por padrão.** Ver o saldo esperado transforma a contagem em
    # conferência: a pessoa lê 12, olha a prateleira e escreve 12. O padrão
    # antigo era o contrário, e a opção certa ficava dependendo de alguém
    # lembrar de marcá-la.
    cega: bool = True

    # ⚠️ `id_local` continua aceito e é o caminho de sempre: um local só. Quando
    # vem, vale como `locais = [ele]` — nada do que já chamava esta API mudou.
    id_local: int | None = None
    locais: list[int] = Field(default_factory=list)
    setores: list[int] = Field(default_factory=list)
    categorias: list[int] = Field(default_factory=list)
    tipos: list[str] = Field(default_factory=list)
    # Lista explícita: entra mesmo sem saldo, porque quem nomeou sabe o que quer.
    produtos: list[int] = Field(default_factory=list)
    # 🔑 **Quem foi ESCALADO para contar esta contagem.** Vazio quer dizer
    # "qualquer um que tenha a permissão de contar" — que é o comportamento de
    # sempre, e o que faz as contagens antigas continuarem valendo.
    # ⚠️ Não é permissão, é escala: a permissão diz o que a pessoa sabe fazer;
    # isto diz quem está no turno de hoje. Misturar as duas obrigaria a mexer em
    # papel toda vez que a equipe mudasse.
    contadores: list[int] = Field(default_factory=list)


class InventarioRenomear(BaseModel):
    nome: str = Field(min_length=2, max_length=80)


class ContagemItem(BaseModel):
    id_produto: int
    # ⚠️ O local da linha. Só é obrigatório quando a contagem cobre mais de um
    # local E o produto aparece em dois — aí "o item do café" é ambíguo. Nas
    # contagens de um local só, continua desnecessário.
    id_local: int | None = None
    qtd_contada: float | None = Field(default=None, ge=0)
    # A unidade em que a pessoa CONTOU. Vazio = a de estoque, que é o padrão da
    # tela. Contar em caixa e deixar a conversão para a cabeça de quem conta é
    # onde o erro do inventário entra.
    um: str | None = Field(default=None, max_length=6)
    observacao: str | None = None


class ContagemRequest(BaseModel):
    itens: list[ContagemItem]


class InventarioResponse(BaseModel):
    id: int
    nome: str | None = None
    # ⚠️ Nulo quando a contagem cobre mais de um local — e aí `local` traz a
    # frase que descreve o recorte, não um nome de prateleira.
    id_local: int | None = None
    local: str
    data: date
    status: str
    cega: bool = False
    observacao: str | None = None
    criado_em: datetime | None = None
    fechado_em: datetime | None = None
    itens: list[dict] = []
    contados: int = 0
    total_itens: int = 0
    diferenca_valor: float | None = None
    # O que gerou a lista, para quem abrir a contagem meses depois entender por
    # que são aqueles produtos e não outros.
    filtros: dict | None = None
    # Quem foi escalado para contar. Vazio = qualquer um com a permissão.
    contadores: list[dict] = []


# ---------------------------------------------------------------------------
# Remessa entre lojas
# ---------------------------------------------------------------------------
class RemessaItem(BaseModel):
    id_produto: int
    quantidade: float = Field(gt=0)
    observacao: str | None = None


class RemessaCreate(BaseModel):
    id_local_origem: int
    id_local_destino: int
    itens: list[RemessaItem]
    observacao: str | None = None


class ItemConferido(BaseModel):
    id_item: int
    # ⚠️ Nulo quer dizer "chegou o que foi mandado" — o caso comum não precisa
    # ser digitado. Zero é uma afirmação diferente: conferi e não veio nada.
    qtd_recebida: float | None = Field(default=None, ge=0)
    id_motivo_perda: int | None = None
    observacao: str | None = None


class RecebimentoRequest(BaseModel):
    itens: list[ItemConferido] = []
    observacao: str | None = None
