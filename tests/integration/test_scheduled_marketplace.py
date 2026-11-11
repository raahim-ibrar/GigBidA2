from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.marketplace import MarketplaceAccounts
from apps.api.models import AgentRun, FreelancerProfile, JobRecord, SearchSchedule, utcnow
from apps.api.schemas.schedules import ScheduleUpdate
from mcp_servers.marketplace.adapters.student_sim import StudentSimAdapter
from simulator.app import create_app
from tests.integration.test_runs import register
from worker.search_schedules import SearchSchedules, check_search_schedules


@pytest.mark.asyncio
async def test_scheduled_real_mcp_search_deduplicates_bounds_analysis_and_preserves_outage(
    client, account_app, tmp_path, monkeypatch
):
    tenant = register(client, "scheduled-sim@example.org")["id"]
    engine, settings = account_app.state.engine, account_app.state.settings
    sim = create_app(tmp_path / "scheduled.sqlite", api_key="test-only", per_persona=3)
    adapter = StudentSimAdapter(
        "http://sim", "test-only", tenant, transport=httpx.ASGITransport(app=sim)
    )
    monkeypatch.setattr(MarketplaceAccounts, "adapter", lambda self, user: adapter)
    account_app.state.marketplace.set_mode(tenant, "student_sim")
    with Session(engine) as db, db.begin():
        db.get(FreelancerProfile, tenant).saved_searches = ["Python", "document search"]
    schedules = SearchSchedules(engine)
    schedules.update(
        tenant,
        ScheduleUpdate(
            version=0,
            enabled=True,
            auto_analyse=True,
            interval_minutes=60,
        ),
    )
    queued = []

    class Queue:
        async def enqueue_job(self, *args, **kwargs):
            queued.append(args)

    ctx = {"engine": engine, "settings": settings, "redis": Queue()}
    first = await check_search_schedules(ctx)
    assert first["imported"] > 1 and len(queued) == 1
    assert schedules.get(tenant).status == "idle"

    def due_again():
        with Session(engine) as db, db.begin():
            db.get(SearchSchedule, tenant).next_check_at = utcnow() - timedelta(minutes=1)

    due_again()
    assert (await check_search_schedules(ctx))["imported"] == 0
    assert len(queued) == 1
    sim.state.fault = "unavailable"
    due_again()
    await check_search_schedules(ctx)
    assert schedules.get(tenant).status == "unavailable"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(JobRecord)) == first["imported"]
        assert db.scalar(select(func.count()).select_from(AgentRun)) == 1
