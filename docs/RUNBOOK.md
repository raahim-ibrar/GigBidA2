# Runbook

Stage: account/profile foundation; no public deployment exists.

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

Default services: web, API, Arq worker, Postgres, Redis, Qdrant and Ollama. Worker jobs are unimplemented. Ollama starts without downloading models. Default container tags are pinned bootstrap versions; review supported tags and security updates before public deployment.

Optional profile `gigsim` requires `GIGSIM_IMAGE` to identify the real supplied simulator image, with its actual configuration added after inspection. The placeholder image name is not a simulator implementation.

Profile `mcp-stdio` contains stdio MCP entry containers for inspection, not a functioning HTTP inter-service network. Complete bearer auth and Streamable HTTP hosting before making these default production services. Full R10/E6 Compose compliance is pending.

Do not run destructive volume resets when investigating failures. Postgres data must survive restarts.

## Future production acceptance

- Implement auth and seed a reviewer account; share its credentials privately.
- Use real secrets and encrypted OAuth tokens, tenant checks and log redaction.
- Give each run a trace ID across API, worker, graph, MCP and audit.
- Queue work while the marketplace is down; show the reason and recover without duplicate effects.
- Use conservative live polling. The provisional interval in config is not yet justified by actual rate limits.
- Declare cost and latency targets, measure p50/p95, and keep the deployment live through grading.
- Validate a crash while waiting for approval, a crash after authorization, and a crash during external execution.
