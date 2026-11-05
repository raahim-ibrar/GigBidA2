"""Shared scaffold helpers. A checkpointer must be supplied by the caller."""

from langgraph.types import interrupt

from agent.handoffs import ApprovalDecision


def missing_node(name):
    async def node(state):
        raise NotImplementedError(f"Node '{name}' is not implemented; see docs/STATUS.md")

    return node


def approval_gate(state):
    compliance = state.get("compliance")
    draft = state.get("draft")
    if not compliance or not compliance.allowed or not draft or not state.get("preview"):
        raise ValueError("Approval requires a draft, successful compliance and a dry-run preview")
    if any(claim.verdict != "supported" for claim in draft.claims):
        raise ValueError("All claims must be verified before approval")
    answer = ApprovalDecision.model_validate(
        interrupt(
            {
                "draft": draft.model_dump(),
                "evidence": [item.model_dump() for item in state.get("evidence", [])],
                "risk": state["risk"].model_dump() if state.get("risk") else None,
                "price": state["price"].model_dump() if state.get("price") else None,
                "preview": state["preview"].model_dump(),
            }
        )
    )
    # Edits cannot reuse the approval for the previous text. Full edit/reverify is future work.
    status = {"approve": "approved", "reject": "rejected", "edit": "needs_attention"}[answer.action]
    return {"approval": answer, "status": status}


def approval_route(state):
    return "execute" if state["status"] == "approved" else "stop"


def blocked(state):
    return {"status": "blocked"}
