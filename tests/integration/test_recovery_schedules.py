from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agent.run_store import RunConflict, RunStore
from apps.api.models import AgentRun, FreelancerProfile, JobRecord, utcnow
from apps.api.schemas.proposals import ManualJob
from apps.api.schemas.schedules import ScheduleUpdate
from tests.integration.test_runs import register
from worker.search_schedules import SearchSchedules


@pytest.fixture
def recovery(client, account_app):
    user = register(client, "recovery@example.org")
    store = RunStore(account_app.state.engine)
    job = store.create_job(
        user["id"],
        ManualJob(
            title="Recovery fixture",
            description="Build an API",
            billing_type="hourly",
            budget_max=30,
        ),
    )
    run = store.create_run(user["id"], job.id, str(uuid4()))
    return user, store, run


def test_retry_preserves_budget_and_command_then_stops_at_limit(recovery):
    user, store, run = recovery
    tenant = user["id"]
    with Session(store.engine) as db, db.begin():
        row = db.get(AgentRun, run.id)
        row.tokens, row.steps = 300, 4
        row.resume = {"interrupt_id": "fixture", "decision": {"action": "approve"}}
    for attempt in range(4):
        token = str(uuid4())
        store.claim(tenant, run.id, token)
        store.fail(tenant, run.id, token, "Local model unavailable", retryable=True)
        failed = store.run(tenant, run.id)
        if attempt == 3:
            assert failed.status == "failed" and not failed.retryable
            with pytest.raises(RunConflict):
                store.retry(tenant, run.id, failed.version)
        else:
            queued = store.retry(tenant, run.id, failed.version)
            assert queued.retry_count == attempt + 1
            assert queued.tokens == 300 and queued.steps == 4
            with Session(store.engine) as db:
                assert db.get(AgentRun, run.id).resume["interrupt_id"] == "fixture"
            with pytest.raises(RunConflict):
                store.retry(tenant, run.id, failed.version)


def test_retry_endpoint_requires_owner_csrf_and_recoverable_failure(recovery, client, account_app):
    user, store, run = recovery
    store.claim(user["id"], run.id, "fixture")
    store.fail(user["id"], run.id, "fixture", "Budget exhausted")
    url = f"/api/runs/{run.id}/retry"
    headers = {"X-CSRF-Token": user["csrf_token"]}
    version = store.run(user["id"], run.id).version
    assert client.post(url, json={"version": version}, headers=headers).status_code == 409
    with Session(store.engine) as db, db.begin():
        db.get(AgentRun, run.id).retryable = True  # Recoverable outage fixture.
    assert client.post(url, json={"version": version}).status_code == 403
    with TestClient(account_app) as other:
        stranger = register(other, "other-recovery@example.org")
        assert (
            other.post(
                url, json={"version": version}, headers={"X-CSRF-Token": stranger["csrf_token"]}
            ).status_code
            == 404
        )

    async def unavailable(*args):
        return False

    account_app.state.enqueue_run = unavailable
    response = client.post(url, json={"version": version}, headers=headers)
    assert response.status_code == 202 and response.json()["status"] == "queued"
    assert "queue unavailable" in response.json()["error"].lower()
    assert store.pending() == [(user["id"], run.id)]


def test_concurrent_retry_requests_enqueue_only_one_transition(recovery):
    user, store, run = recovery
    if store.engine.dialect.name != "postgresql":
        pytest.skip("Row-lock arbitration is a Postgres production contract")
    store.claim(user["id"], run.id, "fixture")
    store.fail(user["id"], run.id, "fixture", "Unavailable", retryable=True)
    version = store.run(user["id"], run.id).version

    def retry():
        try:
            store.retry(user["id"], run.id, version)
            return "queued"
        except RunConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: retry(), range(2))) == ["conflict", "queued"]


def test_schedule_ticks_pause_and_never_create_fake_jobs(recovery):
    user, store, _ = recovery
    now = utcnow()
    schedules = SearchSchedules(store.engine, clock=lambda: now)
    assert schedules.get(user["id"]).status == "paused"
    with Session(store.engine) as db, db.begin():
        db.get(FreelancerProfile, user["id"]).saved_searches = ["Python API"]
    saved = schedules.update(
        user["id"], ScheduleUpdate(version=0, enabled=True, interval_minutes=5)
    )
    assert saved.queries == ["Python API"] and saved.status == "waiting_provider"
    assert schedules.check_due() == 1
    checked = schedules.get(user["id"])
    assert checked.last_checked_at == now
    assert checked.next_check_at == now + timedelta(minutes=5)
    assert schedules.check_due() == 0
    with pytest.raises(RunConflict):
        schedules.update(
            user["id"], ScheduleUpdate(version=saved.version, enabled=False, interval_minutes=5)
        )
    with Session(store.engine) as db:
        assert db.scalar(select(func.count()).select_from(JobRecord)) == 1
    schedules.update(
        user["id"], ScheduleUpdate(version=checked.version, enabled=False, interval_minutes=60)
    )
    assert schedules.get(user["id"]).next_check_at is None


def test_schedule_api_is_account_scoped_and_uses_latest_queries(recovery, client, account_app):
    user, store, _ = recovery
    headers = {"X-CSRF-Token": user["csrf_token"]}
    body = {"version": 0, "enabled": True, "interval_minutes": 15}
    assert client.put("/api/search-schedule", json=body).status_code == 403
    assert (
        client.put(
            "/api/search-schedule", json={**body, "interval_minutes": 1}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.put("/api/search-schedule", json=body, headers=headers).json()["status"]
        == "no_queries"
    )
    with Session(store.engine) as db, db.begin():
        db.get(FreelancerProfile, user["id"]).saved_searches = ["Updated query"]
    assert client.get("/api/search-schedule").json()["queries"] == ["Updated query"]
    with TestClient(account_app) as other:
        register(other, "other-schedule@example.org")
        assert other.get("/api/search-schedule").json()["enabled"] is False
        assert other.get("/api/search-schedule").json()["queries"] == []
