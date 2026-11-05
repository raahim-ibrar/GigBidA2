from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from mcp_servers.common import run_server
from mcp_servers.workspace import tools

mcp = FastMCP("GigBid Workspace")
mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
    )
)(tools.free_calendar_slots)
for function in (tools.create_interview_hold, tools.create_email_draft):
    mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
        )
    )(function)

if __name__ == "__main__":
    run_server(mcp)
