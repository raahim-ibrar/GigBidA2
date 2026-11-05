# Honest implementation status

## Working foundation

- Accounts support registration, sign-in, revocable/expiring database sessions, sign-out and CSRF checks. Passwords use Argon2 and session tokens are stored only as hashes.
- Profile settings are persisted by authenticated user ID; clients cannot select another user in a profile request.
- Sign-in, initial profile setup and settings forms work. Remaining product routes render implementation checklists.
- Portfolio PDF/Markdown/text uploads, tenant-scoped source storage, revisions and deletion work. Source IDs from an older revision cannot be retrieved after replacement.
- Redis/Arq background indexing writes open-model dense vectors to Qdrant. A durable deletion outbox and queued-upload reconciliation handle interrupted work.
- V0 dense, V1 per-requirement, V2 BM25L+dense RRF, V3 cross-encoder reranking and V8 corrective LangGraph retrieval are implemented. These are provisional components, not an evaluation-backed shipped choice.
- Alembic migrations target Postgres. Readiness checks database access and the accounts schema. A process-local auth rate limit exists; a distributed limit is still required before deployment.
- Pydantic contracts reject malformed writes and invalid approval decisions.
- Both graph topologies compile with an injected checkpointer. Deterministic test nodes exercise parallel fan-out/join, skip routing, Critic revision limits, compliance blocking and interrupt/resume.
- Portfolio MCP tools/resources work against the indexed corpus and bind tenant identity at server construction. Marketplace and Workspace implementations remain scaffolded; HTTP MCP is still disabled pending bearer auth.
- Memory promotion predicates and tenant namespace helper exist; persistence does not.
- uv and npm dependency locking, schema export, structural checks and CI entry points exist.

## Requirement coverage

| Area | Present | Still required |
| --- | --- | --- |
| A: MCP | SDK server scaffolds, tool schemas, read/write annotations, port, adapter stubs, allowlists, snapshot and in-memory registration tests | Tool implementations, auth, per-user limiting, durable idempotency, audit, OAuth encryption, GitHub ingestion, retries, Inspector screenshots, tool-granularity study |
| B: RAG | PDF/Markdown ingestion, metadata, source revisions, Qdrant dense index, five implemented variants, real-model runtime smoke tests | GitHub ingestion, bulk supplied-corpus mapping, claim entailment, graded metrics, calibrated judge, human panel, outcomes and ablations |
| C: Graphs | Typed state, Send fan-out/join, revision cap, interrupt gate, two graph builders | Agent logic, Postgres saver lifecycle, total step/token budgets, safe edit loop, write authorization, exactly-once integration, replay, fallback, dead-letter handling, both memories and comparisons |
| D: Web | Accounts and saved profile forms, remaining route shells, generated API types, browser account-flow and navigation tests | Portfolio upload and marketplace onboarding, evidence hover, editing, approval API, Kanban, messaging, SSE, analytics, memory management, five complete assignment E2E flows |
| E: Engineering | Arq entry point, Docker/Compose and CI scaffold | Saved-search schedules, end-to-end tracing, PII redaction, tenant isolation, injection experiments, eval gates, deployment and uptime |
| Portfolio/report | Documentation outlines and AI log | Real results, report, public package, write-up, video/GIF, public traces and résumé numbers |

## Build next, in order

1. Confirm the source of GigSim, persona corpora, policy pack, dev labels and the announced policy update. Creating our own skeleton does not establish that those separate assets are also student-authored.
2. Accounts, profiles, portfolio ingestion and retrieval are implemented. Add the real proposal-agent workflow next; connect GigSim only after its schemas are supplied.
3. Build one vertical slice: retrieve evidence for one job, produce typed analyses and verified draft, persist it, show it in the UI and pause with a Postgres interrupt.
4. Wire approve/reject/edit, edit re-verification, dry-run preview and an authorized executor. Prove recovery across crashes and concurrent retries with a database-backed idempotency ledger/outbox and upstream reconciliation.
5. Complete conversation flow, calendars, search schedules, memory promotion, degraded mode, budgets, logging and real streaming.
6. Run the required tool, model, retrieval and orchestration experiments. Store raw results before choosing the shipped configuration. Implement the selected extension.
7. Complete UI E2E tests, CI eval gates, deploy, collect real trace evidence, write the report and rehearse the viva.

## Deliberate restrictions

MCP HTTP transport is disabled until bearer authentication exists. Write tools cannot contact a provider. Edits at the skeleton interrupt become `needs_attention` instead of reusing an approval for the previous draft. No fallback returns fabricated jobs, evidence or benchmark results.

`make eval`, `make seed` and `make demo` deliberately fail until implemented. The five assignment E2E user flows are pending, not passing empty tests. No tests in this scaffold establish hidden-test readiness.
