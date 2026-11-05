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
