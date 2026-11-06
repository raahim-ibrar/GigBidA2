# Honest implementation status

## Working foundation

- Accounts support registration, sign-in, revocable/expiring database sessions, sign-out and CSRF checks. Passwords use Argon2 and session tokens are stored only as hashes.
- Profile settings are persisted by authenticated user ID; clients cannot select another user in a profile request.
- Sign-in, profiles, portfolio, manual-job inbox/detail, proposal review, manual client conversations and run activity work. Pipeline and analytics remain unfinished.
- Portfolio PDF/Markdown/text uploads, tenant-scoped source storage, revisions and deletion work. Source IDs from an older revision cannot be retrieved after replacement.
- Redis/Arq background indexing writes open-model dense vectors to Qdrant. A durable deletion outbox and queued-upload reconciliation handle interrupted work.
- V0 dense, V1 per-requirement, V2 BM25L+dense RRF, V3 cross-encoder reranking and V8 corrective LangGraph retrieval are implemented. These are provisional components, not an evaluation-backed shipped choice.
- Alembic migrations target Postgres. Readiness checks database access and the accounts schema. A process-local auth rate limit exists; a distributed limit is still required before deployment.
- Pydantic contracts reject malformed writes and invalid approval decisions.
- Both graph topologies compile with an injected checkpointer. Deterministic test nodes exercise parallel fan-out/join, skip routing, Critic revision limits, compliance blocking and interrupt/resume.
- Bid business nodes support manual jobs, typed analyses, provisional pricing, open-model drafts, cover/screening verification, Critic revisions and local-save previews. The API, Redis/Linux worker, tenant-bound MCP and review UI are connected; a real-model development run reached review and an approved local save.
- Postgres checkpoints survive recreated runtimes. Review decisions bind run version, draft digest and interrupt ID. Stale decisions, duplicate workers and unsupported/stale evidence are blocked. Local commits are idempotent and recoverable after execute-checkpoint loss; external writes remain disabled.
- Token reservations and node-attempt budgets are persisted in SQL. The Ollama client validates structured output, records actual usage and bounds fallback by role. An unknown failed-call reservation remains charged conservatively. Model quality and thresholds have not been calibrated.
- Run progress uses persisted redacted events and reconnectable SSE. Queue-outage recovery scans saved pending runs; terminal attention states show safe failures rather than fabricated results.
- Recoverable model/connection failures support three explicit retries from the saved checkpoint. Run versions reject stale or duplicate requests, and retries preserve token/step budgets and exact approval commands. Exhausted runs remain visible in the attention filter. Policy, evidence and budget failures require correction rather than a retry.
- Saved-search schedule settings persist an interval and enabled/paused state per account. Worker ticks record prerequisite checks against the current saved queries. They report the absent marketplace adapter; provider polling and result ingestion remain pending, and no search results are fabricated.
- Portfolio MCP tools/resources work against the indexed corpus. Workspace MCP provides user-declared local availability, tentative holds and email drafts with exact approval checks and an idempotent audit ledger. Both servers bind identity at construction. Marketplace remains scaffolded; HTTP MCP awaits bearer auth.
- Manual conversations use one Postgres-checkpointed graph thread per conversation. Liaison classifies intent and drafts portfolio-grounded replies; interview options come from Workspace MCP. Edits require verification and fresh approval before saving a local email draft. New messages invalidate pending reviews and fence in-flight work; cumulative run budgets remain in force. Provider message ingestion/sending and reply-quality evaluation remain pending.
- Long-term memory uses separate tenant-scoped style/outcome namespaces in the Postgres LangGraph store. Actual draft edits are diffed and saved; a pattern needs three distinct drafts and explicit confirmation before promotion. Outcome memory requires verified provider events on three distinct jobs; the trusted adapter hook is implemented, but no real provider is connected. Settings supports inspection/removal, and new proposal runs load only active promoted values.
- uv and npm dependency locking, schema export, structural checks and CI entry points exist.

## Requirement coverage

| Area | Present | Still required |
| --- | --- | --- |
| A: MCP | SDK server scaffolds, tool schemas, read/write annotations, port, adapter stubs, allowlists, snapshot and in-memory registration tests | Tool implementations, auth, per-user limiting, durable idempotency, audit, OAuth encryption, GitHub ingestion, retries, Inspector screenshots, tool-granularity study |
| B: RAG | PDF/Markdown ingestion, metadata, source revisions, Qdrant dense index, five implemented variants, real-model runtime smoke tests | GitHub ingestion, bulk supplied-corpus mapping, claim entailment, graded metrics, calibrated judge, human panel, outcomes and ablations |
| C: Graphs | Bid and manual-conversation nodes, real Postgres saver, parallel join, verification, bounded revisions/fallback, durable budgets, ID-bound edit/review loop, fenced local commits, bounded explicit retries and exhausted-run UI, edit diffs, promoted style/outcome stores | Provider execution/reconciliation, live outcome ingestion, orchestration/memory experiments |
| D: Web | Accounts, profile/portfolio, manual jobs/conversations, proposal/reply review and editing, evidence hover, calendar settings, run activity/SSE, memory management, generated API types and browser checks | Marketplace onboarding/outage recovery, Kanban, provider messaging, analytics and full provider-backed assignment flows |
| E: Engineering | Arq indexing/graph workers, reconciliation, saved-search scheduling configuration/prerequisite checks, Docker/Compose and CI scaffold | Real scheduled marketplace polling/ingestion, end-to-end tracing, PII redaction, tenant isolation, injection experiments, eval gates, deployment and uptime |
| Portfolio/report | Documentation outlines and AI log | Real results, report, public package, write-up, video/GIF, public traces and résumé numbers |

## Build next, in order

1. Confirm the source of GigSim, persona corpora, policy pack, dev labels and the announced policy update. Creating our own skeleton does not establish that those separate assets are also student-authored.
2. The manual-job vertical slice now works through real inference, MCP, persistent review and a local artifact. Improve proposal quality with measured development checks; do not mistake a smoke pass for evaluation-backed correctness.
3. Complete real scheduled search execution once the marketplace contract is supplied. Scheduling controls and bounded retry/exhausted-run handling are present. The manual conversation flow uses Workspace calendar options and approved local email drafts. Memory learning and provider-derived observations need measurement/integration.
4. Connect GigSim only after inspecting its supplied schemas. Extend human authorization and durable idempotency to real provider effects with upstream reconciliation.
5. Complete degraded marketplace mode, production auth/rate limiting, tracing and remaining product screens.
6. Run the required tool, model, retrieval and orchestration experiments. Store raw results before choosing the shipped configuration. Implement the selected extension.
7. Complete UI E2E tests, CI eval gates, deploy, collect real trace evidence, write the report and rehearse the viva.

## Deliberate restrictions

MCP HTTP transport is disabled until bearer authentication exists. Marketplace write tools cannot contact a provider. Bid edits require verification, local compliance and fresh approval; a failed critique of a user's edit stops for attention instead of silently rewriting it. Local-save authorization is implemented as one SQL transaction; it does not establish provider idempotency. No fallback returns fabricated jobs, evidence or benchmark results.

`make eval`, `make seed` and `make demo` deliberately fail until implemented. One marketplace-outage browser flow remains explicitly pending. Existing browser tests use deterministic role/retrieval fixtures, and none establishes model quality or hidden-test readiness.
