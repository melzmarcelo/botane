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
    # 152: a conversa. Modelo em branco = o padrão (claude-opus-5-5).
    modelo: str | None = Field(default=None, max_length=60, pattern=r"^(claude-[a-z0-9.-]+)?$")
    limite_diario: int = Field(default=40, ge=1, le=500)
    # ⚠️ Só para os testes: o endereço de uma Anthropic falsa. Ignorado fora de DEBUG.
    url_api: str | None = Field(default=None, max_length=200, pattern=r"^(http://127\.0\.0\.1:\d+/[\w/]*)?$")
