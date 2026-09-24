"""Modelos da fidelidade do Portal de Clientes."""

from pydantic import BaseModel, Field, field_validator


def _dias(v: list[int]) -> list[int]:
    # ⚠️ ISO: 1 = segunda … 7 = domingo, como `reserva_horarios.dia_semana`.
    if any(d < 1 or d > 7 for d in v):
        raise ValueError("Dia da semana inválido (1 = segunda … 7 = domingo).")
    if not v:
        raise ValueError("Marque ao menos um dia.")
    return sorted(set(v))


class FidelidadeConfig(BaseModel):
    """A configuração do cartão de visitas — uma para a rede."""
    visitas: int = Field(ge=1, le=100)
    premio: str = Field(min_length=2, max_length=120)
    validade_dias: int = Field(ge=1, le=365)
    dias_pontua: list[int]
    dias_consumo: list[int]
    so_no_horario: bool = True
    site_url: str = Field(min_length=8, max_length=200, pattern=r"^https?://")
    # 🔑 Migração 092: o check-in só conta perto da loja, pela localização do celular.
    exige_local: bool = True
    raio_m: int = Field(default=200, ge=30, le=5000)

    _dias_pontua = field_validator("dias_pontua")(_dias)
    _dias_consumo = field_validator("dias_consumo")(_dias)


class EntregaPremio(BaseModel):
    codigo: str = Field(min_length=4, max_length=8)


class CheckinDoSite(BaseModel):
    """O check-in pelo QR da mesa: quem (telefone) e a prova de que está na casa (token).

    ⚠️ Telefone no CORPO, como em todo o site: dado pessoal fora da URL.
    """
    telefone: str = Field(max_length=30)
    token: str = Field(max_length=32)
    # 🔑 O termo em vigor cita a fidelidade; quem aceitou o anterior aceita aqui.
    aceite_termo: bool = False
    # A posição do celular no check-in (092). ⚠️ Usada para medir a distância e
    # DESCARTADA — só a distância fica gravada.
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    precisao: float | None = Field(default=None, ge=0)


class LocalDaLoja(BaseModel):
    """As coordenadas da loja atual, de onde se mede o raio do check-in."""
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
