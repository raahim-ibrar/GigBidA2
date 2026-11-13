# Development verification

Checked on 5 November 2026. These checks establish working behavior, not graded research results.

## Accounts and portfolio stage

- Full Python suite passed with Postgres plus the opt-in real-model tests enabled: 59 tests.
- Real runtime checks used the CPU BGE embedding model, MiniLM cross-encoder, Qdrant, Redis/Arq and a separate stdio MCP process. Test sources/accounts were development fixtures and were cleaned up.
- At that milestone, browser checks covered account/profile persistence, navigation and portfolio upload â†’ search â†’ deletion. Later proposal checks are recorded below.
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

## Dashboard, evaluation tooling and paragraph regeneration stage

- On 8 November 2026, the final Python regression run passed **137 tests**, with four optional real-model checks skipped. **14 Chromium flows passed**, with the provider-outage recovery flow still explicitly pending. The production frontend build, Python lint/format, required paths and compiled-diagram checks passed.
- New database tests cover local pipeline cards, adapter-only provider receipts, duplicate/conflicting events, out-of-order stage updates, missing submission denominators, known versus unknown spend, measured call usage, exclusion of human review wait, rejection-reason privacy and cohort/account isolation. Provider receipts in tests are fixtures, not real outcomes.
- Offline scoring/gate tests cover exact cohort alignment, invalid/duplicate records, undefined metrics, incomplete claim annotations, known confusion/ranking/kappa results, input overwrite prevention, development provenance, fixed-window outcomes and failed quality gates. Comparison tests verify aligned tasks and unknown usage handling. X2 tests check order-independent stratified assignments, a known Fisher table and incomplete follow-up rejection. These are implementation checks, not assignment research results.
- Paragraph regeneration runs through the durable graph and requires a fresh interrupt/approval. Tests verify that other paragraphs remain unchanged, completed analysis is not repeated, invalid selections are rejected, conversation runs cannot request proposal regeneration, and nothing is saved before the new approval. Verification now preserves original formatting when all text is supported; evidence hover works within multi-sentence paragraphs.
- Initial regeneration tests exposed flattened paragraph breaks and fixtures missing the new node/approval fields. Those were corrected. A concurrent Python/browser run also hit bounded database setup/memory synchronization failures; failed cases and the complete Python suite passed when run without concurrent browser schema setup. CI uses separate service databases for its Python and browser jobs.
- Desktop and phone analytics screenshots were inspected. The first phone check caught page overflow; setting minimum grid-child widths corrected it, and the phone-width assertion then passed. Graph Mermaid files are generated from the actual compiled builders and checked for staleness in CI.
- Connected Drive searches for GigSim, GigBid and AI-4016 returned no matches. No supplied starter kit was found among matching Downloads filenames. Real provider integration, research experiments, trace export and deployment remain outstanding; this stage does not establish model quality or hidden-test readiness.
- The API, frontend and updated Docker worker were restored. Native Ollama was stopped and restarted; all three configured models were present. A separate development-only paragraph response passed the real `qwen3:8b` structured schema check. This checks local inference/format connectivity, not grounding quality, A/B performance or a graded result.

## November 11, 2026 verification checkpoint

- Full current backend regression: **149 passed, 4 opt-in skipped**, in 151.38 seconds,
  using isolated Postgres schemas. This includes simulator MCP effects, duplicate spending
  prevention, full proposal/client-reply flow, durable LLM-client outbox, scheduler dedup and
  outage handling, bearer boundary checks, and trusted UUID versus numerical-claim checks.
- Frontend production build and TypeScript completed successfully after the dark redesign.
  Screenshot checks at 1440px and 390px found no horizontal overflow.
- Browser regression: 14 existing flows passed; the new simulator flow initially failed
  because its assertion used the proposal heading on a reply screen. Correcting that selector
  produced a separate passing outage/retry/submission/client-reply/send check (43.1 seconds).
- The retrieval study executed all five production variants on real BGE/MiniLM models.
  It is a controlled synthetic-corpus experiment, not a fixture test or real-job gold set.
- Model experiments are ongoing and include grounding failures. A passing regression suite
  does not establish that the selected LLM reliably writes acceptable proposals.

## November 11 follow-up regression and Settings layout

- Full Postgres-backed Python suite: **156 passed, 4 optional checks skipped**, in 151.16 seconds.
- Full Chromium browser suite: **15 passed**, reported duration 1.4 minutes. This includes the simulator outage/retry/submission/client-reply flow.
- Python lint, TypeScript, required scaffold paths and the rebuilt production frontend passed.
- Settings now uses an explicit 24px grid gap and consistent section widths. Chromium measurements and screenshot inspection covered signed-out desktop, signed-in desktop (1440px) and signed-in phone (390px), with no page overflow.
- The resumed native-tool research study remains separate from these regression tests; partial calls are not reported as a completed experiment.

## Site-wide spacing review

- Reviewed all 14 page routes at 1440px and 390px (28 screenshots), including job, proposal studio, run activity and conversation detail. Detail layouts used explicit read-only fictional browser fixtures; no proposals or approvals were created.
- Added shared page/section spacing, padded proposal navigation, content-height analysis cards, compact analytics controls and consistent card trailing spacing. Measurements found no horizontal page overflow or unexpected gaps in the page/section stacks.
- Production build passed. Screenshot contact sheets and individual views were inspected; the full browser regression passed again after these shared layout edits: **15 passed**, reported duration 1.3 minutes.

## Live CSV proposal recovery

- A user-authorized live hosted-model check exposed an overly strict job-fit policy: relevant skills were treated as insufficient without an identical past task. Updated matching, writing and critique guidance to distinguish future capability from factual past-work claims. A basic CSV case gained evidence coverage; a specialist-platform negative control remained unsupported.
- The first full attempt then exposed critic revision and local API allowance exhaustion. Those failed attempts were retained. The internal shared application allowance is now configurable (default 200000 per model/day), and quota exhaustion is classified as a retryable service outage; graph token/step caps were preserved.
- A fresh run on the same user job completed through the normal queue, Docker worker, MCP, real Groq inference, claim verification, critic, compliance and preview, reaching **awaiting approval** in 11 steps with 9888 charged tokens. All retained claims passed the host verification predicate, a review payload existed, and no approval was granted. This manually entered job previews a local draft save, not an external submission.
- Focused model transport, quota and proposal regressions: **30 passed**. These development checks do not replace the frozen model-comparison baseline or establish general proposal quality. Private CV text, evidence IDs and draft content are excluded from public research artifacts.

## Orchestration pilot repair

- ReAct, the real langgraph-supervisor baseline, and the production hand-built graph each completed the same separate fictional pilot job with GPT-OSS 120B and no runtime error. The application graph reached its approval interrupt without a fabricated approval; candidate scoring used only the isolated research simulator.
- Five focused control regressions verify termination, tool-call mode, shared budgets and narrow tool-name normalization. The related provider/model regressions also passed; see work/pilot-final-tests.log for the combined run.
- Raw pilot records, the plan and as-run source snapshots are saved under evals/results/pilot-validation-v1. This one-job check is not the required fifty-job study. The 150-run comparison was not started.

## November 12 final research verification

- Gemini optional architecture study: 150/150 cases across fifty matched jobs, 102 error-free and 48 failures; frozen source snapshot hashes verified. No additional GPU runs.
- Independent Nvidia proposal judge: all 103 available drafts have exact validated claim indices; accepted labels are never replaced based on score. Earlier invalid-format and unavailable-model attempts remain separate. Calibration has 30 actual human labels, support kappa 0.402985 and quality weighted kappa 0.681128.
- Statistics/human review/Gemini provider targeted regressions: **11 passed**, 2.48 seconds (`work/final-research-tests.log`). Earlier Gemini/Groq/real graph control regressions: **12 passed**, four dependency deprecation warnings.
- Final analysis asserts the exact 150 unique job-condition keys and validates every judge item and claim index. The A/B analysis retains all 50 assigned hand-graph jobs and reports the null-compatible result.
- R&D report is ten A4 pages. Technical narrative is within the required 1,200-1,800-word range. PDFs were rendered and visually inspected; detailed final artifact verification is saved in `evals/results/final-artifact-verification.json`.

## Public laptop-backed demo, November 12

- Public HTTPS sign-in, Secure cookies, synthetic portfolio uploads and real CPU indexing verified. Three fictional accounts were seeded in a separate database schema.
- Actual Groq custom-graph Document Search proposal reached awaiting approval in 11 steps with 13,717 charged tokens; no approval was granted. Two real negative controls skipped scam and injection requests with risk 1.0.
- JSON activity replay preserves cursor and tenant isolation when the tunnel cannot stream SSE; eight run integration tests passed. Full backend suite: **171 passed, five optional skipped**, 145.61 seconds. Whole-project Ruff, structure and graph checks passed.
- The production demo frontend build passed, and the public sign-in page opened in the browser. Secrets/private login files remain Git-ignored; the public source secret scan passed.
- This is temporary laptop hosting, not an always-on cloud deployment. Current URL and evidence: `evals/results/demo-deployment.json`.

## Public integrations and injection comparison, November 12

- Updated PostgreSQL regression suite: **176 passed, five optional skipped**, 152.02 seconds. Two additional export retry/idempotency/isolation checks passed. Full Chromium suite: **15 passed**, 1.3 minutes. Production frontend and Linux worker builds passed; Ruff passed.
- Real GitHub official read-only MCP imported this public repository's README at commit `cd3352cc91825c9f2910592bbf0b8fc93bdf3a0f`; its portfolio source reached ready status. Public authenticated Portfolio MCP listed three tools, two resource templates and one prompt; skills and evidence searches succeeded. Missing bearer authentication returned 401.
- Three new synthetic workflows produced public LangSmith traces with actual node, LLM and MCP spans. The proposal reached awaiting approval in 11 steps with 12,305 tokens; scam and injection controls skipped. All three share links were read without credentials. Source text and secrets were excluded.
- The 56-call paired injection-boundary comparison completed. Before 3/18 and after 4/18 evaluable attacks disclosed their assigned fake markers/nonces; six model errors per arm are reported separately. Sixteen fully observed pairs had no discordant outcomes, exact p=1.0. This component ablation does not demonstrate an improvement or measure end-to-end approval bypass.
- Known measured usage: 57,691 tokens; usage for twelve failed calls is unknown. No GPU inference or new 150-run study was performed.

## Real Upwork integration, November 12

- The operator completed real OAuth/PKCE in a browser against the official Upwork MCP server. Thirty-three tools were discovered. Account selection, public job search/detail, Connects-balance schema and one real job import through the application adapter passed. Credentials, organization identifiers, account balance and raw responses remain private. Sanitized evidence: `evals/results/upwork-live-verification.json`.
- Encrypted storage, tenant/generation binding, PKCE exchange, persisted-expiry refresh, disconnect fencing, schema changes, provider switching, exact approval, send-once preparation and uncertain-response recovery are covered by synthetic fixtures. Final backend suite: **193 passed, four optional skipped**, 172.89 seconds. An earlier run had one durable-interrupt failure; its seven-test group and the final complete suite subsequently passed. Original failed-run diagnostics are retained in ignored `work` logs.
- The existing Chromium suite passed **15 flows**; the added Upwork UI flow passed separately, including CSRF disconnect and pending-preview labels. TypeScript, production frontend build, Linux worker build and Ruff passed. No live write was performed; final submissions/direct messages are disabled, and provider-preview preparation is fixture-tested only.
- The report remains ten pages and the technical narrative remains within 1,200–1,800 words. Updated pages were rendered and inspected. A publication scan checked exact configured provider keys, OAuth tokens, encryption keys and the organization identifier; none appeared in publication files.
- Public demo services remain stopped. Only local data services were started for migration and tests; no GPU/model inference was used for this integration.


## Completion checks, November 12

- Latest complete backend run: **214 passed, five optional skipped**, 175.68 seconds. Full Chromium suite: **17 passed**, including a replay fork that requires fresh approval and leaves the original run intact. TypeScript, production build, Ruff, required paths and rendered graph checks passed. Evidence: `evals/results/engineering-verification.json`.
- Fresh 30-job deterministic CI control: 27 simulator submissions/replies and three skips; retrieval/decision/claim/reply gates passed. No model API calls or GPU inference. These easy control fixtures do not measure prompt quality. Evidence: `evals/results/ci-control-30/`.
- Official GitHub MCP imported and indexed `agent/graphs/bid_graph.py` at a pinned public commit. Personal CV and account data were unchanged. The installed Portfolio console command was initialized in a clean Linux container; Inspector captured actual tool listings for all three servers. Evidence: `github-source-verification.json`, `portfolio-install-verification.json`, `mcp-inspector-verification.json` under `evals/results/`.
- A genuine three-minute browser recording and 30-second excerpt GIF cover real hosted-model demo runs with fictional evidence/clients. The recording API was actually killed and restarted while approval was pending. One UI approval produced one application receipt and exactly one simulator proposal; a simulator client reply was reviewed and sent. Evidence: `demo-recording.json`, `crash-resume-verification.json`, and `public-traces.json` under `evals/results/`.
- Trace exports now use immutable snapshots per audit cursor, retaining the application correlation ID in metadata. This avoids closed-span repeat-update conflicts; SDK mutation cannot corrupt the JSON audit commit. New public snapshots cover the approved proposal/crash recovery and an existing real-model two-pass Critic loop. No private source text or credentials are shared.
- The technical article is publicly accessible through GitHub Pages. Recording and Inspector services were stopped after use; the public app/tunnel remains off. The instructor policy-update details and hidden-test outcomes remain unavailable.


## Evaluation fidelity correction, November 13

Only the evaluation-fidelity item was changed. The frozen 150 architecture runs and
18 V0/V3 runs were preserved. Ninety-two previously submitted synthetic proposals
received actual LLM-client decisions in 12 requests; no agent or GPU inference was rerun.
The actual simulator LLM-mode outbox and existing eligibility/budget guards produced
new effective outcomes. Public-source provenance was checked before external calls;
no personal CV/evidence bodies or credentials were included in the payload.

The primary B5 table now joins retrieval, draft and outcome metrics on the same nine
jobs per variant and original source corpus. Retrieval was replayed on CPU with declared
synthetic relevance annotations, not substituted from the earlier 60-task cohort.
Three focused integrity/privacy tests passed; Ruff passed. New primary tables and X2
analysis are in `evals/results/evaluation-fidelity-v1/summary.json`. Historical controls
remain labelled and available, rather than overwritten.
