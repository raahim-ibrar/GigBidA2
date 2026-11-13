from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from agent.costs import CostSummary
from agent.handoffs import Contract

Stage = Literal["submitted", "viewed", "replied", "interview", "hired", "lost"]


class ProviderReceipt(Contract):
    event_id: str = Field(min_length=1, max_length=200)
    proposal_id: str = Field(min_length=1, max_length=200)
    source: Literal["gigsim", "upwork", "student_sim"]
    stage: Stage
    occurred_at: datetime
    connects_spent: int | None = Field(default=None, strict=True, ge=0, le=10000)

    @field_validator("occurred_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Provider timestamps must include a time zone")
        return value

    @model_validator(mode="after")
    def spend_only_on_submission(self):
        if self.connects_spent is not None and self.stage != "submitted":
            raise ValueError("Connects charges belong to submission receipts")
        return self


class PipelineCard(Contract):
    run_id: str
    job_id: str
    title: str
    stage: Literal["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"]
    source: str
    updated_at: datetime


class PipelineView(Contract):
    cards: list[PipelineCard]
    truncated: bool
    provider_connected: bool = False


class RunMeasurement(Contract):
    run_id: str
    job_title: str
    kind: str
    status: str
    charged_or_reserved_tokens: int
    measured_model_tokens: int | None
    model_call_seconds: float | None
    inference_api_usd: float | None
    measured_worker_seconds: float | None
    costs: CostSummary


class CategoryRate(Contract):
    category: str
    provider: str = "unknown"
    submitted: int
    replied: int
    hired: int
    reply_rate: float
    hire_rate: float


class RejectionReason(Contract):
    reason: str
    count: int


class AnalyticsView(Contract):
    days: int
    run_count: int
    local_drafts: int
    charged_or_reserved_tokens: int
    measured_model_tokens: int | None
    inference_api_usd: float | None
    connects_spent: int | None
    submissions_with_known_spend: int
    provider_submissions: int
    category_rates: list[CategoryRate]
    rejection_reasons: list[RejectionReason]
    measurements: list[RunMeasurement]
    measurements_truncated: bool
    provider_connected: bool = False
    costs: CostSummary
