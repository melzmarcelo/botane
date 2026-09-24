"""Modelos do módulo de Reservas — por enquanto, só a configuração da loja."""

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class HorarioDia(BaseModel):
    """Um dia da semana na janela de funcionamento.

    ⚠️ **`dia_semana` é ISO: 1 = segunda … 7 = domingo.** Igual a
    `parametros.fechamento_dia_semana`, que já existia, e igual ao que
    `extract(isodow from data)` devolve. NÃO é o `Date.getDay()` do JavaScript.
    """
    dia_semana: int = Field(ge=1, le=7)
    aberto: bool = False
    abre: time
    fecha: time
    ultima_reserva: time

    @model_validator(mode="after")
    def _janela_coerente(self):
        # ⚠️ A validação vale mesmo com o dia FECHADO. As horas continuam
        # gravadas — é assim que a casa fecha a segunda sem perder o horário
        # dela —, e deixar passar um par inválido enquanto está fechado só
        # adiaria o erro para o dia em que alguém reabrisse.
        if self.abre >= self.fecha:
            raise ValueError("A hora de abrir tem de ser antes da de fechar.")
        if self.ultima_reserva > self.fecha:
            raise ValueError(
                "A última reserva não pode ser depois do fechamento — seria prometer "
                "mesa para depois de a casa fechar.")
        if self.ultima_reserva < self.abre:
            raise ValueError("A última reserva não pode ser antes de a casa abrir.")
        return self


class FaixaPermanencia(BaseModel):
    """Quanto tempo a mesa fica ocupada, na faixa de horário que a casa definiu."""
    nome: str = Field(min_length=1, max_length=40)
    de: time
    ate: time
    minutos: int = Field(ge=5, le=720)

    @model_validator(mode="after")
    def _faixa_coerente(self):
        if self.de >= self.ate:
            raise ValueError(f'A faixa "{self.nome}" termina antes de começar.')
        return self


class ReservaCreate(BaseModel):
    """Uma reserva nova. O balcão preenche isto; o site, o mesmo com origem SITE."""
    data: date
    hora: time
    pessoas: int = Field(ge=1, le=99)
    # 🔑 Nome e telefone são DA RESERVA. Quem liga não tem cadastro, e exigir um
    # transformaria uma ligação de trinta segundos num cadastro completo — a
    # recepção deixaria de usar o sistema. `id_pessoa` liga à agenda quando a
    # casa quiser histórico.
    nome: str = Field(min_length=2, max_length=120)
    telefone: str | None = Field(default=None, max_length=30)
    id_pessoa: int | None = None
    origem: Literal["BALCAO", "SITE"] = "BALCAO"
    objetivo: str | None = Field(default=None, max_length=40)
    observacao_cliente: str | None = Field(default=None, max_length=2000)
    observacao_interna: str | None = Field(default=None, max_length=2000)
    # ⚠️ **Só o SITE herda a regra de confirmação da loja.** Quem marca no balcão
    # está falando com a casa: a reserva já nasce confirmada, porque a própria
    # casa acabou de aceitá-la. Pôr o balcão para esperar aprovação criaria uma
    # fila de reservas que a recepção teria de aprovar para si mesma.
    confirmacao_da_loja: Literal["AUTOMATICA", "MANUAL"] = "AUTOMATICA"

    def status_inicial(self) -> str:
        if self.origem == "SITE" and self.confirmacao_da_loja == "MANUAL":
            return "PENDENTE"
        return "CONFIRMADA"


class ReservaRemarcar(BaseModel):
    """Mudar dia, hora ou tamanho do grupo — o que vier, fica; o resto não muda.

    🔑 **É a ligação mais comum depois de marcar.** Sem isto, a recepção teria de
    cancelar e recriar, perdendo o histórico da reserva.
    ⚠️ Os três são opcionais de propósito: quem só adia meia hora não precisa
    repetir a data nem o número de pessoas.
    """
    data: date | None = None
    hora: time | None = None
    pessoas: int | None = Field(default=None, ge=1, le=99)

    @model_validator(mode="after")
    def _algo_mudou(self):
        if self.data is None and self.hora is None and self.pessoas is None:
            raise ValueError("Diga o que muda: dia, hora ou número de pessoas.")
        return self


class MudarStatus(BaseModel):
    status: Literal["CONFIRMADA", "CHEGOU", "ENCERRADA", "CANCELADA", "NAO_COMPARECEU"]


class BloqueioCreate(BaseModel):
    de: date
    ate: date
    motivo: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def _periodo(self):
        if self.de > self.ate:
            raise ValueError("O bloqueio termina antes de começar.")
        return self


class SalaoCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    ativo: bool = True
    ordem: int = Field(default=0, ge=0, le=999)


class SalaoUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=60)
    ativo: bool | None = None
    ordem: int | None = Field(default=None, ge=0, le=999)


class MesaCreate(BaseModel):
    id_salao: int
    nome: str = Field(min_length=1, max_length=20)
    # ⚠️ **Dois números, e o máximo nunca é menor que o confortável.** `lugares`
    # é quem senta bem; `capacidade_max` é com a cadeira extra, e é o que a
    # alocação usa.
    lugares: int = Field(default=2, ge=1, le=40)
    capacidade_max: int | None = Field(default=None, ge=1, le=60)
    ativo: bool = True

    @model_validator(mode="after")
    def _capacidade(self):
        # Não informado, o máximo é o confortável: quem não tem cadeira extra
        # não precisa dizer nada.
        if self.capacidade_max is None:
            self.capacidade_max = self.lugares
        if self.capacidade_max < self.lugares:
            raise ValueError(
                "A capacidade máxima não pode ser menor que os lugares — seria dizer "
                "que a cadeira extra tira lugar.")
        return self


class MesasEmLote(BaseModel):
    """Montar um salão inteiro de uma vez.

    🔑 **Pedido do dono (14/09/2026)**, depois de ver a tela: montar um salão de
    doze mesas era clicar "+ mesa" doze vezes e renomear cada uma. O trabalho
    real do cadastro é esse, e ele acontece uma vez, no dia em que a casa entra
    no sistema — justamente quando ninguém tem paciência.
    """
    id_salao: int
    quantidade: int = Field(ge=1, le=50)
    lugares: int = Field(default=2, ge=1, le=40)
    capacidade_max: int | None = Field(default=None, ge=1, le=60)
    # Prefixo opcional para separar salões na numeração: "V" dá V01, V02…
    # ⚠️ O nome é único por LOJA, não por salão — sem prefixo, a segunda varanda
    # continua a numeração da casa em vez de recomeçar do 01.
    prefixo: str = Field(default="", max_length=6)

    @model_validator(mode="after")
    def _capacidade(self):
        if self.capacidade_max is None:
            self.capacidade_max = self.lugares
        if self.capacidade_max < self.lugares:
            raise ValueError("A capacidade máxima não pode ser menor que os lugares.")
        return self


class MesaUpdate(BaseModel):
    id_salao: int | None = None
    nome: str | None = Field(default=None, min_length=1, max_length=20)
    lugares: int | None = Field(default=None, ge=1, le=40)
    capacidade_max: int | None = Field(default=None, ge=1, le=60)
    ativo: bool | None = None
    # 🔑 A mesa vizinha que encosta nesta. `null` desfaz a junta — nos DOIS
    # lados, e quem grava é `services/reservas.casar_junta`.
    # ⚠️ **"Não mandou" e "mandou nulo" são coisas diferentes aqui**, e o router
    # separa as duas por `model_fields_set`. Sem isso, qualquer PUT que não
    # falasse da junta a desfaria — trocar o nome da mesa 07 soltaria a 08.
    junta_com: int | None = None


class ConfiguracaoReservas(BaseModel):
    """A tela inteira num corpo só — ela grava tudo de uma vez."""
    aceita_online: bool = False
    confirmacao: Literal["AUTOMATICA", "MANUAL"] = "AUTOMATICA"
    teto_online: int = Field(default=8, ge=1, le=99)
    tolerancia_min: int = Field(default=15, ge=0, le=240)
    folga_min: int = Field(default=15, ge=0, le=240)
    passo_min: int = Field(default=30, ge=5, le=240)
    antecedencia_min_horas: int = Field(default=2, ge=0, le=720)
    antecedencia_max_dias: int = Field(default=30, ge=1, le=365)
    cadastro_completo: bool = True
    # 🔑 **O texto da mensagem de WhatsApp, da CASA** (migração 081, pedido do
    # dono, 21/09/2026: *"em configurações da reserva, colocar o texto padrão
    # configurável para o whatsapp"*). Estava escrito no site, e texto de
    # cliente escrito em código só muda quando alguém publica.
    # ⚠️ **São DOIS**: quem clica em "Entre em contato" ainda não escolheu nada;
    # quem vem da reserva já tem dia, hora e quantas pessoas. Uma frase só nos
    # dois lugares ou perde o que o cliente já disse, ou manda "reservar para
    # {pessoas}" sem pessoas nenhuma.
    # ⚠️ Nulo é "usa o padrão da casa" — o site tem um de reserva; apagar o
    # campo não pode deixar a mensagem em branco.
    whatsapp_texto: str | None = Field(default=None, max_length=400)
    whatsapp_texto_reserva: str | None = Field(default=None, max_length=400)
    horarios: list[HorarioDia]
    permanencias: list[FaixaPermanencia] = []

    @model_validator(mode="after")
    def _coerente(self):
        dias = [h.dia_semana for h in self.horarios]
        if sorted(dias) != [1, 2, 3, 4, 5, 6, 7]:
            # ⚠️ A semana inteira, sempre. Aceitar uma lista parcial deixaria o
            # dia que faltou com o valor antigo sem ninguém notar — e um dia
            # invisível na tela é um dia que a casa acha que configurou.
            raise ValueError("A semana precisa vir inteira, um registro por dia (1 a 7).")

        # 🔑 **Faixas de permanência não podem se sobrepor.** Sobrepondo, duas
        # respostas valeriam para a mesma hora e o cálculo pegaria a primeira —
        # ou seja, a mesa liberaria num horário que depende da ORDEM das linhas.
        # É o tipo de erro que não aparece na tela, só no salão.
        ordenadas = sorted(self.permanencias, key=lambda f: f.de)
        for anterior, atual in zip(ordenadas, ordenadas[1:]):
            if atual.de < anterior.ate:
                raise ValueError(
                    f'As faixas "{anterior.nome}" e "{atual.nome}" se sobrepõem. '
                    "Cada horário do dia só pode ter uma permanência.")
        return self


class TelefoneDoSite(BaseModel):
    """A primeira tela da reserva pelo site: só o telefone.

    🔑 **Pedido do dono (21/09/2026):** *"clica em Reserve sua Mesa, abre uma tela
    com o número do telefone; caso não tenha cadastrada, realiza o cadastro."*
    ⚠️ **Vai no CORPO, não na URL.** Telefone é dado pessoal, e dado pessoal em
    query string entra em log de servidor, em histórico de navegador e no
    `Referer` de qualquer coisa que a página carregar depois.
    """
    # ⚠️ **Sem `min_length` aqui, de propósito.** O Pydantic dispara ANTES do
    # serviço e devolve "String should have at least 8 characters" — em inglês,
    # falando de caracteres, para quem só digitou o telefone errado. Quem
    # explica é `telefone_valido`, que sabe dizer que falta o DDD.
    telefone: str = Field(max_length=30)


class ClienteDoSite(BaseModel):
    """Quem pergunta pelas próprias reservas: telefone e nome, no CORPO.

    ⚠️ Os dois pelo mesmo motivo de `TelefoneDoSite`: dado pessoal fora da URL.
    """
    telefone: str = Field(max_length=30)
    nome: str = Field(min_length=2, max_length=120)


class CancelamentoDoSite(ClienteDoSite):
    """Qual das próprias reservas o cliente quer cancelar.

    ⚠️ **Por data e hora, não por id**: o site não recebe id interno (regra de
    `routers/publico.py`). Dentro das reservas de UM cliente, data e hora já
    dizem qual é.
    """
    data: date
    hora: time


class IdentificacaoDoSite(BaseModel):
    """Quem é a pessoa, sem reserva junto — a porta do catálogo que exige cadastro.

    🔑 Os mesmos campos do cadastro de `ReservaDoSite`, e a mesma regra: quem
    decide o que é obrigatório é `clientes.identificar`, pela configuração da loja.
    """
    telefone: str = Field(max_length=30)
    nome: str = Field(min_length=2, max_length=120)
    genero: Literal["FEMININO", "MASCULINO", "OUTRO", "NAO_INFORMADO"] | None = None
    cidade: str | None = Field(default=None, max_length=80)
    nascimento: date | None = None


class ReservaDoSite(BaseModel):
    """A reserva que o cliente marca sozinho, com o cadastro junto.

    🔑 **Uma requisição só, não três.** Cadastrar, conferir a mesa e gravar a
    reserva em chamadas separadas deixaria a porta aberta para o cadastro nascer
    e a reserva falhar logo depois — e a casa ficaria com fichas de gente que
    nunca reservou. Aqui tudo acontece na mesma transação.

    ⚠️ **`genero` e `cidade` são opcionais AQUI e obrigatórios lá dentro**, se a
    loja pedir cadastro completo e a pessoa for nova. A regra é da configuração
    da casa (`reserva_config.cadastro_completo`), não do modelo — um campo
    obrigatório no Pydantic valeria igual para a casa que só quer o nome.
    """
    # ⚠️ **Sem `min_length` aqui, de propósito.** O Pydantic dispara ANTES do
    # serviço e devolve "String should have at least 8 characters" — em inglês,
    # falando de caracteres, para quem só digitou o telefone errado. Quem
    # explica é `telefone_valido`, que sabe dizer que falta o DDD.
    telefone: str = Field(max_length=30)
    nome: str = Field(min_length=2, max_length=120)
    genero: Literal["FEMININO", "MASCULINO", "OUTRO", "NAO_INFORMADO"] | None = None
    cidade: str | None = Field(default=None, max_length=80)
    # 🔑 Migração 086 (pedido do dono, 24/09/2026). Obrigatória para quem é NOVO
    # quando a casa pede cadastro completo — quem exige é o serviço, pelo mesmo
    # motivo de gênero e cidade.
    nascimento: date | None = None
    data: date
    hora: time
    pessoas: int = Field(ge=1, le=99)
    observacao_cliente: str | None = Field(default=None, max_length=500)
