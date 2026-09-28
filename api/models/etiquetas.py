"""Modelos do módulo de Etiquetas (validade do que se produz e do que se abre)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Evento = Literal["PRODUCAO", "ABERTURA", "DESCONGELAMENTO"]
Conservacao = Literal["REFRIGERADO", "CONGELADO", "AMBIENTE"]


class RegraDeValidade(BaseModel):
    """Quanto o produto dura depois de um evento, numa conservação."""
    evento: Evento
    conservacao: Conservacao
    prazo: int = Field(ge=1, le=3650)
    unidade: Literal["HORAS", "DIAS"] = "DIAS"
    padrao: bool = False


class ValidadesDoProduto(BaseModel):
    """⚠️ Substitui o conjunto inteiro: a tela manda a tabela como ela ficou."""
    regras: list[RegraDeValidade] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def _sem_repetir(self):
        vistos = set()
        for r in self.regras:
            chave = (r.evento, r.conservacao)
            if chave in vistos:
                raise ValueError("A mesma conservação aparece duas vezes no mesmo evento.")
            vistos.add(chave)
        return self


class EtiquetaConfig(BaseModel):
    tamanho: Literal["40x40", "50x30", "60x40", "100x50", "A4"] = "60x40"
    mostrar_alergenos: bool = True
    mostrar_lote: bool = True
    mostrar_quantidade: bool = True
    mostrar_qr: bool = True
    texto_extra: str | None = Field(default=None, max_length=80)


class EmitirEtiquetas(BaseModel):
    """Uma ou várias etiquetas iguais (o porcionamento: 5 potes, 5 etiquetas).

    Com `id_producao`, produto, lote, local e data vêm da produção. Com `id_origem`
    (descongelamento, reetiquetagem), vêm da etiqueta anterior, que deixa de valer.
    """
    id_produto: int | None = None
    evento: Evento
    conservacao: Conservacao | None = None
    copias: int = Field(default=1, ge=1, le=60)
    # Por etiqueta, na unidade de estoque do produto.
    quantidade: float | None = Field(default=None, gt=0)
    id_producao: int | None = None
    id_origem: int | None = None
    id_local: int | None = None
    lote: str | None = Field(default=None, max_length=40)
    validade_fabricante: date | None = None
    # ⚠️ Só quando o produto não tem regra: sem ela, alguém precisa dizer a validade.
    vence_em: datetime | None = None
    responsavel: str | None = Field(default=None, max_length=120)
    observacao: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _tem_produto(self):
        if not (self.id_produto or self.id_producao or self.id_origem):
            raise ValueError("Escolha o produto.")
        return self


class DescarteDeEtiqueta(BaseModel):
    # Vazio = a quantidade da etiqueta.
    quantidade: float | None = Field(default=None, ge=0)
    id_motivo_perda: int | None = None
    motivo: str | None = Field(default=None, max_length=200)
    # Falso = só tira a etiqueta das ativas (a perda já foi lançada por outro caminho).
    lancar_perda: bool = True


class BaixaDeEtiqueta(BaseModel):
    observacao: str | None = Field(default=None, max_length=200)
