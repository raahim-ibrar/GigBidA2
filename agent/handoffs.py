"""Structured contracts. Business rules and provider mappings still need implementation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceItem(Contract):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source: str = Field(min_length=1)
    type: str
    date: str | None = None
    outcome: Literal["won", "replied", "ignored"] | None = None
    project: str | None = None
    skills: list[str] = Field(default_factory=list)
    persona: str | None = None
    client_industry: str | None = None
    document_id: str | None = None
    page: int | None = None


class JobSpec(Contract):
    job_id: str
    title: str
    requirements: list[str]
    deliverables: list[str] = Field(default_factory=list)
    screening_questions: list[str] = Field(default_factory=list)
    budget_min: float | None = Field(default=None, ge=0)
    budget_max: float | None = Field(default=None, ge=0)
    timeline: str | None = None
    billing_type: Literal["hourly", "fixed", "unknown"] = "unknown"

    @model_validator(mode="after")
    def budget_order(self):
        if self.budget_min is not None and self.budget_max is not None:
            if self.budget_min > self.budget_max:
                raise ValueError("The minimum budget cannot exceed the maximum")
        return self


class RiskReport(Contract):
    score: float = Field(ge=0, le=1)
    flags: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class FitReport(Contract):
    score: float = Field(ge=0, le=1)
    requirement_evidence: dict[str, list[str]]
    gaps: list[str] = Field(default_factory=list)


class BidDecision(Contract):
    action: Literal["skip", "watch", "bid"]
    reasons: list[str] = Field(min_length=1)


class PriceQuote(Contract):
    amount: float = Field(gt=0)
    currency: Literal["USD"] = "USD"
    connects: int | None = Field(default=None, ge=0)
    rationale: str = Field(min_length=1)
    billing_type: Literal["hourly", "fixed", "unknown"] = "unknown"


class Claim(Contract):
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    verdict: Literal["supported", "partly_supported", "unsupported"]
    kind: Literal["experience", "non_experience"] = "experience"
    reason: str | None = None


class ProposalDraft(Contract):
    text: str = Field(min_length=1, max_length=20000)
    screening_answers: dict[str, str] = Field(default_factory=dict)
    claims: list[Claim] = Field(default_factory=list)


class Critique(Contract):
    verdict: Literal["pass", "revise"]
    reasons: list[str] = Field(default_factory=list)


class ComplianceVerdict(Contract):
    allowed: bool
    reasons: list[str] = Field(default_factory=list)


class WritePreview(Contract):
    tool: Literal[
        "submit_proposal",
        "send_message",
        "save_local_draft",
        "create_interview_hold",
        "create_email_draft",
    ]
    arguments: dict
    connects_cost: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=200)


class ApprovalDecision(Contract):
    action: Literal["approve", "reject", "edit"]
    reason: str | None = Field(default=None, max_length=1000)
    edited_text: str | None = Field(default=None, max_length=20000)

    @model_validator(mode="after")
    def validate_action(self):
        if self.action == "reject" and not (self.reason and self.reason.strip()):
            raise ValueError("A rejection reason is required")
        if self.action == "edit" and not (self.edited_text and self.edited_text.strip()):
            raise ValueError("An edited draft is required")
        return self
