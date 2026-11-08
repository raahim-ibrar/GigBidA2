"""Shared scaffold helpers. A checkpointer must be supplied by the caller."""

from langgraph.types import interrupt

from agent.handoffs import ApprovalDecision, ProposalDraft
from agent.proposal_nodes import draft_digest


def missing_node(name):
    async def node(state):
        raise NotImplementedError(f"Node '{name}' is not implemented; see docs/STATUS.md")

    return node


def approval_gate(state):
    compliance = state.get("compliance")
    draft = state.get("draft")
    if not compliance or not compliance.allowed or not draft or not state.get("preview"):
        raise ValueError("Approval requires a draft, successful compliance and a dry-run preview")
    if any(
        claim.verdict != "supported" or (claim.kind == "experience" and not claim.evidence_ids)
        for claim in draft.claims
    ):
        raise ValueError("All claims must be verified before approval")
    answer = ApprovalDecision.model_validate(
        interrupt(
            {
                "draft": draft.model_dump(),
                "draft_digest": draft_digest(draft),
                "evidence": [item.model_dump() for item in state.get("evidence", [])],
                "risk": state["risk"].model_dump() if state.get("risk") else None,
                "price": state["price"].model_dump() if state.get("price") else None,
                "preview": state["preview"].model_dump(),
            }
        )
    )
    if answer.action == "regenerate":
        return {
            "approval": answer,
            "status": "regenerating",
            "compliance": None,
            "preview": None,
            "user_edited": True,
        }
    if answer.action == "edit":
        return {
            "approval": answer,
            "status": "editing",
            "draft": ProposalDraft(
                text=answer.edited_text,
                screening_answers=draft.screening_answers,
            ),
            "user_edited": True,
            "compliance": None,
            "preview": None,
        }
    return {"approval": answer, "status": "approved" if answer.action == "approve" else "rejected"}


def approval_route(state):
    return "execute" if state["status"] == "approved" else "stop"


def bid_approval_route(state):
    if state["status"] == "regenerating":
        return "regenerate"
    return "edit" if state["status"] == "editing" else approval_route(state)


def blocked(state):
    return {"status": "blocked"}
