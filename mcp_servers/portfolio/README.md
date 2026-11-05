# GigBid Portfolio MCP

Read-only tools using the official MCP Python SDK, backed by indexed portfolio sources, open embeddings and Qdrant. No marketplace access is required.

From the installed repository:

```powershell
$env:GIGBID_TENANT_ID = "your GigBid account ID"
uv run python -m mcp_servers.portfolio.server
```

Transport is stdio. Tools: search_evidence, get_case_study, list_skills. Resource templates: portfolio://case/{id}, portfolio://proposal/{id}. Prompt: answer_screening_question.

Upload and index documents through GigBid first. `search_evidence` returns source chunk IDs, document IDs, provenance and metadata. `get_case_study` loads an indexed source or chunk; `list_skills` lists indexed skills. `request.variant` selects V0/V1/V2/V3/V8 for development comparisons. The tenant is never a tool argument, and sources from other accounts cannot be retrieved.

This repository-local server is not independently published yet. Public package/image publication and Inspector screenshots remain assignment deliverables. Treat the stdio host as trusted; do not expose it over HTTP without authentication.
