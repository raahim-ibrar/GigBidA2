from datetime import UTC, datetime, timedelta

from pydantic import Field, model_validator

from agent.handoffs import Contract


class TimeWindow(Contract):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_range(self):
        if self.start.utcoffset() is None or self.end.utcoffset() is None:
            raise ValueError("Use timezone-aware datetimes")
        if self.end <= self.start:
            raise ValueError("end must follow start")
        if self.end - self.start > timedelta(days=31):
            raise ValueError("Search at most 31 days at a time")
        self.start, self.end = self.start.astimezone(UTC), self.end.astimezone(UTC)
        return self


class SlotRequest(TimeWindow):
    minutes: int = Field(default=30, ge=15, le=240)


class HoldRequest(Contract):
    start: datetime
    minutes: int = Field(ge=15, le=240)
    idempotency_key: str = Field(min_length=8, max_length=200)
    dry_run: bool = True

    @model_validator(mode="after")
    def aware_start(self):
        if self.start.utcoffset() is None:
            raise ValueError("Use a timezone-aware start time")
        self.start = self.start.astimezone(UTC)
        return self


class EmailDraftRequest(Contract):
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=20000)
    idempotency_key: str = Field(min_length=8, max_length=200)
    dry_run: bool = True


class WorkspaceResult(Contract):
    data: dict
