# Development verification

Checked on 5 November 2026. These checks establish working behavior, not graded research results.

## Accounts and portfolio stage

- Full Python suite passed with Postgres plus the opt-in real-model tests enabled: 59 tests.
- Real runtime checks used the CPU BGE embedding model, MiniLM cross-encoder, Qdrant, Redis/Arq and a separate stdio MCP process. Test sources/accounts were development fixtures and were cleaned up.
- Browser checks passed for account/profile persistence, navigation, and portfolio upload → search → deletion. Five full assignment flows remain explicitly pending.
- TypeScript checks, the frontend production build, Python lint, required-path checks and Compose configuration validation passed.
- The Linux worker and migration images built successfully and the worker started against the local Postgres/Redis/Qdrant services.
- A live API upload was indexed by the Docker worker, retrieved through the API and standalone MCP, then deleted. Its development account was removed; the user's account was untouched.

Run the automated runtime checks with `GIGBID_TEST_DATABASE_URL` pointing to a local test-capable Postgres database and `GIGBID_REAL_MODELS=1`, then `uv run pytest`. Each Python integration test owns a disposable schema. Browser tests own a disposable database and deterministic test models; they do not measure retrieval quality.

## Still unverified or unimplemented

No evidence yet establishes proposal-agent quality, claim entailment, durable proposal approval/execution, marketplace interoperability, memory learning, grading-set performance, live Upwork OAuth, production security or public deployment. The instructor's GigSim/corpora/policy/dev labels have not been supplied. No simulated reply/hire rates or research tables have been invented.

## Proposal-node development checks

- Full Python suite after adding bid business nodes: **76 passed, 1 skipped** with Postgres and real retrieval models enabled. The skipped test requires the separate `GIGBID_REAL_AGENTS=1` flag.
- That opt-in Ollama smoke passed separately against the configured `qwen3.5:4b` model, returning a valid Analyst handoff with measured input/output token counts. This is an API integration check, not a proposal-quality or model-comparison result.
- Deterministic proposal tests exercise the implemented nodes, manual-job identity binding, rate floors, rejection of invented evidence IDs, injected-instruction risk flags, sentence checks across cover/screening answers, unsupported numerical claims, stale sources, draft digests, fresh approval after edits and a host-injected local-save fixture.
- HTTP transport fixtures exercise structured schemas, usage accounting, concurrent reservations, resumed usage limits and bounded fallback. The current budget counter is per runtime instance; database restoration is pending with the worker host.
- The Portfolio MCP reader used by the new nodes passed against the real in-memory MCP protocol and tenant-scoped retrieval service. The full suite also retained its separate real stdio subprocess check.
- No complete proposal has yet traversed real inference, durable checkpoints, API and browser review. The injected local save in unit tests does not establish transactional or marketplace execution.

Run the local Analyst smoke with `GIGBID_REAL_AGENTS=1 uv run pytest tests/integration/test_agent_models.py -q` while Ollama and the configured model are available.
