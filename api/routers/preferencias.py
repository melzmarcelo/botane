"""As preferências de tela de quem está usando (migração 148).

🔑 **Layout novo, fase 2 (05/11/2026, pedido do dono):** o grid configurável guarda colunas,
ordem, densidade e visões salvas POR USUÁRIO, no servidor — para valer em qualquer aparelho.

⚠️ **Só autenticação, sem chave de permissão, de propósito** — como `/auth/me`: cada um lê e
grava apenas as PRÓPRIAS preferências (o `id_usuario` vem do token, nunca da requisição). Não há
dado da casa aqui, só o jeito de cada pessoa ver as telas.
⚠️ O valor é um JSON de tela, com teto de tamanho: não é lugar de guardar dado de negócio.
"""

import json
import re

from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import Json

from database import get_cursor
from models.preferencias import PreferenciaIn
from seguranca import Contexto, contexto_atual

router = APIRouter(prefix="/preferencias", tags=["preferencias"])

# `grade:produtos`, `grade:notas`… — letras, números, ponto, dois-pontos, hífen e sublinhado.
CHAVE = re.compile(r"^[a-z0-9][a-z0-9:._-]{0,79}$")
TETO_BYTES = 32_000


def _chave(chave: str) -> str:
    if not CHAVE.match(chave):
        raise HTTPException(status_code=422, detail="Chave de preferência inválida")
    return chave


@router.get("/{chave}")
def ler(chave: str, ctx: Contexto = Depends(contexto_atual)) -> dict:
    with get_cursor() as cur:
        cur.execute("SELECT valor FROM preferencias_usuario WHERE id_usuario = %s AND chave = %s",
                    (ctx.id_usuario, _chave(chave)))
        linha = cur.fetchone()
    return {"valor": linha["valor"] if linha else None}


@router.put("/{chave}")
def gravar(chave: str, body: PreferenciaIn, ctx: Contexto = Depends(contexto_atual)) -> dict:
    if len(json.dumps(body.valor)) > TETO_BYTES:
        raise HTTPException(status_code=413, detail="Preferência grande demais")
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO preferencias_usuario (id_usuario, chave, valor)
               VALUES (%s, %s, %s)
               ON CONFLICT (id_usuario, chave)
               DO UPDATE SET valor = EXCLUDED.valor, atualizado_em = now()""",
            (ctx.id_usuario, _chave(chave), Json(body.valor)))
    return {"ok": True}


@router.delete("/{chave}")
def apagar(chave: str, ctx: Contexto = Depends(contexto_atual)) -> dict:
    with get_cursor() as cur:
        cur.execute("DELETE FROM preferencias_usuario WHERE id_usuario = %s AND chave = %s",
                    (ctx.id_usuario, _chave(chave)))
    return {"ok": True}
