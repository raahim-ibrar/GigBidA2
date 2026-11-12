# Implementation status

Updated November 12, 2026. This file supersedes older notes about waiting for GigSim.
The instructor's follow-up permits student-built data/simulation, confirmed by the user.

## Implemented and verified

- Authenticated multi-user accounts, profiles, rate/budget settings and CSRF-protected writes.
- PDF/Markdown/text portfolio ingestion, source revisions, tenant-scoped Qdrant evidence,
  five retrieval variants, source-linked claims and paragraph regeneration.
- Bid and conversation LangGraph StateGraphs with Postgres checkpoints, parallel analyses,
  bounded Critic loops, token/step budgets, durable interrupt/edit/review and explicit retries.
- Independent persistent student simulator: job search, client histories, balances, previews,
  proposals, messages, lifecycle events, fault fixtures and atomic idempotent Connects debits.
- Actual tenant-bound Marketplace MCP tools implementing the port. Approval receipts bind
  exact payload, draft digest, version and key; source evidence, connection and budget are
  rechecked immediately before an effect. Reconciliation can recover observed proposals.
- Simulator event ingestion into pipeline/analytics and client conversations, plus approved
  outbound replies. An end-to-end integration test verifies proposal-to-client-reply and
  duplicate worker safety through actual MCP sessions and persistent simulator writes.
- Saved searches now fetch and deduplicate jobs; optional automatic analysis is bounded to
  one new job per account/tick. No automatic proposal/message submission.
- Workspace MCP with local availability, reviewed holds/email drafts and durable receipts.
- Rule-promoted style/outcome memory with user inspection, confirmation and deletion.
- Dark responsive frontend with purple accents, active navigation and actual overview counts.
- Pinned approved Kaggle archive and reproducible preprocessing to 600 hybrid scenarios;
  separately labelled fictional demo portfolios and seed command.
- Backend regression: **193 passed, four optional skipped**. Existing and new Upwork
  browser checks: **16 passed**.
- Public GitHub README ingestion through official read-only MCP, pinned to a commit.
- Temporary public laptop-backed application and bearer-protected Portfolio MCP HTTP
  endpoint, with Redis account rate limits and host-bound tenant identity.
- Explicit metadata-only LangSmith audit export and three public synthetic traces,
  each verified without authentication; private source text and secrets are omitted.

## Research and review completed

- Five real retrieval variants evaluated on 66 synthetic tasks; V3 selected by the declared rule.
- Two open-weight local configurations, 30 jobs each, completed with negative grounding results preserved.
- 40 known-call tasks across three tool designs: 120 actual GPT-OSS 120B calls recorded.
- 50 synthetic jobs across ReAct, real langgraph-supervisor and custom graph: 150 Gemini executions recorded, 102 error-free and 48 failures. This optional closed-model experiment is distinct from the open configurations.
- Thirty actual student calibration labels and two user-supplied blind classmate panels saved; agreement and limitations documented.
- All 103 available architecture drafts independently judged using the calibrated Nvidia rubric; no-draft and later-failing runs remain visible.
- Ten-page R&D PDF and 1,500-word technical narrative finalized with measured results and limitations.
- Final architecture and intention-to-treat X2 analysis saved in `evals/results/gemini-orchestration-v1/analysis.json`.
- Full browser regression: 15 passed; TypeScript passed. These control checks are distinct from model quality.
- Paired injection-boundary comparison: 56 calls completed, including all model errors.
  No security improvement was established; see `evals/results/injection-boundary-v2`.

## Remaining evidence or access requirements

- Real Upwork OAuth and verified tool mappings are implemented. Authorization, job
  search/detail and Connects reads passed on the existing personal account. No live
  client was contacted. Provider-preview preparation is fixture-tested only; final
  confirmation and direct message sending remain disabled. See `UPWORK.md`.
- The published MCP endpoint serves the read-only demo portfolio; graph capability
  calls continue to use tenant-bound stdio. Production-wide authentication limits
  remain incomplete. No public package-registry release is claimed.
- The public app depends on the laptop and tunnel staying active. Always-on availability
  until grading is not established. Reviewer connection files remain private. Report
  and write-up PDFs are updated; the requested video/GIF remains a student deliverable.
- The independent rule client is not the original GigSim/LLM client. Compatibility with an
  unseen grading simulator is not established. Hidden-test results cannot be reported in advance.

See DATA_CARD.md for provenance and `evals/STUDENT_RESEARCH_PLAN.md` for declared studies.


## Completion update (November 12)

The entries above describe earlier checkpoints. Current evidence adds source-code GitHub import,
safe checkpoint replay in the UI, a fresh 30-job CI control, 214 passing backend checks and
17 browser flows, actual Inspector screenshots, an installable MCP command, public technical
article, video/GIF, and approved-proposal / Critic / actual API-crash public trace snapshots.
See `SUBMISSION.md` and `evals/results/engineering-verification.json`. E6 uptime is explicitly
excluded by the student, not claimed complete. Real Upwork write verification, unseen GigSim
compatibility, the instructor-specific policy change and hidden-test results remain unverified.
