"""Precificação — configuração da loja, análise dos preços e aplicação.

A conta e as regras moram em `services/precificacao.py`; o estudo, em
`docs/precificacao-estudo.md`. Três chaves, três autoridades:

* `precificacao.analisar`   — ver margens, sugestões e simular;
* `precificacao.aplicar`    — mudar o preço dos produtos;
* `precificacao.configurar` — imposto, taxas, custo operacional e margem da loja.
"""

from fastapi import APIRouter, Depends, Query

from database import get_cursor
from models.precificacao import AplicarRequest, ConfigRequest, SimularRequest
from seguranca import Contexto, requer_permissao, unidade_atual
from services import precificacao as motor

router = APIRouter(prefix="/precificacao", tags=["Precificação"])

# ⚠️ Quem configura também precisa LER a configuração; quem só analisa a lê para
# entender de onde saiu o número. Gravar é só de quem configura.
_ver = requer_permissao("precificacao.analisar", "precificacao.configurar")


def _para_fora(k: dict) -> dict:
    """A configuração sem o que é só da conta (`_linhas`, em Decimal)."""
    return {chave: valor for chave, valor in k.items() if not chave.startswith("_")}


@router.get("/config")
def obter_config(ctx: Contexto = Depends(_ver)) -> dict:
    """A configuração que VALE nesta loja — a dela, ou a de quem ela segue."""
    with get_cursor() as cur:
        return _para_fora(motor.config(cur, unidade_atual(cur, ctx)))


@router.put("/config")
def gravar_config(body: ConfigRequest,
                  ctx: Contexto = Depends(requer_permissao("precificacao.configurar"))) -> dict:
    """Grava a configuração INTEIRA da loja atual, ou a decisão de seguir outra.

    ⚠️ Sempre a loja em que a pessoa ESTÁ: a de outra se edita trocando de loja
    no seletor — quem segue outra loja não a altera por aqui.
    """
    with get_cursor() as cur:
        k = motor.salvar(cur, unidade_atual(cur, ctx), body.model_dump(), ctx.id_usuario,
                         ctx.ve_unidade)
    return _para_fora(k) | {
        "message": (f"Esta loja passou a seguir a configuração de {k['origem']}."
                    if k["somente_leitura"] else "Configuração salva.")}


@router.get("/faturamento")
def faturamento(meses: int = Query(default=3, ge=1, le=12),
                ctx: Contexto = Depends(requer_permissao("precificacao.configurar"))
                ) -> list[dict]:
    """O faturamento dos últimos meses fechados — a base da calculadora do custo operacional."""
    with get_cursor() as cur:
        return motor.faturamento_recente(cur, unidade_atual(cur, ctx), meses)


@router.get("/analise")
def analise(dias: int = Query(default=30, ge=1, le=365),
            limite: int = Query(default=200, ge=1, le=500),
            id_produto: int | None = None,
            ctx: Contexto = Depends(requer_permissao("precificacao.analisar"))) -> dict:
    """Os produtos vendidos no período: quem está abaixo da margem, e quanto isso pesa no mês."""
    with get_cursor() as cur:
        return motor.analise(cur, unidade_atual(cur, ctx), dias, limite, id_produto)


@router.post("/simular")
def simular(body: SimularRequest,
            ctx: Contexto = Depends(requer_permissao("precificacao.analisar"))) -> dict:
    """De cada venda do produto a este preço: para onde vai cada real. Não grava nada.

    ⚠️ É POST porque leva corpo, mas só lê — a conta é do servidor, e a tela não
    a refaz: uma segunda versão da fórmula no navegador divergiria na primeira
    regra nova.
    """
    with get_cursor() as cur:
        return motor.simular(cur, unidade_atual(cur, ctx), body.id_produto, body.preco)


@router.post("/aplicar")
def aplicar(body: AplicarRequest,
            ctx: Contexto = Depends(requer_permissao("precificacao.aplicar"))) -> dict:
    """Grava os preços escolhidos. Vale na hora; o envio ao PDV segue o parâmetro da loja."""
    with get_cursor() as cur:
        r = motor.aplicar(cur, unidade_atual(cur, ctx),
                          [i.model_dump() for i in body.itens], ctx.id_usuario)
    n = len(r["aplicados"])
    frase = f"{n} preço(s) aplicado(s) — já valem no sistema." if n else "Nenhum preço mudou."
    if n and r["integrados_ao_pdv"]:
        frase += (f" {r['integrados_ao_pdv']} entram na fila de envio ao PDV."
                  if r["envia_ao_pdv"] else
                  f" O envio ao PDV está desligado nesta loja: {r['integrados_ao_pdv']} "
                  "produto(s) integrado(s) continuam com o preço antigo no caixa.")
    return r | {"message": frase}
