"""Modelos das mensagens por WhatsApp (migração 099; conexão por número na 146)."""

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
    # 146: por qual número sai — a `chave` de um dos números enviados junto (ou o id dele,
    # em texto). Nulo = o principal da loja.
    whatsapp: str | None = Field(default=None, max_length=40)


class NumeroWhatsapp(BaseModel):
    """Um número da loja e a conexão dele com a Meta (146).

    ⚠️ Token e segredo em branco = mantém o que já está.
    `chave`: como a tela chama o número antes de ele ter id (é por ela que um aviso aponta para
    um número recém-criado); para um número que já existe, vale o id.
    """
    id: int | None = None
    chave: str | None = Field(default=None, max_length=40)
    rotulo: str | None = Field(default=None, max_length=60)
    numero: str = Field(default="", max_length=30)
    principal: bool = False
    conectado: bool = False
    modo: Literal["simulado", "real"] = "simulado"
    phone_number_id: str | None = Field(default=None, max_length=40)
    waba_id: str | None = Field(default=None, max_length=40)
    api_versao: str | None = Field(default=None, max_length=10, pattern=r"^(v\d+\.\d+)?$")
    token: str | None = Field(default=None, max_length=600)
    app_secret: str | None = Field(default=None, max_length=120)
    conta_do_principal: bool = False


class ConfigWhatsapp(BaseModel):
    """A aba WhatsApp da loja: os números (com a conexão de cada um) e os avisos.

    `numeros` ausente = não mexe nos números (só os avisos).
    """
    numeros: list[NumeroWhatsapp] | None = None
    avisos: list[AvisoWhatsapp] = []


class TesteWhatsapp(BaseModel):
    telefone: str = Field(max_length=30)
    evento: str = Field(max_length=30)
