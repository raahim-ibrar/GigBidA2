"""Account connections and trusted normalization of our student simulator jobs."""

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agent.run_store import RunConflict, RunNotFound
from apps.api.models import JobRecord, MarketplaceConnection, OAuthCredential, User, utcnow
from apps.api.schemas.proposals import JobView
from mcp_servers.marketplace.adapters.student_sim import StudentSimAdapter


class MarketplaceAccounts:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings

    def adapter(self, tenant, mode=None, generation=None):
        mode = mode or self.status(tenant)["mode"]
        if mode == "upwork":
            from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter

            return UpworkLiveAdapter(self.engine, self.settings, tenant, generation=generation)
        return StudentSimAdapter(
            self.settings.student_sim_url, self.settings.student_sim_api_key, tenant
        )

    def status(self, tenant):
        with Session(self.engine) as db:
            row = db.get(MarketplaceConnection, tenant)
            oauth = db.get(OAuthCredential, (tenant, "upwork"))
            live = bool(oauth and oauth.connected)
            mode = row.mode if row else "manual"
            expires_at = None
            if live:
                from apps.api.auth.token_store import EncryptedTokenStorage, OAuthUnavailable

                try:
                    expires_at = (
                        EncryptedTokenStorage(self.engine, self.settings, tenant)
                        .read()
                        .get("expires_at")
                    )
                except OAuthUnavailable:
                    live = False
            return {
                "mode": mode,
                "connected": bool(
                    row and (row.mode == "student_sim" or row.mode == "upwork" and live)
                ),
                "error": row.error if row else None,
                "synthetic": mode != "upwork",
                "label": "Upwork live account; final submissions are disabled"
                if mode == "upwork"
                else "Student-built simulator; not instructor GigSim",
                "upwork_connected": live,
                "capabilities": list(oauth.capabilities) if live else [],
                "unavailable_capabilities": ["final_submission", "send_message", "events"]
                if mode == "upwork"
                else [],
                "reconnect_required": mode == "upwork" and not live,
                "expires_at": expires_at,
            }

    def set_mode(self, tenant, mode):
        with Session(self.engine) as db, db.begin():
            if (
                db.scalar(select(User.id).where(User.id == tenant).with_for_update(key_share=True))
                is None
            ):
                raise RunNotFound("Account not found")
            row = db.get(MarketplaceConnection, tenant)
            if mode == "upwork":
                oauth = db.get(OAuthCredential, (tenant, "upwork"))
                if not oauth or not oauth.connected:
                    raise RunConflict("Authorize Upwork on the host laptop first")
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
        provider = raw.get("source")
        if provider not in {"student_sim", "upwork"} or not raw.get("id"):
            raise RunConflict("Unexpected marketplace job schema")
        if provider == "student_sim" and not raw.get("synthetic"):
            raise RunConflict("Simulator jobs must be labelled synthetic")
        if provider == "upwork":
            with Session(self.engine) as db:
                oauth = db.get(OAuthCredential, (tenant, "upwork"))
                if (
                    not oauth
                    or not oauth.connected
                    or raw.get("connection_generation") != oauth.generation
                ):
                    raise RunConflict("Upwork job belongs to a different or expired connection")
        clean = {key: value for key, value in raw.items() if key != "gold"}
        clean["provider_job_id"] = clean.pop("id")
        fingerprint = (
            hashlib.sha256(
                (
                    f"{provider}:{clean.get('connection_generation', '')}:"
                    f"{clean['provider_job_id']}"
                ).encode()
            ).hexdigest()
            if provider == "upwork"
            else hashlib.sha256(f"student_sim:{clean['provider_job_id']}".encode()).hexdigest()
        )
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
