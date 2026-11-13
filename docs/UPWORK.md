# Upwork connection

GigBid uses Upwork's official Streamable HTTP MCP endpoint:
`https://mcp.upwork.com/mcp`. The operator completed real OAuth authorization and
read-only account discovery, job search, job detail and Connects-balance checks on
November 12, 2026. One real job was imported into the existing personal GigBid
account. No model inference, proposal preparation, submission or message send was
performed during live verification. Sanitized evidence is in
`evals/results/upwork-live-verification.json`.

On November 13, 2026, the saved authorization was revalidated with nine audited
official MCP reads. Four jobs were checked; all returned `can_apply=false` and
Connects costs above the available account balance. The actual production Pricing
node, through Marketplace MCP, stopped with the insufficient-balance review gate.
The balance was unchanged afterward. **Live provider-preview preparation remains
unverified**: no provider write was called, no preview was created and no approval
gate was bypassed. This establishes an application preflight blocker; it does not
claim that Upwork itself charges for generating a preview. Finishing the existing
flow needs an eligible job/account state that passes its Connects checks. Evidence:
[`upwork-preview-verification-2026-11-13.json`](../evals/results/upwork-preview-verification-2026-11-13.json).

## Connect on the host laptop

1. Install the pinned Python dependencies and run `alembic upgrade head`.
2. Set `OAUTH_ENCRYPTION_KEY` in the ignored `.env` to a Fernet key. Generate one
   with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
   Keep the key private and stable; replacing it requires reconnecting accounts.
3. Run `python -m scripts.connect_upwork --email YOUR_GIGBID_EMAIL` from the
   repository root. The email selects an existing GigBid account. If there is exactly
   one personal account, `--email` can be omitted. This command is for the trusted
   laptop operator and is not exposed as a public HTTP endpoint.
4. Sign in and approve access on Upwork. A temporary listener binds only
   `127.0.0.1:8766`, accepts the matching one-time OAuth state, and expires after
   five minutes. The installed MCP SDK performs PKCE and the token exchange.
5. Refresh GigBid Settings. The selected account is in Upwork mode; simulator jobs
   remain stored separately. Reauthorization pauses saved searches and automatic
   analysis. No credentials are returned to the frontend.

Only a single freelancer/TALENT organization is selected automatically. Multiple
freelancer organizations are an unsupported selection case and stop connection
completion. A custom hosted callback is not used. Upwork currently restricts custom
website callbacks; its documentation supports local desktop clients.

## Capabilities and limits

The verified names/actions are captured in `tests/contract/upwork_schema.json`.
The adapter exposes job search/detail, public client history contextualized by job,
Connects balance, room-message reads and approved proposal-preview preparation.
Upwork search is capped at ten results per request. Missing client/budget/cost fields
remain unknown; they are never replaced with simulator values.

Before approval, proposal previewing is local plus read-only job checks. After exact
GigBid approval, the host may call `manage_proposals/create` to prepare an Upwork
server preview. Existing invitations/proposals are checked first; paginated results
that cannot establish absence block preparation. Changed Connects cost blocks it.
The result is **pending_provider_confirmation**, not submitted. The provider preview
ID is shown; no fabricated browser confirmation link is generated. Preparing a
provider preview has been tested with fixtures only, not the real account.

GigBid never calls `confirm_preview`, `manage_proposals/send_proposal` or direct
message-send actions. Upwork's message tool sends directly, so replies use approved
local drafts for the user to send manually. Final provider confirmation must happen
through an authorized Upwork client or a manually prepared application on Upwork.
No compatible simulator-style event feed or confirmed-receipt mapping is enabled.

## Persistence and recovery

OAuth tokens, client credentials, selected organization and authorization-server
metadata are encrypted together, bound to the GigBid user and provider. The adapter
restores saved expiry and issuer metadata on SDK startup so token refresh does not
mistake a stored expired token for an indefinitely valid one. A PostgreSQL advisory
lock serializes refreshes across API and worker processes.

Disconnect immediately erases local secrets and changes the connection generation;
remote token revocation is best-effort. An in-flight refresh cannot restore a
disconnected generation. Runs are bound to their source and authorization generation;
switching modes or reconnecting cannot redirect an approved action to another account.

Before non-idempotent provider preparation, the host commits a send-once intent.
Successful results are replayed locally. Crashes/timeouts remain uncertain and are
never automatically retried or reported as submitted. Review Upwork before starting
another attempt. Public traces never contain OAuth tokens or raw tool results.

Live status polling does not poll Upwork. Explicit saved-search opt-in permits one
query per account per tick, at an interval of at least 60 minutes, with automatic
live analysis disabled. Jobs are analysed only when the user requests it; configured
model-provider privacy terms still apply to that separate action.

References: [Upwork MCP](https://www.upwork.com/ai/mcp),
[official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).
