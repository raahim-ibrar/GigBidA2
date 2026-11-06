"""Workspace capabilities bind account and approved run identity at the host boundary."""

import asyncio

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from apps.api.database import make_engine
from apps.api.settings import Settings
from mcp_servers.workspace.service import WorkspaceService
from mcp_servers.workspace.tools import EmailDraftRequest, HoldRequest, SlotRequest, WorkspaceResult


def create_workspace_server(service=None, tenant_id=None, run_id=None):
    mcp = FastMCP("GigBid Workspace")
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True)

    def owner():
        nonlocal service
        if not tenant_id:
            raise ValueError("Set GIGBID_TENANT_ID before starting Workspace MCP")
        if service is None:
            service = WorkspaceService(make_engine(Settings().database_url))
        return service

    @mcp.tool(annotations=read)
    async def free_calendar_slots(request: SlotRequest) -> WorkspaceResult:
        """Find slots inside declared local availability, excluding this account's holds."""
        return WorkspaceResult(data=await asyncio.to_thread(owner().free_slots, tenant_id, request))

    @mcp.tool(annotations=write)
    async def create_interview_hold(request: HoldRequest) -> WorkspaceResult:
        """Preview or create one local tentative hold. Execution requires exact human approval."""
        return WorkspaceResult(
            data=await asyncio.to_thread(owner().hold, tenant_id, run_id, request)
        )

    @mcp.tool(annotations=write)
    async def create_email_draft(request: EmailDraftRequest) -> WorkspaceResult:
        """Preview or save an approved local email draft with a durable idempotency key."""
        return WorkspaceResult(
            data=await asyncio.to_thread(owner().email, tenant_id, run_id, request)
        )

    return mcp
