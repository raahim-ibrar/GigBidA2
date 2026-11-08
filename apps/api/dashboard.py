"""Tenant-scoped product views and a trusted adapter-only lifecycle receipt hook."""

import math
from collections import Counter, defaultdict
from datetime import UTC, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from agent.run_store import TERMINAL, RunConflict, RunNotFound
from agent.safety import mask_pii
from apps.api.models import (
    AgentRun,
    ApprovalAudit,
    JobRecord,
    LocalDraftArtifact,
    PipelineEvent,
    RunEvent,
    User,
    utcnow,
)
from apps.api.schemas.dashboard import AnalyticsView, PipelineCard, PipelineView, RunMeasurement

STAGES = {
    name: i
    for i, name in enumerate(("submitted", "viewed", "replied", "interview", "lost", "hired"))
}


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


class Dashboard:
    def __init__(self, engine):
        self.engine = engine

    def record_provider_event(self, tenant, run_id, receipt):
        """Only an authenticated provider adapter may call this; no HTTP/model write tool.

        Provider authentication and reconciliation remain the adapter's responsibility.
        A fixture invoking this hook does not establish a live marketplace integration.
        """
        if receipt.occurred_at > utcnow() + timedelta(minutes=5):
            raise RunConflict("Provider event timestamp is in the future")
        with Session(self.engine) as db, db.begin():
            # Account lock serializes duplicate event IDs across different runs too.
            db.scalar(select(User.id).where(User.id == tenant).with_for_update(key_share=True))
            row = db.execute(
                select(AgentRun, JobRecord)
                .join(JobRecord)
                .where(
                    AgentRun.id == run_id, AgentRun.user_id == tenant, JobRecord.user_id == tenant
                )
            ).first()
            if row is None:
                raise RunNotFound("Provider run not found")
            run, job = row
            if run.kind != "bid" or job.raw.get("source") != receipt.source:
                raise RunConflict("A local/manual run cannot establish a provider outcome")
            values = receipt.model_dump()
            if db.scalar(
                select(PipelineEvent.id)
                .where(
                    PipelineEvent.user_id == tenant,
                    PipelineEvent.source == receipt.source,
                    PipelineEvent.proposal_id == receipt.proposal_id,
                    PipelineEvent.run_id != run_id,
                )
                .limit(1)
            ):
                raise RunConflict("This provider proposal is already bound to another run")
            previous = db.scalar(
                select(PipelineEvent).where(
                    PipelineEvent.user_id == tenant, PipelineEvent.event_id == receipt.event_id
                )
            )
            if previous:
                if previous.run_id != run_id or any(
                    (
                        utc(getattr(previous, key))
                        if key == "occurred_at"
                        else getattr(previous, key)
                    )
                    != value
                    for key, value in values.items()
                ):
                    raise RunConflict("Provider event ID has conflicting content")
                return previous.id
            history = db.scalars(
                select(PipelineEvent).where(
                    PipelineEvent.user_id == tenant, PipelineEvent.run_id == run_id
                )
            ).all()
            if any(
                item.proposal_id != receipt.proposal_id or item.source != receipt.source
                for item in history
            ):
                raise RunConflict("The run belongs to a different provider proposal")
            if any({item.stage, receipt.stage} == {"hired", "lost"} for item in history):
                raise RunConflict("Conflicting terminal provider outcomes require reconciliation")
            if receipt.stage == "submitted" and any(item.stage == "submitted" for item in history):
                raise RunConflict("A submission receipt is already recorded for this proposal")
            event = PipelineEvent(user_id=tenant, run_id=run_id, **values)
            db.add(event)
            db.flush()
            return event.id

    def pipeline(self, tenant):
        with Session(self.engine) as db:
            drafts = select(LocalDraftArtifact.run_id).where(LocalDraftArtifact.user_id == tenant)
            receipts = select(PipelineEvent.run_id).where(PipelineEvent.user_id == tenant)
            rows = db.execute(
                select(AgentRun, JobRecord)
                .join(JobRecord)
                .where(
                    AgentRun.user_id == tenant,
                    JobRecord.user_id == tenant,
                    AgentRun.kind == "bid",
                    or_(AgentRun.id.in_(drafts), AgentRun.id.in_(receipts)),
                )
                .order_by(AgentRun.updated_at.desc(), AgentRun.id)
                .limit(201)
            ).all()
            ids = [row[0].id for row in rows[:200]]
            events = defaultdict(list)
            for item in db.scalars(
                select(PipelineEvent).where(
                    PipelineEvent.user_id == tenant, PipelineEvent.run_id.in_(ids)
                )
            ):
                events[item.run_id].append(item)
            cards = []
            for run, job in rows[:200]:
                history = events[run.id]
                # Lifecycle progress never regresses when delayed receipts arrive.
                latest = max(history, key=lambda event: STAGES[event.stage]) if history else None
                cards.append(
                    PipelineCard(
                        run_id=run.id,
                        job_id=job.id,
                        title=job.title,
                        stage=latest.stage if latest else "drafted",
                        source=latest.source if latest else "local",
                        updated_at=max(
                            [utc(run.updated_at), *[utc(item.occurred_at) for item in history]]
                        ),
                    )
                )
            return PipelineView(cards=cards, truncated=len(rows) > 200)

    def analytics(self, tenant, days):
        cutoff = utcnow() - timedelta(days=days)
        with Session(self.engine) as db:
            rows = db.execute(
                select(AgentRun, JobRecord)
                .join(JobRecord)
                .where(
                    AgentRun.user_id == tenant,
                    JobRecord.user_id == tenant,
                    AgentRun.created_at >= cutoff,
                )
                .order_by(AgentRun.created_at.desc(), AgentRun.id)
            ).all()
            runs = {run.id: (run, job) for run, job in rows}
            events = defaultdict(list)
            for event in db.scalars(
                select(RunEvent)
                .join(AgentRun)
                .where(AgentRun.user_id == tenant, AgentRun.created_at >= cutoff)
                .order_by(RunEvent.id)
            ):
                events[event.run_id].append(event)
            measurements = [self._measurement(run, job, events[run.id]) for run, job in rows]
            local_count = len(
                db.scalars(
                    select(LocalDraftArtifact.run_id)
                    .join(AgentRun)
                    .where(
                        LocalDraftArtifact.user_id == tenant,
                        AgentRun.user_id == tenant,
                        AgentRun.created_at >= cutoff,
                    )
                ).all()
            )
            reasons = Counter()
            for audit in db.scalars(
                select(ApprovalAudit)
                .join(AgentRun)
                .where(
                    ApprovalAudit.user_id == tenant,
                    AgentRun.user_id == tenant,
                    AgentRun.created_at >= cutoff,
                )
            ):
                if audit.decision.get("action") == "reject":
                    reasons[mask_pii(str(audit.decision.get("reason", "Unspecified")))[:300]] += 1
            history = defaultdict(list)
            for event in db.scalars(select(PipelineEvent).where(PipelineEvent.user_id == tenant)):
                if event.run_id in runs:
                    history[event.run_id].append(event)
            categories = defaultdict(lambda: Counter(submitted=0, replied=0, hired=0))
            spend = []
            for id, receipts in history.items():
                submitted = next((item for item in receipts if item.stage == "submitted"), None)
                if submitted is None:
                    continue  # No denominator is inferred from a reply or local draft.
                category = runs[id][1].raw.get("category", "unknown")
                category = (
                    category
                    if category in {"ai_ml", "full_stack", "data_analyst", "other"}
                    else "unknown"
                )
                counts = categories[category]
                counts["submitted"] += 1
                counts["replied"] += any(
                    item.stage in {"replied", "interview", "hired"} for item in receipts
                )
                counts["hired"] += any(item.stage == "hired" for item in receipts)
                if submitted.connects_spent is not None:
                    spend.append(submitted.connects_spent)
            known_tokens = [
                item.measured_model_tokens
                for item in measurements
                if item.measured_model_tokens is not None
            ]
            known_costs = [
                item.inference_api_usd
                for item in measurements
                if item.inference_api_usd is not None
            ]
            return AnalyticsView(
                days=days,
                run_count=len(rows),
                local_drafts=local_count,
                charged_or_reserved_tokens=sum(run.tokens for run, _ in rows),
                measured_model_tokens=sum(known_tokens) if known_tokens else None,
                inference_api_usd=sum(known_costs) if known_costs else None,
                connects_spent=sum(spend) if spend else None,
                submissions_with_known_spend=len(spend),
                provider_submissions=sum(item["submitted"] for item in categories.values()),
                category_rates=[
                    {
                        "category": key,
                        **value,
                        "reply_rate": value["replied"] / value["submitted"],
                        "hire_rate": value["hired"] / value["submitted"],
                    }
                    for key, value in sorted(categories.items())
                ],
                rejection_reasons=[
                    {"reason": reason, "count": count} for reason, count in reasons.most_common(10)
                ],
                measurements=measurements[:200],
                measurements_truncated=len(measurements) > 200,
            )

    def _measurement(self, run, job, events):
        tokens, durations, costs, segments = [], [], [], []
        started = None
        for event in events:
            data = event.details
            if event.kind == "model_usage":
                if all(
                    type(data.get(key)) is int and data[key] >= 0
                    for key in ("input_tokens", "output_tokens")
                ):
                    tokens.append(data["input_tokens"] + data["output_tokens"])
                if number(data.get("elapsed_seconds")):
                    durations.append(data["elapsed_seconds"])
                if number(data.get("usd")):
                    costs.append(data["usd"])
            if event.kind == "worker_started":
                started = utc(event.created_at)
            if started and (
                event.kind
                in {"needs_attention", "retries_exhausted", "committed_local_write_recovered"}
                or (
                    event.kind == "state_saved"
                    and data.get("status") in TERMINAL | {"awaiting_approval"}
                )
            ):
                segments.append(max(0, (utc(event.created_at) - started).total_seconds()))
                started = None
        return RunMeasurement(
            run_id=run.id,
            job_title=job.title,
            kind=run.kind,
            status=run.status,
            charged_or_reserved_tokens=run.tokens,
            measured_model_tokens=sum(tokens) if tokens else None,
            model_call_seconds=round(sum(durations), 4) if durations else None,
            inference_api_usd=sum(costs) if costs else None,
            measured_worker_seconds=round(sum(segments), 4) if segments else None,
        )
