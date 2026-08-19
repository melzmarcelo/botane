"""Registro de auditoria — quem mudou o quê, com o valor antes e depois."""

import json
from typing import Any

from database import get_cursor


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
                               antes, depois, ip)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
        ),
    )


def listar(limite: int = 100, offset: int = 0, entidade: str | None = None) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.id, a.entidade, a.id_entidade, a.acao, a.antes, a.depois,
                   a.em, a.ip, u.nome AS usuario, u.email
              FROM auditoria a
              LEFT JOIN usuarios u ON u.id = a.id_usuario
             WHERE (%s::varchar IS NULL OR a.entidade = %s)
             ORDER BY a.em DESC
             LIMIT %s OFFSET %s
            """,
            (entidade, entidade, limite, offset),
        )
        return [dict(r) for r in cur.fetchall()]
