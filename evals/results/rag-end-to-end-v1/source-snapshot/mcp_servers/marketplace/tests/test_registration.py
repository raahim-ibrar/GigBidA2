import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.marketplace.server import mcp


@pytest.mark.asyncio
async def test_unimplemented_submission_is_an_mcp_error():
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool(
            "submit_proposal",
            arguments={
                "request": {
                    "job_id": "fixture",
                    "text": "Fixture",
                    "bid_amount": 10,
                    "idempotency_key": "fixture-key",
                    "dry_run": False,
                }
            },
        )
        assert result.isError
