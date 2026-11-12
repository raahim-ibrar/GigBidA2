# GigBid Portfolio MCP

Read-only tools using the official MCP Python SDK, backed by indexed portfolio sources, open embeddings and Qdrant. No marketplace access is required.

## Install from the public repository

The project exposes the `gigbid-portfolio` console command. A PyPI release is not
required; install the reviewed public revision with uvx:

```text
uvx --from git+https://github.com/raahim-ibrar/GigBidA2.git@c498e6562d321965e2429e41c770c93323128bcf gigbid-portfolio
```

That revision contains the same Portfolio MCP package surface verified below. Set
`GIGBID_TENANT_ID`, `DATABASE_URL`, `QDRANT_URL` and `MODEL_CACHE_DIR` in the MCP
client's private environment. PostgreSQL/Qdrant and indexed documents must already
exist; the command does not provision a database or manufacture portfolio evidence.
Models are downloaded on first retrieval if not cached. These are CPU models.

Alternatively build the standalone server image from this public checkout:

```text
docker build -f infra/docker/portfolio.Dockerfile -t gigbid-portfolio .
docker run --rm -i --env-file portfolio.private.env gigbid-portfolio
```

Keep `portfolio.private.env` private. Docker connections to host services use
`host.docker.internal` rather than container-local `127.0.0.1`. Protocol discovery
does not require model inference. The installed console entrypoint was verified in
a clean disposable Linux container: [evidence](../../evals/results/portfolio-install-verification.json).

From an already installed repository:

```powershell
$env:GIGBID_TENANT_ID = "your GigBid account ID"
uv run python -m mcp_servers.portfolio.server
```

Transport is stdio. Tools: search_evidence, get_case_study, list_skills. Resource templates: portfolio://case/{id}, portfolio://proposal/{id}. Prompt: answer_screening_question.

Upload and index documents through GigBid first. `search_evidence` returns source chunk IDs, document IDs, provenance and metadata. `get_case_study` loads an indexed source or chunk; `list_skills` lists indexed skills. `request.variant` selects V0/V1/V2/V3/V8 for development comparisons. The tenant is never a tool argument, and sources from other accounts cannot be retrieved.

## Optional HTTP demo

The temporary Streamable HTTP publication was verified previously and is currently off.
Its old tunnel URL is not a permanent endpoint. When started, it serves only the
isolated fictional AI demo portfolio. Authentication uses a random bearer
token, held privately in `work/public-demo/MCP-CONNECTION.json`; ask the operator for
access rather than putting that token in a public submission. Requests are limited to
60 per account per minute and fail closed if Redis is unavailable. JSON responses and
stateless sessions support the temporary tunnel. The three tools remain read-only;
the host binds the account, and clients cannot choose a tenant in arguments.

Run your own HTTP instance with `GIGBID_TENANT_ID`, `WEB_ORIGIN`,
`MCP_BEARER_TOKEN` (random, at least 32 characters), database/Redis/Qdrant settings,
and `uv run uvicorn mcp_servers.http:configured_app --factory --host 127.0.0.1 --port 8104`.
The supervisor and frontend proxy expose this during the demo. The URL changes when
the tunnel restarts; stdio remains available independently. This is an HTTP publication,
not a PyPI/package-registry release. Live protocol evidence is in
`evals/results/public-integrations.json`.

## MCP Inspector

Actual stdio discovery screenshots are in
[Portfolio](../../docs/images/mcp-inspector-portfolio.png),
[Marketplace](../../docs/images/mcp-inspector-marketplace.png) and
[Workspace](../../docs/images/mcp-inspector-workspace.png). They use Inspector 1.0.5
(the supported legacy line compatible with the installed Node version) and the
official Python MCP SDK 1.30.0. No write tools were executed for these screenshots.
