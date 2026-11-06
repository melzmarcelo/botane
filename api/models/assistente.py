"""Modelos do assistente pelo WhatsApp (migração 151)."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


# Os serviços falsos dos testes moram sempre em 127.0.0.1.
_LOCAL = r"^(http://127\.0\.0\.1:\d+(/[\w/.-]*)?)?$"


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
    url_api: str | None = Field(default=None, max_length=200, pattern=_LOCAL)
    # 153: a transcrição do áudio. Provedor em branco = não ouve áudio. Chave em branco = mantém.
    transcricao_provedor: Literal["", "openai", "groq"] = ""
    transcricao_modelo: str | None = Field(default=None, max_length=60, pattern=r"^[\w.-]*$")
    transcricao_chave: str | None = Field(default=None, max_length=300)
    # ⚠️ Só para os testes: Meta e transcrição falsas. Ignorados fora de DEBUG.
    url_meta: str | None = Field(default=None, max_length=200, pattern=_LOCAL)
    url_transcricao: str | None = Field(default=None, max_length=200, pattern=_LOCAL)
    # 155: o bom dia. Dias na ISO (1 = segunda … 7 = domingo).
    bom_dia_ligado: bool = False
    bom_dia_hora: str = Field(default="07:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    bom_dia_dias: list[int] = Field(default=[1, 2, 3, 4, 5, 6], max_length=7)
    bom_dia_so_com_pendencia: bool = True
    bom_dia_modelo: str | None = Field(default=None, max_length=120, pattern=r"^[a-z0-9_]*$")
    bom_dia_idioma: str | None = Field(default=None, max_length=10, pattern=r"^[a-zA-Z_]*$")

    @field_validator("bom_dia_dias")
    @classmethod
    def _dias_validos(cls, v: list[int]) -> list[int]:
        if any(d < 1 or d > 7 for d in v):
            raise ValueError("Dias de 1 (segunda) a 7 (domingo).")
        return v


class BomDiaPessoa(BaseModel):
    """155: a pessoa liga ou desliga o bom dia no Perfil."""
    ligado: bool
