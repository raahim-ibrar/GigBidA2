"""Job/conversation state is distinct from execution traces and promoted memory."""

from operator import add
from typing import Annotated, Literal, TypedDict

from agent.handoffs import (
    ApprovalDecision,
    BidDecision,
    ComplianceVerdict,
    Critique,
    EvidenceItem,
    FitReport,
    JobSpec,
    PriceQuote,
    ProposalDraft,
    RiskReport,
    WritePreview,
)


class BidState(TypedDict, total=False):
    tenant_id: str
    job_id: str
    raw_job: dict
    job: JobSpec
    risk: RiskReport
    fit: FitReport
    evidence: list[EvidenceItem]
    decision: BidDecision
    price: PriceQuote
    draft: ProposalDraft
    critique: Critique
    compliance: ComplianceVerdict
    preview: WritePreview
    approval: ApprovalDecision
    revisions: int
    status: str
    # Branches append independent progress observations; these are not long-term memory.
    events: Annotated[list[str], add]


class ConversationState(TypedDict, total=False):
    tenant_id: str
    conversation_id: str
    messages: list[dict]
    intent: Literal["question", "negotiation", "interview", "scam"]
    draft: ProposalDraft
    evidence: list[EvidenceItem]
    compliance: ComplianceVerdict
    preview: WritePreview
    approval: ApprovalDecision
    status: str
    events: Annotated[list[str], add]
