"""Manual conversation intake. A newer message invalidates the pending review."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.run_store import RunConflict, RunNotFound, RunStore
from apps.api.models import (
    AgentRun,
    ClientConversation,
    ClientMessage,
    FreelancerProfile,
    JobRecord,
    MarketplaceWrite,
    User,
    WorkspaceWrite,
)
from apps.api.schemas.conversations import ConversationView, MessageView


class ConversationStore(RunStore):
    def _conversation(self, db, tenant, id):
        conversation = db.scalar(
            select(ClientConversation).where(
                ClientConversation.user_id == tenant,
                ClientConversation.id == id,
            )
        )
        if conversation is None:
            raise RunNotFound("Conversation not found")
        return conversation

    def create(self, tenant, body, *, provider_id=None):
        # Request identity belongs to the account and is shared with the run ledger.
        key = str(body.idempotency_key)
        with Session(self.engine) as db, db.begin():
            if db.scalar(select(User.id).where(User.id == tenant).with_for_update()) is None:
                raise RunNotFound("Account not found")
            existing = db.scalar(
                select(AgentRun).where(AgentRun.user_id == tenant, AgentRun.request_key == key)
            )
            if existing:
                conversation = db.scalar(
                    select(ClientConversation).where(
                        ClientConversation.user_id == tenant,
                        ClientConversation.run_id == existing.id,
                    )
                )
                if (
                    conversation is None
                    or conversation.job_id != str(body.job_id)
                    or conversation.title != body.title
                    or conversation.provider_id != provider_id
                ):
                    raise RunConflict("This request key belongs to a different operation")
                first = db.scalar(
                    select(ClientMessage).where(
                        ClientMessage.conversation_id == conversation.id,
                        ClientMessage.request_key == key,
                    )
                )
                if first is None or first.text != body.text:
                    raise RunConflict("This request key has different message text")
                return ConversationView.model_validate(conversation)
            job = db.scalar(
                select(JobRecord).where(
                    JobRecord.id == str(body.job_id), JobRecord.user_id == tenant
                )
            )
            if job is None:
                raise RunNotFound("Job not found")
            run_id, conversation_id = str(uuid4()), str(uuid4())
            run = AgentRun(
                id=run_id, user_id=tenant, job_id=job.id, request_key=key, kind="conversation"
            )
            db.add(run)
            db.flush()
            conversation = ClientConversation(
                id=conversation_id,
                user_id=tenant,
                job_id=job.id,
                run_id=run_id,
                title=body.title,
                provider_id=provider_id,
                revision=1,
            )
            db.add(conversation)
            db.flush()
            db.add(
                ClientMessage(
                    id=str(uuid4()),
                    conversation_id=conversation_id,
                    user_id=tenant,
                    request_key=key,
                    text=body.text,
                )
            )
            db.flush()
            run.snapshot = self._input(db, tenant, run, conversation, job)
            self._event(db, run, "manual_conversation_created")
            return ConversationView.model_validate(conversation)

    def add_message(self, tenant, id, body):
        with Session(self.engine) as db, db.begin():
            conversation = self._conversation(db, tenant, id)
            run = self._run(db, tenant, conversation.run_id, lock=True)
            db.refresh(conversation)
            previous = db.scalar(
                select(ClientMessage).where(
                    ClientMessage.conversation_id == id,
                    ClientMessage.request_key == str(body.idempotency_key),
                )
            )
            if previous:
                if previous.text != body.text:
                    raise RunConflict("This message request key has different text")
                return ConversationView.model_validate(conversation)
            db.add(
                ClientMessage(
                    id=str(uuid4()),
                    conversation_id=id,
                    user_id=tenant,
                    request_key=str(body.idempotency_key),
                    text=body.text,
                )
            )
            conversation.revision += 1
            db.flush()
            job = db.get(JobRecord, conversation.job_id)
            run.snapshot = self._input(db, tenant, run, conversation, job)
            run.review, run.resume, run.worker_token, run.error = None, None, None, None
            run.status = "queued"
            run.retryable = False
            run.version += 1
            self._event(db, run, "client_message_added", {"revision": conversation.revision})
            return ConversationView.model_validate(conversation)

    def _input(self, db, tenant, run, conversation, job):
        profile = self.create_profile_snapshot(db, tenant)
        rows = db.scalars(
            select(ClientMessage)
            .where(
                ClientMessage.user_id == tenant, ClientMessage.conversation_id == conversation.id
            )
            .order_by(ClientMessage.created_at.desc(), ClientMessage.id.desc())
            .limit(20)
        ).all()
        messages, size = [], 0
        for row in rows:
            if size + len(row.text) > 12000:
                break
            messages.append({"id": row.id, "text": row.text})
            size += len(row.text)
        return {
            "tenant_id": tenant,
            "run_id": run.id,
            "job_id": job.id,
            "raw_job": job.raw,
            "preferences": profile,
            "conversation_id": conversation.id,
            "provider_conversation_id": conversation.provider_id,
            "source_revision": conversation.revision,
            "conversation_title": conversation.title,
            "messages": list(reversed(messages)),
            "events": [],
            "status": "queued",
            "draft": None,
            "preview": None,
            "approval": None,
            "compliance": None,
            "verification": {},
            "risk": None,
            "intent": None,
            "calendar_slots": [],
            "memory": {},
            "evidence": [],
            "user_edited": False,
        }

    def create_profile_snapshot(self, db, tenant):
        profile = db.get(FreelancerProfile, tenant)
        return {"hourly_floor": str(profile.hourly_floor) if profile else "15"}

    def conversations(self, tenant):
        with Session(self.engine) as db:
            return [
                ConversationView.model_validate(row)
                for row in db.scalars(
                    select(ClientConversation)
                    .where(ClientConversation.user_id == tenant)
                    .order_by(ClientConversation.created_at.desc())
                    .limit(200)
                )
            ]

    def conversation(self, tenant, id):
        with Session(self.engine) as db:
            return ConversationView.model_validate(self._conversation(db, tenant, id))

    def messages(self, tenant, id):
        with Session(self.engine) as db:
            self._conversation(db, tenant, id)
            return [
                MessageView.model_validate(row)
                for row in db.scalars(
                    select(ClientMessage)
                    .where(
                        ClientMessage.user_id == tenant,
                        ClientMessage.conversation_id == id,
                    )
                    .order_by(ClientMessage.created_at)
                    .limit(500)
                )
            ]

    def local_replies(self, tenant, id):
        conversation = self.conversation(tenant, id)
        with Session(self.engine) as db:
            local = [
                {"id": row.id, "body": row.arguments["body"], "created_at": row.created_at}
                for row in db.scalars(
                    select(WorkspaceWrite)
                    .where(
                        WorkspaceWrite.user_id == tenant,
                        WorkspaceWrite.run_id == conversation.run_id,
                        WorkspaceWrite.tool == "create_email_draft",
                    )
                    .order_by(WorkspaceWrite.created_at)
                )
            ]
            sent = [
                {
                    "id": row.id,
                    "body": row.arguments["text"],
                    "created_at": row.created_at,
                    "status": "sent to student simulator",
                }
                for row in db.scalars(
                    select(MarketplaceWrite).where(
                        MarketplaceWrite.user_id == tenant,
                        MarketplaceWrite.run_id == conversation.run_id,
                        MarketplaceWrite.tool == "send_message",
                    )
                )
            ]
            return sorted(local + sent, key=lambda item: item["created_at"])
