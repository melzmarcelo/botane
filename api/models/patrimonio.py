"""Modelos do Patrimônio: os bens (um por item físico) e a manutenção deles."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Tensao = Literal["110V", "220V", "380V", "GAS", "NA"]
Criticidade = Literal["ALTA", "MEDIA", "BAIXA"]
Situacao = Literal["A_CONFIRMAR", "EM_USO", "EM_MANUTENCAO", "PARADO", "DESATIVADO", "BAIXADO"]
TipoManutencao = Literal["PREVENTIVA", "CORRETIVA"]

# Os campos que o cadastro edita — a mesma lista do `PUT` e da importação.
CAMPOS = ("apelido", "descricao", "id_produto", "id_setor", "id_local", "marca", "modelo",
          "numero_serie", "tensao", "data_compra", "valor_compra", "fornecedor",
          "nota_fiscal", "garantia_ate", "assistencia", "assistencia_contato", "criticidade",
          "situacao", "motivo_baixa", "preventiva_meses", "ultima_preventiva", "observacao")


class Bem(BaseModel):
    """⚠️ No `PUT` só muda o que vier (`model_fields_set`): a tela manda o formulário
    inteiro, o conector manda só o campo que a pessoa pediu para trocar."""
    apelido: str | None = Field(default=None, max_length=20)
    descricao: str = Field(min_length=1, max_length=120)
    id_produto: int | None = None
    id_setor: int | None = None
    id_local: int | None = None
    marca: str | None = Field(default=None, max_length=60)
    modelo: str | None = Field(default=None, max_length=60)
    numero_serie: str | None = Field(default=None, max_length=60)
    tensao: Tensao | None = None
    data_compra: date | None = None
    valor_compra: float | None = Field(default=None, ge=0, le=99_999_999)
    fornecedor: str | None = Field(default=None, max_length=120)
    nota_fiscal: str | None = Field(default=None, max_length=40)
    garantia_ate: date | None = None
    assistencia: str | None = Field(default=None, max_length=120)
    assistencia_contato: str | None = Field(default=None, max_length=80)
    criticidade: Criticidade | None = None
    situacao: Situacao = "EM_USO"
    motivo_baixa: str | None = Field(default=None, max_length=200)
    preventiva_meses: int | None = Field(default=None, ge=1, le=120)
    ultima_preventiva: date | None = None
    observacao: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _baixa_com_motivo(self):
        # ⚠️ Baixa sem motivo é bem que sumiu sem explicação — o que o controle existe
        # para não ter.
        if self.situacao == "BAIXADO" and not (self.motivo_baixa or "").strip():
            raise ValueError("Para dar baixa, diga o motivo (venda, descarte, perda, doação…).")
        return self


class BemParcial(Bem):
    """O `PUT`: tudo opcional, e só o que vier muda."""
    descricao: str | None = Field(default=None, min_length=1, max_length=120)
    situacao: Situacao | None = None

    @model_validator(mode="after")
    def _baixa_com_motivo(self):
        return self


class Manutencao(BaseModel):
    tipo: TipoManutencao
    data: date
    executado_por: str | None = Field(default=None, max_length=120)
    custo: float | None = Field(default=None, ge=0, le=99_999_999)
    descricao: str | None = Field(default=None, max_length=500)
    # 🔑 A situação do bem DEPOIS da visita: a corretiva que consertou devolve o bem ao
    # uso no mesmo gesto — senão ele ficaria "em manutenção" até alguém lembrar.
    situacao_depois: Situacao | None = None
