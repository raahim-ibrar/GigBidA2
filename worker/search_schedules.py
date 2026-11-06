"""Durable polling configuration; no search result is invented while the adapter is absent.

The worker checks prerequisites on schedule. Provider reads and result ingestion must
be implemented against the supplied GigSim contract before this can fetch jobs.
"""

from datetime import UTC, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.run_store import RunConflict, RunNotFound
from apps.api.models import FreelancerProfile, SearchSchedule, User, utcnow
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
            interval_minutes=row.interval_minutes if row else 60,
            queries=queries,
            status=("no_queries" if not queries else "waiting_provider")
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
            row.enabled, row.interval_minutes = body.enabled, body.interval_minutes
            row.version += 1
            row.next_check_at = self.clock() if body.enabled else None
            row.status = "waiting_provider" if body.enabled else "paused"
            return self._view(db, tenant, row)

    def check_due(self):
        now = self.clock()
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
                row.last_checked_at = now
                row.next_check_at = now + timedelta(minutes=row.interval_minutes)
                # Version covers worker changes too; stale UI edits must reload.
                row.version += 1
            return len(rows)


async def check_search_schedules(ctx):
    import asyncio

    return await asyncio.to_thread(SearchSchedules(ctx["engine"]).check_due)
