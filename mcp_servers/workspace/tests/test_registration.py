import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.workspace.server import mcp


@pytest.mark.asyncio
async def test_workspace_lists_three_tools_with_schemas():
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.list_tools()
        assert {tool.name for tool in result.tools} == {
            "free_calendar_slots",
            "create_interview_hold",
            "create_email_draft",
        }
        assert all(tool.inputSchema and tool.outputSchema for tool in result.tools)
