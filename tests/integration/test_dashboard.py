from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from agent.run_store import RunConflict, RunStore
from apps.api.models import AgentRun, ApprovalAudit, JobRecord, LocalDraftArtifact, RunEvent, utcnow
from apps.api.schemas.dashboard import ProviderReceipt
from apps.api.schemas.proposals import ManualJob
from tests.integration.test_runs import register


@pytest.fixture
def dashboard(client, account_app):
    user = register(client, "dashboard@example.org")
    store = RunStore(account_app.state.engine)
    job = store.create_job(
        user["id"],
        ManualJob(
            title="Dashboard API fixture",
            description="Build an API",
            billing_type="hourly",
            budget_max=30,
        ),
    )
    run = store.create_run(user["id"], job.id, str(uuid4()))
    return user, store, run, account_app.state.dashboard


def receipt(stage, **kwargs):
    return ProviderReceipt(
        event_id=str(uuid4()),
        proposal_id="provider-fixture",
        source="gigsim",
        stage=stage,
        occurred_at=utcnow() - timedelta(minutes=1),
        **kwargs,
    )


def provider_job(store, run):
    with Session(store.engine) as db, db.begin():
        job = db.get(JobRecord, run.job_id)
        job.raw = {**job.raw, "source": "gigsim", "category": "full_stack"}


def test_local_draft_is_not_submission_and_unknown_metrics_stay_null(dashboard, client):
    user, store, run, service = dashboard
    assert service.pipeline(user["id"]).cards == []
    with Session(store.engine) as db, db.begin():
        db.add(
            LocalDraftArtifact(
                run_id=run.id,
                user_id=user["id"],
                draft={"text": "Local draft"},
                idempotency_key=str(uuid4()),
            )
        )
    assert service.pipeline(user["id"]).cards[0].stage == "drafted"
    summary = client.get("/api/analytics").json()
    assert summary["local_drafts"] == 1 and summary["provider_submissions"] == 0
    assert summary["connects_spent"] is None and summary["category_rates"] == []
    assert summary["inference_api_usd"] is None
    assert summary["measurements"][0]["measured_worker_seconds"] is None
    with pytest.raises(RunConflict, match="local/manual"):
        service.record_provider_event(user["id"], run.id, receipt("submitted"))
    assert client.post("/api/pipeline", json={"stage": "hired"}).status_code == 405


def test_provider_receipts_deduplicate_and_do_not_regress_pipeline(dashboard):
    user, store, run, service = dashboard
    provider_job(store, run)
    submitted = receipt("submitted", connects_spent=8)
    id = service.record_provider_event(user["id"], run.id, submitted)
    assert service.record_provider_event(user["id"], run.id, submitted) == id
    service.record_provider_event(user["id"], run.id, receipt("interview"))
    service.record_provider_event(user["id"], run.id, receipt("viewed"))
    assert service.pipeline(user["id"]).cards[0].stage == "interview"
    summary = service.analytics(user["id"], 30)
    assert summary.connects_spent == 8 and summary.submissions_with_known_spend == 1
    rate = summary.category_rates[0]
    assert rate.submitted == rate.replied == 1 and rate.hired == 0
    with pytest.raises(RunConflict, match="conflicting"):
        service.record_provider_event(
            user["id"], run.id, submitted.model_copy(update={"connects_spent": 9})
        )
    service.record_provider_event(user["id"], run.id, receipt("hired"))
    with pytest.raises(RunConflict, match="terminal"):
        service.record_provider_event(user["id"], run.id, receipt("lost"))
    another = store.create_run(user["id"], run.job_id, str(uuid4()))
    with pytest.raises(RunConflict, match="another run"):
        service.record_provider_event(user["id"], another.id, receipt("submitted"))


def test_incomplete_provider_history_does_not_invent_a_denominator(dashboard):
    user, store, run, service = dashboard
    provider_job(store, run)
    service.record_provider_event(user["id"], run.id, receipt("replied"))
    summary = service.analytics(user["id"], 30)
    assert summary.provider_submissions == 0 and not summary.category_rates
    assert service.pipeline(user["id"]).cards[0].stage == "replied"


def test_actual_usage_worker_segments_and_private_rejection_reasons(dashboard):
    user, store, run, service = dashboard
    start = utcnow() - timedelta(minutes=20)
    events = [
        ("worker_started", {}, 0),
        (
            "model_usage",
            {"input_tokens": 10, "output_tokens": 5, "elapsed_seconds": 2.5, "usd": 0},
            1,
        ),
        ("state_saved", {"status": "awaiting_approval"}, 3),
        ("review_decision", {"action": "approve"}, 600),
        ("worker_started", {}, 601),
        ("state_saved", {"status": "drafted"}, 603),
    ]
    with Session(store.engine) as db, db.begin():
        db.get(AgentRun, run.id).tokens = 100
        for kind, details, seconds in events:
            db.add(
                RunEvent(
                    run_id=run.id,
                    kind=kind,
                    details=details,
                    created_at=start + timedelta(seconds=seconds),
                )
            )
        db.add(
            ApprovalAudit(
                run_id=run.id,
                user_id=user["id"],
                version=1,
                draft_digest="a" * 64,
                decision={"action": "reject", "reason": "Contact me at private@example.org"},
            )
        )
    summary = service.analytics(user["id"], 30)
    item = summary.measurements[0]
    assert item.charged_or_reserved_tokens == 100 and item.measured_model_tokens == 15
    assert item.model_call_seconds == 2.5 and item.inference_api_usd == 0
    assert item.measured_worker_seconds == 5  # Human review delay is excluded.
    assert "private@example.org" not in summary.rejection_reasons[0].reason
    with Session(store.engine) as db, db.begin():
        db.get(AgentRun, run.id).created_at = utcnow() - timedelta(days=60)
    assert service.analytics(user["id"], 30).rejection_reasons == []


def test_dashboard_requires_auth_and_isolates_accounts(dashboard, account_app, client):
    user, store, run, service = dashboard
    provider_job(store, run)
    service.record_provider_event(user["id"], run.id, receipt("submitted", connects_spent=0))
    with TestClient(account_app) as other:
        assert other.get("/api/analytics").status_code == 401
        register(other, "other-dashboard@example.org")
        assert other.get("/api/analytics").json()["run_count"] == 0
        assert other.get("/api/pipeline").json()["cards"] == []
    assert client.get("/api/analytics?days=0").status_code == 422
    assert client.get("/api/analytics?days=366").status_code == 422
