"""Modelos de vendas e CMV."""

from datetime import date, time

from pydantic import BaseModel, Field


class ItemVenda(BaseModel):
    id_produto: int | None = None
    codigo: str | None = None          # alternativa ao id: o código do produto
    descricao: str | None = None
    quantidade: float = Field(gt=0)
    valor_unitario: float = Field(default=0, ge=0)
    # 🔑 **O preço de tabela, antes da política da pessoa** (04/09/2026).
    # ⚠️ **Quem preenche é o SERVIDOR, nunca o cliente.** `_aplicar_politica` o
    # grava ao reescrever o valor, e `importar` o zera antes disso — aceitá-lo
    # de fora deixaria qualquer chamador declarar um desconto que não houve, e
    # o relatório de consumo somaria um desconto inventado.
    valor_unitario_cheio: float | None = None


class VendaImportar(BaseModel):
    data: date
    # 🔑 **A HORA do cupom.** A coluna existe desde o começo e o mapeador do PDV
    # já a lia — ela só nunca chegava ao `INSERT`, e o dado morria no caminho.
    # ⚠️ Opcional porque a planilha não a tem: quem digita venda do dia informa
    # o dia, e inventar meia-noite seria pior que não ter.
    hora: time | None = None
    documento: str | None = Field(default=None, max_length=40)
    canal: str | None = None
    origem: str = "PLANILHA"
    # 🔑 **O cupom cancelado ENTRA, marcado** (pedido do dono, 03/09/2026).
    # Antes ele era descartado na preparação, e o efeito era a conferência não
    # fechar: o PDV dizia 164 cupons no dia e o Botané mostrava 154, sem nada
    # explicando os 10 — e quem confere não tem como saber se sumiram ou se
    # foram excluídos de propósito. Marcado, ele aparece, não move estoque e
    # não conta em receita nenhuma (tudo que soma filtra `NOT cancelada`).
    cancelada: bool = False
    # 🔑 **O desconto do cupom** (pedido do dono, 03/09/2026). A coluna
    # `vendas.desconto` existe desde o começo e nunca foi preenchida: o Botané
    # gravava a soma dos ITENS (bruto) e o PDV informa o valor cobrado
    # (líquido). Medido na conta real: 02/09 diferia 26,50, 29/08 diferia 13,50,
    # 28/08 diferia 722,00 — em todos, exatamente o desconto do dia.
    # ⚠️ Receita é o DENOMINADOR do food cost: receita inflada faz o food cost
    # parecer melhor do que é, que é o mesmo erro silencioso do custo zero.
    desconto: float = 0
    # 🔑 **A PESSOA do cupom** (04/09/2026, pedido do dono). A venda lançada à
    # mão sempre puxa o preço de venda; informando a pessoa, ela passa a valer o
    # CUSTO ou o preço com desconto, conforme a política do cadastro dela. É o
    # desconto de funcionário e o consumo do proprietário com a mesma mecânica.
    # ⚠️ Só a venda MANUAL usa isto. O cupom que vem do PDV traz os valores
    # cobrados de verdade, e reescrevê-los aqui inventaria receita.
    id_pessoa: int | None = None
    itens: list[ItemVenda]


class ImportarVendasRequest(BaseModel):
    vendas: list[VendaImportar]


class PreviaCupomRequest(BaseModel):
    """O que a tela de lançamento pergunta antes de gravar: quanto vai sair.

    🔑 **Existe para que a regra tenha UMA implementação** (04/09/2026, pedido
    do dono: "que o valor fosse ajustado ao digitar para ter esta percepção
    visual"). A tela poderia multiplicar pelo desconto sozinha, mas o CUSTO ela
    não sabe calcular — ele vem da mesma cascata da ficha — e as duas contas
    divergiriam no dia em que a cascata mudasse. Aqui a prévia sai do MESMO
    código que o lançamento usa.
    """

    id_pessoa: int | None = None
    itens: list[ItemVenda]


class VendaResponse(BaseModel):
    id: int
    data: date
    hora: time | None = None
    origem: str
    canal: str | None = None
    documento: str | None = None
    valor_total: float
    cancelada: bool
    itens: int = 0
    sem_custo: int = 0


class ApuracaoResponse(BaseModel):
    inicio: date
    fim: date
    estoque_inicial: float
    compras: float
    estoque_final: float
    cmv_real: float
    cmv_teorico: float
    variancia: float
    variancia_pct: float | None = None
    perdas: float
    consumo_interno: float
    ajustes: float
    # ⚠️ Efeito NO CMV da reavaliação de custo, já com o sinal invertido:
    # estoque reavaliado para cima deixa o CMV MENOR. Sem esta linha o número
    # mudaria sem explicação — o produto não se moveu, só passou a valer outra
    # coisa. Campo novo tem de entrar aqui também, senão sai do serviço e não
    # chega à tela, calado.
    ajuste_custo: float = 0
    receita: float
    vendas: int
    itens_sem_custo: int
    cobertura_ficha_pct: float
    food_cost_pct: float | None = None
    fechado: bool = False
    # O ritmo em que esta loja fecha, e como o período se chama. Vão na
    # apuração porque é a tela que mostra os dois lado a lado — e uma tela que
    # diz "agosto" enquanto o fechamento congela a semana mente sobre si mesma.
    ciclo: str = "MENSAL"
    rotulo: str | None = None
    # Os grupos que a casa montou por tipo de produto — quanto do CMV é
    # material de limpeza, embalagem, o que ela tiver separado. Grupo marcado
    # como fora do CMV traz `considerar_no_cmv: false` e o valor dele NÃO está
    # no `cmv_real`.
    grupos: list[dict] = Field(default_factory=list)
    tipos_fora_do_cmv: list[str] = Field(default_factory=list)


class GrupoCmvRequest(BaseModel):
    nome: str = Field(min_length=2, max_length=60)
    # ⚠️ Lista de TIPOS de produto, não de produtos. Vazia é legítima: o grupo
    # existe e ainda não recebeu tipo nenhum — some do painel até receber.
    tipos: list[str] = Field(default_factory=list)
    ordem: int = Field(default=0, ge=0, le=999)
    ativo: bool = True
    # ⚠️ Falso tira os produtos destes tipos do CMV real — do estoque inicial,
    # das compras e do estoque final. É o que separa comida de detergente no
    # food cost. O grupo continua aparecendo no painel, à parte.
    considerar_no_cmv: bool = True


class GrupoCmvResponse(BaseModel):
    id: int
    nome: str
    tipos: list[str]
    ordem: int
    ativo: bool
    considerar_no_cmv: bool = True


class FechamentoRequest(BaseModel):
    # ⚠️ Qualquer dia DENTRO do período a fechar. O tamanho do período vem da
    # configuração da loja (`parametros.ciclo_fechamento`), não daqui: mandar o
    # ciclo no pedido deixaria a tela fechar num ritmo e o razão travar noutro.
    competencia: date


class FechamentoResponse(BaseModel):
    id: int
    competencia: date
    inicio: date
    fim: date
    estoque_inicial: float
    compras: float
    estoque_final: float
    cmv_real: float
    cmv_teorico: float
    variancia: float
    perdas: float
    consumo_interno: float
    ajustes: float
    receita: float
    food_cost_pct: float | None = None
    status: str
    ciclo: str = "MENSAL"
    rotulo: str | None = None
    fechado_por: str | None = None
    fechado_em: str | None = None
