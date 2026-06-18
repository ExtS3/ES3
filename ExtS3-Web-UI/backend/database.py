import os
import threading

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

load_dotenv()

_pool = None
_pool_lock = threading.Lock()


class _PooledConnection:
    def __init__(self, pool, connection):
        self._pool = pool
        self._connection = connection
        self._closed = False

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._pool.putconn(self._connection)

    def __getattr__(self, name):
        return getattr(self._connection, name)


def _connection_kwargs():
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "user": os.getenv("DB_USER", "example_db_user"),
        "password": os.getenv("DB_PASSWORD", "example_db_password"),
        "database": os.getenv("DB_NAME", "example_db_name"),
        "port": os.getenv("DB_PORT", "5432"),
        "options": "-c search_path=admin",
    }


def _get_pool():
    global _pool
    if _pool is not None:
        return _pool

    with _pool_lock:
        if _pool is None:
            minconn = int(os.getenv("DB_POOL_MIN", "1"))
            maxconn = int(os.getenv("DB_POOL_MAX", "10"))
            _pool = ThreadedConnectionPool(minconn, maxconn, **_connection_kwargs())
        return _pool


def get_db_connection():
    """Return a pooled PostgreSQL connection."""
    try:
        pool = _get_pool()
        connection = pool.getconn()
        connection.rollback()
        return _PooledConnection(pool, connection)
    except Exception as e:
        print(f"DB connection failed: {e}")
        return None


def execute_query(query, params=None):
    conn = get_db_connection()
    if not conn:
        return None

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            if query.strip().upper().startswith("SELECT"):
                return cur.fetchall()
            conn.commit()
            return True
    except Exception as e:
        print(f"Query error: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()
