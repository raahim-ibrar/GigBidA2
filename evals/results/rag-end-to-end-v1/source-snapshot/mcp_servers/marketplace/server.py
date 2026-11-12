from mcp_servers.common import run_server
from mcp_servers.marketplace.factory import configured_server

mcp = configured_server()

if __name__ == "__main__":
    run_server(mcp)
