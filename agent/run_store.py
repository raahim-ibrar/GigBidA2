"""Tenant-scoped run persistence and the local-write authorization transaction."""

import hashlib
import json
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agent.handoffs import ApprovalDecision, ProposalDraft
from agent.memory.edits import edit_observation
from agent.model_client import BudgetExceeded
from agent.proposal_nodes import ReviewRequired, draft_digest
from agent.safety import mask_pii
from apps.api.models import (
    AgentRun,
    ApprovalAudit,
    DraftEdit,
    EvidenceChunk,
    FreelancerProfile,
    JobRecord,
    LocalDraftArtifact,
    PortfolioDocument,
    RunEvent,
    WorkspaceWrite,
    utcnow,
)
from apps.api.schemas.proposals import EventView, JobView, LocalDraftView, RunView

TERMINAL = {"drafted", "rejected", "skip", "watch", "blocked", "needs_attention", "failed"}
MAX_RETRIES = 3


class RunNotFound(LookupError):
    pass


class RunConflict(ValueError):
    pass


class LostWorkerLease(RuntimeError):
    pass


def json_state(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: json_state(item) for key, item in value.items() if key != "__interrupt__"}
    if isinstance(value, (list, tuple)):
        return [json_state(item) for item in value]
    return value


class RunStore:
    def __init__(self, engine):
        self.engine = engine

    def _run(self, db, tenant, run_id, *, lock=False, worker_token=None):
        query = select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == tenant)
        run = db.scalar(query.with_for_update() if lock else query)
        if run is None:
            raise RunNotFound("Run not found")
        if worker_token is not None and run.worker_token != worker_token:
            raise LostWorkerLease("A newer worker owns this run")
        return run

    def _event(self, db, run, kind, details=None):
        db.add(RunEvent(run_id=run.id, kind=kind, details=mask_pii(details or {})))
        run.updated_at = utcnow()

    def create_job(self, tenant, body):
        raw = {"source": "manual", **body.model_dump(mode="json")}
        fingerprint = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
        with Session(self.engine) as db:
            query = select(JobRecord).where(
                JobRecord.user_id == tenant,
                JobRecord.fingerprint == fingerprint,
            )
            job = db.scalar(query)
            if job is None:
                job = JobRecord(user_id=tenant, title=body.title, fingerprint=fingerprint, raw=raw)
                db.add(job)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    job = db.scalar(query)
                    if job is None:
                        raise
            return JobView.model_validate(job)

    def jobs(self, tenant):
        with Session(self.engine) as db:
            return [
                JobView.model_validate(row)
                for row in db.scalars(
                    select(JobRecord)
                    .where(JobRecord.user_id == tenant)
                    .order_by(JobRecord.created_at.desc())
                    .limit(200)
                )
            ]

    def job(self, tenant, job_id):
        with Session(self.engine) as db:
            row = db.scalar(
                select(JobRecord).where(
                    JobRecord.id == job_id,
                    JobRecord.user_id == tenant,
                )
            )
            if row is None:
                raise RunNotFound("Job not found")
            return JobView.model_validate(row)

    def create_run(self, tenant, job_id, request_key):
        job = self.job(tenant, job_id)
        with Session(self.engine) as db:
            existing_query = select(AgentRun).where(
                AgentRun.user_id == tenant,
                AgentRun.request_key == request_key,
            )
            run = db.scalar(existing_query)
            if run is None:
                profile = db.get(FreelancerProfile, tenant)
                run = AgentRun(
                    id=str(uuid4()),
                    user_id=tenant,
                    job_id=job_id,
                    request_key=request_key,
                    snapshot={
                        "tenant_id": tenant,
                        "job_id": job_id,
                        "raw_job": job.raw,
                        "preferences": {
                            "hourly_floor": str(profile.hourly_floor) if profile else "15"
                        },
                        "events": [],
                    },
                )
                run.snapshot = {**run.snapshot, "run_id": run.id}
                db.add(run)
                self._event(db, run, "queued")
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    run = db.scalar(existing_query)
                    if run is None:
                        raise
            if run.job_id != job_id or run.kind != "bid":
                raise RunConflict("This request key was used for a different job")
            return RunView.model_validate(run)

    def run(self, tenant, run_id):
        with Session(self.engine) as db:
            return RunView.model_validate(self._run(db, tenant, run_id))

    def runs(self, tenant, job_id=None):
        with Session(self.engine) as db:
            query = select(AgentRun).where(AgentRun.user_id == tenant)
            if job_id:
                query = query.where(AgentRun.job_id == job_id)
            return [
                RunView.model_validate(row)
                for row in db.scalars(query.order_by(AgentRun.created_at.desc()).limit(200))
            ]

    def events(self, tenant, run_id, after=0):
        with Session(self.engine) as db:
            self._run(db, tenant, run_id)
            return [
                EventView.model_validate(row)
                for row in db.scalars(
                    select(RunEvent)
                    .where(RunEvent.run_id == run_id, RunEvent.id > after)
                    .order_by(RunEvent.id)
                    .limit(200)
                )
            ]

    def review(self, tenant, body):
        run_id = str(body.run_id)
        with Session(self.engine) as db, db.begin():
            run = self._run(db, tenant, run_id, lock=True)
            if run.status != "awaiting_approval" or run.version != body.version or not run.review:
                raise RunConflict("This review is stale. Reload the run before deciding.")
            draft = ProposalDraft.model_validate(run.review["draft"])
            digest = draft_digest(draft)
            if digest != body.draft_digest:
                raise RunConflict("The draft changed. Reload its preview before deciding.")
            decision = ApprovalDecision.model_validate(
                body.model_dump(
                    include={
                        "action",
                        "reason",
                        "edited_text",
                    }
                )
            )
            if decision.action == "approve":
                self._check_evidence(db, tenant, draft)
            audit = ApprovalAudit(
                run_id=run_id,
                user_id=tenant,
                version=run.version,
                draft_digest=digest,
                decision=decision.model_dump(),
                preview=run.review["preview"],
            )
            db.add(audit)
            if decision.action == "edit":
                patterns, diff = edit_observation(draft.text, decision.edited_text)
                db.flush()
                db.add(
                    DraftEdit(
                        audit_id=audit.id,
                        user_id=tenant,
                        run_id=run_id,
                        before_text=draft.text,
                        after_text=decision.edited_text,
                        diff=diff,
                        patterns=patterns,
                    )
                )
            run.resume = {
                "interrupt_id": run.review["interrupt_id"],
                "decision": decision.model_dump(),
            }
            run.status, run.review, run.error = "queued", None, None
            run.version += 1
            self._event(db, run, "review_decision", {"action": decision.action})
        return self.run(tenant, run_id)

    def claim(self, tenant, run_id, worker_token):
        # The host must already hold the session advisory lock for this run.
        with Session(self.engine) as db, db.begin():
            run = self._run(db, tenant, run_id, lock=True)
            if run.status not in {"queued", "running"}:
                return None
            run.worker_token, run.status, run.error = worker_token, "running", None
            run.retryable = False
            self._event(db, run, "worker_started")
            return {
                "snapshot": run.snapshot,
                "resume": run.resume,
                "tokens": run.tokens,
                "steps": run.steps,
                "kind": run.kind,
            }

    def step(self, tenant, run_id, token, node, max_steps):
        with Session(self.engine) as db, db.begin():
            run = self._run(db, tenant, run_id, lock=True, worker_token=token)
            if run.steps >= max_steps:
                raise BudgetExceeded("The run's step budget has been reached")
            run.steps += 1
            self._event(db, run, "node_started", {"node": node})

    def reserve(self, tenant, run_id, token, amount, limit):
        with Session(self.engine) as db, db.begin():
            run = self._run(db, tenant, run_id, lock=True, worker_token=token)
            if run.tokens + amount > limit:
                raise BudgetExceeded("The run's token budget has been reached")
            run.tokens += amount

    def settle(self, tenant, run_id, token, reserved, charged):
        with Session(self.engine) as db, db.begin():
            run = self._run(db, tenant, run_id, lock=True, worker_token=token)
            run.tokens += charged - reserved

    def event(self, tenant, run_id, token, kind, details):
        with Session(self.engine) as db, db.begin():
            run = self._run(db, tenant, run_id, lock=True, worker_token=token)
            self._event(db, run, kind, details)

    def save(self, tenant, run_id, token, state, review=None, *, complete=False):
        with Session(self.engine) as db, db.begin():
            run = self._run(db, tenant, run_id, lock=True, worker_token=token)
            run.snapshot = json_state(state)
            run.review = json_state(review) if review is not None else None
            run.status = (
                "awaiting_approval"
                if review is not None
                else (
                    state.get("status")
                    if complete and state.get("status") in TERMINAL
                    else "running"
                )
            )
            if complete:
                run.resume = None
            run.version += 1
            self._event(db, run, "state_saved", {"status": run.status, "version": run.version})

    def finish(self, tenant, run_id, token):
        with Session(self.engine) as db, db.begin():
            run = self._run(db, tenant, run_id, lock=True, worker_token=token)
            run.worker_token = None

    def fail(self, tenant, run_id, token, message, *, retryable=False):
        with Session(self.engine) as db, db.begin():
            run = self._run(db, tenant, run_id, lock=True, worker_token=token)
            exhausted = retryable and run.retry_count >= MAX_RETRIES
            run.status, run.error = "failed" if exhausted else "needs_attention", message[:300]
            run.retryable = retryable and not exhausted
            run.version += 1
            run.worker_token = None
            self._event(
                db,
                run,
                "retries_exhausted" if exhausted else "needs_attention",
                {"message": message[:300], "retryable": run.retryable},
            )

    def retry(self, tenant, run_id, version):
        with Session(self.engine) as db, db.begin():
            run = self._run(db, tenant, run_id, lock=True)
            if run.version != version:
                raise RunConflict("This run changed. Reload before retrying.")
            if (
                run.status != "needs_attention"
                or not run.retryable
                or run.retry_count >= MAX_RETRIES
            ):
                raise RunConflict(
                    "This run cannot be retried; inspect its error and source inputs."
                )
            run.retry_count += 1
            run.status, run.error, run.retryable = "queued", None, False
            run.worker_token = None
            run.version += 1
            self._event(db, run, "retry_requested", {"attempt": run.retry_count})
        return self.run(tenant, run_id)

    def pending(self):
        with Session(self.engine) as db:
            return db.execute(
                select(AgentRun.user_id, AgentRun.id)
                .where(AgentRun.status.in_(["queued", "running"]))
                .limit(100)
            ).all()

    def _check_evidence(self, db, tenant, draft):
        ids = {item for claim in draft.claims for item in claim.evidence_ids}
        if any(
            claim.verdict != "supported" or (claim.kind == "experience" and not claim.evidence_ids)
            for claim in draft.claims
        ):
            raise ReviewRequired("The draft contains an unverified claim")
        if not ids:
            return
        # Lock source rows before chunks, in stable order. Ingestion takes the same
        # source lock before replacing chunks; deletion waits on this row lock too.
        docs = db.scalars(
            select(PortfolioDocument)
            .join(EvidenceChunk)
            .where(
                EvidenceChunk.id.in_(ids),
                EvidenceChunk.user_id == tenant,
                PortfolioDocument.user_id == tenant,
            )
            .order_by(PortfolioDocument.id)
            .with_for_update(of=PortfolioDocument)
        ).all()
        ready = {doc.id: doc.revision for doc in docs if doc.status == "ready"}
        rows = db.scalars(
            select(EvidenceChunk).where(
                EvidenceChunk.id.in_(ids),
                EvidenceChunk.user_id == tenant,
            )
        ).all()
        if {row.id for row in rows if ready.get(row.document_id) == row.revision} != ids:
            raise ReviewRequired("Portfolio evidence changed; generate and verify a fresh draft")

    def save_local(self, tenant, run_id, token, state):
        with Session(self.engine) as db, db.begin():
            run = self._run(db, tenant, run_id, lock=True, worker_token=token)
            draft = state["draft"]
            digest = draft_digest(draft)
            preview = state["preview"]
            audit = db.scalar(
                select(ApprovalAudit)
                .where(
                    ApprovalAudit.run_id == run_id,
                    ApprovalAudit.user_id == tenant,
                )
                .order_by(ApprovalAudit.version.desc())
                .limit(1)
            )
            if (
                audit is None
                or audit.decision.get("action") != "approve"
                or audit.draft_digest != digest
                or preview.tool != "save_local_draft"
                or preview.arguments.get("draft_digest") != digest
            ):
                raise ReviewRequired("Saving this draft requires a matching human approval")
            existing = db.get(LocalDraftArtifact, run_id)
            if existing:
                if existing.idempotency_key != preview.idempotency_key:
                    raise RunConflict("A different draft was already saved for this run")
                return LocalDraftView.model_validate(existing)
            self._check_evidence(db, tenant, draft)
            artifact = LocalDraftArtifact(
                run_id=run_id,
                user_id=tenant,
                draft=draft.model_dump(mode="json"),
                idempotency_key=preview.idempotency_key,
            )
            db.add(artifact)
            self._event(db, run, "local_write_committed", {"draft_digest": digest})
            db.flush()
            return LocalDraftView.model_validate(artifact)

    def local_draft(self, tenant, run_id):
        with Session(self.engine) as db:
            row = db.scalar(
                select(LocalDraftArtifact).where(
                    LocalDraftArtifact.run_id == run_id,
                    LocalDraftArtifact.user_id == tenant,
                )
            )
            if row is None:
                raise RunNotFound("Saved local draft not found")
            return LocalDraftView.model_validate(row)

    def recover_local(self, tenant, run_id, token):
        """A committed artifact is authoritative even if the final checkpoint failed."""
        with Session(self.engine) as db, db.begin():
            run = self._run(db, tenant, run_id, lock=True, worker_token=token)
            if run.kind == "conversation":
                preview = run.snapshot.get("preview")
                if not preview:
                    return False
                artifact = db.scalar(
                    select(WorkspaceWrite).where(
                        WorkspaceWrite.user_id == tenant,
                        WorkspaceWrite.run_id == run_id,
                        WorkspaceWrite.idempotency_key == preview["idempotency_key"],
                    )
                )
                if artifact is None:
                    return False
                run.snapshot = {**run.snapshot, "status": "drafted"}
            else:
                artifact = db.get(LocalDraftArtifact, run_id)
                if artifact is None or artifact.user_id != tenant:
                    return False
                run.snapshot = {**run.snapshot, "draft": artifact.draft, "status": "drafted"}
            run.status, run.review, run.resume, run.worker_token = "drafted", None, None, None
            run.error = None
            self._event(db, run, "committed_local_write_recovered")
            return True
