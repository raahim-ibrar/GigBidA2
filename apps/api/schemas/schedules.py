from datetime import datetime
from typing import Literal

from pydantic import Field

from agent.handoffs import Contract


class ScheduleUpdate(Contract):
    version: int = Field(ge=0)
    enabled: bool
    auto_analyse: bool = False
    interval_minutes: int = Field(ge=5, le=1440)


class ScheduleView(ScheduleUpdate):
    queries: list[str]
    status: Literal["paused", "waiting_provider", "no_queries", "queued", "idle", "unavailable"]
    next_check_at: datetime | None = None
    last_checked_at: datetime | None = None
    connection_message: str = (
        "Scheduled searches use the connected student simulator. "
        "Automatic analysis is optional; submission always needs approval."
    )
