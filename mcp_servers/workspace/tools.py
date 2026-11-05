from datetime import datetime

from pydantic import Field, model_validator

from agent.handoffs import Contract


class SlotRequest(Contract):
    start: datetime
    end: datetime
    minutes: int = Field(default=30, ge=15, le=240)

    @model_validator(mode="after")
    def validate_range(self):
        if self.start.utcoffset() is None or self.end.utcoffset() is None:
            raise ValueError("Use timezone-aware datetimes")
        if self.end <= self.start:
            raise ValueError("end must follow start")
        return self


class HoldRequest(Contract):
    start: datetime
    minutes: int = Field(ge=15, le=240)
    idempotency_key: str = Field(min_length=8, max_length=200)


class EmailDraftRequest(Contract):
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=20000)
    idempotency_key: str = Field(min_length=8, max_length=200)


class WorkspaceResult(Contract):
    data: dict


async def free_calendar_slots(request: SlotRequest) -> WorkspaceResult:
    raise NotImplementedError("Implement local calendar mock or official Calendar API")


async def create_interview_hold(request: HoldRequest) -> WorkspaceResult:
    raise NotImplementedError("Implement tentative holds with approval and idempotency")


async def create_email_draft(request: EmailDraftRequest) -> WorkspaceResult:
    raise NotImplementedError("Implement local draft mock or official Gmail API; never send")
