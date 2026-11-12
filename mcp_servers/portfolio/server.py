import os

from mcp_servers.common import run_server
from mcp_servers.portfolio.factory import create_portfolio_server

mcp = create_portfolio_server(tenant_id=os.getenv("GIGBID_TENANT_ID"))

def main():
    run_server(mcp)


if __name__ == "__main__":
    main()
