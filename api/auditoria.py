"""Registro de auditoria — quem mudou o quê, com o valor antes e depois."""

import json
from contextvars import ContextVar
from typing import Any

from database import get_cursor
from paginacao import pagina


# 🔑 **Por onde veio a alteração, sem tocar nos 80 chamadores.** `registrar` é
# chamado de todo canto com o mesmo punhado de argumentos; acrescentar um
# parâmetro `origem` significaria passar o contexto em cada um — e a chamada
# NOVA nasceria sem. Quem marca é `seguranca`, uma vez, ao resolver a chave.
# ⚠️ `ContextVar` é da tarefa: o servidor reaproveita tarefas entre requisições,
# então quem marca também devolve (mesma lição do `pediram_o_total`).
origem_do_pedido: ContextVar[str | None] = ContextVar("origem_do_pedido", default=None)


def _limpar(d: dict[str, Any] | None) -> str | None:
    if d is None:
        return None
    # Nada de credencial ou hash no histórico.
    proibidos = {"senha", "senha_hash", "credenciais", "refresh_hash", "app_secret",
                 "client_secret", "password"}
    limpo = {k: v for k, v in d.items() if k not in proibidos}
    return json.dumps(limpo, default=str, ensure_ascii=False)


def registrar(
    cur,
    id_usuario: int | None,
    entidade: str,
    id_entidade: Any,
    acao: str,
    antes: dict | None = None,
    depois: dict | None = None,
    id_unidade: int | None = None,
    ip: str | None = None,
) -> None:
    """Grava no MESMO cursor da operação — se a operação falhar, o log some junto."""
    cur.execute(
        """
        INSERT INTO auditoria (id_usuario, id_unidade, entidade, id_entidade, acao,
                               antes, depois, ip, origem)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            id_usuario,
            id_unidade,
            entidade,
            str(id_entidade) if id_entidade is not None else None,
            acao,
            _limpar(antes),
            _limpar(depois),
            ip,
            origem_do_pedido.get(),
        ),
    )


def listar(limite: int = 100, offset: int = 0, entidade: str | None = None,
           resposta=None) -> list[dict]:
    """Os eventos, do mais recente para o mais antigo.

    A auditoria é a tabela que mais cresce da casa — uma linha por ação de
    qualquer pessoa. Por isso o total sai em consulta separada e só na primeira
    página: contar tudo a cada virada de página seria pagar a tabela inteira
    para mostrar cinquenta linhas.
    """
    with get_cursor() as cur:
        return pagina(
            cur,
            """
            SELECT a.id, a.entidade, a.id_entidade, a.acao, a.antes, a.depois,
                   a.em, a.ip, a.origem, u.nome AS usuario, u.email
              FROM auditoria a
              LEFT JOIN usuarios u ON u.id = a.id_usuario
             WHERE (%s::varchar IS NULL OR a.entidade = %s)
             ORDER BY a.em DESC
            """,
            (entidade, entidade),
            limite=limite, offset=offset, resposta=resposta,
        )
