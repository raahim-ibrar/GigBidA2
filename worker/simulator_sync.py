"""Import authenticated simulator receipts and messages, including lost-commit recovery."""

import asyncio
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.conversation_store import ConversationStore
from agent.run_store import RunConflict
from apps.api.dashboard import Dashboard
from apps.api.marketplace import MarketplaceAccounts
from apps.api.models import (
    AgentRun,
    ApprovalAudit,
    ClientConversation,
    ClientMessage,
    JobRecord,
    MarketplaceConnection,
    MarketplaceWrite,
    User,
    utcnow,
)
from apps.api.schemas.conversations import AddClientMessage, CreateConversation
from apps.api.schemas.dashboard import ProviderReceipt


def reconcile_receipt(engine, tenant, event, proposal):
    payload = proposal["request"]
    key = payload["idempotency_key"]
    with Session(engine) as db, db.begin():
        # Wait for any in-flight submit transaction before deciding its receipt is missing.
        db.scalar(select(User.id).where(User.id == tenant).with_for_update(key_share=True))
        stored = db.scalar(
            select(MarketplaceWrite).where(
                MarketplaceWrite.user_id == tenant, MarketplaceWrite.idempotency_key == key
            )
        )
        if stored:
            if stored.result.get("id") != proposal["id"]:
                raise RunConflict("Provider receipt identity conflicts with its idempotency key")
            return stored.run_id
        matches = db.execute(
            select(ApprovalAudit, AgentRun, JobRecord)
            .select_from(ApprovalAudit)
            .join(AgentRun, ApprovalAudit.run_id == AgentRun.id)
            .join(JobRecord, AgentRun.job_id == JobRecord.id)
            .where(
                ApprovalAudit.user_id == tenant,
                AgentRun.user_id == tenant,
                JobRecord.user_id == tenant,
                AgentRun.kind == "bid",
            )
        ).all()
        for audit, run, job in matches:
            preview = audit.preview or {}
            arguments = preview.get("arguments", {})
            actual = {k: v for k, v in payload.items() if k != "idempotency_key"}
            if (
                audit.decision.get("action") == "approve"
                and preview.get("tool") == "submit_proposal"
                and preview.get("idempotency_key") == key
                and job.raw.get("source") == "student_sim"
                and job.raw.get("provider_job_id") == event["job_id"]
                and {k: v for k, v in arguments.items() if k != "draft_digest"} == actual
            ):
                result = {
                    "id": proposal["id"],
                    "job_id": event["job_id"],
                    "status": "submitted",
                    "source": "student_sim",
                    "connects_spent": preview["connects_cost"],
                }
                db.add(
                    MarketplaceWrite(
                        user_id=tenant,
                        run_id=run.id,
                        approval_id=audit.id,
                        tool="submit_proposal",
                        idempotency_key=key,
                        arguments=arguments,
                        result=result,
                        connects_spent=preview["connects_cost"],
                    )
                )
                # Reconciliation records an already-observed effect; it does not authorize another.
                run.status, run.review, run.resume, run.worker_token, run.error = (
                    "submitted",
                    None,
                    None,
                    None,
                    None,
                )
                run.snapshot = {**run.snapshot, "status": "submitted"}
                return run.id
        return None  # A direct simulator call with no application approval is not our run.


def event_cursor(engine, tenant, value):
    with Session(engine) as db, db.begin():
        row = db.scalar(
            select(MarketplaceConnection)
            .where(MarketplaceConnection.user_id == tenant)
            .with_for_update()
        )
        if row:
            row.event_cursor = max(row.event_cursor, value)
            row.error, row.updated_at = None, utcnow()


async def import_messages(engine, tenant, run_id, proposal_id, adapter, enqueue=None):
    messages = (await adapter.list_messages(proposal_id)).data["items"]
    incoming = [item for item in messages if item.get("sender") == "client"]
    if not incoming:
        return 0
    store = ConversationStore(engine)
    with Session(engine) as db:
        parent = db.get(AgentRun, run_id)
        job = db.get(JobRecord, parent.job_id)
        conversation = db.scalar(
            select(ClientConversation).where(
                ClientConversation.user_id == tenant, ClientConversation.provider_id == proposal_id
            )
        )
        conversation_id = conversation.id if conversation else None
        title, job_id = job.title, job.id
    added = 0
    for message in incoming:
        key = str(uuid5(NAMESPACE_URL, "student-message:" + message["id"]))
        if conversation_id is None:
            created = await asyncio.to_thread(
                store.create,
                tenant,
                CreateConversation(
                    job_id=job_id, title=title, text=message["text"], idempotency_key=key
                ),
                provider_id=proposal_id,
            )
            conversation_id = created.id
            added += 1
        else:
            with Session(engine) as db:
                known = db.scalar(
                    select(ClientMessage.id).where(
                        ClientMessage.user_id == tenant,
                        ClientMessage.conversation_id == conversation_id,
                        ClientMessage.request_key == key,
                    )
                )
            if known:
                continue
            await asyncio.to_thread(
                store.add_message,
                tenant,
                conversation_id,
                AddClientMessage(text=message["text"], idempotency_key=key),
            )
            added += 1
    if added and enqueue:
        conversation = await asyncio.to_thread(store.conversation, tenant, conversation_id)
        await enqueue(tenant, conversation.run_id)
    return added


async def sync_account(engine, settings, tenant, *, adapter=None, enqueue=None):
    accounts = MarketplaceAccounts(engine, settings)
    adapter = adapter or accounts.adapter(tenant)
    with Session(engine) as db:
        connection = db.get(MarketplaceConnection, tenant)
        if not connection or connection.mode != "student_sim":
            return {"events": 0, "messages": 0}
        cursor = connection.event_cursor
    count, messages = 0, 0
    dashboard = Dashboard(engine)
    proposals = {}
    for _ in range(5):
        page = (await adapter.events(cursor)).data["items"]
        if not page:
            break
        for event in page:
            if event["proposal_id"] not in proposals:
                proposals[event["proposal_id"]] = (
                    await adapter.get_proposal(event["proposal_id"])
                ).data
            proposal = proposals[event["proposal_id"]]
            run_id = await asyncio.to_thread(reconcile_receipt, engine, tenant, event, proposal)
            if run_id:
                receipt = ProviderReceipt.model_validate(
                    {
                        key: event[key]
                        for key in (
                            "event_id",
                            "proposal_id",
                            "source",
                            "stage",
                            "occurred_at",
                            "connects_spent",
                        )
                        if key in event
                    }
                )
                await asyncio.to_thread(dashboard.record_provider_event, tenant, run_id, receipt)
                if event["stage"] == "replied":
                    messages += await import_messages(
                        engine, tenant, run_id, event["proposal_id"], adapter, enqueue
                    )
            cursor = event["cursor"]
            await asyncio.to_thread(event_cursor, engine, tenant, cursor)
            count += 1
    return {"events": count, "messages": messages}


async def reconcile_simulator(ctx):
    with Session(ctx["engine"]) as db:
        tenants = db.scalars(
            select(MarketplaceConnection.user_id)
            .where(MarketplaceConnection.mode == "student_sim")
            .limit(100)
        ).all()

    async def enqueue(tenant, run_id):
        await ctx["redis"].enqueue_job("run_bid", tenant, run_id, _job_id=f"bid:{run_id}")

    for tenant in tenants:
        try:
            await sync_account(ctx["engine"], ctx["settings"], tenant, enqueue=enqueue)
        except Exception:
            await asyncio.to_thread(
                MarketplaceAccounts(ctx["engine"], ctx["settings"]).failure,
                tenant,
                "Student simulator sync pending; saved state is preserved",
            )
