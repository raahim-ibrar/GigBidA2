import os

from mcp_servers.common import run_server
from mcp_servers.workspace.factory import create_workspace_server

mcp = create_workspace_server(
    tenant_id=os.getenv("GIGBID_TENANT_ID"), run_id=os.getenv("GIGBID_RUN_ID")
)

if __name__ == "__main__":
    run_server(mcp)
