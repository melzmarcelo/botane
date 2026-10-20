"""Modelos do período de consumo."""

from datetime import date

from pydantic import BaseModel, Field


class PeriodoAbrir(BaseModel):
    """O ciclo que o administrador abre: de tal dia a tal dia."""

    inicio: date
    fim: date
    # Opcional: o par de datas já identifica o ciclo. Serve para "Setembro/1ª
    # quinzena" quando a casa quiser chamar pelo nome.
    nome: str | None = Field(default=None, max_length=60)
    observacao: str | None = None


class PeriodoFechar(BaseModel):
    observacao: str | None = None


class PeriodoRenomear(BaseModel):
    """O nome do ciclo, aberto ou fechado (pedido do dono, 20/10/2026).

    ⚠️ Vazio volta a ser "sem nome": a tela mostra as datas, que já identificam.
    """

    nome: str | None = Field(default=None, max_length=60)
