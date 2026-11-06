"""Local Workspace backend. Availability is supplied by the user, writes need a review."""

from datetime import UTC, datetime, timedelta
from math import ceil
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.handoffs import ProposalDraft
from agent.run_store import RunConflict, RunNotFound, RunStore
from apps.api.models import (
    AgentRun,
    ApprovalAudit,
    CalendarAvailability,
    CalendarHold,
    User,
    WorkspaceWrite,
    utcnow,
)


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class WorkspaceService:
    def __init__(self, engine, *, clock=utcnow):
        self.engine, self.clock = engine, clock

    def availability(self, tenant):
        with Session(self.engine) as db:
            return [
                {"id": row.id, "start": utc(row.start), "end": utc(row.end)}
                for row in db.scalars(
                    select(CalendarAvailability)
                    .where(CalendarAvailability.user_id == tenant)
                    .order_by(CalendarAvailability.start)
                    .limit(500)
                )
            ]

    def add_availability(self, tenant, start, end):
        start, end = utc(start), utc(end)
        if end <= self.clock():
            raise RunConflict("Choose availability ending in the future")
        with Session(self.engine) as db, db.begin():
            self._owner_lock(db, tenant)
            row = CalendarAvailability(id=str(uuid4()), user_id=tenant, start=start, end=end)
            db.add(row)
            return {"id": row.id, "start": start, "end": end}

    def remove_availability(self, tenant, id):
        with Session(self.engine) as db, db.begin():
            self._owner_lock(db, tenant)
            row = db.scalar(
                select(CalendarAvailability).where(
                    CalendarAvailability.user_id == tenant,
                    CalendarAvailability.id == id,
                )
            )
            if row is None:
                raise RunNotFound("Availability window not found")
            db.delete(row)

    def _owner_lock(self, db, tenant):
        if (
            db.scalar(select(User.id).where(User.id == tenant).with_for_update(key_share=True))
            is None
        ):
            raise RunNotFound("Account not found")

    def _can_hold(self, db, tenant, start, end):
        window = db.scalar(
            select(CalendarAvailability.id)
            .where(
                CalendarAvailability.user_id == tenant,
                CalendarAvailability.start <= start,
                CalendarAvailability.end >= end,
            )
            .limit(1)
        )
        busy = db.scalar(
            select(CalendarHold.id)
            .where(
                CalendarHold.user_id == tenant,
                CalendarHold.start < end,
                CalendarHold.end > start,
            )
            .limit(1)
        )
        return window is not None and busy is None

    def free_slots(self, tenant, request):
        start = max(request.start, self.clock())
        duration = timedelta(minutes=request.minutes)
        # Align candidates to a UTC quarter hour and preserve explicit timezone output.
        tick = datetime.fromtimestamp(ceil(start.timestamp() / 900) * 900, UTC)
        slots = []
        with Session(self.engine) as db:
            windows = [
                (utc(row.start), utc(row.end))
                for row in db.scalars(
                    select(CalendarAvailability).where(
                        CalendarAvailability.user_id == tenant,
                        CalendarAvailability.start < request.end,
                        CalendarAvailability.end > start,
                    )
                )
            ]
            busy = [
                (utc(row.start), utc(row.end))
                for row in db.scalars(
                    select(CalendarHold).where(
                        CalendarHold.user_id == tenant,
                        CalendarHold.start < request.end,
                        CalendarHold.end > start,
                    )
                )
            ]
        while tick + duration <= request.end and len(slots) < 20:
            finish = tick + duration
            declared = any(left <= tick and right >= finish for left, right in windows)
            occupied = any(left < finish and right > tick for left, right in busy)
            if declared and not occupied:
                slots.append({"start": tick.isoformat(), "end": finish.isoformat()})
            tick += timedelta(minutes=15)
        return {"backend": "local", "slots": slots}

    def hold(self, tenant, run_id, request):
        start, end = request.start, request.start + timedelta(minutes=request.minutes)
        arguments = {"start": start.isoformat(), "minutes": request.minutes}
        if request.dry_run:
            with Session(self.engine) as db:
                available = start >= self.clock() and self._can_hold(db, tenant, start, end)
            return {
                "backend": "local",
                "dry_run": True,
                "tool": "create_interview_hold",
                "arguments": arguments,
                "available": available,
                "cost": 0,
            }
        return self._write(
            tenant,
            run_id,
            "create_interview_hold",
            request.idempotency_key,
            arguments,
            start=start,
            end=end,
        )

    def email(self, tenant, run_id, request):
        arguments = request.arguments()
        if not request.subject.strip() or not request.body.strip():
            raise RunConflict("A subject and body are required")
        if request.dry_run:
            return {
                "backend": "local",
                "dry_run": True,
                "tool": "create_email_draft",
                "arguments": arguments,
                "cost": 0,
            }
        return self._write(tenant, run_id, "create_email_draft", request.idempotency_key, arguments)

    def _write(self, tenant, run_id, tool, key, arguments, *, start=None, end=None):
        with Session(self.engine) as db, db.begin():
            run = db.scalar(
                select(AgentRun)
                .where(
                    AgentRun.id == run_id,
                    AgentRun.user_id == tenant,
                )
                .with_for_update()
            )
            if run is None:
                raise RunNotFound("Approved run not found")
            self._owner_lock(db, tenant)
            existing = db.scalar(
                select(WorkspaceWrite).where(
                    WorkspaceWrite.user_id == tenant,
                    WorkspaceWrite.tool == tool,
                    WorkspaceWrite.idempotency_key == key,
                )
            )
            if existing:
                if existing.arguments != arguments or existing.run_id != run_id:
                    raise RunConflict("This idempotency key has different arguments")
                return existing.result
            approval = db.scalar(
                select(ApprovalAudit)
                .where(
                    ApprovalAudit.run_id == run_id,
                    ApprovalAudit.user_id == tenant,
                )
                .order_by(ApprovalAudit.version.desc())
                .limit(1)
            )
            preview = approval.preview if approval else None
            if (
                approval is None
                or approval.decision.get("action") != "approve"
                or not preview
                or preview.get("tool") != tool
                or preview.get("arguments") != arguments
                or preview.get("idempotency_key") != key
                or run.snapshot.get("preview") != preview
                or run.status not in {"queued", "running"}
            ):
                raise RunConflict("This action needs approval of its exact preview")
            if tool == "create_interview_hold":
                if start < self.clock() or not self._can_hold(db, tenant, start, end):
                    raise RunConflict("The reviewed calendar slot is no longer available")
            for slot in arguments.get("calendar_slots", []):
                slot_start, slot_end = (
                    datetime.fromisoformat(slot["start"]),
                    datetime.fromisoformat(slot["end"]),
                )
                if slot_start < self.clock() or not self._can_hold(
                    db, tenant, slot_start, slot_end
                ):
                    raise RunConflict("The reviewed interview options are no longer available")
            if run.snapshot.get("draft"):
                RunStore(self.engine)._check_evidence(
                    db, tenant, ProposalDraft.model_validate(run.snapshot["draft"])
                )
            id = str(uuid4())
            result = {
                "id": id,
                "backend": "local",
                "tool": tool,
                "status": "tentative" if tool == "create_interview_hold" else "draft",
                "arguments": arguments,
            }
            db.add(
                WorkspaceWrite(
                    id=id,
                    user_id=tenant,
                    run_id=run_id,
                    approval_id=approval.id,
                    tool=tool,
                    idempotency_key=key,
                    arguments=arguments,
                    result=result,
                )
            )
            db.flush()
            if tool == "create_interview_hold":
                db.add(CalendarHold(id=id, user_id=tenant, start=start, end=end))
            return result

    def actions(self, tenant):
        with Session(self.engine) as db:
            return [
                {
                    "id": row.id,
                    "run_id": row.run_id,
                    "tool": row.tool,
                    "result": row.result,
                    "created_at": utc(row.created_at),
                }
                for row in db.scalars(
                    select(WorkspaceWrite)
                    .where(WorkspaceWrite.user_id == tenant)
                    .order_by(WorkspaceWrite.created_at.desc())
                    .limit(100)
                )
            ]
