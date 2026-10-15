"""O que entra e sai do Cardápio Vivo (113). Nada de `body: dict` — regra da casa."""

from datetime import time
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

_COR = r"^#[0-9a-fA-F]{6}$"


class ConfigCardapio(BaseModel):
    id_catalogo: int | None = None
    modo: str = Field("VITRINE", pattern="^(VITRINE|PEDIDO)$")
    exige_confirmacao: bool = True
    pedido_hora_de: time | None = None
    pedido_hora_ate: time | None = None
    chamar_garcom: bool = False
    esconder_esgotado: bool = False
    cor_principal: str | None = Field(None, pattern=_COR)
    cor_fundo: str | None = Field(None, pattern=_COR)
    fonte: str = "NEWSREADER"
    retencao_meses: int = Field(13, ge=1, le=60)
    # O Hub (114): cada botão se liga à parte; o dado (link, rede) mora no cadastro da loja.
    hub_avaliacao: bool = False
    hub_wifi: bool = False

    @model_validator(mode="after")
    def _faixa(self):
        if (self.pedido_hora_de is None) != (self.pedido_hora_ate is None):
            raise ValueError("Informe as duas pontas do horário do pedido, ou nenhuma.")
        return self


class ExcecaoCardapio(BaseModel):
    id_salao: int | None = None
    id_mesa: int | None = None
    # Nulo = herda da loja (ou do salão, para a mesa).
    modo: str | None = Field(None, pattern="^(VITRINE|PEDIDO)$")
    exige_confirmacao: bool | None = None
    pedido_hora_de: time | None = None
    pedido_hora_ate: time | None = None

    @model_validator(mode="after")
    def _faixa(self):
        if (self.pedido_hora_de is None) != (self.pedido_hora_ate is None):
            raise ValueError("Informe as duas pontas do horário do pedido, ou nenhuma.")
        return self


class Evento(BaseModel):
    tipo: str = Field(pattern="^(abriu_cardapio|viu_item|tocou_categoria|abriu_detalhe|"
                              "adicionou|removeu|enviou_pedido|chamou_garcom|pediu_conta|saiu|"
                              # 🔑 Os do complemento (114).
                              "deslizou_frente|deslizou_tras|favoritou|desfavoritou|"
                              "abriu_personalizacao|escolheu_opcao|abriu_hub|clicou_avaliacao|"
                              "clicou_wifi)$")
    item: int | None = None
    categoria: int | None = None
    midia: str | None = Field(None, pattern="^(VIDEO|FOTO|NENHUMA)$")
    duracao_ms: int | None = Field(None, ge=0)
    # Há quanto tempo aconteceu, no relógio do navegador — o servidor recua a PRÓPRIA hora.
    idade_ms: int | None = Field(None, ge=0)


class LoteEventos(BaseModel):
    """O que o `sendBeacon` manda. ⚠️ Chega como `text/plain` (ver a rota)."""

    sessao: UUID
    loja: int
    mesa: str | None = Field(None, max_length=24)
    modo: str = Field(pattern="^(VITRINE|PEDIDO)$")
    dispositivo: str = Field("OUTRO", pattern="^(CELULAR|TABLET|DESKTOP|OUTRO)$")
    idioma: str | None = Field(None, pattern="^(pt|en|de)$")
    eventos: list[Evento] = Field(max_length=200)


class MarcasDoItem(BaseModel):
    destaque: bool | None = None
    esgotado: bool | None = None
    # Fase 2 (115). Nulo = não mexe; "" = limpa (volta ao calculado / sem objetivo).
    objetivo: str | None = Field(None, pattern="^(AUMENTAR_VENDA|GIRAR_ESTOQUE|LANCAMENTO|MANTER|)$")
    margem_nivel: str | None = Field(None, pattern="^(ALTA|MEDIA|BAIXA|)$")


class ExibicaoDaSecao(BaseModel):
    """Quando a seção aparece. Tudo nulo = sempre."""

    dias: list[int] | None = Field(None, min_length=1, max_length=7)
    hora_de: time | None = None
    hora_ate: time | None = None
    horario_especial: bool = False

    @model_validator(mode="after")
    def _coerente(self):
        if self.dias is not None:
            if any(d < 1 or d > 7 for d in self.dias):
                raise ValueError("Dia da semana vai de 1 (segunda) a 7 (domingo).")
            self.dias = sorted(set(self.dias))
            if len(self.dias) == 7:
                self.dias = None  # todos os dias é o mesmo que nenhum filtro
        if (self.hora_de is None) != (self.hora_ate is None):
            raise ValueError("Informe as duas pontas do horário, ou nenhuma.")
        if self.hora_de is not None and self.hora_de == self.hora_ate:
            raise ValueError("O horário de início e de fim não podem ser iguais.")
        return self


class RestricoesDoProduto(BaseModel):
    restricoes: list[str] = Field(default_factory=list)


class OpcaoAdicional(BaseModel):
    id: int | None = None
    nome: str = Field(min_length=1, max_length=80)
    preco: float | None = Field(None, ge=0)
    id_produto_ref: int | None = None
    ativo: bool = True


class GrupoAdicional(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    minimo: int = Field(0, ge=0, le=20)
    maximo: int = Field(1, ge=1, le=20)
    opcoes: list[OpcaoAdicional] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def _faixa(self):
        if self.minimo > self.maximo:
            raise ValueError("O mínimo de escolhas não pode passar do máximo.")
        if self.minimo > len([o for o in self.opcoes if o.ativo]):
            raise ValueError("O mínimo pede mais escolhas do que há opções ativas.")
        return self


# ------------------------------------------------------------------ fase 2 (115)

class ItemDoPedidoDaMesa(BaseModel):
    item: int
    quantidade: int = Field(ge=1, le=50)
    adicionais: list[int] = Field(default_factory=list, max_length=30)
    observacao: str | None = Field(None, max_length=200)


class PedidoDaMesa(BaseModel):
    """O carrinho da mesa. ⚠️ O preço NÃO vem daqui: o servidor o tira do cardápio."""

    sessao: UUID
    # Gerada no aparelho e trocada a cada mudança no carrinho (como o pedido do site, 101).
    chave: str = Field(min_length=8, max_length=60)
    itens: list[ItemDoPedidoDaMesa] = Field(min_length=1, max_length=40)
    observacao: str | None = Field(None, max_length=500)
    # Só de quem se identificou: liga o pedido ao cadastro. Nunca vai para os eventos.
    telefone: str | None = Field(None, max_length=30)


class ChamadoDaMesa(BaseModel):
    tipo: str = Field(pattern="^(GARCOM|CONTA)$")
    sessao: UUID | None = None
