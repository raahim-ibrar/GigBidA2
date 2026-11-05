"""Capture public MCP registration schemas through the SDK, never private tool registries."""

import asyncio
import json
from pathlib import Path

from mcp_servers.marketplace.server import mcp as marketplace
from mcp_servers.portfolio.server import mcp as portfolio
from mcp_servers.workspace.server import mcp as workspace


async def schemas():
    result = {}
    for name, server in (
        ("portfolio", portfolio),
        ("marketplace", marketplace),
        ("workspace", workspace),
    ):
        result[name] = [
            tool.model_dump(mode="json", exclude_none=True) for tool in await server.list_tools()
        ]
    return result


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    (root / "tests/contract/mcp_schema.json").write_text(
        json.dumps(asyncio.run(schemas()), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
