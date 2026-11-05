# Runbook

Stage: accounts, portfolio retrieval and durable local proposal review; no public deployment exists.

## Local development

Follow the root README for uv, npm and the two terminal commands. Start Postgres and run `uv run alembic upgrade head` before the API. `/health/live` checks the API process; `/health/ready` checks database access and the accounts schema. `/api/status` lists unfinished integrations.

Use `localhost` consistently for the browser and API during normal development. Sessions use an HttpOnly, SameSite=Lax cookie; mutating authenticated requests also require the session's CSRF token. Production settings require HTTPS and Secure cookies. Passwords use Argon2. Sessions store a SHA-256 digest of a random token, never the raw token. A process-local auth request limit is present; replace it with a proxy-aware Redis limit before public deployment.

Python tests can use Postgres by setting `GIGBID_TEST_DATABASE_URL` to a local test database. Each test creates and removes only its own random schema. Browser tests automatically start a disposable API/database alongside Next.js; they do not use the development database.

On Windows use `npm.cmd` if PowerShell blocks the npm script wrapper. Install uv if absent with `python -m pip install uv==0.9.6`; do not install project dependencies into a shared global environment.

To inspect MCP registration with the official Inspector, run from the repository root:

```powershell
npx @modelcontextprotocol/inspector uv run python -m mcp_servers.portfolio.server
```

Equivalent modules exist for Marketplace and Workspace. They currently register schemas and return not-implemented errors. Inspector screenshots are still required for submission. HTTP MCP deliberately refuses to start until bearer auth is implemented.

## Compose

Use `docker compose --project-directory . -f infra/docker-compose.yml up --build` from the repository root. The explicit project directory makes the build context the repository root. Docker Desktop must be running.

Default services: web, API, Arq worker, Postgres, Redis and Qdrant. The worker handles indexing and manual-job proposals. It starts a tenant-bound Portfolio MCP subprocess per run segment and calls native Ollama using `WORKER_OLLAMA_BASE_URL` (default `http://host.docker.internal:11434`). Pull the models in `agent/config.yaml` into native Ollama before running proposals.

For container inference, enable `--profile container-inference`, pull the configured models inside that service and set `WORKER_OLLAMA_BASE_URL=http://ollama:11434`. The host endpoint is `http://localhost:11435`. This optional CPU configuration has not been performance-tested or selected for deployment.

Jobs and review decisions are saved before queueing. Pending-run scans recover queued/running work. Worker ownership uses a Postgres advisory lock and fenced metadata updates. An approved local draft is one SQL transaction with source-revision checks and a unique artifact per run. This does not establish exactly-once external marketplace behavior. See ADR 0003 for crash boundaries and durable token reservations.

Review at `/studio/<run ID>` and follow redacted progress at `/runs/<run ID>`. A run marked `needs_attention` has a saved explanation; correct its evidence/input/services before starting a new run. Existing incomplete runs are not silently restarted with a fresh token budget.

Optional profile `gigsim` requires `GIGSIM_IMAGE` to identify the real supplied simulator image, with its actual configuration added after inspection. The placeholder image name is not a simulator implementation.

Profile `mcp-stdio` contains stdio MCP entry containers for inspection, not a functioning HTTP inter-service network. Complete bearer auth and Streamable HTTP hosting before making these default production services. Full R10/E6 Compose compliance is pending.

Do not run destructive volume resets when investigating failures. Postgres data must survive restarts.

## Future production acceptance

- Complete production auth controls and create a reviewer account; share its credentials privately.
- Use real secrets and encrypted OAuth tokens, tenant checks and log redaction.
- Give each run a trace ID across API, worker, graph, MCP and audit.
- Queue work while the marketplace is down; show the reason and recover without duplicate effects.
- Use conservative live polling. The provisional interval in config is not yet justified by actual rate limits.
- Declare cost and latency targets, measure p50/p95, and keep the deployment live through grading.
- Validate a crash while waiting for approval, a crash after authorization, and a crash during external execution.
