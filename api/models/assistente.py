"""Modelos do assistente pelo WhatsApp (migração 151)."""

from typing import Literal

from pydantic import BaseModel, Field


class ConfigAssistente(BaseModel):
    """O número do assistente — UM, da casa toda — e a conexão dele com a Meta.

    ⚠️ Token e segredo em branco = mantém o que já está.
    """
    ativa: bool = False
    modo: Literal["simulado", "real"] = "simulado"
    numero: str = Field(default="", max_length=30)
    phone_number_id: str | None = Field(default=None, max_length=40)
    waba_id: str | None = Field(default=None, max_length=40)
    api_versao: str | None = Field(default=None, max_length=10, pattern=r"^(v\d+\.\d+)?$")
    token: str | None = Field(default=None, max_length=600)
    app_secret: str | None = Field(default=None, max_length=120)
