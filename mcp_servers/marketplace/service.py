"""Host-bound provider access with exact-preview approval and durable local receipts."""

import asyncio
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agent.handoffs import ProposalDraft
from agent.proposal_nodes import draft_digest
from agent.run_store import RunConflict, RunNotFound, RunStore
from apps.api.models import (
    AgentRun,
    ApprovalAudit,
    FreelancerProfile,
    JobRecord,
    MarketplaceConnection,
    MarketplaceWrite,
    User,
    utcnow,
)
from mcp_servers.marketplace.adapters.student_sim import StudentSimAdapter


class MarketplaceService:
    def __init__(self, engine, settings, tenant, run_id=None, *, adapter=None):
        self.engine, self.settings, self.tenant, self.run_id = engine, settings, tenant, run_id
        with Session(engine) as db:
            connection = db.get(MarketplaceConnection, tenant)
            run = db.get(AgentRun, run_id) if run_id else None
            raw = run.snapshot.get("raw_job", {}) if run and run.user_id == tenant else {}
            self.provider = raw.get("source") or (connection.mode if connection else "student_sim")
            self.generation = raw.get("connection_generation")
        if adapter is None and self.provider == "upwork":
            from apps.api.marketplace import MarketplaceAccounts

            adapter = MarketplaceAccounts(engine, settings).adapter(
                tenant, "upwork", self.generation
            )
        self.adapter = adapter or StudentSimAdapter(
            settings.student_sim_url, settings.student_sim_api_key, tenant
        )

    def connected(self):
        if self.provider not in {"student_sim", "upwork"}:
            raise RunConflict("Connect a marketplace in Settings first")
        with Session(self.engine) as db:
            row = db.get(MarketplaceConnection, self.tenant)
            if row is None or row.mode != self.provider:
                raise RunConflict(
                    "Connect this run's original marketplace provider before continuing"
                )
            if self.provider == "upwork":
                from apps.api.models import OAuthCredential

                credential = db.get(OAuthCredential, (self.tenant, "upwork"))
                if (
                    not credential
                    or not credential.connected
                    or (self.generation and credential.generation != self.generation)
                ):
                    raise RunConflict("Upwork authorization changed; start a new run")

    async def read(self, name, *args):
        await asyncio.to_thread(self.connected)
        return await getattr(self.adapter, name)(*args)

    async def pricing_statistics(self, job_id):
        """Our own host MCP capability, not an invented Upwork tool."""
        import json

        from agent.marketplace_port import MarketplaceResult
        from agent.pricing import budget_statistics

        await asyncio.to_thread(self.connected)
        if self.provider == "student_sim":
            from urllib.parse import quote

            return await self.adapter.request(
                "GET", "/jobs/" + quote(job_id, safe="") + "/pricing-statistics"
            )
        job = (await self.adapter.get_job(job_id)).data

        def historical():
            path = self.settings.pricing_catalogue_path
            if not path.is_file():
                return []
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
                return (
                    [
                        r
                        for r in rows
                        if isinstance(r, dict)
                        and isinstance(r.get("provenance"), dict)
                        and r["provenance"].get("base_text") == "real_historical_job"
                    ]
                    if isinstance(rows, list)
                    else []
                )
            except (OSError, ValueError, TypeError):
                return []

        data = budget_statistics(job, await asyncio.to_thread(historical), provider="upwork")
        data["client"]["source"] = "unavailable_live_client_price_history"
        return MarketplaceResult(provider="upwork", data=data)

    def _run(self, db, *, lock=False):
        query = select(AgentRun).where(AgentRun.id == self.run_id, AgentRun.user_id == self.tenant)
        run = db.scalar(query.with_for_update() if lock else query)
        if run is None:
            raise RunNotFound("Approved provider run not found")
        return run

    def _arguments(self, run, tool, request):
        draft = ProposalDraft.model_validate(run.snapshot["draft"])
        arguments = request.model_dump(exclude={"dry_run", "idempotency_key"})
        if tool == "submit_proposal":
            if (
                run.kind != "bid"
                or request.text != draft.text
                or request.screening_answers != draft.screening_answers
            ):
                raise RunConflict("Proposal differs from the verified draft")
            with Session(self.engine) as db:
                job = db.get(JobRecord, run.job_id)
                if (
                    job is None
                    or job.user_id != self.tenant
                    or job.raw.get("source") != self.provider
                    or job.raw.get("provider_job_id") != request.job_id
                ):
                    raise RunConflict("Provider job does not match this run")
            if float(run.snapshot["price"]["amount"]) != request.bid_amount:
                raise RunConflict("Price differs from the reviewed quote")
        else:
            if (
                run.kind != "conversation"
                or run.snapshot.get("provider_conversation_id") != request.conversation_id
            ):
                raise RunConflict("Provider conversation does not match this run")
            expected = draft.text
            if run.snapshot.get("calendar_slots"):
                expected += "\n\nInterview options (UTC):\n" + "\n".join(
                    f"{slot['start']} to {slot['end']}" for slot in run.snapshot["calendar_slots"]
                )
            if request.text != expected:
                raise RunConflict("Message differs from the verified reply")
        return {**arguments, "draft_digest": draft_digest(draft)}

    async def write(self, tool, request):
        from agent.marketplace_port import MarketplaceResult

        await asyncio.to_thread(self.connected)
        if request.dry_run:
            with Session(self.engine) as db:
                arguments = self._arguments(self._run(db), tool, request)
            if tool == "submit_proposal":
                response = await self.adapter.create_proposal_draft(request)
            else:
                response = await self.adapter.send_message(request)
            return MarketplaceResult(
                provider=self.provider, data={**response.data, "arguments": arguments}
            )
        return MarketplaceResult(
            provider=self.provider, data=await asyncio.to_thread(self._execute, tool, request)
        )

    def _execute(self, tool, request):
        with Session(self.engine) as db, db.begin():
            run = self._run(db, lock=True)
            # Match the Workspace lock order: run, account, source evidence.
            db.scalar(select(User.id).where(User.id == self.tenant).with_for_update(key_share=True))
            connection = db.get(MarketplaceConnection, self.tenant)
            if connection is None or connection.mode != self.provider:
                raise RunConflict("Original marketplace provider was disconnected")
            arguments = self._arguments(run, tool, request)
            previous = db.scalar(
                select(MarketplaceWrite).where(
                    MarketplaceWrite.user_id == self.tenant,
                    MarketplaceWrite.idempotency_key == request.idempotency_key,
                )
            )
            if previous:
                if (
                    previous.run_id != run.id
                    or previous.tool != tool
                    or previous.arguments != arguments
                ):
                    raise RunConflict("Provider idempotency key has different arguments")
                if previous.result.get("status") in {"in_flight", "provider_outcome_unknown"}:
                    raise RunConflict(
                        "Provider draft outcome is uncertain; inspect Upwork before any new attempt"
                    )
                return previous.result
            audit = db.scalar(
                select(ApprovalAudit)
                .where(ApprovalAudit.user_id == self.tenant, ApprovalAudit.run_id == run.id)
                .order_by(ApprovalAudit.version.desc())
                .limit(1)
            )
            preview = audit.preview if audit else None
            if (
                not audit
                or audit.decision.get("action") != "approve"
                or not preview
                or (
                    preview.get("tool") != tool
                    or preview.get("arguments") != arguments
                    or preview.get("idempotency_key") != request.idempotency_key
                    or run.snapshot.get("preview") != preview
                    or run.status not in {"queued", "running"}
                )
            ):
                raise RunConflict("Provider writes require approval of the exact preview")
            draft = ProposalDraft.model_validate(run.snapshot["draft"])
            RunStore(self.engine)._check_evidence(db, self.tenant, draft)
            cost = int(preview.get("connects_cost", 0))
            if tool == "submit_proposal":
                profile = db.get(FreelancerProfile, self.tenant)
                now = utcnow()
                week_start = (now - timedelta(days=now.weekday())).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                spent = db.scalar(
                    select(func.coalesce(func.sum(MarketplaceWrite.connects_spent), 0)).where(
                        MarketplaceWrite.user_id == self.tenant,
                        MarketplaceWrite.created_at >= week_start,
                    )
                )
                if not profile or spent + cost > profile.weekly_connects_budget:
                    raise RunConflict("Weekly Connects budget would be exceeded")
            elif run.snapshot.get("calendar_slots"):
                from datetime import datetime

                from mcp_servers.workspace.service import WorkspaceService

                calendar = WorkspaceService(self.engine)
                for slot in run.snapshot["calendar_slots"]:
                    start, end = (
                        datetime.fromisoformat(slot["start"]),
                        datetime.fromisoformat(slot["end"]),
                    )
                    if start < utcnow() or not calendar._can_hold(db, self.tenant, start, end):
                        raise RunConflict("Reviewed interview options are no longer available")
            # Bounded provider IO while locks preserve the authorization/evidence snapshot.
            # If commit is lost, retry the SAME upstream key; never invent a new key.
            if self.provider == "upwork":
                if tool != "submit_proposal":
                    raise RunConflict(
                        "Live messages are local drafts only; direct Upwork sending is disabled"
                    )
                intent = MarketplaceWrite(
                    user_id=self.tenant,
                    run_id=run.id,
                    approval_id=audit.id,
                    tool=tool,
                    idempotency_key=request.idempotency_key,
                    arguments=arguments,
                    result={"status": "in_flight", "provider": "upwork", "connects_spent": 0},
                    connects_spent=0,
                )
                db.add(intent)
                db.flush()
                identity = intent.id
                # Commit before non-idempotent remote IO; never repeat a committed intent.
                db.commit()
                return self._finish_live(identity, request, cost)
            result = asyncio.run(getattr(self.adapter, tool)(request)).data
            if tool == "submit_proposal" and result.get("connects_spent") != cost:
                raise RunConflict(
                    "Provider charge differs from the approved preview; reconcile this key"
                )
            db.add(
                MarketplaceWrite(
                    user_id=self.tenant,
                    run_id=run.id,
                    approval_id=audit.id,
                    tool=tool,
                    idempotency_key=request.idempotency_key,
                    arguments=arguments,
                    result=result,
                    connects_spent=cost,
                )
            )
            return result

    def _finish_live(self, identity, request, approved_cost):
        try:
            result = asyncio.run(
                self.adapter.prepare_approved_proposal(request, approved_cost=approved_cost)
            )
        except Exception:
            with Session(self.engine) as db, db.begin():
                row = db.get(MarketplaceWrite, identity)
                row.result = {
                    "status": "provider_outcome_unknown",
                    "provider": "upwork",
                    "connects_spent": 0,
                }
            raise RunConflict(
                "Provider draft outcome unknown. No automatic retry; inspect Upwork first."
            ) from None
        with Session(self.engine) as db, db.begin():
            row = db.get(MarketplaceWrite, identity)
            row.result = result
        return result
