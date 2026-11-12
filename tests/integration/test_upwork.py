import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from cryptography.fernet import Fernet
from mcp.shared.auth import OAuthToken
from mcp.types import Tool
from pydantic import SecretStr
from sqlalchemy.orm import Session

from apps.api.auth.token_store import EncryptedTokenStorage, OAuthUnavailable
from apps.api.models import OAuthCredential
from mcp_servers.marketplace.adapters.student_sim import MarketplaceRejected, MarketplaceUnavailable
from mcp_servers.marketplace.adapters.upwork_live import (
    CAPABILITIES,
    UpworkLiveAdapter,
    normalize_job,
    verified_capabilities,
)
from tests.integration.test_runs import register

SCHEMAS = json.loads(Path("tests/contract/upwork_schema.json").read_text())


@pytest.fixture
def live_account(client, account_app):
    user = register(client)
    settings = account_app.state.settings.model_copy(
        update={"oauth_encryption_key": SecretStr(Fernet.generate_key().decode())}
    )
    account_app.state.settings = settings
    account_app.state.marketplace.settings = settings
    storage = EncryptedTokenStorage(
        account_app.state.engine, settings, user["id"], allow_create=True
    )
    storage.update(
        {
            "org_uid": "fake-freelancer-account",
            "tokens": {
                "access_token": "FAKE_ACCESS_CANARY",
                "refresh_token": "FAKE_REFRESH_CANARY",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        }
    )
    with Session(account_app.state.engine) as db, db.begin():
        row = db.get(OAuthCredential, (user["id"], "upwork"))
        row.connected = True
        row.schema_snapshot = SCHEMAS
        row.capabilities = verified_capabilities([Tool.model_validate(t) for t in SCHEMAS])
    account_app.state.marketplace.set_mode(user["id"], "upwork")
    return user, settings, storage


@pytest.mark.asyncio
async def test_tokens_are_encrypted_bound_to_tenant_and_revocation_fences_refresh(
    account_app, live_account
):
    user, settings, storage = live_account
    with Session(account_app.state.engine) as db:
        row = db.get(OAuthCredential, (user["id"], "upwork"))
        assert "FAKE_ACCESS_CANARY" not in row.encrypted_payload
        assert "FAKE_REFRESH_CANARY" not in row.encrypted_payload
    assert (await storage.get_tokens()).access_token == "FAKE_ACCESS_CANARY"
    old = EncryptedTokenStorage(
        account_app.state.engine, settings, user["id"], generation=storage.generation
    )
    storage.disconnect()
    with pytest.raises(OAuthUnavailable):
        await old.set_tokens(OAuthToken(access_token="LATE_REFRESH_CANARY", token_type="Bearer"))
    assert (
        not EncryptedTokenStorage(account_app.state.engine, settings, user["id"])
        .read()
        .get("tokens")
    )


@pytest.mark.asyncio
async def test_refresh_preserves_refresh_token_and_expiry_is_not_reset(live_account):
    _, _, storage = live_account
    await storage.set_tokens(
        OAuthToken(
            access_token="NEW_ACCESS",
            refresh_token="REFRESH_CANARY",
            token_type="Bearer",
            expires_in=100,
        )
    )
    await storage.set_tokens(
        OAuthToken(access_token="REFRESHED_ACCESS", token_type="Bearer", expires_in=60)
    )
    tokens = await storage.get_tokens()
    assert tokens.refresh_token == "REFRESH_CANARY" and 0 <= tokens.expires_in <= 60
    storage.update({"expires_at": "2000-01-01T00:00:00+00:00"})
    assert (await storage.get_tokens()).expires_in == 0


def test_wrong_key_and_cross_tenant_ciphertext_fail_closed(account_app, live_account):
    user, settings, storage = live_account
    wrong = settings.model_copy(
        update={"oauth_encryption_key": SecretStr(Fernet.generate_key().decode())}
    )
    with pytest.raises(OAuthUnavailable):
        EncryptedTokenStorage(account_app.state.engine, wrong, user["id"]).read()
    with Session(account_app.state.engine) as db:
        row = db.get(OAuthCredential, (user["id"], "upwork"))
        other = EncryptedTokenStorage(account_app.state.engine, settings, "other-tenant")
        with pytest.raises(OAuthUnavailable):
            other._decode(row)


def test_status_is_private_no_remote_poll_and_disconnect_requires_csrf(
    client, account_app, live_account, monkeypatch
):
    user, _, _ = live_account

    def forbidden(*args, **kwargs):
        raise AssertionError("Status polling must not contact Upwork")

    monkeypatch.setattr(account_app.state.marketplace, "adapter", forbidden)

    async def revoke(*args, **kwargs):
        return httpx.Response(200)

    monkeypatch.setattr(httpx.AsyncClient, "post", revoke)
    response = client.get("/api/marketplace")
    assert response.status_code == 200 and response.json()["upwork_connected"]
    assert "CANARY" not in response.text and "fake-freelancer-account" not in response.text
    assert client.delete("/api/marketplace/upwork").status_code == 403
    assert (
        client.delete(
            "/api/marketplace/upwork", headers={"X-CSRF-Token": user["csrf_token"]}
        ).status_code
        == 200
    )
    assert not client.get("/api/marketplace").json()["upwork_connected"]


def test_live_jobs_require_the_original_connection_and_provider_specific_identity(
    account_app, live_account
):
    user, _, storage = live_account
    accounts = account_app.state.marketplace
    raw = normalize_job(
        {
            "id": "123",
            "title": "Python API",
            "description": "Public job",
            "budget": "12.00–28.00/hr",
            "job_type": "hourly",
        },
        storage.generation,
    )
    job = accounts.import_job(user["id"], raw)
    assert job.raw["source"] == "upwork" and not job.raw["synthetic"]
    assert accounts.import_job(user["id"], raw).id == job.id
    storage.disconnect()
    with pytest.raises(Exception, match="expired connection"):
        accounts.import_job(user["id"], raw)


@pytest.mark.asyncio
async def test_live_adapter_only_calls_verified_action_and_org(account_app, live_account):
    user, settings, storage = live_account
    calls = []

    class Remote:
        async def list_tools(self):
            return SimpleNamespace(tools=[Tool.model_validate(t) for t in SCHEMAS])

        async def call_tool(self, name, arguments):
            calls.append((name, arguments))
            return SimpleNamespace(
                isError=False, structuredContent={"balance": {"connectsBalance": 7}}
            )

    @asynccontextmanager
    async def factory(*args, **kwargs):
        yield Remote(), storage

    adapter = UpworkLiveAdapter(
        account_app.state.engine, settings, user["id"], session_factory=factory
    )
    assert (await adapter.get_connects_balance()).data["connects"] == 7
    assert calls == [
        (
            "upwork__get_freelancer_financials",
            {"action": "connects_balance", "org_uid": "fake-freelancer-account", "params": {}},
        )
    ]
    for name, action in [
        ("upwork__confirm_preview", "confirm"),
        ("upwork__send_message", "send"),
        ("upwork__manage_proposals", "send_proposal"),
    ]:
        with pytest.raises(MarketplaceRejected):
            await adapter._call(name, action)
    with pytest.raises(MarketplaceRejected):
        await adapter.send_message(None)
    with pytest.raises(MarketplaceRejected):
        await adapter.submit_proposal(None)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_changed_schema_outage_and_replaced_connection_do_not_call_tools(
    account_app, live_account
):
    user, settings, storage = live_account

    class Remote:
        async def list_tools(self):
            changed = [Tool.model_validate(t) for t in SCHEMAS]
            for tool in changed:
                if tool.name == "upwork__get_freelancer_financials":
                    tool.inputSchema = {"type": "object"}
            return SimpleNamespace(tools=changed)

        async def call_tool(self, *args):
            raise AssertionError("Schema changed")

    @asynccontextmanager
    async def factory(*args, **kwargs):
        yield Remote(), storage

    adapter = UpworkLiveAdapter(
        account_app.state.engine, settings, user["id"], session_factory=factory
    )
    with pytest.raises(MarketplaceRejected, match="schema changed"):
        await adapter.get_connects_balance()
    with pytest.raises(MarketplaceRejected, match="connection changed"):
        UpworkLiveAdapter(
            account_app.state.engine, settings, user["id"], generation="old-generation"
        )

    @asynccontextmanager
    async def outage(*args, **kwargs):
        raise ConnectionError("PRIVATE_PROVIDER_BODY")
        yield

    adapter.session_factory = outage
    with pytest.raises(MarketplaceUnavailable) as error:
        await adapter.get_connects_balance()
    assert "PRIVATE_PROVIDER_BODY" not in str(error.value)


def test_upwork_contract_contains_only_verified_capability_actions():
    tools = [Tool.model_validate(t) for t in SCHEMAS]
    assert set(verified_capabilities(tools)) == set(CAPABILITIES)
    assert "send_message" not in CAPABILITIES and "submit_proposal" not in CAPABILITIES


@pytest.mark.asyncio
async def test_loopback_rejects_bad_state_wrong_path_and_times_out():
    from scripts.connect_upwork import LoopbackCallback

    callback = LoopbackCallback(port=0, timeout=0.05)
    callback.thread.start()
    callback.expected_state = "state-canary"
    url = "http://127.0.0.1:" + str(callback.server.server_port)
    try:
        async with httpx.AsyncClient() as client:
            assert (await client.get(url + "/callback?code=code&state=wrong")).status_code == 400
            assert (
                await client.get(url + "/other?code=code&state=state-canary")
            ).status_code == 400
            with pytest.raises(OAuthUnavailable, match="timed out"):
                await callback.callback()
            assert (
                await client.get(url + "/callback?code=code&state=state-canary")
            ).status_code == 200
            assert await callback.callback() == ("code", "state-canary")
    finally:
        callback.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("refresh", [False, True])
async def test_real_mcp_oauth_sdk_uses_pkce_and_refresh_against_controlled_server(
    live_account, refresh
):
    import base64
    import hashlib
    from urllib.parse import parse_qs, urlparse

    from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata

    from mcp_servers.marketplace.upwork_transport import (
        PersistentOAuthProvider as OAuthClientProvider,
    )

    _, _, storage = live_account
    origin = "https://oauth-fixture.example.test"
    redirects = []
    grants = []
    metadata = OAuthClientMetadata(
        redirect_uris=["http://127.0.0.1:8766/callback"],
        client_name="GigBid fixture",
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
    )
    storage.update({"tokens": None, "client": None, "expires_at": None})
    if refresh:
        await storage.set_client_info(
            OAuthClientInformationFull(client_id="fixture-client", **metadata.model_dump())
        )
        await storage.set_tokens(
            OAuthToken(
                access_token="EXPIRED",
                refresh_token="REFRESH_CANARY",
                token_type="Bearer",
                expires_in=0,
            )
        )

    async def authorize(url):
        redirects.append(parse_qs(urlparse(url).query))

    async def callback():
        return "fixture-code", redirects[-1]["state"][0]

    async def handler(request):
        path = request.url.path
        if path == "/mcp":
            if request.headers.get("authorization") == "Bearer FRESH_TOKEN":
                return httpx.Response(200, json={"ok": True})
            return httpx.Response(
                401,
                headers={
                    "WWW-Authenticate": (
                        f'Bearer resource_metadata="{origin}/.well-known/oauth-protected-resource"'
                    )
                },
            )
        if "oauth-protected-resource" in path:
            return httpx.Response(
                200, json={"resource": origin + "/mcp", "authorization_servers": [origin]}
            )
        if "oauth-authorization-server" in path or "openid-configuration" in path:
            return httpx.Response(
                200,
                json={
                    "issuer": origin,
                    "authorization_endpoint": origin + "/authorize",
                    "token_endpoint": origin + "/token",
                    "registration_endpoint": origin + "/register",
                    "response_types_supported": ["code"],
                    "code_challenge_methods_supported": ["S256"],
                    "token_endpoint_auth_methods_supported": ["none"],
                },
            )
        if path == "/register":
            return httpx.Response(
                201, json={"client_id": "fixture-client", **json.loads(request.content)}
            )
        if path == "/token":
            fields = parse_qs(request.content.decode())
            grants.append(fields["grant_type"][0])
            if not refresh:
                challenge = (
                    base64.urlsafe_b64encode(
                        hashlib.sha256(fields["code_verifier"][0].encode()).digest()
                    )
                    .rstrip(b"=")
                    .decode()
                )
                assert challenge == redirects[0]["code_challenge"][0]
                assert redirects[0]["code_challenge_method"] == ["S256"]
            else:
                assert fields["refresh_token"] == ["REFRESH_CANARY"]
            return httpx.Response(
                200,
                json={
                    "access_token": "FRESH_TOKEN",
                    "refresh_token": "REFRESH_CANARY",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            )
        raise AssertionError(str(request.url))

    if refresh:
        storage.update(
            {
                "oauth_metadata": {
                    "issuer": origin,
                    "authorization_endpoint": origin + "/authorize",
                    "token_endpoint": origin + "/token",
                    "response_types_supported": ["code"],
                }
            }
        )
    provider = OAuthClientProvider(
        origin + "/mcp", metadata, storage, redirect_handler=authorize, callback_handler=callback
    )
    async with httpx.AsyncClient(auth=provider, transport=httpx.MockTransport(handler)) as client:
        response = await client.get(origin + "/mcp")
    assert response.status_code == 200
    assert grants == ["refresh_token" if refresh else "authorization_code"]
    assert (await storage.get_tokens()).access_token == "FRESH_TOKEN"
