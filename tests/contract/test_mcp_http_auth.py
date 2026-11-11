from uuid import uuid4

import httpx
import pytest

from mcp_servers.http import BearerBoundary


@pytest.mark.asyncio
async def test_http_mcp_auth_limit_and_failure_boundary():
    called = []

    async def server(scope, receive, send):
        called.append(True)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"MCP fixture"})

    mode = {"allowed": True, "fail": False}

    async def limit(tenant):
        if mode["fail"]:
            raise ConnectionError("Redis fixture outage")
        return mode["allowed"]

    token = "test-only-token-with-at-least-32-characters"
    app = BearerBoundary(server, token, str(uuid4()), limiter=limit)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://mcp"
    ) as client:
        assert (await client.post("/mcp")).status_code == 401
        assert not called
        headers = {"Authorization": "Bearer " + token}
        assert (await client.post("/mcp", headers=headers)).status_code == 200
        mode["allowed"] = False
        denied = await client.post("/mcp", headers=headers)
        assert denied.status_code == 429 and denied.headers["Retry-After"] == "60"
        mode["fail"] = True
        assert (await client.post("/mcp", headers=headers)).status_code == 503
        assert len(called) == 1
