"""Client-message classification, grounded replies and reviewed local email drafts."""

import hashlib
import re
from datetime import timedelta

from agent.handoffs import LiaisonReply, RiskReport, WritePreview
from agent.proposal_nodes import ProposalNodes, ReviewRequired
from agent.safety import INJECTION
from apps.api.models import utcnow
from mcp_servers.workspace.tools import EmailDraftRequest, SlotRequest

DATE_REFERENCE = re.compile(
    r"\b\d{1,2}:\d{2}\b|\b20\d{2}-\d{2}-\d{2}\b|"
    r"\b(?:today|tomorrow|tonight|next week|next month)\b",
    re.I,
)


class ConversationNodes:
    def __init__(
        self, models, portfolio, workspace, config, *, load_memory, clock=utcnow, marketplace=None
    ):
        self.models, self.portfolio, self.workspace = models, portfolio, workspace
        self.config, self.load_memory, self.clock = config, load_memory, clock
        self.marketplace = marketplace
        self.grounding = ProposalNodes(models, portfolio, config, execute_local=None)

    def mapping(self):
        return {
            name: getattr(self, name)
            for name in (
                "intake",
                "liaison",
                "verifier",
                "compliance",
                "preview",
                "execute",
            )
        }

    async def intake(self, state):
        messages = state.get("messages", [])
        if not messages or sum(len(item["text"]) for item in messages) > 12000:
            raise ReviewRequired("Provide a bounded recent client-message context")
        injection = any(INJECTION.search(item["text"]) for item in messages)
        risk = RiskReport(
            score=1 if injection else 0,
            flags=["prompt_injection"] if injection else [],
            reasons=[
                (
                    "Upwork job context; messages are user-provided, not automatically synced."
                    if state.get("raw_job", {}).get("source") == "upwork"
                    else "Student-simulator conversation; all content is synthetic."
                )
                if state.get("provider_conversation_id")
                else "Manually entered client messages; provider history is unavailable."
            ],
        )
        return {
            "risk": risk,
            "intent": "scam" if injection else None,
            "memory": await self.load_memory(),
            "status": "analysing",
            "events": ["client_context_loaded"],
        }

    async def liaison(self, state):
        query = (state["raw_job"]["title"] + "\n" + state["messages"][-1]["text"])[:4000]
        evidence = await self.portfolio.search(
            query, k=self.config.retrieval["top_k"], variant=self.config.retrieval["variant"]
        )
        if state.get("raw_job", {}).get("source") == "upwork":
            evidence = [
                item
                for item in evidence
                if not any(
                    marker in item.text.casefold()
                    for marker in ("synthetic persona", "fictional", "synthetic prototype")
                )
            ]
        now = self.clock()
        slots = await self.workspace.slots(SlotRequest(start=now, end=now + timedelta(days=7)))
        reply = await self.models.complete(
            "liaison",
            {
                "job": state["raw_job"],
                "client_messages": state["messages"],
                "source": (
                    "upwork (real job; user-provided message context)"
                    if state.get("raw_job", {}).get("source") == "upwork"
                    else "student_sim (synthetic)"
                )
                if state.get("provider_conversation_id")
                else "manually entered",
                "current_time_utc": now.isoformat(),
                "hourly_floor": state["preferences"]["hourly_floor"],
                "portfolio_evidence": [item.model_dump() for item in evidence],
                "available_calendar_slots": slots[:3],
                "promoted_memory": state.get("memory", {}),
            },
            LiaisonReply,
        )
        risk = state["risk"]
        if reply.intent == "scam":
            risk = RiskReport(score=1, flags=["client_scam_signal"], reasons=reply.reasons)
        return {
            "intent": reply.intent,
            "risk": risk,
            "evidence": evidence,
            "calendar_slots": slots[:3] if reply.intent == "interview" else [],
            "draft": reply.draft.model_copy(update={"claims": [], "screening_answers": {}}),
            "status": "drafting",
            "events": ["reply_drafted"],
        }

    async def verifier(self, state):
        if DATE_REFERENCE.search(state["draft"].text):
            raise ReviewRequired(
                "Keep calendar dates in the verified slot options; revise the reply body"
            )
        return await self.grounding.verifier(state)

    async def compliance(self, state):
        return await self.grounding.compliance(state)

    def _email(self, state, *, dry_run):
        body = state["draft"].text
        if state.get("calendar_slots"):
            body += "\n\nInterview options (UTC):\n" + "\n".join(
                f"{slot['start']} to {slot['end']}" for slot in state["calendar_slots"]
            )
        fingerprint = hashlib.sha256(body.encode()).hexdigest()
        return EmailDraftRequest(
            subject="Re: " + state["conversation_title"],
            body=body,
            idempotency_key=f"reply:{state['run_id']}:{state['source_revision']}:{fingerprint}",
            calendar_slots=state.get("calendar_slots", []),
            dry_run=dry_run,
        )

    async def preview(self, state):
        request = self._email(state, dry_run=True)
        if (
            state.get("provider_conversation_id")
            and state.get("raw_job", {}).get("source") != "upwork"
        ):
            from agent.marketplace_port import MessageWrite
            from agent.proposal_nodes import draft_digest

            message = MessageWrite(
                conversation_id=state["provider_conversation_id"],
                text=request.body,
                idempotency_key=request.idempotency_key,
            )
            result = await self.marketplace.message(message)
            expected = {
                "conversation_id": message.conversation_id,
                "text": message.text,
                "draft_digest": draft_digest(state["draft"]),
            }
            if result.get("arguments") != expected:
                raise ReviewRequired("Simulator message preview differs from the verified reply")
            return {
                "preview": WritePreview(
                    tool="send_message",
                    arguments=expected,
                    connects_cost=0,
                    idempotency_key=message.idempotency_key,
                ),
                "status": "awaiting_approval",
                "events": ["student_reply_previewed"],
            }
        result = await self.workspace.email(request)
        expected = request.arguments()
        if result.get("arguments") != expected or result.get("backend") != "local":
            raise ReviewRequired("Workspace preview differs from the reviewed reply")
        return {
            "preview": WritePreview(
                tool="create_email_draft",
                arguments=expected,
                connects_cost=0,
                idempotency_key=request.idempotency_key,
            ),
            "status": "awaiting_approval",
            "events": ["local_reply_previewed"],
        }

    async def execute(self, state):
        if state["approval"].action != "approve":
            raise ReviewRequired("Saving a reply requires human approval")
        request = self._email(state, dry_run=False)
        if (
            state.get("provider_conversation_id")
            and state.get("raw_job", {}).get("source") != "upwork"
        ):
            from agent.marketplace_port import MessageWrite
            from agent.proposal_nodes import draft_digest

            expected = {
                "conversation_id": state["provider_conversation_id"],
                "text": request.body,
                "draft_digest": draft_digest(state["draft"]),
            }
            if state["preview"].tool != "send_message" or state["preview"].arguments != expected:
                raise ReviewRequired("Simulator reply changed after approval")
            for item in state.get("evidence", []):
                await self.portfolio.read(item.id)
            await self.marketplace.message(
                MessageWrite(
                    conversation_id=state["provider_conversation_id"],
                    text=request.body,
                    idempotency_key=request.idempotency_key,
                    dry_run=False,
                )
            )
            return {"status": "sent", "events": ["student_reply_sent"]}
        if state["preview"].arguments != request.arguments():
            raise ReviewRequired("The reply changed after preview")
        for item in state.get("evidence", []):
            await self.portfolio.read(item.id)
        await self.workspace.email(request)
        return {"status": "drafted", "events": ["local_reply_saved"]}
