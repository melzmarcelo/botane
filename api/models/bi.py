"""Os corpos do Estúdio BI (migração 149). Só NOMES da lista branca de `services/bi.py`."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class LigacaoManual(BaseModel):
    a: str = Field(max_length=40)
    ca: str = Field(max_length=40)
    b: str = Field(max_length=40)
    cb: str = Field(max_length=40)
    tipo: Literal["INNER", "LEFT"] = "INNER"


class DefinicaoBI(BaseModel):
    fontes: list[str] = Field(default_factory=list, max_length=8)
    # id da ligação conhecida (`itens.id_venda-vendas.id`) → INNER | LEFT | NENHUMA
    tipos: dict[str, Literal["INNER", "LEFT", "NENHUMA"]] = Field(default_factory=dict)
    manuais: list[LigacaoManual] = Field(default_factory=list, max_length=6)
    dimensoes: list[str] = Field(default_factory=list, max_length=2)
    medidas: list[str] = Field(default_factory=list, max_length=6)
    de: date | None = None
    ate: date | None = None
    visual: Literal["barras", "tabela", "indicadores"] = "barras"


class RelatorioBIIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    definicao: DefinicaoBI
    visibilidade: Literal["EU", "TODOS", "PAPEIS"] = "EU"
    papeis_vistos: list[int] = Field(default_factory=list, max_length=50)
    no_menu: bool = True


class PeriodoBI(BaseModel):
    de: date | None = None
    ate: date | None = None
