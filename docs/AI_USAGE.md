# AI usage

| Date (PKT) | Tool | Work |
| --- | --- | --- |
| 2026-11-04 | Codex | Repository scaffold, Python contracts and graph builders, MCP registrations, Next.js route shells, Docker/CI scaffolding, documentation and scaffold tests |
| 2026-11-05 | Codex | Account/profile foundation: SQLAlchemy models, Alembic migration, Argon2 passwords, cookie sessions and CSRF, forms, generated API types, isolation/restart tests and browser account flow |
| 2026-11-05 | Codex | Portfolio source revisions and ingestion, Qdrant/FastEmbed retrieval variants, background indexing/outbox, tenant-bound MCP, portfolio UI and runtime/browser tests |
| 2026-11-05 | Codex | Bid business nodes, structured Ollama client, MCP reader capability, sentence verification, fresh approval after edits, token reservations and regression tests; one real Analyst inference smoke |
| 2026-11-05 | Codex | Postgres proposal runtime, manual-job/run/approval APIs, durable budgets, local artifact/audit transaction, SSE, inbox/review/activity UI, restart/concurrency/browser tests and a real local-model proposal smoke |

Files affected: apps/, agent/, rag/, mcp_servers/, worker/, evals/, tests/, scripts/, infra/, .github/, and root configuration/docs. Development drafts were generated from explicitly artificial test sources. No marketplace submissions, grading experiments or outcome data were generated.

Errors caught during scaffold generation: the initial frontend dependency selection used TypeScript 7, but the API type generator required TypeScript 5. The install rejected the incompatible dependency tree; TypeScript was pinned to a compatible release instead of forcing the install. An initial command also referenced the test interpreter from the wrong relative directory and was corrected.

Portfolio validation also caught an omitted API router registration and a Windows stdio startup stall when NumPy was imported inside the first MCP request. Integration tests caught the route issue; a live subprocess stack identified the late numerical-runtime import. Startup order and bounded MCP session timeouts were added, and the complete standalone retrieval path was then verified.

This records errors detected during assisted work. The student should review the implementation and add their own independently caught issues; do not claim to have reviewed code that has not been understood.

Durable proposal checks caught LangGraph's node-cancellation wrapper, stale resume commands at a newer interrupt, browser selectors targeting hidden source text and the Next.js alert announcer, and a stale OpenAPI assertion. A real-model run then exposed omitted citation IDs and punctuation-only screening-key differences. These were corrected with bounded recovery, ID-bound resumes, precise selectors and strict source/text normalization, followed by automated and real-runtime rechecks.
