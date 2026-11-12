from datetime import date as Date
from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field, field_validator

from agent.handoffs import Contract, EvidenceItem

Variant = Literal["v0", "v1", "v2", "v3", "v8"]


class DocumentMetadata(Contract):
    persona: Literal["own", "ai_ml", "full_stack", "data_analyst"] = "own"
    type: Literal["cv", "case_study", "readme", "code", "review", "proposal"]
    project: str = Field(min_length=1, max_length=200)
    skills: list[str] = Field(default_factory=list, max_length=50)
    date: Date | None = None
    client_industry: str | None = Field(default=None, max_length=200)
    outcome: Literal["won", "replied", "ignored"] | None = None
    source_url: str | None = Field(default=None, max_length=1000)
    source_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, values):
        if any(not value.strip() or len(value) > 100 for value in values):
            raise ValueError("Skills must contain 1-100 characters")
        return list(dict.fromkeys(value.strip() for value in values))


class DocumentView(Contract):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: str
    filename: str
    details: DocumentMetadata
    revision: int
    status: str
    error: str | None
    indexed_model: str | None
    created_at: datetime
    updated_at: datetime


class PortfolioSearch(Contract):
    query: str = Field(min_length=1, max_length=4000)
    k: int = Field(default=5, ge=1, le=50)
    variant: Variant = "v0"
    filters: dict[str, str] = Field(default_factory=dict)

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value):
        if not value.strip():
            raise ValueError("Enter a job requirement to search")
        return value.strip()


class EvidenceHit(Contract):
    evidence: EvidenceItem
    score: float


class SearchResult(Contract):
    variant: Variant
    items: list[EvidenceHit]
    queries: list[str]
    abstained: bool = False
