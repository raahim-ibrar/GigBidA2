"""Interactive desktop OAuth. Run on the host laptop, never through a public callback."""

import argparse
import asyncio
import hmac
import json
import logging
import queue
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.mcp_audit import ReadAuditor
from apps.api.auth.token_store import EncryptedTokenStorage, OAuthUnavailable
from apps.api.database import make_engine
from apps.api.models import MarketplaceConnection, OAuthCredential, SearchSchedule, User
from apps.api.settings import Settings
from mcp_servers.marketplace.upwork_transport import upwork_session


class LoopbackCallback:
    def __init__(self, *, port=8766, timeout=300):
        self.expected_state = None
        self.results = queue.Queue(maxsize=1)
        self.timeout = timeout
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                parts = urlparse(self.path)
                query = parse_qs(parts.query)
                state = query.get("state", [""])[0]
                valid = (
                    parts.path == "/callback"
                    and owner.expected_state
                    and hmac.compare_digest(state, owner.expected_state)
                )
                if not valid or not query.get("code") or query.get("error"):
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Authorization callback rejected. Restart GigBid sign-in.")
                    return
                if owner.results.empty():
                    owner.results.put_nowait((query["code"][0], state))
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(
                    b"Authorization received. You may close this tab and return to GigBid."
                )

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    async def redirect(self, url):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "www.upwork.com":
            raise OAuthUnavailable("Unexpected authorization host; sign-in stopped")
        self.expected_state = parse_qs(parsed.query).get("state", [""])[0]
        if not self.expected_state:
            raise OAuthUnavailable("Provider did not supply OAuth state")
        print("Sign in to Upwork in the browser. Waiting up to five minutes.", flush=True)
        # URL contains a one-time state and PKCE challenge, not a credential or access token.
        Path("work/upwork").mkdir(parents=True, exist_ok=True)
        Path("work/upwork/authorization-url.txt").write_text(url, encoding="utf-8")
        webbrowser.open(url)

    async def callback(self):
        try:
            return await asyncio.to_thread(self.results.get, True, self.timeout)
        except queue.Empty:
            raise OAuthUnavailable("Sign-in timed out; run the connection helper again") from None

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


async def connect(email=None):
    settings = Settings()
    engine = make_engine(settings.database_url)
    with Session(engine) as db:
        users = (
            list(db.scalars(select(User).where(User.email == email)))
            if email
            else list(
                db.scalars(
                    select(User).where(
                        ~User.email.like("demo-%"), ~User.email.like("%@example.org")
                    )
                )
            )
        )
        if len(users) != 1:
            raise OAuthUnavailable("Choose an existing account with --email YOUR_GIGBID_EMAIL")
        tenant = users[0].id
    storage = EncryptedTokenStorage(engine, settings, tenant, allow_create=True)
    # New authorization identity fences in-flight runs and stale refreshes.
    with Session(engine) as db, db.begin():
        row = db.get(OAuthCredential, (tenant, "upwork"), with_for_update=True)
        if row:
            row.generation = str(uuid4())
            row.connected = False
    storage.update({})
    callback = LoopbackCallback()
    callback.thread.start()
    try:
        async with upwork_session(
            engine,
            settings,
            tenant,
            interactive=True,
            generation=storage.generation,
            redirect_handler=callback.redirect,
            callback_handler=callback.callback,
        ) as (session, store):
            tools = (await session.list_tools()).tools
            snapshot = [tool.model_dump(mode="json") for tool in tools]
            from mcp_servers.marketplace.adapters.upwork_live import (
                parse_result,
                verified_capabilities,
            )

            accounts = parse_result(
                await ReadAuditor(engine, tenant).invoke(
                    "upwork",
                    "upwork__list_accounts",
                    {},
                    lambda: session.call_tool("upwork__list_accounts", {}),
                )
            ).get("accounts", [])
            freelancers = [a for a in accounts if a.get("role") == "TALENT"]
            if len(freelancers) != 1:
                raise OAuthUnavailable("Select exactly one freelancer account before proceeding")
            await asyncio.to_thread(store.update, {"org_uid": freelancers[0]["org_uid"]})
            with Session(engine) as db, db.begin():
                row = db.get(OAuthCredential, (tenant, "upwork"), with_for_update=True)
                if row.generation != store.generation:
                    raise OAuthUnavailable("Connection changed during sign-in")
                row.connected = True
                row.schema_snapshot = snapshot
                row.capabilities = verified_capabilities(tools)
                schedule = db.get(SearchSchedule, tenant)
                if schedule:
                    schedule.enabled = False
                    schedule.auto_analyse = False
                connection = db.get(MarketplaceConnection, tenant)
                if connection is None:
                    db.add(MarketplaceConnection(user_id=tenant, mode="upwork"))
                else:
                    connection.mode = "upwork"
                    connection.error = None
            Path("work/upwork/schema.json").write_text(
                json.dumps(snapshot, indent=2), encoding="utf-8"
            )
            Path("work/upwork/connection.json").write_text(
                json.dumps(
                    {
                        "tenant_id": tenant,
                        "tool_count": len(tools),
                        "verified": "authorized schema discovery only",
                        "live_writes": 0,
                    }
                ),
                encoding="utf-8",
            )
            print(
                "Upwork authorization and tool discovery succeeded. No live writes performed.",
                flush=True,
            )
    finally:
        callback.close()
        engine.dispose()
        Path("work/upwork/authorization-url.txt").unlink(missing_ok=True)


def main():
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--email")
    args = parser.parse_args()
    try:
        asyncio.run(connect(args.email))
    except Exception as error:
        # SDK errors can contain authorization codes/provider response bodies.
        print(
            "Upwork connection did not complete ("
            + type(error).__name__
            + "). No token details logged.",
            flush=True,
        )
        if isinstance(error, OAuthUnavailable):
            print(str(error), flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
