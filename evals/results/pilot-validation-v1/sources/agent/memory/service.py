"""Promotion ledger plus separate tenant-scoped LangGraph style/outcome namespaces.

Observations remain business records. Only derived, rule-approved values enter the
LangGraph store; raw drafts, tool outputs and client messages never do.
"""

import re
from contextlib import contextmanager
from threading import Lock

from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres import PostgresStore
from psycopg.conninfo import make_conninfo
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agent.memory.edits import STYLE_RULES
from agent.memory.promotion_rules import may_promote_outcome, may_promote_style
from agent.memory.store import memory_namespace
from agent.persistence import ensure_storage
from agent.run_store import RunConflict, RunNotFound
from apps.api.models import (
    AgentRun,
    DraftEdit,
    JobRecord,
    LocalDraftArtifact,
    MemoryRecord,
    OutcomeObservation,
    User,
    utcnow,
)
from apps.api.schemas.memory import (
    EditView,
    MemoryList,
    MemoryValue,
    MemoryView,
    OutcomeFeatures,
    StyleCandidate,
)


class MemoryUnavailable(RuntimeError):
    pass


class LangGraphStoreFactory:
    def __init__(self, database_url):
        self.dsn = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self.ready, self.lock = False, Lock()
        # SQLite is a test-only deployment; the SQL ledger can repopulate this mirror.
        self.test_store = InMemoryStore() if self.dsn.startswith("sqlite") else None

    def setup(self):
        if self.test_store is not None:
            self.ready = True
            return
        with self.lock:
            if not self.ready:
                ensure_storage(self.dsn)
                self.ready = True

    @contextmanager
    def open(self):
        # DDL must happen before authentication opens a request transaction.
        # CREATE INDEX CONCURRENTLY can otherwise wait on that same request.
        if not self.ready:
            raise MemoryUnavailable("Memory schema is not ready")
        if self.test_store is not None:
            yield self.test_store
        else:
            with PostgresStore.from_conn_string(
                make_conninfo(self.dsn, connect_timeout=5)
            ) as store:
                store.conn.execute("SET lock_timeout = '3s'")
                store.conn.execute("SET statement_timeout = '5s'")
                yield store


class MemoryService:
    def __init__(self, engine, database_url, *, store_factory=None):
        self.engine = engine
        self.factory = store_factory or LangGraphStoreFactory(database_url)

    def ensure(self):
        try:
            self.factory.setup()
        except Exception:
            raise MemoryUnavailable("Memory schema initialization is unavailable") from None

    def _owner_lock(self, db, tenant):
        if db.scalar(select(User.id).where(User.id == tenant).with_for_update()) is None:
            raise RunNotFound("Account not found")

    def _style_support(self, db, tenant):
        support = {key: set() for key in STYLE_RULES}
        for row in db.scalars(select(DraftEdit).where(DraftEdit.user_id == tenant)):
            for key in row.patterns:
                if key in support:
                    support[key].add(row.run_id)
        return support

    def candidates(self, tenant):
        with Session(self.engine) as db:
            support = self._style_support(db, tenant)
            active = {
                row.key
                for row in db.scalars(
                    select(MemoryRecord).where(
                        MemoryRecord.user_id == tenant,
                        MemoryRecord.kind == "style",
                        MemoryRecord.active,
                    )
                )
            }
            return [
                StyleCandidate(
                    key=key,
                    instruction=STYLE_RULES[key],
                    observations=len(ids),
                    eligible=may_promote_style(user_confirmed=True, matching_edits=len(ids)),
                    active=key in active,
                )
                for key, ids in support.items()
                if ids
            ]

    def confirm_style(self, tenant, key, *, confirmed):
        if key not in STYLE_RULES:
            raise RunNotFound("Style candidate not found")
        with Session(self.engine) as db, db.begin():
            self._owner_lock(db, tenant)
            ids = sorted(self._style_support(db, tenant)[key])
            if not may_promote_style(user_confirmed=confirmed, matching_edits=len(ids)):
                raise RunConflict(
                    "Confirm a pattern observed in edits to at least three distinct drafts"
                )
            value = MemoryValue(
                kind="style",
                instruction=STYLE_RULES[key],
                observations=len(ids),
                supporting_run_ids=ids[:50],
                promotion_rule="user-confirmed pattern in at least 3 distinct drafts",
            )
            self._upsert(db, tenant, key, value, activate=True)
        return self.list(tenant)

    def _upsert(self, db, tenant, key, value, *, activate=False):
        record = db.scalar(
            select(MemoryRecord)
            .where(
                MemoryRecord.user_id == tenant,
                MemoryRecord.key == key,
            )
            .with_for_update()
        )
        payload = value.model_dump(mode="json")
        if record is None:
            record = MemoryRecord(
                user_id=tenant, key=key, kind=value.kind, value=payload, active=True, synced=False
            )
            db.add(record)
        else:
            if record.value != payload or (activate and not record.active):
                record.value, record.synced = payload, False
                record.version += 1
                record.updated_at = utcnow()
            if activate:
                record.active = True
        return record

    def record_outcome(self, tenant, *, event_id, run_id, category, outcome):
        """Trusted adapter hook only; deliberately absent from HTTP and model tools.

        The provider adapter must authenticate/verify the event before calling. Manual
        jobs can never qualify, even if a user labels a local draft 'won'.
        """
        if category not in {"ai_ml", "full_stack", "data_analyst", "other"}:
            raise ValueError("Unsupported job category")
        if outcome not in {"won", "replied", "ignored"} or not event_id or len(event_id) > 200:
            raise ValueError("Invalid provider outcome event")
        with Session(self.engine) as db:
            row = db.execute(
                select(AgentRun, JobRecord)
                .join(JobRecord)
                .where(
                    AgentRun.id == run_id,
                    AgentRun.user_id == tenant,
                    JobRecord.user_id == tenant,
                )
            ).first()
            if row is None:
                raise RunNotFound("Provider run not found")
            if row[1].raw.get("source") not in {"gigsim", "upwork"}:
                raise RunConflict("A manual job cannot establish a marketplace outcome")
            query = select(OutcomeObservation).where(
                OutcomeObservation.user_id == tenant,
                OutcomeObservation.event_id == event_id,
            )
            observation = db.scalar(query)
            if observation is None:
                db.add(
                    OutcomeObservation(
                        user_id=tenant,
                        run_id=run_id,
                        event_id=event_id,
                        category=category,
                        outcome=outcome,
                        source="marketplace_event",
                    )
                )
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    observation = db.scalar(query)
                    if observation is None:
                        raise
            if observation and (observation.run_id, observation.category, observation.outcome) != (
                run_id,
                category,
                outcome,
            ):
                raise RunConflict("This provider event ID has conflicting content")
        self.promote_outcome(tenant, category, outcome)

    def promote_outcome(self, tenant, category, outcome):
        with Session(self.engine) as db, db.begin():
            self._owner_lock(db, tenant)
            rows = db.execute(
                select(OutcomeObservation.run_id, AgentRun.job_id)
                .join(AgentRun)
                .where(
                    OutcomeObservation.user_id == tenant,
                    AgentRun.user_id == tenant,
                    OutcomeObservation.source == "marketplace_event",
                    OutcomeObservation.category == category,
                    OutcomeObservation.outcome == outcome,
                )
                .order_by(OutcomeObservation.id)
            ).all()
            per_job = {job: run for run, job in rows}
            if not may_promote_outcome(
                source="marketplace_event", outcome=outcome, observations=len(per_job)
            ):
                return False
            artifacts = db.scalars(
                select(LocalDraftArtifact).where(
                    LocalDraftArtifact.user_id == tenant,
                    LocalDraftArtifact.run_id.in_(list(per_job.values())),
                )
            ).all()
            features = None
            if len(artifacts) >= 3:
                features = OutcomeFeatures(
                    artifact_samples=len(artifacts),
                    mean_cover_words=round(
                        sum(len(re.findall(r"\b\w+\b", row.draft["text"])) for row in artifacts)
                        / len(artifacts),
                        2,
                    ),
                    mean_verified_claims=round(
                        sum(
                            sum(
                                claim.get("verdict") == "supported"
                                for claim in row.draft.get("claims", [])
                            )
                            for row in artifacts
                        )
                        / len(artifacts),
                        2,
                    ),
                    question_fraction=round(
                        sum("?" in row.draft["text"] for row in artifacts) / len(artifacts), 3
                    ),
                )
            value = MemoryValue(
                kind="outcome",
                category=category,
                outcome=outcome,
                observations=len(per_job),
                supporting_run_ids=list(per_job.values())[:50],
                promotion_rule="at least 3 distinct provider jobs with verified outcome events",
                proposal_features=features,
            )
            self._upsert(db, tenant, f"{category}:{outcome}", value)
        self.reconcile(tenant)
        return True

    def remove(self, tenant, kind, key, version):
        memory_namespace(tenant, kind)
        with Session(self.engine) as db, db.begin():
            record = db.scalar(
                select(MemoryRecord)
                .where(
                    MemoryRecord.user_id == tenant,
                    MemoryRecord.kind == kind,
                    MemoryRecord.key == key,
                )
                .with_for_update()
            )
            if record is None or not record.active:
                raise RunNotFound("Memory not found")
            if record.version != version:
                raise RunConflict("This memory changed; reload before removing it")
            record.active, record.synced = False, False
            record.version += 1
            record.updated_at = utcnow()
        self.reconcile(tenant)

    def reconcile(self, tenant):
        # A small bounded keyspace (5 style + 8 outcome rules) permits full repair.
        # The SQL lock orders promotion/removal, including a failed mirror write.
        try:
            with self.factory.open() as store, Session(self.engine) as db, db.begin():
                records = db.scalars(
                    select(MemoryRecord)
                    .where(
                        MemoryRecord.user_id == tenant,
                    )
                    .order_by(MemoryRecord.key)
                    .with_for_update()
                ).all()
                for record in records:
                    namespace = memory_namespace(tenant, record.kind)
                    if record.active:
                        store.put(namespace, record.key, record.value, index=False)
                    else:
                        store.delete(namespace, record.key)
                    record.synced = True
            return True
        except Exception:
            return False  # The SQL ledger remains authoritative for eligibility/removal.

    def list(self, tenant):
        synced = self.reconcile(tenant)
        with Session(self.engine) as db:
            items = [
                MemoryView(
                    key=record.key,
                    kind=record.kind,
                    version=record.version,
                    value=MemoryValue.model_validate(record.value),
                    updated_at=record.updated_at,
                )
                for record in db.scalars(
                    select(MemoryRecord).where(
                        MemoryRecord.user_id == tenant,
                        MemoryRecord.active,
                    )
                )
            ]
        try:
            with self.factory.open() as store:
                for record in items:
                    item = store.get(memory_namespace(tenant, record.kind), record.key)
                    if item is None or item.value != record.value.model_dump(mode="json"):
                        synced = False
        except Exception:
            synced = False
        return MemoryList(items=items, sync_pending=not synced)

    def context(self, tenant):
        result = self.list(tenant)
        if result.sync_pending:
            raise MemoryUnavailable("Long-term memory is unavailable; this run uses no memory")
        return {
            "style_preferences": [
                item.value.instruction for item in result.items if item.kind == "style"
            ],
            "outcome_patterns": [
                item.value.model_dump(mode="json")
                for item in result.items
                if item.kind == "outcome"
            ],
        }

    def edits(self, tenant):
        with Session(self.engine) as db:
            return [
                EditView(
                    audit_id=row.audit_id,
                    run_id=row.run_id,
                    before_text=row.before_text,
                    after_text=row.after_text,
                    diff=row.diff,
                    created_at=row.created_at,
                )
                for row in db.scalars(
                    select(DraftEdit)
                    .where(DraftEdit.user_id == tenant)
                    .order_by(DraftEdit.created_at.desc())
                    .limit(50)
                )
            ]
