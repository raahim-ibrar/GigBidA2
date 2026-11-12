# AI usage

| Date (PKT) | Tool | Work |
| --- | --- | --- |
| 2026-11-04 | Codex | Repository scaffold, Python contracts and graph builders, MCP registrations, Next.js route shells, Docker/CI scaffolding, documentation and scaffold tests |
| 2026-11-05 | Codex | Account/profile foundation: SQLAlchemy models, Alembic migration, Argon2 passwords, cookie sessions and CSRF, forms, generated API types, isolation/restart tests and browser account flow |
| 2026-11-05 | Codex | Portfolio source revisions and ingestion, Qdrant/FastEmbed retrieval variants, background indexing/outbox, tenant-bound MCP, portfolio UI and runtime/browser tests |
| 2026-11-05 | Codex | Bid business nodes, structured Ollama client, MCP reader capability, sentence verification, fresh approval after edits, token reservations and regression tests; one real Analyst inference smoke |
| 2026-11-05 | Codex | Postgres proposal runtime, manual-job/run/approval APIs, durable budgets, local artifact/audit transaction, SSE, inbox/review/activity UI, restart/concurrency/browser tests and a real local-model proposal smoke |
| 2026-11-05 | Codex | Private edit diffs, deterministic style candidates, explicit promotion rules, tenant-scoped LangGraph memory, trusted provider-outcome hook, removal ledger, Settings controls and memory integration tests |
| 2026-11-06 | Codex | Local Workspace MCP calendar/draft tools, complete approval-preview receipts, idempotent action audit, concurrent hold checks, calendar Settings and browser/integration verification |
| 2026-11-06 | Codex | Durable manual conversations, Liaison intent/reply nodes, calendar options, fenced new-message intake, reviewed local email drafts, conversation screens and persistence tests |
| 2026-11-06 | Codex | Bounded explicit checkpoint retries, exhausted-run visibility, saved-search schedule settings and prerequisite worker checks; provider polling remains unavailable |
| 2026-11-08 | Codex | Tenant-scoped pipeline and analytics, adapter-only lifecycle receipts, missing-measurement handling, desktop/phone checks, recorded-input evaluation metrics and gates, comparison scorers, and X2 assignment/statistics tooling; no actual grading experiments generated |
| 2026-11-08 | Codex | Budgeted paragraph-only regeneration, full re-verification and fresh review, preservation of paragraph formatting/citations, compiled graph diagrams and updated architecture/walkthrough documentation |

Files affected: apps/, agent/, rag/, mcp_servers/, worker/, evals/, tests/, scripts/, infra/, .github/, and root configuration/docs. Development drafts were generated from explicitly artificial test sources. No marketplace submissions, grading experiments or outcome data were generated.

Errors caught during scaffold generation: the initial frontend dependency selection used TypeScript 7, but the API type generator required TypeScript 5. The install rejected the incompatible dependency tree; TypeScript was pinned to a compatible release instead of forcing the install. An initial command also referenced the test interpreter from the wrong relative directory and was corrected.

Portfolio validation also caught an omitted API router registration and a Windows stdio startup stall when NumPy was imported inside the first MCP request. Integration tests caught the route issue; a live subprocess stack identified the late numerical-runtime import. Startup order and bounded MCP session timeouts were added, and the complete standalone retrieval path was then verified.

This records errors detected during assisted work. The student should review the implementation and add their own independently caught issues; do not claim to have reviewed code that has not been understood.

Durable proposal checks caught LangGraph's node-cancellation wrapper, stale resume commands at a newer interrupt, browser selectors targeting hidden source text and the Next.js alert announcer, and a stale OpenAPI assertion. A real-model run then exposed omitted citation IDs and punctuation-only screening-key differences. These were corrected with bounded recovery, ID-bound resumes, precise selectors and strict source/text normalization, followed by automated and real-runtime rechecks.

Memory tests caught a concurrent-index setup wait on the authenticated request's own
transaction. Store setup was moved to application/worker initialization and bounded
with timeouts. The blocked connection belonged to a disposable test schema; only that
test session was released. SQLite verification also exposed lost timezone information
on an idempotent draft response; that read contract now normalizes timestamps to UTC.

| 2026-11-11 | Codex | Student-built simulator, approval-gated Marketplace MCP, event/message reconciliation, scheduled imports, dark purple frontend, approved Kaggle preprocessing, fictional persona generator, controlled retrieval experiments, model-study runner, regression tests and documentation. Model failures and missing human/external evidence are retained. |

## November 11-12 research completion

Codex prepared calibration and blinded panel packets, implemented and repaired the real orchestration baselines and optional Gemini transport, ran the recorded studies, and calculated agreement and intention-to-treat outcomes. Raahim supplied 30 calibration ratings and reported two classmate responses. The second classmate response was reconstructed from the user-stated final-choice difference; reviewer identity/independence was not verified. No AI-generated rating is represented as human. Earlier statements about no generated research apply to their dated development checkpoints, not these later explicitly labelled synthetic experiments. Failed API/output-format pilots remain separate. Codex drafted the final report and technical narrative from saved measurements.

## November 12 Upwork integration

Codex implemented the local OAuth helper, encrypted per-user storage, provider routing, verified MCP mappings, draft-only approval ledger, UI, tests and documentation. Raahim completed the real Upwork browser login and authorization himself. Actual verification used account discovery and read-only public job/balance requests, with no model inference, live proposal preparation, submission or message send. Provider-write behavior was tested only with synthetic fixtures. Raw account data and credentials were excluded from published evidence.
