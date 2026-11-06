from datetime import datetime
from typing import Literal

from pydantic import Field

from agent.handoffs import Contract


class ScheduleUpdate(Contract):
    version: int = Field(ge=0)
    enabled: bool
    interval_minutes: int = Field(ge=5, le=1440)


class ScheduleView(ScheduleUpdate):
    queries: list[str]
    status: Literal["paused", "waiting_provider", "no_queries"]
    next_check_at: datetime | None = None
    last_checked_at: datetime | None = None
    connection_message: str = (
        "Marketplace search is unavailable until the supplied GigSim adapter is connected."
    )
