"""Pool de conexões. Sessão em America/Sao_Paulo, banco em UTC."""

from contextlib import contextmanager

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_SSLMODE, DB_USER

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def init_pool() -> None:
    global _pool
    if _pool is not None:
        return
    _pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=10,
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
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


@contextmanager
def get_cursor():
    """Cursor com commit automático no fim do bloco.

    Tudo que precisa ser atômico (razão de estoque, por exemplo) usa UM cursor
    só do início ao fim — nunca dois blocos em sequência.
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
