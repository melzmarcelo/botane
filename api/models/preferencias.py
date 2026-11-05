"""O corpo de uma preferência de tela (migração 148)."""

from typing import Any

from pydantic import BaseModel


class PreferenciaIn(BaseModel):
    # Um objeto JSON de tela (colunas, densidade, visões). O teto de tamanho é do router.
    valor: dict[str, Any]
