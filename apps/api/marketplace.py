"""Account connections and trusted normalization of our student simulator jobs."""

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agent.run_store import RunConflict, RunNotFound
from apps.api.models import JobRecord, MarketplaceConnection, User, utcnow
from apps.api.schemas.proposals import JobView
from mcp_servers.marketplace.adapters.student_sim import StudentSimAdapter


class MarketplaceAccounts:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings

    def adapter(self, tenant):
        return StudentSimAdapter(
            self.settings.student_sim_url, self.settings.student_sim_api_key, tenant
        )

    def status(self, tenant):
        with Session(self.engine) as db:
            row = db.get(MarketplaceConnection, tenant)
            return {
                "mode": row.mode if row else "manual",
                "connected": bool(row and row.mode == "student_sim"),
                "error": row.error if row else None,
                "synthetic": True,
                "label": "Student-built simulator; not instructor GigSim",
            }

    def set_mode(self, tenant, mode):
        with Session(self.engine) as db, db.begin():
            if (
                db.scalar(select(User.id).where(User.id == tenant).with_for_update(key_share=True))
                is None
            ):
                raise RunNotFound("Account not found")
            row = db.get(MarketplaceConnection, tenant)
            if row is None:
                row = MarketplaceConnection(user_id=tenant, mode=mode)
                db.add(row)
            row.mode, row.error, row.updated_at = mode, None, utcnow()
        return self.status(tenant)

    def failure(self, tenant, message):
        with Session(self.engine) as db, db.begin():
            row = db.get(MarketplaceConnection, tenant)
            if row:
                row.error, row.updated_at = message[:200], utcnow()

    def import_job(self, tenant, raw):
        # Identity/source/cost come from our authenticated adapter, never a model.
        if raw.get("source") != "student_sim" or not raw.get("synthetic") or not raw.get("id"):
            raise RunConflict("Unexpected student simulator job schema")
        clean = {key: value for key, value in raw.items() if key != "gold"}
        clean["provider_job_id"] = clean.pop("id")
        fingerprint = hashlib.sha256(f"student_sim:{clean['provider_job_id']}".encode()).hexdigest()
        if not isinstance(clean.get("title"), str) or not isinstance(clean.get("description"), str):
            raise RunConflict("Invalid provider job text")
        if len(clean["title"]) > 200 or len(json.dumps(clean)) > 25000:
            raise RunConflict("Provider job is too large")
        with Session(self.engine) as db:
            query = select(JobRecord).where(
                JobRecord.user_id == tenant, JobRecord.fingerprint == fingerprint
            )
            row = db.scalar(query)
            if row is None:
                row = JobRecord(
                    user_id=tenant, title=clean["title"], fingerprint=fingerprint, raw=clean
                )
                db.add(row)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    row = db.scalar(query)
                    if row is None:
                        raise
            return JobView.model_validate(row)
