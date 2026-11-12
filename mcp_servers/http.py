"""Bearer-protected HTTP transport for a host-bound account's MCP server.

One process serves one account selected by the host environment. Tenant identity never
comes from tool arguments or an unverified HTTP header. Agents normally use stdio.
"""

import hmac
import os
from uuid import UUID

from redis.asyncio import Redis

from apps.api.settings import Settings


class BearerBoundary:
    def __init__(self, app, token, tenant, *, limiter):
        if len(token) < 32:
            raise ValueError("HTTP MCP requires a random bearer token of at least 32 characters")
        self.app, self.expected, self.tenant, self.limiter = (
            app,
            ("Bearer " + token).encode(),
            tenant,
            limiter,
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        provided = dict(scope["headers"]).get(b"authorization", b"")
        if len(provided) > 512 or not hmac.compare_digest(provided, self.expected):
            await self.reject(send, 401, b"Bearer authentication required")
            return
        try:
            allowed = await self.limiter(self.tenant)
        except Exception:
            await self.reject(send, 503, b"Rate limiter unavailable")
            return
        if not allowed:
            await self.reject(send, 429, b"Account request limit exceeded", retry=True)
            return
        await self.app(scope, receive, send)

    async def reject(self, send, status, body, *, retry=False):
        headers = [(b"content-type", b"text/plain"), (b"cache-control", b"no-store")]
        if status == 401:
            headers.append((b"www-authenticate", b"Bearer"))
        if retry:
            headers.append((b"retry-after", b"60"))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


def create_http_app(server, token, tenant, *, redis_url=None, limiter=None):
    tenant = str(UUID(tenant))
    if limiter is None:
        redis = Redis.from_url(redis_url or Settings().redis_url, socket_timeout=3)

        async def limiter(tenant):
            # Atomic shared counter, fixed 60-second window, 60 HTTP requests/account.
            count = await redis.eval(
                "local n=redis.call('INCR',KEYS[1]); "
                "if n==1 then redis.call('EXPIRE',KEYS[1],60) end; return n",
                1,
                "gigbid:mcp:http:" + tenant,
            )
            return count <= 60

    return BearerBoundary(server.streamable_http_app(), token, tenant, limiter=limiter)


def configured_app():
    tenant, run_id = os.getenv("GIGBID_TENANT_ID", ""), os.getenv("GIGBID_RUN_ID")
    name, token = os.getenv("GIGBID_MCP_SERVER", "portfolio"), os.getenv("MCP_BEARER_TOKEN", "")
    if name == "portfolio":
        from urllib.parse import urlparse

        from mcp.server.transport_security import TransportSecuritySettings

        from mcp_servers.portfolio.factory import create_portfolio_server

        origin = os.environ["WEB_ORIGIN"]
        host = urlparse(origin).netloc
        server = create_portfolio_server(
            tenant_id=tenant,
            json_response=True,
            stateless_http=True,
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=[host, "127.0.0.1:*", "localhost:*"],
                allowed_origins=[origin, "http://127.0.0.1:*", "http://localhost:*"],
            ),
        )
    elif name == "marketplace":
        from mcp_servers.marketplace.factory import create_marketplace_server

        server = create_marketplace_server(tenant_id=tenant, run_id=run_id)
    elif name == "workspace":
        from mcp_servers.workspace.factory import create_workspace_server

        server = create_workspace_server(tenant_id=tenant, run_id=run_id)
    else:
        raise ValueError("Unknown MCP server")
    return create_http_app(server, token, tenant)
