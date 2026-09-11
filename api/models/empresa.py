"""Modelos da empresa, das lojas e dos parâmetros de operação."""

from datetime import date

from typing import Literal

from pydantic import BaseModel, Field


class EmpresaUpdate(BaseModel):
    razao_social: str | None = Field(default=None, max_length=160)
    nome_fantasia: str | None = Field(default=None, max_length=160)
    cnpj: str | None = Field(default=None, max_length=18)
    inscricao_estadual: str | None = None
    inscricao_municipal: str | None = None
    cnae_principal: str | None = None
    regime_tributario: str | None = None      # SIMPLES | PRESUMIDO | REAL | MEI
    data_abertura: date | None = None
    telefone: str | None = None
    whatsapp: str | None = None
    email: str | None = None
    site: str | None = None
    instagram: str | None = None
    cep: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = Field(default=None, max_length=2)
    codigo_ibge: str | None = None
    responsavel_nome: str | None = None
    responsavel_cpf: str | None = None
    responsavel_email: str | None = None
    contador_nome: str | None = None
    contador_crc: str | None = None
    contador_email: str | None = None
    contador_telefone: str | None = None
    logo_url: str | None = None
    cor_primaria: str | None = Field(default=None, max_length=9)


class EmpresaResponse(EmpresaUpdate):
    id: int


class UnidadeCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    apelido: str | None = Field(default=None, max_length=40)
    cnpj: str | None = None
    inscricao_estadual: str | None = None
    matriz: bool = False
    cep: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = Field(default=None, max_length=2)
    codigo_ibge: str | None = None
    telefone: str | None = None
    email: str | None = None
    timezone: str = "America/Sao_Paulo"
    horario_funcionamento: dict | None = None
    mesas: int | None = None
    ativo: bool = True


class UnidadeUpdate(UnidadeCreate):
    nome: str | None = Field(default=None, min_length=2, max_length=120)


class UnidadeResponse(UnidadeCreate):
    id: int


class ParametrosUpdate(BaseModel):
    # ⚠️ O ritmo do fechamento do CMV. Mensal é o padrão e o de sempre; a casa
    # que conta a despensa toda semana fecha em SEMANAL, e quem confere o caixa
    # toda noite, em DIARIO. Quem interpreta os três é `services/periodos.py`.
    ciclo_fechamento: Literal["DIARIO", "SEMANAL", "MENSAL"] | None = None
    # Dia em que a semana FECHA, no padrão ISO: 1 = segunda … 7 = domingo.
    fechamento_dia_semana: int | None = Field(default=None, ge=1, le=7)
    # ⚠️ Era campo MORTO — estava na tela de Lojas e ninguém lia. Agora é o dia
    # em que o mês do CMV COMEÇA: 1 dá o mês do calendário (o padrão, e o
    # comportamento de antes), 26 dá o ciclo 26/07–25/08. Limitado a 28 porque
    # dia 30 não existe em fevereiro.
    dia_fechamento_cmv: int | None = Field(default=None, ge=1, le=28)
    bloquear_retroativo: bool | None = None
    permitir_saldo_negativo: bool | None = None
    exigir_motivo_perda: bool | None = None
    exigir_local_movimento: bool | None = None
    casas_decimais_qtd: int | None = Field(default=None, ge=0, le=6)
    alerta_validade_dias: int | None = Field(default=None, ge=0, le=365)
    alerta_variacao_preco_pct: float | None = Field(default=None, ge=0, le=999)
    # 🔑 **`bloquear_saida_vencido` e `criar_produto_da_nota` saíram daqui**
    # (11/09/2026, decisão do dono: "tira os dois da tela"). Estavam na tela de
    # Lojas desde o começo e **ninguém os lia** — zero referências em serviço ou
    # rota. Configuração que não muda nada é pior que configuração ausente: a
    # casa desliga o bloqueio de vencido, continua vendendo vencido, e conclui
    # que o sistema está quebrado.
    # ⚠️ **As COLUNAS ficam no banco**, com os padrões delas. Apagar coluna é
    # irreversível e não é o que foi pedido; e no dia em que a regra for
    # implementada de verdade, o campo volta para cá e para a tela junto com
    # ela — que é a ordem certa.
    # ⚠️ Saindo do modelo, saem também do `_CAMPOS_PARAM` — a API deixa de
    # aceitá-los no PUT e de devolvê-los no GET. É isso que fecha a promessa.
    # 🔑 **Como o custo médio é apurado** (migração 064, pedido do dono).
    # `false` — o padrão — dá UM custo por produto na loja: a mesma mercadoria
    # não vale uma coisa na despensa e outra no bar, e prateleira nova já nasce
    # sabendo quanto custa. `true` volta ao médio por local, que faz sentido
    # para quem compra o mesmo item por preços diferentes em depósitos
    # diferentes.
    # ⚠️ Ligar a chave não reavalia nada: ela vale dali para a frente. O que já
    # está no estoque se unifica pelo botão em Estoque → Ajustes.
    custo_por_local: bool | None = None


class ParametrosResponse(ParametrosUpdate):
    id_unidade: int
