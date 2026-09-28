"""Modelos das mensagens por WhatsApp (migração 099)."""

from typing import Literal

from pydantic import BaseModel, Field


class AvisoWhatsapp(BaseModel):
    evento: str = Field(max_length=30)
    ativo: bool = False
    # O NOME do modelo aprovado na Meta, e o idioma dele (pt_BR).
    modelo: str | None = Field(default=None, max_length=120)
    idioma: str = Field(default="pt_BR", max_length=10)
    # Horas antes (lembrete) ou dias antes (prêmio vencendo).
    antecedencia: int | None = Field(default=None, ge=0, le=720)


class ConfigWhatsapp(BaseModel):
    """A aba WhatsApp da loja. ⚠️ Token e segredo em branco = mantém o que já está."""
    ativa: bool = False
    modo: Literal["simulado", "real"] = "simulado"
    phone_number_id: str | None = Field(default=None, max_length=40)
    waba_id: str | None = Field(default=None, max_length=40)
    numero: str | None = Field(default=None, max_length=30)
    api_versao: str | None = Field(default=None, max_length=10, pattern=r"^v\d+\.\d+$")
    token: str | None = Field(default=None, max_length=600)
    app_secret: str | None = Field(default=None, max_length=120)
    avisos: list[AvisoWhatsapp] = []


class TesteWhatsapp(BaseModel):
    telefone: str = Field(max_length=30)
    evento: str = Field(max_length=30)
