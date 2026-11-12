from pydantic import BaseModel, ConfigDict, Field

from agent.handoffs import ApprovalDecision


class StartRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str = Field(min_length=1, max_length=200)


class ApproveRun(ApprovalDecision):
    thread_id: str = Field(min_length=1, max_length=200)


class EditDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=20000)


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)
