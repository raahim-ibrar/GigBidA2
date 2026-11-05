import json
from pathlib import Path

import pytest

from scripts.snapshot_mcp import schemas


@pytest.mark.asyncio
async def test_tool_schemas_match_reviewed_snapshot():
    snapshot = Path(__file__).with_name("mcp_schema.json")
    assert await schemas() == json.loads(snapshot.read_text(encoding="utf-8"))
