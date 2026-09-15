"""Modelos da ficha técnica."""

from datetime import date, datetime

from pydantic import BaseModel, Field

STATUS = ("RASCUNHO", "HOMOLOGADA", "ARQUIVADA")


class ItemFicha(BaseModel):
    id_insumo: int | None = None
    id_subficha: int | None = None
    qtd_bruta: float = Field(gt=0)
    qtd_liquida: float | None = Field(default=None, ge=0)
    um: str | None = Field(default=None, max_length=6)
    fator_correcao: float = Field(default=1, gt=0)
    fator_coccao: float = Field(default=1, gt=0)
    observacao: str | None = None
    ordem: int = 0


class FichaCreate(BaseModel):
    id_produto: int
    rendimento_qtd: float = Field(default=1, gt=0)
    rendimento_um: str | None = Field(default=None, max_length=6)
    porcoes: float = Field(default=1, gt=0)
    # 🔑 **Quanto vale UMA porção**, na unidade do rendimento (migração 065,
    # pedido do dono 12/09/2026). Com ele a conta vai nos dois sentidos: o
    # rendimento dividido pelo tamanho dá as porções, e dividido pelas porções dá
    # o tamanho. ⚠️ Nulo é resposta: "ninguém informou", e a tela deriva sem
    # gravar palpite.
    porcao_qtd: float | None = Field(default=None, gt=0)
    tempo_preparo_min: int | None = Field(default=None, ge=0, le=6000)
    modo_preparo: str | None = None
    alergenos: str | None = None
    observacao: str | None = None
    itens: list[ItemFicha] = []


class FichaUpdate(BaseModel):
    rendimento_qtd: float | None = Field(default=None, gt=0)
    rendimento_um: str | None = None
    porcoes: float | None = Field(default=None, gt=0)
    # O tamanho da porção, como em `FichaCreate`.
    porcao_qtd: float | None = Field(default=None, gt=0)
    tempo_preparo_min: int | None = Field(default=None, ge=0, le=6000)
    modo_preparo: str | None = None
    alergenos: str | None = None
    observacao: str | None = None
    itens: list[ItemFicha] | None = None


class LocalDaFicha(BaseModel):
    """Quanto a receita rende quando produzida PARA esta prateleira.

    🔑 **Pedido do dono (12/09/2026):** a massa de pizza que fica como insumo e a
    que vai para a vitrine saem da mesma receita — mas a da vitrine vai ao forno,
    e o rendimento muda.

    ⚠️ `porcoes` e `porcao_qtd` são opcionais: o que sempre muda é o rendimento,
    e obrigar o porcionamento faria pedir um número que ninguém tem.
    """

    id_local: int
    rendimento_qtd: float = Field(gt=0)
    porcoes: float | None = Field(default=None, gt=0)
    porcao_qtd: float | None = Field(default=None, gt=0)
    observacao: str | None = Field(default=None, max_length=160)


class LocaisDaFichaRequest(BaseModel):
    """Substitui a tabela inteira de destinos — o mesmo contrato das embalagens
    do produto (`PUT /produtos/{id}/unidades`), para as duas telas se parecerem."""

    itens: list[LocalDaFicha] = Field(default_factory=list)


class ItemEmMontagem(BaseModel):
    """Uma linha da receita como ela está NA TELA — ainda sendo digitada.

    ⚠️ **`qtd_bruta` aceita ZERO aqui, e `ItemFicha` não.** Enquanto a pessoa
    escolhe o insumo e ainda não digitou a quantidade, a linha existe com zero —
    e recusar isso com 422 apagaria o custo da tela exatamente no meio da
    digitação, que é quando ele mais serve.
    """
    id_insumo: int | None = None
    id_subficha: int | None = None
    qtd_bruta: float = Field(default=0, ge=0)
    qtd_liquida: float | None = Field(default=None, ge=0)
    um: str | None = Field(default=None, max_length=6)
    fator_correcao: float = Field(default=1, gt=0)
    fator_coccao: float = Field(default=1, gt=0)
    observacao: str | None = None
    ordem: int = 0


class CustoPrevisto(BaseModel):
    """O que a tela manda para saber quanto a receita está custando agora."""
    itens: list[ItemEmMontagem] = []
    rendimento_qtd: float | None = None
    rendimento_um: str | None = Field(default=None, max_length=6)
    porcoes: float | None = None


class RendimentoSugerido(BaseModel):
    """Os itens de uma receita, para o servidor somar o que ela rende.

    ⚠️ **Vai a receita inteira, não o id da ficha**: a tela pede o número enquanto
    a pessoa monta os itens, e numa ficha nova não há nada gravado. `um` é a
    unidade em que a resposta deve sair — a do rendimento da ficha, quando ela é
    de peso ou volume.
    """

    itens: list[ItemFicha] = Field(default_factory=list)
    um: str | None = Field(default=None, max_length=6)


class FichaDuplicar(BaseModel):
    """Para qual produto a receita vai ser copiada.

    ⚠️ **Produto EXISTENTE, escolhido na tela.** Criar o produto aqui exigiria
    tipo, unidade de estoque, categoria e setor — um cadastro inteiro dentro de
    uma janela de cópia. Quem duplica já tem o bolo de banana cadastrado; quem
    não tem, cadastra em Produtos, que é onde essas perguntas moram.
    """

    id_produto: int


class FichaResumo(BaseModel):
    id: int
    id_produto: int
    produto: str
    codigo: str
    versao: int
    status: str
    rendimento_qtd: float
    rendimento_um: str | None = None
    porcoes: float
    itens: int = 0
    # 🔑 **Quantas versões este produto tem** (13/09/2026, relato do dono: *"quando
    # sai uma nova versão, parece que há dois produtos na lista"*). Só vem
    # preenchido na listagem AGRUPADA — fora dela cada linha já é uma versão, e o
    # número seria a mesma informação dita duas vezes.
    versoes: int = 1
    atualizada_em: datetime | None = None
    # A foto do prato pronto. Na LISTA ela vale como miniatura: um cardápio de
    # 464 pratos se percorre pelo olho, não lendo 464 nomes.
    foto_url: str | None = None
    # Só vem para quem tem `fichas.custos`.
    custo_total: float | None = None
    custo_por_porcao: float | None = None
    custo_completo: bool | None = None


class FichaResponse(BaseModel):
    id: int
    id_produto: int
    produto: str
    codigo: str
    # 🔑 **A prateleira padrão do PRODUTO** (13/09/2026). Ela encabeça a tabela de
    # rendimentos da ficha: o rendimento da própria ficha é o daquele destino, e os
    # de `ficha_locais` são os outros. Sem o nome aqui, a tela diria "padrão" sem
    # dizer de que prateleira.
    id_local_padrao: int | None = None
    local_padrao: str | None = None
    versao: int
    status: str
    rendimento_qtd: float
    rendimento_um: str | None = None
    porcoes: float
    porcao_qtd: float | None = None
    # Os destinos com rendimento próprio. Lista vazia = a ficha vale para todos.
    locais: list[dict] = []
    tempo_preparo_min: int | None = None
    modo_preparo: str | None = None
    alergenos: str | None = None
    observacao: str | None = None
    vigente_de: date | None = None
    vigente_ate: date | None = None
    homologada_em: datetime | None = None
    homologada_por: str | None = None
    criado_em: datetime | None = None
    # 🔑 **A coluna existe desde a etapa 3 e nunca tinha sido usada.** A ficha é
    # seguida por quem está de pé na cozinha, e "está pronto?" é uma pergunta
    # visual — nenhuma descrição de montagem responde o que uma foto responde.
    foto_url: str | None = None
    itens: list[dict] = []
    # Bloco de dinheiro — ausente para quem não tem `fichas.custos`.
    custo_total: float | None = None
    custo_por_porcao: float | None = None
    custo_por_unidade_rendimento: float | None = None
    itens_sem_custo: int | None = None
    custo_completo: bool | None = None
    ve_custo: bool = False
