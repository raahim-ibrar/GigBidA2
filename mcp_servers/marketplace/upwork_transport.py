"""Official Upwork transport; interactive sign-in is confined to the local helper."""

import asyncio
import hashlib
from contextlib import asynccontextmanager

from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import OAuthClientMetadata, OAuthMetadata
from sqlalchemy import text

from agent.mcp_client import build_client
from apps.api.auth.token_store import EncryptedTokenStorage, OAuthUnavailable

UPWORK_URL = "https://mcp.upwork.com/mcp"
REDIRECT_URI = "http://127.0.0.1:8766/callback"


class PersistentOAuthProvider(OAuthClientProvider):
    """Restore expiry/AS metadata omitted by the SDK's default storage reload."""

    async def _initialize(self):
        await super()._initialize()
        payload = await asyncio.to_thread(self.context.storage.read)
        if self.context.current_tokens:
            self.context.update_token_expiry(self.context.current_tokens)
        if payload.get("oauth_metadata"):
            metadata = OAuthMetadata.model_validate(payload["oauth_metadata"])
            if (
                self.context.client_info
                and self.context.client_info.issuer
                and str(metadata.issuer).rstrip("/")
                != str(self.context.client_info.issuer).rstrip("/")
            ):
                raise OAuthUnavailable("Stored OAuth issuer changed; reconnect")
            self.context.oauth_metadata = metadata
            self.context.auth_server_url = str(metadata.issuer)
        elif self.context.current_tokens and not self.context.is_token_valid():
            raise OAuthUnavailable(
                "Reconnect Upwork to restore authorization-server metadata for refresh"
            )


async def reconnect_required(*args):
    raise OAuthUnavailable(
        "Upwork authorization expired or was revoked. Reconnect on the host laptop."
    )


@asynccontextmanager
async def upwork_session(
    engine,
    settings,
    tenant,
    *,
    generation=None,
    redirect_handler=None,
    callback_handler=None,
    interactive=False,
):
    storage = EncryptedTokenStorage(
        engine, settings, tenant, generation=generation, allow_create=interactive
    )
    auth = PersistentOAuthProvider(
        server_url=UPWORK_URL,
        client_metadata=OAuthClientMetadata(
            redirect_uris=[REDIRECT_URI],
            client_name="GigBid local desktop",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",
        ),
        storage=storage,
        redirect_handler=redirect_handler or reconnect_required,
        callback_handler=callback_handler or reconnect_required,
        timeout=300 if interactive else 30,
    )
    client = build_client(
        {
            "upwork": {
                "transport": "streamable_http",
                "url": UPWORK_URL,
                "auth": auth,
                "timeout": 30,
                "sse_read_timeout": 45,
            }
        }
    )
    # Serialize refreshes across API/worker processes; rotating refresh tokens must
    # not be redeemed concurrently. A session lock is explicitly released on exit.
    connection = None
    key = int.from_bytes(
        hashlib.sha256(("upwork:" + tenant).encode()).digest()[:8], "big", signed=True
    )
    if engine.dialect.name == "postgresql":

        def acquire():
            conn = engine.connect()
            try:
                conn.execute(text("SET lock_timeout = '10s'"))
                conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": key})
                return conn
            except Exception:
                conn.close()
                raise

        connection = await asyncio.to_thread(acquire)
    try:
        async with client.session("upwork") as session:
            yield session, storage
            if auth.context.oauth_metadata is not None:
                await asyncio.to_thread(
                    storage.update,
                    {"oauth_metadata": auth.context.oauth_metadata.model_dump(mode="json")},
                )
    finally:
        if connection is not None:

            def release():
                try:
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                finally:
                    connection.close()

            await asyncio.to_thread(release)
