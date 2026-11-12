# GigBid Portfolio MCP

Read-only tools using the official MCP Python SDK, backed by indexed portfolio sources, open embeddings and Qdrant. No marketplace access is required.

From the installed repository:

```powershell
$env:GIGBID_TENANT_ID = "your GigBid account ID"
uv run python -m mcp_servers.portfolio.server
```

Transport is stdio. Tools: search_evidence, get_case_study, list_skills. Resource templates: portfolio://case/{id}, portfolio://proposal/{id}. Prompt: answer_screening_question.

Upload and index documents through GigBid first. `search_evidence` returns source chunk IDs, document IDs, provenance and metadata. `get_case_study` loads an indexed source or chunk; `list_skills` lists indexed skills. `request.variant` selects V0/V1/V2/V3/V8 for development comparisons. The tenant is never a tool argument, and sources from other accounts cannot be retrieved.

The temporary published Streamable HTTP endpoint is
`https://interpreted-vid-recovered-estimation.trycloudflare.com/mcp`.
It serves the isolated fictional AI demo portfolio. Authentication uses a random bearer
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
