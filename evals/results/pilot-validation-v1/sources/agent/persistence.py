"""Initialize LangGraph schemas before accepting requests or starting queued work."""

import hashlib
import time

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore
from psycopg.rows import dict_row


def ensure_storage(database_url):
    dsn = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    key = int.from_bytes(
        hashlib.sha256(b"gigbid:persistence-schema").digest()[:8], "big", signed=True
    )
    with psycopg.connect(
        dsn, autocommit=True, prepare_threshold=0, row_factory=dict_row, connect_timeout=5
    ) as connection:
        connection.execute("SET lock_timeout = '5s'")
        connection.execute("SET statement_timeout = '15s'")
        # A blocking SELECT pg_advisory_lock holds a snapshot while waiting. A peer's
        # CREATE INDEX CONCURRENTLY can wait on that snapshot, creating a deadlock.
        # Try-lock queries finish immediately; the backoff owns no SQL transaction.
        for _ in range(100):
            if connection.execute("SELECT pg_try_advisory_lock(%s) AS locked", (key,)).fetchone()[
                "locked"
            ]:
                break
            time.sleep(0.1)
        else:
            raise TimeoutError("Another process is initializing persistence")
        try:
            PostgresSaver(connection).setup()
            PostgresStore(connection).setup()
        finally:
            connection.execute("SELECT pg_advisory_unlock(%s)", (key,))
