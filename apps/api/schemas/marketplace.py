from typing import Literal

from pydantic import Field

from agent.handoffs import Contract
from apps.api.schemas.proposals import JobView


class ConnectionUpdate(Contract):
    mode: Literal["manual", "student_sim"]


class ConnectionStatus(Contract):
    mode: Literal["manual", "student_sim"]
    connected: bool
    available: bool = False
    balance: int | None = None
    error: str | None = None
    synthetic: bool = True
    label: str = "Student-built simulator; not instructor GigSim"


class MarketplaceSearch(Contract):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)


class ImportedJobs(Contract):
    jobs: list[JobView]
    synthetic: bool = True
    provider: Literal["student_sim"] = "student_sim"


class SyncResult(Contract):
    events: int
    messages: int
