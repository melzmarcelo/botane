"""Modelos da Precificação (configuração da loja, simulação e aplicação de preços)."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

TipoDeLinha = Literal["PERCENTUAL", "VALOR", "MARGEM"]
Alcance = Literal["TUDO", "CATEGORIA", "SETOR"]
Arredondamento = Literal["NOVENTA", "MEIO", "NENHUM"]


class Linha(BaseModel):
    """Uma linha da configuração: um percentual da venda, um valor por unidade ou a margem."""
    nome: str = Field(min_length=1, max_length=80)
    tipo: TipoDeLinha
    valor: float = Field(ge=0, le=999999)
    alcance: Alcance = "TUDO"
    id_categoria: int | None = None
    id_setor: int | None = None

    @model_validator(mode="after")
    def _coerente(self):
        self.nome = self.nome.strip()
        if not self.nome:
            raise ValueError("Dê um nome à linha.")
        if self.tipo != "VALOR" and self.valor >= 100:
            raise ValueError(f"“{self.nome}”: percentual precisa ser menor que 100.")
        if self.alcance == "CATEGORIA" and (self.id_categoria is None or self.id_setor is not None):
            raise ValueError(f"“{self.nome}”: escolha a categoria em que a linha vale.")
        if self.alcance == "SETOR" and (self.id_setor is None or self.id_categoria is not None):
            raise ValueError(f"“{self.nome}”: escolha o setor em que a linha vale.")
        if self.alcance == "TUDO":
            self.id_categoria = self.id_setor = None
        return self


class ConfigRequest(BaseModel):
    """⚠️ Substitui a configuração INTEIRA da loja: a tela manda como ela ficou."""
    # Preenchido: esta loja passa a SEGUIR a configuração daquela (e as linhas
    # daqui são ignoradas). Nulo: a configuração é desta loja.
    id_unidade_origem: int | None = None
    arredondamento: Arredondamento = "NOVENTA"
    linhas: list[Linha] = Field(default_factory=list, max_length=200)


class SimularRequest(BaseModel):
    id_produto: int
    preco: float = Field(gt=0, le=9999999)


class PrecoAplicar(BaseModel):
    id_produto: int
    preco: float = Field(gt=0, le=9999999)


class AplicarRequest(BaseModel):
    itens: list[PrecoAplicar] = Field(min_length=1, max_length=500)
