from pydantic import Field

from agent.handoffs import Contract, EvidenceItem
from rag.contracts import Variant


class SearchEvidence(Contract):
    requirement: str = Field(min_length=1, max_length=4000)
    k: int = Field(default=5, ge=1, le=50)
    filters: dict[str, str] = Field(default_factory=dict)
    variant: Variant = "v0"


class EvidenceResult(Contract):
    items: list[EvidenceItem]


class SkillList(Contract):
    skills: list[str]


# Implementations are bound to the authenticated tenant in factory.create_portfolio_server.
