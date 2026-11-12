"""Real Postgres saver/transactions; deterministic role outputs are control fixtures."""

import asyncio
import os
from collections import Counter
from uuid import uuid4

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agent.model_client import ModelUnavailable
from agent.run_store import RunStore
from agent.runtime import lock_key, process_bid
from apps.api.models import ApprovalAudit, LocalDraftArtifact
from apps.api.schemas.proposals import ManualJob, ReviewRun
from rag.contracts import DocumentMetadata, PortfolioSearch
from tests.integration.test_runs import register
from tests.portfolio_fixtures import portfolio_fixture

pytestmark = pytest.mark.skipif(
    not os.getenv("GIGBID_TEST_DATABASE_URL"), reason="requires Postgres checkpoint storage"
)


def execute(coroutine):
    # Psycopg async requires SelectorEventLoop on Windows. Production workers run
    # on Linux; these host-control tests inject a reader without subprocess IO.
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        return runner.run(coroutine)


@pytest.fixture
def durable(client, account_app):
    user = register(client, "durable@example.org")
    tenant = user["id"]
    service = portfolio_fixture(account_app.state.engine)
    doc = service.ingest(
        tenant,
        "fixture.md",
        b"I built a Python API.",
        DocumentMetadata(type="case_study", project="Checkpoint fixture"),
    )
    service.index_document(tenant, doc.id)
    evidence = service.search(tenant, PortfolioSearch(query="Python")).items[0].evidence

    class Reader:
        async def search(self, query, **kwargs):
            return [evidence]

        async def read(self, id):
            return service.evidence(tenant, id)

    counts = Counter()

    class Models:
        crash_writer = False
        fail_writer = False
        writer_text = "I built a Python API. Could we discuss scope?"

        def __init__(self, *args, **kwargs):
            pass

        async def complete(self, role, payload, schema):
            counts[role] += 1
            if role == "writer" and self.crash_writer:
                raise asyncio.CancelledError()
            if role == "writer" and self.fail_writer:
                raise ModelUnavailable("Development model outage fixture")
            outputs = {
                "analyst": {"job_id": "fixture", "title": "Fixture", "requirements": ["Python"]},
                "risk": {"score": 0},
                "matcher": {"requirement_evidence": {"Python": [evidence.id]}},
                "writer": {
                    "text": "Could we clarify priorities?"
                    if payload.get("task") == "regenerate_one_paragraph"
                    else self.writer_text
                },
                "critic": {"verdict": "pass"},
            }
            if role == "verifier":
                outputs[role] = {
                    "claims": [
                        {
                            "index": item["index"],
                            "kind": "experience" if "built" in item["text"] else "non_experience",
                            "verdict": "supported",
                            "evidence_ids": [evidence.id],
                            "reason": "Deterministic checkpoint fixture",
                        }
                        for item in payload["sentences"]
                    ]
                }
            return schema.model_validate(outputs[role])

    store = RunStore(account_app.state.engine)
    job = store.create_job(
        tenant,
        ManualJob(
            title="Python API", description="Build an API", billing_type="hourly", budget_max=30
        ),
    )
    run = store.create_run(tenant, job.id, str(uuid4()))

    async def process(target_id=None):
        return await process_bid(
            account_app.state.engine,
            account_app.state.settings,
            tenant,
            target_id or run.id,
            models_factory=Models,
            portfolio_reader=Reader(),
        )

    def review(action, **kwargs):
        current = store.run(tenant, run.id)
        return store.review(
            tenant,
            ReviewRun(
                run_id=run.id,
                version=current.version,
                action=action,
                draft_digest=current.review["preview"]["arguments"]["draft_digest"],
                **kwargs,
            ),
        )

    yield store, tenant, run.id, process, review, Models, counts, account_app.state.settings
    service.index.client.close()


def test_failed_model_resumes_after_explicit_retry_without_repeating_analysis(durable):
    store, tenant, id, process, _, models, counts, _ = durable
    models.fail_writer = True
    assert execute(process())["status"] == "needs_attention"
    failed = store.run(tenant, id)
    assert failed.retryable and failed.review is None
    store.retry(tenant, id, failed.version)
    models.fail_writer = False
    assert execute(process())["status"] == "awaiting_approval"
    assert counts["analyst"] == 1 and counts["writer"] == 2
    assert store.run(tenant, id).steps > failed.steps


def test_regenerate_one_paragraph_preserves_the_rest_and_requires_fresh_approval(durable):
    store, tenant, id, process, review, models, counts, _ = durable
    models.writer_text = "I built a Python API.\n\nCould we discuss scope?"
    assert execute(process())["status"] == "awaiting_approval"
    old = store.run(tenant, id)
    review("regenerate", paragraph_index=1)
    assert execute(process())["status"] == "awaiting_approval"
    new = store.run(tenant, id)
    assert new.snapshot.draft.text == "I built a Python API.\n\nCould we clarify priorities?"
    assert old.review["interrupt_id"] != new.review["interrupt_id"]
    assert counts["writer"] == counts["verifier"] == 2
    assert counts["analyst"] == 1
    from agent.run_store import RunConflict, RunNotFound

    with pytest.raises(RunNotFound):
        store.local_draft(tenant, id)
    with pytest.raises(RunConflict):
        review("regenerate", paragraph_index=99)
    review("approve")
    assert execute(process())["status"] == "drafted"


def test_postgres_pause_edit_restart_and_approved_local_commit(durable):
    store, tenant, id, process, review, _, counts, _ = durable
    result = execute(process())
    assert result["status"] == "awaiting_approval", (result, store.run(tenant, id).error)
    first = store.run(tenant, id)
    assert first.review["interrupt_id"]
    review("edit", edited_text="Could we discuss scope?")
    assert execute(process())["status"] == "awaiting_approval"
    edited = store.run(tenant, id)
    assert edited.review["interrupt_id"] != first.review["interrupt_id"]
    assert edited.review["draft"]["text"] == "Could we discuss scope?"
    review("approve")
    assert execute(process())["status"] == "drafted"
    assert store.local_draft(tenant, id).draft["text"] == "Could we discuss scope?"
    assert counts["writer"] == 1 and counts["verifier"] == 2
    assert execute(process())["status"] == "not_pending"
    with Session(store.engine) as db:
        assert db.scalar(select(func.count()).select_from(LocalDraftArtifact)) == 1
        assert db.scalar(select(func.count()).select_from(ApprovalAudit)) == 2


def test_interrupted_worker_resumes_checkpoint_without_repeating_analysis(durable):
    store, tenant, id, process, _, models, counts, _ = durable
    models.crash_writer = True
    try:
        result = execute(process())
    except asyncio.CancelledError:
        pass
    else:
        pytest.fail(f"Expected cancellation, got {result}; calls={counts}")
    assert store.run(tenant, id).status == "running"
    models.crash_writer = False
    assert execute(process())["status"] == "awaiting_approval"
    assert counts["analyst"] == 1 and counts["risk"] == 1
    assert counts["writer"] == 2


def test_crash_after_new_interrupt_does_not_reuse_old_edit(durable, monkeypatch):
    store, tenant, id, process, review, _, counts, _ = durable
    execute(process())
    first_id = store.run(tenant, id).review["interrupt_id"]
    review("edit", edited_text="Could we discuss scope?")
    original_save = RunStore.save

    def crash_before_review_publication(self, *args, **kwargs):
        if kwargs.get("complete"):
            raise asyncio.CancelledError()
        return original_save(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(RunStore, "save", crash_before_review_publication)
        with pytest.raises(asyncio.CancelledError):
            execute(process())
    assert store.run(tenant, id).status == "running"
    assert execute(process())["status"] == "awaiting_approval"
    current = store.run(tenant, id)
    assert current.review["interrupt_id"] != first_id
    assert current.review["draft"]["text"] == "Could we discuss scope?"
    assert counts["verifier"] == 2  # The old edit did not apply a second time.


def test_second_worker_cannot_acquire_an_active_run(durable):
    store, tenant, id, process, _, _, counts, settings = durable

    async def scenario():
        dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
            await saver.conn.execute(
                "SELECT pg_advisory_lock(%s)", (lock_key(f"bid:{tenant}:{id}"),)
            )
            assert (await process())["status"] == "already_running"

    execute(scenario())
    assert not counts and store.run(tenant, id).status == "queued"


def test_commit_survives_failure_before_execute_checkpoint(durable, monkeypatch):
    store, tenant, id, process, review, _, _, _ = durable
    execute(process())
    review("approve")
    original = RunStore.save_local

    def commit_then_crash(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError("Development crash after SQL commit")

    with monkeypatch.context() as patch:
        patch.setattr(RunStore, "save_local", commit_then_crash)
        assert execute(process())["status"] == "drafted"
    assert store.run(tenant, id).status == "drafted"
    assert execute(process())["status"] == "not_pending"
    with Session(store.engine) as db:
        assert db.scalar(select(func.count()).select_from(LocalDraftArtifact)) == 1
