"""Modelos do módulo de Reservas — por enquanto, só a configuração da loja."""

from datetime import time
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
