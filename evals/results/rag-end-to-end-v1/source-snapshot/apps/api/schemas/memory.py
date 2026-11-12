from datetime import datetime
from typing import Literal

from pydantic import Field

from agent.handoffs import Contract

Kind = Literal["style", "outcome"]
Category = Literal["ai_ml", "full_stack", "data_analyst", "other"]
StyleKey = Literal["cut_opening", "concise", "avoid_passionate", "avoid_excited", "avoid_thrilled"]


class StyleCandidate(Contract):
    key: StyleKey
    instruction: str
    observations: int = Field(ge=0)
    eligible: bool
    active: bool


class OutcomeFeatures(Contract):
    artifact_samples: int = Field(ge=3)
    mean_cover_words: float = Field(ge=0)
    mean_verified_claims: float = Field(ge=0)
    question_fraction: float = Field(ge=0, le=1)


class MemoryValue(Contract):
    kind: Kind
    instruction: str | None = None
    category: Category | None = None
    outcome: Literal["won", "replied"] | None = None
    observations: int = Field(ge=3)
    supporting_run_ids: list[str]
    promotion_rule: str
    proposal_features: OutcomeFeatures | None = None


class MemoryView(Contract):
    key: str
    kind: Kind
    version: int
    value: MemoryValue
    updated_at: datetime


class MemoryList(Contract):
    items: list[MemoryView]
    sync_pending: bool


class MemoryContext(Contract):
    style_preferences: list[str] = Field(default_factory=list)
    outcome_patterns: list[MemoryValue] = Field(default_factory=list)


class ConfirmStyle(Contract):
    key: StyleKey
    confirmed: Literal[True]


class RemoveMemory(Contract):
    version: int = Field(ge=1)


class EditView(Contract):
    audit_id: int
    run_id: str
    before_text: str
    after_text: str
    diff: str
    created_at: datetime
