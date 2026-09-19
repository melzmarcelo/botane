"""Modelos do OAuth do conector do Claude."""

from pydantic import BaseModel, ConfigDict, Field


class RegistroCliente(BaseModel):
    """Pedido de registro dinâmico (RFC 7591).

    ⚠️ `extra="ignore"`: o protocolo permite dezenas de campos (logo, contato,
    termos). Recusar os que não usamos faria um cliente correto falhar no
    registro por mandar informação a mais.
    """

    model_config = ConfigDict(extra="ignore")

    redirect_uris: list[str] = Field(default_factory=list, max_length=10)
    client_name: str | None = Field(default=None, max_length=200)
    token_endpoint_auth_method: str | None = None
