from typing import Literal

from pydantic import Field

from agent.handoffs import Contract


class FitAssessment(Contract):
    requirement_evidence: dict[str, list[str]]
    gaps: list[str] = Field(default_factory=list)


class ClaimReview(Contract):
    index: int = Field(ge=0)
    kind: Literal["experience", "non_experience"]
    verdict: Literal["supported", "partly_supported", "unsupported", "not_applicable"]
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str


class Verification(Contract):
    claims: list[ClaimReview]
