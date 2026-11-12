from datetime import datetime
from uuid import UUID, uuid4

from pydantic import ConfigDict, Field, field_validator

from agent.handoffs import Contract


class AddClientMessage(Contract):
    text: str = Field(min_length=1, max_length=8000)
    idempotency_key: UUID = Field(default_factory=uuid4)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Enter a client message")
        return value.strip()


class CreateConversation(AddClientMessage):
    job_id: UUID
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def title_nonblank(cls, value):
        if not value.strip():
            raise ValueError("Enter a conversation title")
        return value.strip()


class MessageView(Contract):
    model_config = ConfigDict(from_attributes=True)
    id: str
    text: str
    created_at: datetime


class ConversationView(Contract):
    model_config = ConfigDict(from_attributes=True)
    id: str
    job_id: str
    run_id: str
    title: str
    provider_id: str | None = None
    revision: int
    created_at: datetime


class ReplyDraftView(Contract):
    id: str
    body: str
    created_at: datetime
    status: str = "local draft"
