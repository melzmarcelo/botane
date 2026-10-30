"""Pool de conexões. Sessão em America/Sao_Paulo, banco em UTC."""

import threading
import time
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

# 🔑 **Conexão parada pode estar MORTA** (v1.2.0, achado no registro de erros do ar, 26/10/2026:
# `/saude` em 500 com "SSL SYSCALL error: EOF detected" e, no rollback, "connection already
# closed"). O Postgres gerenciado (ou a rede no meio) derruba a conexão ociosa, e o pool a
# entregava ao próximo pedido como se estivesse boa. Três defesas:
# 1. keepalive de TCP, para a rede não derrubar a ociosa;
# 2. a conexão parada há mais de `TESTAR_APOS` segundos faz um `SELECT 1` antes de ser usada
#    (a usada há pouco não paga esse custo);
# 3. a que quebrou (fechada, ou erro de conexão) SAI do pool em vez de voltar para ele — e o
#    rollback dela não pode levantar um segundo erro por cima do primeiro.
TESTAR_APOS = 30  # segundos
_ultimo_uso: dict[int, float] = {}


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
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=3,
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
        conn = _conexao_viva()
        quebrou = False
        try:
            yield conn
            conn.commit()
        except Exception as e:
            quebrou = conn.closed or isinstance(e, (psycopg2.OperationalError,
                                                    psycopg2.InterfaceError))
            if not conn.closed:
                try:
                    conn.rollback()
                except psycopg2.Error:
                    quebrou = True
            raise
        finally:
            quebrou = quebrou or bool(conn.closed)
            if quebrou:
                _ultimo_uso.pop(id(conn), None)
            else:
                _ultimo_uso[id(conn)] = time.monotonic()
            _pool.putconn(conn, close=quebrou)
    finally:
        _vagas.release()


def _conexao_viva():
    """Uma conexão do pool que responde. ⚠️ Testa só a que ficou parada; troca a morta."""
    for _ in range(MAXIMO_DE_CONEXOES + 1):
        conn = _pool.getconn()
        if conn.closed:
            _ultimo_uso.pop(id(conn), None)
            _pool.putconn(conn, close=True)
            continue
        if time.monotonic() - _ultimo_uso.get(id(conn), 0) < TESTAR_APOS:
            return conn
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.rollback()
            return conn
        except psycopg2.Error:
            _ultimo_uso.pop(id(conn), None)
            _pool.putconn(conn, close=True)
    raise BancoOcupado("Sem conexão com o banco agora. Tente de novo em instantes.")


@contextmanager
def get_cursor():
    """Cursor com commit automático no fim do bloco.

    Tudo que precisa ser atômico (razão de estoque, por exemplo) usa UM cursor
    só do início ao fim — nunca dois blocos em sequência.
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
