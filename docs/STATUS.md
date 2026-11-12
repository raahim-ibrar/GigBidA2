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
- Backend regression checkpoint: **162 passed, four opt-in skipped**. Later changes are
  validated in targeted checks; consult VERIFICATION.md for the latest complete run.

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

## Remaining evidence or access requirements

- Official Upwork OAuth/schema mapping and GitHub MCP ingestion are not implemented/connected.
  No user's real marketplace account has been authorised and no live client is contacted.
- Marketplace HTTP MCP bearer endpoint, shared rate limiting and a tracing backend still need
  completion/verification; current production agent transport is tenant-bound stdio.
- Public hosting, reviewer credentials delivered privately, public repository/package/write-up,
  final PDF and recorded demo have not yet been delivered. A local URL is not deployment.
- The independent rule client is not the original GigSim/LLM client. Compatibility with an
  unseen grading simulator is not established. Hidden-test results cannot be reported in advance.

See DATA_CARD.md for provenance and `evals/STUDENT_RESEARCH_PLAN.md` for declared studies.
