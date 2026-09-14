"""Reservas — o módulo que a casa liga uma loja de cada vez.

A porta de entrada de tudo é `parametros.reservas_ligado`. Enquanto ele estiver
desligado nesta loja, o menu não mostra o módulo, a tela não abre e **estas
rotas recusam** — as três coisas, e não só a primeira.

⚠️ **A trava do servidor não é redundância da do menu.** Esconder o item do menu
é conforto; o que impede uma loja sem o módulo de ganhar configuração de reserva
é a recusa aqui. É a regra da casa desde sempre: nada de checagem só na tela.

Por enquanto só a configuração. Agenda, salões, mesas e a reserva em si vêm
depois — o estudo está em `docs/reservas-esboco.md`.
"""

from fastapi import APIRouter, Depends, HTTPException

import auditoria
from database import get_cursor
from models.reservas import ConfiguracaoReservas
from seguranca import Contexto, requer_permissao, unidade_atual
from services import reservas as servico

router = APIRouter(prefix="/reservas", tags=["Reservas"])

# 🔑 **Ver, operar e configurar são três chaves** (migração 068), e a divisão
# tem razão de ser: quem atende o telefone precisa marcar e cancelar, e não
# precisa poder mudar o horário de funcionamento da casa. É a mesma divisão que
# Transferências já faz entre enviar e receber.
_CONFIGURAR = requer_permissao("reservas.configurar")


def _unidade(cur, ctx: Contexto) -> int:
    """A loja atual — desde que ela tenha o módulo ligado."""
    id_unidade = unidade_atual(cur, ctx)
    if not servico.ligado(cur, id_unidade):
        raise HTTPException(
            status_code=409,
            detail=("O módulo de Reservas não está ligado nesta loja. "
                    "Ligue em Administração → Lojas, no parâmetro Reservas."),
        )
    return id_unidade


@router.get("/configuracao")
def obter_configuracao(ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    """Horário de funcionamento e permanência desta loja.

    ⚠️ **Cria a configuração se ela ainda não existe** — o mesmo desenho
    preguiçoso de `parametros`. Loja ligada hoje, configurada amanhã.
    """
    with get_cursor() as cur:
        return servico.obter(cur, _unidade(cur, ctx))


@router.put("/configuracao")
def salvar_configuracao(body: ConfiguracaoReservas,
                        ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    """Grava a tela inteira de uma vez.

    ⚠️ A auditoria guarda o ANTES: mudança de horário é o tipo de coisa que
    alguém faz e ninguém lembra de ter feito, e a agenda de amanhã depende dela.
    """
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        antes = servico.obter(cur, id_unidade)
        depois = servico.salvar(cur, id_unidade, body)
        auditoria.registrar(cur, ctx.id_usuario, "reserva_config", id_unidade,
                            "atualizar", antes=antes, depois=depois)
    return depois | {"message": "Configuração de reservas salva"}
