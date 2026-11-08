from typing import Literal

from pydantic import Field, model_validator

from agent.handoffs import Contract


class GoldJob(Contract):
    id: str = Field(min_length=1)
    persona: str = Field(min_length=1)
    bid: bool = Field(strict=True)
    scam: bool = Field(strict=True)
    relevant_ids: list[str] = Field(default_factory=list)
    price_min: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    price_max: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def price_band(self):
        if (self.price_min is None) != (self.price_max is None):
            raise ValueError("Supply both price bounds or neither")
        if self.price_min is not None and self.price_min > self.price_max:
            raise ValueError("Price bounds are reversed")
        if len(self.relevant_ids) != len(set(self.relevant_ids)):
            raise ValueError("Relevant evidence IDs must be unique")
        return self


class Prediction(Contract):
    id: str = Field(min_length=1)
    bid: bool | None = Field(default=None, strict=True)
    scam: bool | None = Field(default=None, strict=True)
    ranked_ids: list[str] | None = None
    price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    claim_labels: list[Literal["supported", "unsupported", "ambiguous"]] | None = None
    claim_label_source: str | None = None
    measured_tokens: int | None = Field(default=None, strict=True, ge=0)
    elapsed_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    compliance_violations_caught: int | None = Field(default=None, strict=True, ge=0)

    @model_validator(mode="after")
    def annotations(self):
        if self.ranked_ids is not None and len(self.ranked_ids) != len(set(self.ranked_ids)):
            raise ValueError("Ranked evidence IDs must be unique")
        if self.claim_labels is not None and not (self.claim_label_source or "").strip():
            raise ValueError("Claim annotations need a human/calibrated-judge source identifier")
        return self


class JudgeLabel(Contract):
    id: str = Field(min_length=1)
    human: bool = Field(strict=True)
    judge: bool = Field(strict=True)


class Outcome(Contract):
    id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    source: Literal["gigsim"]
    submitted: bool = Field(strict=True)
    replied: bool = Field(strict=True)
    hired: bool = Field(strict=True)
    connects: int | None = Field(default=None, strict=True, ge=0)
    followup_complete: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def observed_submission(self):
        if self.submitted and self.followup_complete is not True:
            raise ValueError("Research outcomes require complete fixed-window follow-up")
        if (self.replied or self.hired or self.connects is not None) and not self.submitted:
            raise ValueError("Outcomes and spend require a verified submission")
        if self.hired and not self.replied:
            raise ValueError("A hire must also be counted as a reply")
        return self
