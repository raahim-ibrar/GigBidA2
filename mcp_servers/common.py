"""Use stdio locally until bearer authentication is implemented for HTTP transport."""

import os


def run_server(server):
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport != "stdio":
        raise RuntimeError("HTTP MCP is disabled until bearer authentication is implemented")
    server.run(transport="stdio")
