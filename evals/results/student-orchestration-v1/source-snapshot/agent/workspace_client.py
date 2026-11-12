"""Bound Workspace MCP capabilities. Write identity is supplied by the trusted host."""

from mcp_servers.workspace.tools import EmailDraftRequest, SlotRequest, TimeWindow, WorkspaceResult


class WorkspaceMCP:
    def __init__(self, session):
        self.session = session

    async def _call(self, name, request):
        result = await self.session.call_tool(name, {"request": request.model_dump(mode="json")})
        if result.isError or result.structuredContent is None:
            raise RuntimeError("Workspace MCP request failed")
        return WorkspaceResult.model_validate(result.structuredContent).data

    async def slots(self, request: SlotRequest):
        result = await self._call("free_calendar_slots", request)
        return [TimeWindow.model_validate(item).model_dump(mode="json") for item in result["slots"]]

    async def email(self, request: EmailDraftRequest):
        return await self._call("create_email_draft", request)
