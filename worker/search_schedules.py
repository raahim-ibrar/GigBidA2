"""Durable, bounded simulator searches with opt-in analysis and no automatic writes."""

from datetime import UTC, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.run_store import RunConflict, RunNotFound
from apps.api.models import (
    AgentRun,
    FreelancerProfile,
    JobRecord,
    MarketplaceConnection,
    SearchSchedule,
    User,
    utcnow,
)
from apps.api.schemas.schedules import ScheduleView


def aware(value):
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


class SearchSchedules:
    def __init__(self, engine, *, clock=utcnow):
        self.engine, self.clock = engine, clock

    def _view(self, db, tenant, row):
        profile = db.get(FreelancerProfile, tenant)
        queries = profile.saved_searches if profile else []
        return ScheduleView(
            version=row.version if row else 0,
            enabled=row.enabled if row else False,
            auto_analyse=row.auto_analyse if row else False,
            interval_minutes=row.interval_minutes if row else 60,
            queries=queries,
            status=("no_queries" if not queries else row.status)
            if row and row.enabled
            else "paused",
            next_check_at=aware(row.next_check_at) if row else None,
            last_checked_at=aware(row.last_checked_at) if row else None,
        )

    def get(self, tenant):
        with Session(self.engine) as db:
            return self._view(db, tenant, db.get(SearchSchedule, tenant))

    def update(self, tenant, body):
        with Session(self.engine) as db, db.begin():
            # Serializes first creation, while allowing unrelated FK inserts.
            if (
                db.scalar(select(User.id).where(User.id == tenant).with_for_update(key_share=True))
                is None
            ):
                raise RunNotFound("Account not found")
            # The worker also updates this row. Wait for its commit before checking
            # the version, rather than overwriting a newer tick with a stale read.
            row = db.scalar(
                select(SearchSchedule).where(SearchSchedule.user_id == tenant).with_for_update()
            )
            if body.version != (row.version if row else 0):
                raise RunConflict("The search schedule changed. Reload Settings.")
            if row is None:
                row = SearchSchedule(user_id=tenant, version=0)
                db.add(row)
            connection = db.get(MarketplaceConnection, tenant)
            if (
                connection
                and connection.mode == "upwork"
                and (body.auto_analyse or body.interval_minutes < 60)
            ):
                raise RunConflict(
                    "Live Upwork schedules require at least 60 minutes and automatic analysis off"
                )
            row.enabled, row.interval_minutes = body.enabled, body.interval_minutes
            row.auto_analyse = body.auto_analyse
            row.version += 1
            row.next_check_at = self.clock() if body.enabled else None
            row.status = "waiting_provider" if body.enabled else "paused"
            return self._view(db, tenant, row)

    def check_due(self, *, collect=False):
        now = self.clock()
        work = []
        with Session(self.engine) as db, db.begin():
            rows = db.scalars(
                select(SearchSchedule)
                .where(SearchSchedule.enabled.is_(True), SearchSchedule.next_check_at <= now)
                .order_by(SearchSchedule.next_check_at)
                .limit(100)
                .with_for_update(skip_locked=True)
            ).all()
            for row in rows:
                profile = db.get(FreelancerProfile, row.user_id)
                row.status = (
                    "waiting_provider" if profile and profile.saved_searches else "no_queries"
                )
                connection = db.get(MarketplaceConnection, row.user_id)
                if (
                    profile
                    and profile.saved_searches
                    and connection
                    and connection.mode in {"student_sim", "upwork"}
                ):
                    row.status = "queued"
                    queries = (
                        profile.saved_searches[:1]
                        if connection.mode == "upwork"
                        else profile.saved_searches[:5]
                    )
                    work.append(
                        (
                            row.user_id,
                            queries,
                            row.auto_analyse if connection.mode != "upwork" else False,
                        )
                    )
                row.last_checked_at = now
                row.next_check_at = now + timedelta(minutes=row.interval_minutes)
                # Version covers worker changes too; stale UI edits must reload.
                row.version += 1
            return work if collect else len(rows)

    def finish(self, tenant, status):
        with Session(self.engine) as db, db.begin():
            row = db.get(SearchSchedule, tenant)
            if row and row.enabled:
                row.status = status
                row.version += 1


async def check_search_schedules(ctx):
    import asyncio
    from uuid import NAMESPACE_URL, uuid5

    from mcp.shared.memory import create_connected_server_and_client_session

    from agent.marketplace_client import MarketplaceMCP
    from agent.run_store import RunStore
    from apps.api.marketplace import MarketplaceAccounts
    from mcp_servers.marketplace.factory import create_marketplace_server
    from mcp_servers.marketplace.service import MarketplaceService

    engine, settings = ctx["engine"], ctx["settings"]
    schedules, accounts = SearchSchedules(engine), MarketplaceAccounts(engine, settings)
    work = await asyncio.to_thread(schedules.check_due, collect=True)
    imported = 0
    for tenant, queries, analyse in work:
        try:
            service = MarketplaceService(engine, settings, tenant, adapter=accounts.adapter(tenant))
            with Session(engine) as db:
                existing = set(db.scalars(select(JobRecord.id).where(JobRecord.user_id == tenant)))
            new_jobs = []
            server = create_marketplace_server(service, tenant)
            async with create_connected_server_and_client_session(server) as session:
                for query in queries:
                    result = await MarketplaceMCP(session).search(query, 20)
                    for raw in result["items"]:
                        job = await asyncio.to_thread(accounts.import_job, tenant, raw)
                        if job.id not in existing:
                            existing.add(job.id)
                            new_jobs.append(job)
            imported += len(new_jobs)
            if analyse and new_jobs:
                # At most one new analysis per account/tick. No submission is authorized here.
                job = new_jobs[0]
                with Session(engine) as db:
                    known = db.scalar(
                        select(AgentRun.id).where(
                            AgentRun.user_id == tenant,
                            AgentRun.job_id == job.id,
                        )
                    )
                if not known:
                    run = await asyncio.to_thread(
                        RunStore(engine).create_run,
                        tenant,
                        job.id,
                        str(uuid5(NAMESPACE_URL, "saved-search:" + tenant + ":" + job.id)),
                    )
                    await ctx["redis"].enqueue_job(
                        "run_bid", tenant, run.id, _job_id=f"bid:{run.id}"
                    )
            await asyncio.to_thread(schedules.finish, tenant, "idle")
        except Exception:
            # The already-reserved next tick bounds retries, including 429/503 outages.
            await asyncio.to_thread(schedules.finish, tenant, "unavailable")
            await asyncio.to_thread(
                accounts.failure, tenant, "Scheduled simulator search unavailable"
            )
    return {"accounts": len(work), "imported": imported}
