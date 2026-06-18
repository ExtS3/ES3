import json
import os
from contextlib import contextmanager
from typing import Any

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()

DEFAULT_TABLE = "public.es3_vector"


def _embedding_dim() -> int:
    return int(os.getenv("EMBEDDING_DIM", "1024"))


def _table_name() -> str:
    return os.getenv("PGVECTOR_TABLE", DEFAULT_TABLE)


def _connection_kwargs() -> dict[str, Any]:
    return {
        "host": os.getenv("PGVECTOR_DB_HOST", os.getenv("DB_HOST", "localhost")),
        "port": os.getenv("PGVECTOR_DB_PORT", os.getenv("DB_PORT", "5432")),
        "user": os.getenv("PGVECTOR_DB_USER", os.getenv("DB_USER", "example_db_user")),
        "password": os.getenv("PGVECTOR_DB_PASSWORD", os.getenv("DB_PASSWORD", "example_db_password")),
        "dbname": os.getenv("PGVECTOR_DB_NAME", os.getenv("DB_NAME", "example_db_name")),
    }


def _vector_literal(vector: list[float]) -> str:
    if not isinstance(vector, list) or not vector:
        raise ValueError("embedding vector is empty")
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


@contextmanager
def get_connection():
    conn = psycopg2.connect(**_connection_kwargs())
    try:
        yield conn
    finally:
        conn.close()


def ensure_schema(dim: int | None = None) -> None:
    dim = dim or _embedding_dim()
    table = _table_name()
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        id BIGSERIAL PRIMARY KEY,
                        document TEXT NOT NULL,
                        embedding vector({dim}) NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            conn.commit()
    except psycopg2.Error as exc:
        message = str(exc).strip()
        if "extension" in message and "vector" in message:
            cfg = _connection_kwargs()
            raise RuntimeError(
                "pgvector extension is not installed on the connected PostgreSQL server "
                f"({cfg['host']}:{cfg['port']}/{cfg['dbname']}). "
                "Use the pgvector/pgvector:pg16 container from ExtS3-Demo/docker-compose.yml "
                "or install pgvector on that PostgreSQL instance."
            ) from exc
        raise


def count_vectors() -> int:
    ensure_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {_table_name()}")
            return int(cur.fetchone()[0])


def clear_vectors() -> None:
    """Remove all rows from the vector table (used before a full re-seed)."""
    ensure_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE TABLE {_table_name()} RESTART IDENTITY")
        conn.commit()


def insert_vector_record(document: str | dict[str, Any], embedding: list[float]) -> None:
    ensure_schema(len(embedding))
    document_text = json.dumps(document, ensure_ascii=False, sort_keys=True) if isinstance(document, dict) else document
    vector_text = _vector_literal(embedding)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {_table_name()} (document, embedding) VALUES (%s, %s::vector)",
                (document_text, vector_text),
            )
        conn.commit()


def search_vectors(
    embedding: list[float],
    *,
    match_threshold: float = 0.0,
    match_count: int = 10,
) -> list[dict[str, Any]]:
    ensure_schema(len(embedding))
    vector_text = _vector_literal(embedding)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT
                    id::text AS id,
                    document,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM {_table_name()}
                WHERE 1 - (embedding <=> %s::vector) > %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (vector_text, vector_text, match_threshold, vector_text, match_count),
            )
            return [dict(row) for row in cur.fetchall()]
