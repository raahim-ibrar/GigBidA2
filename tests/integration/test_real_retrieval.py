"""Opt-in runtime smoke test. This is not a graded retrieval-quality experiment."""

import os
from uuid import uuid4

import pytest

from apps.api.settings import Settings
from rag.contracts import DocumentMetadata, PortfolioSearch
from rag.runtime import build_portfolio


@pytest.mark.skipif(
    os.getenv("GIGBID_REAL_MODELS") != "1", reason="requires local models, Redis and Qdrant"
)
@pytest.mark.asyncio
async def test_real_redis_worker_indexes_a_saved_upload(client, account_app):
    from arq import create_pool
    from arq.connections import RedisSettings
    from arq.worker import Worker

    from worker.settings import index_portfolio

    response = client.post(
        "/api/auth/register",
        json={
            "email": "worker-smoke@example.org",
            "password": "Worker smoke fixture password 123!",
        },
    )
    assert response.status_code == 201
    user = response.json()["id"]
    service = build_portfolio(account_app.state.engine, Settings())
    doc = service.ingest(
        user,
        "worker-development-fixture.md",
        b"Built a Python FastAPI service.",
        DocumentMetadata(type="case_study", project="Worker development fixture"),
    )
    pool = await create_pool(RedisSettings(host="127.0.0.1", port=6379))
    queue = "gigbid-test:" + uuid4().hex
    health_key = queue + ":health"
    worker = Worker(
        [index_portfolio],
        redis_pool=pool,
        queue_name=queue,
        burst=True,
        max_burst_jobs=1,
        handle_signals=False,
        poll_delay=0.01,
        keep_result=0,
        health_check_key=health_key,
        ctx={"portfolio": service, "engine": account_app.state.engine},
        log_results=False,
    )
    try:
        await pool.enqueue_job("index_portfolio", user, doc.id, _queue_name=queue, _job_id=doc.id)
        await worker.async_run()
        assert worker.jobs_complete == 1 and worker.jobs_failed == 0
        assert service.list_documents(user)[0].status == "ready"
        assert service.search(user, PortfolioSearch(query="Python API")).items
    finally:
        if os.name == "nt":
            # Arq 0.28 close() references Unix-only SIGUSR1. The burst has finished;
            # close its public resources explicitly. Production workers run in Linux Docker.
            await pool.delete(health_key)
            await pool.aclose()
        else:
            await worker.close()
        service.delete_document(user, doc.id)
        service.cleanup_vectors(user, doc.id)
        service.index.client.close()


@pytest.mark.skipif(
    os.getenv("GIGBID_REAL_MODELS") != "1", reason="requires local open models and Qdrant"
)
def test_real_open_models_index_retrieve_and_delete_in_qdrant(client, account_app):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "runtime-smoke@example.org",
            "password": "Runtime smoke fixture password 123!",
        },
    )
    assert response.status_code == 201
    user = response.json()["id"]
    service = build_portfolio(account_app.state.engine, Settings())
    docs = []
    try:
        for name, text in [
            (
                "development-api.md",
                "Built a Python FastAPI REST API backed by a PostgreSQL database "
                "for a retail inventory system.",
            ),
            (
                "development-design.md",
                "Designed a brochure and logo for a restaurant "
                "using typography and color palettes.",
            ),
        ]:
            doc = service.ingest(
                user,
                name,
                text.encode(),
                DocumentMetadata(
                    type="case_study",
                    project="Development smoke fixture",
                ),
            )
            docs.append(doc)
            service.index_document(user, doc.id)
        for variant in ["v0", "v2", "v3"]:
            result = service.search(
                user, PortfolioSearch(query="Python FastAPI PostgreSQL REST API", variant=variant)
            )
            assert result.items[0].evidence.document_id == docs[0].id
        result = service.search(
            user,
            PortfolioSearch(query="Certified underwater archaeological excavation", variant="v8"),
        )
        assert result.abstained
        old_id = service.search(user, PortfolioSearch(query="Python FastAPI")).items[0].evidence.id
        service.delete_document(user, docs[0].id)
        service.cleanup_vectors(user, docs[0].id)
        docs.pop(0)
        assert client.get(f"/api/portfolio/evidence/{old_id}").status_code == 404
    finally:
        for doc in docs:
            service.delete_document(user, doc.id)
            service.cleanup_vectors(user, doc.id)
        service.index.client.close()
