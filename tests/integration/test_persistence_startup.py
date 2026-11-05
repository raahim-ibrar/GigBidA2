"""Cold concurrent setup must not hold waiting transactions against concurrent indexes."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore

from agent.persistence import ensure_storage


def test_concurrent_cold_start_initializes_both_langgraph_schemas(account_app):
    if account_app.state.engine.dialect.name != "postgresql":
        pytest.skip("Requires actual Postgres concurrent-index semantics")
    url = account_app.state.settings.database_url
    with ThreadPoolExecutor(max_workers=4) as workers:
        futures = [workers.submit(ensure_storage, url) for _ in range(4)]
        for future in futures:
            assert future.result(timeout=30) is None
    dsn = url.replace("postgresql+psycopg://", "postgresql://", 1)
    with PostgresSaver.from_conn_string(dsn) as saver:
        assert saver.get_tuple({"configurable": {"thread_id": "uncreated-fixture"}}) is None
    with PostgresStore.from_conn_string(dsn) as store:
        assert store.search(("uncreated-fixture", "style")) == []
