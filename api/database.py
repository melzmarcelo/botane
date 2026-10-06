"""Pool de conexões. Sessão em America/Sao_Paulo, banco em UTC."""

import threading
from contextlib import contextmanager

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_SSLMODE, DB_USER

_pool: psycopg2.pool.ThreadedConnectionPool | None = None

# Quantas conexões o processo abre no máximo, e quanto um pedido espera por uma.
MAXIMO_DE_CONEXOES = 10
ESPERA_POR_CONEXAO = 20  # segundos

# 🔑 **Quem não acha conexão livre ESPERA a vez — não estoura** (06/10/2026, achado
# no log de produção). O pool do psycopg2 não tem fila: com as dez conexões em
# uso, a décima primeira levava `PoolError: connection pool exhausted` na hora, e
# o pedido morria em 500. Aconteceu de verdade: o conector do Claude dispara as
# consultas em rajadas de cinco a dez ao mesmo tempo (a prévia de fusão de vários
# cadastros de uma vez), e uma parte voltava com erro sem que nada estivesse
# quebrado — só ocupado por meio segundo.
# ⚠️ **A fila é este semáforo, com as MESMAS vagas do pool.** Quem entra aqui tem
# conexão garantida; quem não entra em `ESPERA_POR_CONEXAO` recebe um 503 com
# frase, que é a verdade ("ocupado, tente de novo") e não um 500 de traceback.
# ⚠️ **Aumentar o pool não é a saída**: o Postgres gerenciado tem teto de conexões
# por plano, e durante o deploy dois contêineres dividem esse teto.
_vagas = threading.BoundedSemaphore(MAXIMO_DE_CONEXOES)


class BancoOcupado(RuntimeError):
    """Nenhuma conexão ficou livre dentro da espera. Vira 503 em `main.py`."""


def init_pool() -> None:
    global _pool
    if _pool is not None:
        return
    _pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=MAXIMO_DE_CONEXOES,
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        sslmode=DB_SSLMODE,
        # O fechamento do dia de um restaurante vira madrugada: sem isto a venda
        # das 23h50 cairia no dia seguinte.
        options="-c timezone=America/Sao_Paulo",
    )


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def get_conn():
    if _pool is None:
        init_pool()
    if not _vagas.acquire(timeout=ESPERA_POR_CONEXAO):
        raise BancoOcupado("O sistema está ocupado agora. Tente de novo em instantes.")
    try:
        conn = _pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            _pool.putconn(conn)
    finally:
        _vagas.release()


@contextmanager
def get_cursor():
    """Cursor com commit automático no fim do bloco.

    Tudo que precisa ser atômico (razão de estoque, por exemplo) usa UM cursor
    só do início ao fim — nunca dois blocos em sequência.
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
