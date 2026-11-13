from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.run_store import RunNotFound
from apps.api.auth.dependencies import CurrentUser
from apps.api.models import AgentRun, MCPReadAudit

router = APIRouter(tags=["mcp-audits"])


class MCPReadAuditView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    run_id: str | None
    server: str
    tool: str
    status: Literal["started", "completed", "tool_error", "exception", "cancelled"]
    arguments: JsonValue
    result: JsonValue
    elapsed_seconds: float | None
    started_at: datetime
    finished_at: datetime | None


@router.get("/mcp/read-audits", response_model=list[MCPReadAuditView])
def read_audits(
    user: CurrentUser,
    request: Request,
    run_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Owner-only redacted local receipts. No credentials, prompts or source bodies."""
    with Session(request.app.state.engine) as db:
        query = select(MCPReadAudit).where(MCPReadAudit.user_id == user.id)
        if run_id:
            run = db.get(AgentRun, run_id)
            if not run or run.user_id != user.id:
                raise RunNotFound("Run not found")
            query = query.where(MCPReadAudit.run_id == run_id)
        rows = db.scalars(
            query.order_by(MCPReadAudit.started_at.desc(), MCPReadAudit.id)
            .offset(offset)
            .limit(limit)
        )
        return [MCPReadAuditView.model_validate(row) for row in rows]
