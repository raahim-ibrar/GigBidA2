# ADR 0001: Bootstrap choices

Status: accepted for the scaffold; quality-dependent choices remain provisional.

Use Python/FastAPI, Next.js App Router/TypeScript, hand-written LangGraph StateGraphs, official MCP Python SDK, Arq/Redis, Postgres and Qdrant. These fit the required stack and keep frontend, API, tool ownership and slow work separate.

Pin MCP SDK to the v1 release line because the selected langchain-mcp-adapters release requires MCP below v2. Pin TypeScript to v5 because the selected openapi-typescript release requires that major. Exact dependencies and transitive resolutions are recorded in pyproject.toml/uv.lock and package.json/package-lock.json.

Use local open-model candidates first. Hosted open models can serve the deployed profile after access/quota checks. No measured model or RAG choice has been made.
