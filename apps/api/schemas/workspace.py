from datetime import datetime
from typing import Literal

from agent.handoffs import Contract
from mcp_servers.workspace.tools import TimeWindow


class AvailabilityView(TimeWindow):
    id: str


class WorkspaceActionView(Contract):
    id: str
    run_id: str
    tool: str
    result: dict
    created_at: datetime


class SlotList(Contract):
    backend: Literal["local"] = "local"
    slots: list[TimeWindow]
