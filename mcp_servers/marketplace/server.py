from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from mcp_servers.common import run_server
from mcp_servers.marketplace import tools

mcp = FastMCP("GigBid Marketplace")
for function in (
    tools.search_jobs,
    tools.get_job,
    tools.get_client_history,
    tools.get_connects_balance,
    tools.list_messages,
):
    mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
        )
    )(function)
for function in (tools.create_proposal_draft, tools.submit_proposal, tools.send_message):
    # Idempotency is not implemented yet; annotation must not promise it prematurely.
    mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
        )
    )(function)

if __name__ == "__main__":
    run_server(mcp)
