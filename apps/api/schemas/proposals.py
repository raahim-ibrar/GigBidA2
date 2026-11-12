from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import ConfigDict, Field, field_validator, model_validator

from agent.handoffs import (
    ApprovalDecision,
    BidDecision,
    ComplianceVerdict,
    Contract,
    Critique,
    EvidenceItem,
    FitReport,
    JobSpec,
    PriceQuote,
    ProposalDraft,
    RiskReport,
    WritePreview,
)
from apps.api.schemas.memory import MemoryContext
from mcp_servers.workspace.tools import TimeWindow


class ManualJob(Contract):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=12000)
    billing_type: Literal["hourly", "fixed"]
    budget_min: float | None = Field(default=None, gt=0, le=1000000)
    budget_max: float = Field(gt=0, le=1000000)
    currency: Literal["USD"] = "USD"

    @field_validator("title", "description")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Enter a nonblank value")
        return value.strip()

    @model_validator(mode="after")
    def budget_order(self):
        if self.budget_min is not None and self.budget_min > self.budget_max:
            raise ValueError("Minimum budget cannot exceed maximum budget")
        return self


class JobView(Contract):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: str
    title: str
    raw: dict
    created_at: datetime


class CreateRun(Contract):
    job_id: UUID
    idempotency_key: UUID = Field(default_factory=uuid4)


class ReviewRun(ApprovalDecision):
    run_id: UUID
    version: int = Field(ge=0)
    draft_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class RetryRun(Contract):
    version: int = Field(ge=0)


class ReplayRun(Contract):
    checkpoint_id: UUID
    node: Literal[
        "scout",
        "analyst",
        "risk",
        "matcher",
        "decision",
        "pricing",
        "writer",
        "regenerate",
        "verifier",
        "critic",
        "compliance",
        "preview",
        "approval",
        "execute",
    ]
    idempotency_key: UUID = Field(default_factory=uuid4)


class CheckpointView(Contract):
    checkpoint_id: str
    created_at: str | None
    next_nodes: list[str]
    step: int | None


class SnapshotView(Contract):
    model_config = ConfigDict(extra="ignore")
    status: str | None = None
    job: JobSpec | None = None
    risk: RiskReport | None = None
    fit: FitReport | None = None
    decision: BidDecision | None = None
    price: PriceQuote | None = None
    draft: ProposalDraft | None = None
    critique: Critique | None = None
    compliance: ComplianceVerdict | None = None
    preview: WritePreview | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    verification: dict | None = None
    events: list[str] = Field(default_factory=list)
    memory: MemoryContext | None = None
    conversation_id: str | None = None
    provider_conversation_id: str | None = None
    conversation_title: str | None = None
    source_revision: int | None = None
    provider_result: dict | None = None
    marketplace_provider: str | None = None
    replay_request: dict | None = None
    intent: Literal["question", "negotiation", "interview", "scam"] | None = None
    calendar_slots: list[TimeWindow] = Field(default_factory=list)


class RunView(Contract):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: str
    job_id: str
    kind: Literal["bid", "conversation"] = "bid"
    status: str
    snapshot: SnapshotView
    review: dict | None
    version: int
    tokens: int
    steps: int
    error: str | None
    retry_count: int = 0
    retryable: bool = False
    created_at: datetime
    updated_at: datetime


class EventView(Contract):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: int
    kind: str
    details: dict
    created_at: datetime


class LocalDraftView(Contract):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    run_id: str
    draft: dict
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def utc_timestamp(cls, value):
        # SQLite test reads lose timezone information; stored timestamps are UTC.
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
