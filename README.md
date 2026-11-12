# GigBid

A freelancer workspace for finding suitable jobs, drafting evidence-backed proposals and
reviewing every outgoing action. Built with LangGraph, MCP, FastAPI and Next.js.

![GigBid dark workspace](docs/images/workspace-dark.png)

**Working locally:** accounts, portfolios, durable proposal/reply review, the student-built
marketplace simulator, scheduled job imports, pipeline, analytics and a responsive dark UI.
A temporary public laptop-backed demo is available; stable hosting and some integrations remain unfinished. No real Upwork
client is contacted, and simulated replies or hires are not real business outcomes.

## Run

```text
uv sync --frozen --extra dev
python -m scripts.download_student_data
# Copy .env.example to .env and configure local values.
docker compose --project-directory . -f infra/docker-compose.yml up --build
```

The prepared catalogue contains 600 historical job texts with clearly labelled synthetic
context. Without prepared data, the simulator uses fully synthetic jobs and identifies that
in `/health`. See [the data card](docs/DATA_CARD.md) for licenses, attribution and limitations.
The original instructor GigSim was not delivered; `simulator/` is our independent implementation.

Open [the app](http://localhost:3000). Create an account, upload evidence, and connect the
student simulator from the inbox or Settings. Search jobs, open one and start analysis.
Review its evidence and exact preview before approving. Use Sync simulator activity to
import lifecycle events and client replies. Every reply requires another approval.

The worker normally calls native Ollama at `host.docker.internal:11434`. Pull the models in
`agent/config.yaml` first. Optional container inference runs with the `container-inference`
profile. Models, downloads and queued indexing take time; none of the tests below prove
proposal quality. [Runbook](docs/RUNBOOK.md) and [implementation status](docs/STATUS.md).

Create separate fictional reviewer accounts and portfolios with `python -m scripts.seed`.
Private generated credentials stay in ignored `work/demo-accounts.json`; never publish them.

## Architecture

```mermaid
flowchart LR
  UI[Next.js workspace] --> API[FastAPI / sessions / CSRF]
  API --> Redis[Redis + Arq]
  Redis --> Graph[Durable bid + conversation graphs]
  Graph --> MCP[Tenant-bound MCP capabilities]
  MCP --> RAG[Portfolio / BGE / Qdrant / BM25 / MiniLM]
  MCP --> Market[Marketplace port / student simulator]
  MCP --> Workspace[Local calendar + drafts]
  Graph --> PG[Postgres checkpoints + audit + memory ledger]
  Graph --> Review[Human interrupt: approve / edit / reject]
  Review --> API
```

The Analyst, Risk Assessor and Matcher branches run in parallel. Typed handoffs, evidence
re-reads, bounded Critic loops, token/step limits and checkpointed approvals govern execution.
An approval binds a version, interrupt ID, digest and exact write payload. The simulator's
idempotency receipt prevents duplicate debits; SQL reconciliation preserves observed effects.
[Rendered graphs](docs/GRAPHS.md) Ã‚Â· [Architecture](docs/ARCHITECTURE.md) Ã‚Â· [Tools](docs/TOOLS.md).

## Measured retrieval

Controlled synthetic study: 60 answerable project tasks and six unrelated tasks, with real
BGE-small embeddings and MiniLM cross-encoder inference. This is easier than independently
labelled real job relevance. Source: [results.json](evals/results/student-retrieval/results.json).

| Variant | Recall@5 | MRR@5 | nDCG@10 | p95 seconds | Unrelated tasks retrieving evidence |
|---|---:|---:|---:|---:|---:|
| V0 dense | 1.000 | 0.987 | 0.990 | 0.050 | 6/6 |
| V1 decomposition | 0.725 | 0.529 | 0.631 | 0.068 | 6/6 |
| V2 hybrid | 0.983 | 0.858 | 0.894 | 0.061 | 6/6 |
| V3 hybrid + rerank | 1.000 | 1.000 | 1.000 | 3.342 | 6/6 |
| V8 corrective | 1.000 | 1.000 | 1.000 | 10.715 | 0/6 |

The hypothesis that reranking improves recall over V0 was not supported here. V3 improved
ordering; V8 improved abstention at greater latency. The declared recall/ordering/latency
selection rule chooses V3. This does not establish better client reply rates.

The two open-model cohorts are complete (30 jobs each); grounding failures are retained.
The 150-run optional Gemini architecture comparison is complete: ReAct had 41/50
error-free runs, supervisor 24/50, and the custom graph 37/50. Intermediate decision
accuracy must not be confused with full-run success. The 40-task tool study, 30-item
human calibration and twelve-pair classmate panel are also recorded. X2 reply rates
were 48% versus 68%, Fisher p=0.252: no significant strategy benefit established.
See [measured results](docs/RESULTS.md), [technical narrative](docs/TECHNICAL_WRITEUP.md),
[study plan](evals/STUDENT_RESEARCH_PLAN.md), and [evaluation guide](docs/EVALUATION.md).
Hidden-test results are unavailable before grading.

## Verification

```text
python -m pytest
python -m ruff check .
python scripts/check_structure.py
python scripts/render_graphs.py --check
cd apps/web
npm run typecheck
npm run build
npm run test:e2e
```

Set `GIGBID_TEST_DATABASE_URL` for isolated Postgres schemas. The latest full backend run
passed 193 tests with four opt-in skips.
The existing Chromium suite and added Upwork UI check passed 16 flows in total. Deterministic
browser/control fixtures are not quality measurements. [Verification history](docs/VERIFICATION.md).

## Submission status

Repository: [raahim-ibrar/GigBidA2](https://github.com/raahim-ibrar/GigBidA2).
Temporary public demo: [open GigBid](https://interpreted-vid-recovered-estimation.trycloudflare.com).
It depends on the laptop, Docker and tunnel remaining running; the URL changes after restart.
Actual verification: [demo results](evals/results/demo-deployment.json) and
[demo hosting notes](docs/DEMO_HOSTING.md). Reviewer credentials are kept private.
The optional [student-credit Azure/Vercel configuration](docs/DEPLOYMENT.md) is prepared
but no Azure resources were provisioned.
Public [Portfolio MCP](https://interpreted-vid-recovered-estimation.trycloudflare.com/mcp)
is bearer-protected; private connection details are in `work/public-demo/MCP-CONNECTION.json`.
GitHub import reads a public repository's README through the official read-only MCP server,
pins the commit, and indexes it in the signed-in account's portfolio.

Public LangSmith traces contain measured timings, token usage and MCP calls, with source
content omitted: [proposal awaiting approval](https://smith.langchain.com/public/a2f56a69-3bde-4159-b994-cd81ed98a3f9/r),
[scam rejected](https://smith.langchain.com/public/b55b89d4-881e-4c66-8516-cef09cba7cd2/r),
[injection rejected](https://smith.langchain.com/public/06918fe8-f9e4-4551-a7d8-f1435f522869/r).
See [trace evidence](evals/results/public-traces.json) and [tracing policy](docs/TRACING.md).
The [56-call injection comparison](evals/results/injection-boundary-v2/README.md) is complete.
It does not establish a security improvement; model failures and paired outcomes are reported.
Real Upwork OAuth, account-scoped encrypted credentials and live job reads are verified.
See [Upwork setup and limits](docs/UPWORK.md) and [sanitized live evidence](evals/results/upwork-live-verification.json).
Provider-preview preparation is approval-gated and fixture-tested; no live write was
attempted. Final submissions and direct message sending remain disabled. The required video/GIF
is excluded from the current work at the user's request.

[Portfolio MCP install instructions](mcp_servers/portfolio/README.md) Ã‚Â·
[Data provenance](docs/DATA_CARD.md) Ã‚Â· [AI assistance disclosure](docs/AI_USAGE.md).
