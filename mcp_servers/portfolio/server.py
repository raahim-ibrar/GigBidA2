import os

from mcp_servers.common import run_server
from mcp_servers.portfolio.factory import create_portfolio_server

mcp = create_portfolio_server(tenant_id=os.getenv("GIGBID_TENANT_ID"))

if __name__ == "__main__":
    run_server(mcp)
