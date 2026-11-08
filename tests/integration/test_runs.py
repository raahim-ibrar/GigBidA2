"""Account isolation and transactional review/local-save checks using development fixtures."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agent.handoffs import ApprovalDecision, Claim, ProposalDraft, WritePreview
from agent.model_client import BudgetExceeded
from agent.proposal_nodes import ReviewRequired, draft_digest
from agent.run_store import LostWorkerLease, RunConflict, RunStore
from apps.api.models import LocalDraftArtifact
from apps.api.schemas.proposals import ManualJob, ReviewRun
from rag.contracts import DocumentMetadata
from tests.portfolio_fixtures import portfolio_fixture


def register(client, email="runs@example.org"):
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "Development fixture password 123!",
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def run_fixture(client, account_app):
    user = register(client)
    store = RunStore(account_app.state.engine)
    portfolio = portfolio_fixture(account_app.state.engine)
    doc = portfolio.ingest(
        user["id"],
        "fixture.md",
        b"I built a Python API.",
        DocumentMetadata(type="case_study", project="Run test fixture"),
    )
    portfolio.index_document(user["id"], doc.id)
    evidence = portfolio.case_study(user["id"], doc.id)
    from rag.contracts import PortfolioSearch

    evidence = portfolio.search(user["id"], PortfolioSearch(query="Python")).items[0].evidence
    job = store.create_job(
        user["id"],
        ManualJob(
            title="Build a Python API",
            description="Develop an API",
            billing_type="hourly",
            budget_max=30,
        ),
    )
    run = store.create_run(user["id"], job.id, str(uuid4()))
    token = "fixture-worker"
    store.claim(user["id"], run.id, token)
    draft = ProposalDraft(
        text="I built a Python API.",
        claims=[
            Claim(text="I built a Python API.", evidence_ids=[evidence.id], verdict="supported"),
        ],
    )
    preview = WritePreview(
        tool="save_local_draft",
        arguments={"draft_digest": draft_digest(draft)},
        connects_cost=0,
        idempotency_key=f"local:{run.id}:{draft_digest(draft)}",
    )
    state = {
        "draft": draft,
        "preview": preview,
        "evidence": [evidence],
        "status": "awaiting_approval",
    }
    review = {
        "draft": draft.model_dump(),
        "preview": preview.model_dump(),
        "interrupt_id": "fixture-interrupt",
    }
    store.save(user["id"], run.id, token, state, review, complete=True)
    store.finish(user["id"], run.id, token)

    async def queue(*args):
        return True

    account_app.state.enqueue_run = queue
    yield user, store, store.run(user["id"], run.id), state, portfolio, doc
    portfolio.index.client.close()


def review_body(run, action="approve", **kwargs):
    return ReviewRun(
        run_id=run.id,
        version=run.version,
        draft_digest=run.review["preview"]["arguments"]["draft_digest"],
        action=action,
        **kwargs,
    )


def test_jobs_runs_idempotency_and_cross_account_boundaries(account_app):
    async def unavailable(*args):
        return False

    account_app.state.enqueue_run = unavailable
    with TestClient(account_app) as alice, TestClient(account_app) as bob:
        a, b = register(alice, "alice-runs@example.org"), register(bob, "bob-runs@example.org")
        headers = {"X-CSRF-Token": a["csrf_token"]}
        job_body = {
            "title": "API",
            "description": "Build an API",
            "billing_type": "fixed",
            "budget_max": 200,
        }
        assert alice.post("/api/jobs", json=job_body).status_code == 403
        job = alice.post("/api/jobs", json=job_body, headers=headers).json()
        assert alice.post("/api/jobs", json=job_body, headers=headers).json()["id"] == job["id"]
        body = {"job_id": job["id"], "idempotency_key": str(uuid4())}
        created = alice.post("/api/runs", json=body, headers=headers)
        assert created.status_code == 202, created.text
        run = created.json()
        assert "queue unavailable" in run["error"].lower()
        assert alice.post("/api/runs", json=body, headers=headers).json()["id"] == run["id"]
        for url in (
            f"/api/jobs/{job['id']}",
            f"/api/runs/{run['id']}",
            f"/api/runs/{run['id']}/events",
            f"/api/proposals/{run['id']}",
        ):
            assert bob.get(url).status_code == 404
        assert bob.get("/api/jobs").json() == [] and bob.get("/api/runs").json() == []
        assert (
            bob.post("/api/runs", json=body, headers={"X-CSRF-Token": b["csrf_token"]}).status_code
            == 404
        )


def test_review_rejects_stale_version_digest_and_duplicate_decisions(client, run_fixture):
    user, store, run, _, _, _ = run_fixture
    body = review_body(run).model_dump(mode="json")
    headers = {"X-CSRF-Token": user["csrf_token"]}
    assert (
        client.post(
            "/api/approvals", json={**body, "version": run.version + 1}, headers=headers
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/approvals", json={**body, "draft_digest": "0" * 64}, headers=headers
        ).status_code
        == 409
    )
    assert client.post("/api/approvals", json=body).status_code == 403
    response = client.post("/api/approvals", json=body, headers=headers)
    assert response.status_code == 202, response.text
    assert client.post("/api/approvals", json=body, headers=headers).status_code == 409
    claimed = store.claim(user["id"], run.id, "next-worker")
    assert claimed["resume"] == {
        "interrupt_id": "fixture-interrupt",
        "decision": {
            "action": "approve",
            "reason": None,
            "edited_text": None,
            "paragraph_index": None,
        },
    }


def test_local_save_requires_audit_is_idempotent_and_recovers_after_checkpoint_loss(run_fixture):
    user, store, run, state, _, _ = run_fixture
    tenant, token = user["id"], "next-worker"
    store.claim(tenant, run.id, token)  # Awaiting review cannot be claimed yet.
    store.review(tenant, review_body(run))
    store.claim(tenant, run.id, token)
    state["approval"] = ApprovalDecision(action="approve")
    first = store.save_local(tenant, run.id, token, state)
    second = store.save_local(tenant, run.id, token, state)
    assert first == second
    with Session(store.engine) as db:
        assert db.scalar(select(func.count()).select_from(LocalDraftArtifact)) == 1
    assert store.recover_local(tenant, run.id, token)
    assert store.run(tenant, run.id).status == "drafted"


def test_unapproved_or_stale_source_cannot_be_written(run_fixture):
    user, store, run, state, portfolio, doc = run_fixture
    tenant, token = user["id"], "bad-worker"
    # No audit exists even if an untrusted caller claims its own approval in state.
    store.review(tenant, review_body(run, action="edit", edited_text="A changed draft"))
    store.claim(tenant, run.id, token)
    state["approval"] = ApprovalDecision(action="approve")
    with pytest.raises(ReviewRequired, match="approval"):
        store.save_local(tenant, run.id, token, state)
    # Use a fresh run/review to test stale evidence at the approval boundary.
    portfolio.delete_document(tenant, doc.id)
    from apps.api.models import AgentRun

    with Session(store.engine) as db, db.begin():
        row = db.get(AgentRun, run.id)
        row.status, row.review = "awaiting_approval", run.review
    current = store.run(tenant, run.id)
    with pytest.raises(ReviewRequired, match="evidence changed"):
        store.review(tenant, review_body(current))


def test_durable_budgets_and_worker_fence(run_fixture):
    user, store, run, _, _, _ = run_fixture
    tenant, token = user["id"], "lease-1"
    store.review(tenant, review_body(run))
    store.claim(tenant, run.id, token)
    store.reserve(tenant, run.id, token, 1000, 16000)
    store.settle(tenant, run.id, token, 1000, 200)
    assert store.run(tenant, run.id).tokens == 200
    with pytest.raises(BudgetExceeded):
        store.reserve(tenant, run.id, token, 16000, 16000)
    store.step(tenant, run.id, token, "fixture", 1)
    with pytest.raises(BudgetExceeded):
        store.step(tenant, run.id, token, "fixture", 1)
    store.claim(tenant, run.id, "lease-2")
    with pytest.raises(LostWorkerLease):
        store.event(tenant, run.id, token, "stale", {})


def test_sse_reconnect_only_returns_new_persisted_events(client, run_fixture):
    user, store, run, _, _, _ = run_fixture
    events = store.events(user["id"], run.id)
    last = events[-1].id
    response = client.get(f"/api/runs/{run.id}/events", headers={"Last-Event-ID": str(last)})
    assert response.status_code == 200 and "event: done" in response.text
    assert "event: progress" not in response.text
    response = client.get(f"/api/runs/{run.id}/events?after=0")
    assert "event: progress" in response.text and f"id: {last}" in response.text


def test_concurrent_approval_requests_have_one_winner(run_fixture):
    user, store, run, _, _, _ = run_fixture
    if store.engine.dialect.name != "postgresql":
        pytest.skip("Requires Postgres row-lock semantics")
    body = review_body(run)

    def attempt():
        try:
            store.review(user["id"], body)
            return "accepted"
        except RunConflict:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == ["accepted", "stale"]
