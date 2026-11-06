# Development verification

Checked on 5 November 2026. These checks establish working behavior, not graded research results.

## Accounts and portfolio stage

- Full Python suite passed with Postgres plus the opt-in real-model tests enabled: 59 tests.
- Real runtime checks used the CPU BGE embedding model, MiniLM cross-encoder, Qdrant, Redis/Arq and a separate stdio MCP process. Test sources/accounts were development fixtures and were cleaned up.
- At that milestone, browser checks covered account/profile persistence, navigation and portfolio upload → search → deletion. Later proposal checks are recorded below.
- TypeScript checks, the frontend production build, Python lint, required-path checks and Compose configuration validation passed.
- The Linux worker and migration images built successfully and the worker started against the local Postgres/Redis/Qdrant services.
- A live API upload was indexed by the Docker worker, retrieved through the API and standalone MCP, then deleted. Its development account was removed; the user's account was untouched.

Run the automated runtime checks with `GIGBID_TEST_DATABASE_URL` pointing to a local test-capable Postgres database and `GIGBID_REAL_MODELS=1`, then `uv run pytest`. Each Python integration test owns a disposable schema. Browser tests own a disposable database and deterministic test models; they do not measure retrieval quality.

## Still unverified or unimplemented

No evidence yet establishes proposal-agent quality, calibrated claim entailment, marketplace interoperability/execution, memory learning, grading-set performance, live Upwork OAuth, production security or public deployment. The instructor's GigSim/corpora/policy/dev labels have not been supplied. No simulated reply/hire rates or research tables have been invented.

## Proposal-node development checks

- Full Python suite after adding bid business nodes: **76 passed, 1 skipped** with Postgres and real retrieval models enabled. The skipped test requires the separate `GIGBID_REAL_AGENTS=1` flag.
- That opt-in Ollama smoke passed separately against the configured `qwen3.5:4b` model, returning a valid Analyst handoff with measured input/output token counts. This is an API integration check, not a proposal-quality or model-comparison result.
- Deterministic proposal tests exercise the implemented nodes, manual-job identity binding, rate floors, rejection of invented evidence IDs, injected-instruction risk flags, sentence checks across cover/screening answers, unsupported numerical claims, stale sources, draft digests, fresh approval after edits and a host-injected local-save fixture.
- HTTP transport fixtures exercise structured schemas, usage accounting, concurrent reservations, resumed usage limits and bounded fallback. Durable accounting was added in the later worker stage below.
- The Portfolio MCP reader used by the new nodes passed against the real in-memory MCP protocol and tenant-scoped retrieval service. The full suite also retained its separate real stdio subprocess check.
- At this earlier node milestone, local saving was an injected fixture. The later checks below establish actual SQL execution and real inference separately; external marketplace execution remains unverified.

Run the local Analyst smoke with `GIGBID_REAL_AGENTS=1 uv run pytest tests/integration/test_agent_models.py -q` while Ollama and the configured model are available.

## Durable local-proposal stage

- **93 Python tests passed** with isolated Postgres schemas, `GIGBID_REAL_MODELS=1` and `GIGBID_REAL_AGENTS=1`. Coverage includes real standalone MCP evidence re-reads, durable pause/edit/resume, cancelled workers, stale interrupt commands, concurrent-worker exclusion, source invalidation, SQL token/step budgets, competing approvals and recovery after local commit but before checkpoint.
- **7 Chromium browser tests passed; 1 marketplace-outage flow remains pending.** Proposal tests exercise actual API/Postgres/saver paths with deterministic role/retrieval fixtures. They prove UI/control behavior, not LLM correctness.
- TypeScript checking and the production build passed with the new inbox, job detail, run list, proposal review/evidence hover and activity screens. Python lint, required paths, Compose config and diff checks passed.
- Rebuilt Linux worker/migration images started successfully. The worker reached the installed native Ollama through Docker's host endpoint.
- A disposable live API account uploaded a development source, which the Linux worker indexed. A manual job traversed real Ollama roles and the standalone Portfolio MCP, paused for a Postgres review, then resumed after an API approval and saved a local artifact. Its source vectors, graph checkpoints and account were cleaned up; the user's account was untouched.
- Real inference exposed omitted citation IDs even for supported exact excerpts. The prompt now requires IDs, and a strict fallback binds only exact normalized source substrings. Uncited paraphrases remain unsupported. Complete numerical tokens are checked rather than matching substrings such as `100` inside `1000`.
- The live smoke establishes connectivity/recovery mechanics only. Draft completeness, relevance, judge reliability, budgets and latency still need the required measured experiments. No marketplace proposal was submitted.

## Persistent memory stage

- On 6 November 2026, all 102 Python tests passed with Postgres, real retrieval models, and the local Ollama smoke enabled. The cold-start regression initialized both LangGraph schemas from four concurrent callers on a disposable schema.
- Eight Chromium tests passed. The memory flow recorded three edits, confirmed a preference, verified that a later run loaded it, and removed it. The marketplace-outage flow remains pending.
- Integration tests verified namespace isolation, event deduplication, promotion thresholds, and durable removal during a simulated store outage. Outcome tests used development fixtures for verified provider events. Live outcome ingestion awaits the marketplace adapter.
- TypeScript, the frontend production build, Python lint, and the required path check passed. The rebuilt worker and migration images started successfully. The local API reported ready and Settings returned HTTP 200.

## Local Workspace stage

- On 6 November 2026, the Python suite passed 106 tests with Postgres. Four opt-in real-model/runtime checks were skipped for this run. Seven Workspace integration cases cover preview parity, unchanged arguments and keys, stale approvals, calendar races, time zones, account isolation, and MCP execution.
- Nine Chromium tests passed, including availability entry, slot search, persistence after refresh, and removal. The marketplace-outage browser flow remains pending.
- The intentional Workspace MCP schema changes were reviewed and the snapshot test passed. Both write tools default to dry runs and expose idempotent local execution. The approval audit now preserves the complete reviewed preview, with nullable receipts for older records.
- TypeScript checking, the frontend production build and Python lint passed. The migration and worker images were rebuilt. Docker services were restarted after their stopped state caused an initial database timeout.
- Workspace uses the local backend allowed by A3. Client Liaison and conversation-graph integration remain unfinished. No email or marketplace message was sent during these checks.

## Manual conversation stage

- On 6 November 2026, 30 targeted Python tests passed against isolated Postgres schemas. These include seven conversation cases plus Workspace, durable bid runtime and graph regressions. Multiple incoming messages reuse one checkpoint thread; new messages fence in-flight work and invalidate pending approvals. Edits require fresh verification and approval. Calendar availability is checked again at commit, and message requests are idempotent and account scoped.
- Five Chromium tests passed: the new conversation flow and four proposal review regressions. The conversation check exercises manual intake, review, editing, approval, a second message, saved reply history and persistence after reload.
- Browser and conversation role responses are deterministic development fixtures. These checks establish control flow, persistence and local MCP execution, not Liaison model quality, simulator compatibility or benchmark performance. No email was sent.
- The Workspace schema snapshot now includes optional calendar slots on email drafts; its contract test and Python lint passed. The worker and migration images were rebuilt and started successfully. The public development database has migration 0006.
- The frontend production build includes the conversation list/detail screens. Dataset-dependent experiments and provider messaging remain pending. The user requested a stop after this feature.

## Run recovery and schedule configuration stage

- Work resumed at the user's request. On 6 November 2026, the full Postgres Python suite passed **119 tests**, with four opt-in real-model checks skipped. Recovery tests cover checkpoint resumption after a deterministic model outage, retained token/step charges and approval commands, three-retry exhaustion, concurrent/stale requests, CSRF, ownership and queue-outage persistence.
- **12 Chromium tests passed; one provider-outage recovery flow remains pending.** The new tests cover retrying a saved failed step through to review/approval and persistence of enabled/paused search settings. An initial run with eight browsers timed out on onboarding redirects; the complete rerun passed with two workers. Browser concurrency is now bounded in the checked-in configuration.
- Schedule checks use current profile queries, durable due times, and locked rows. Their state explicitly reports that the provider is unavailable. Tests verify pause/resume, stale settings and account isolation without creating fake jobs. After a final row-lock adjustment, all five recovery/schedule tests passed again.
- Python lint, the required 55 paths, diff checks, TypeScript and the frontend production build passed. Migration 0007 and the rebuilt worker started successfully. Actual scheduled marketplace reads, ingestion, live outage recovery and quality benchmarks still await the supplied provider assets.
