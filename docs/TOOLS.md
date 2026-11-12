# Tool inventory

Portfolio tools use tenant-scoped source storage and retrieval. Workspace tools use a
local calendar and email-draft backend, as allowed by A3. The trusted stdio host binds
`GIGBID_TENANT_ID` and the Workspace executor's `GIGBID_RUN_ID`. Tool arguments cannot
select another account or run. Marketplace tools use the connected simulator or verified Upwork adapter. The published
Portfolio HTTP transport has bearer authentication and Redis per-account rate limits.

| Tool | Server | Access | readOnly / destructive / idempotent | Current auth |
| --- | --- | --- | --- | --- |
| search_evidence | Portfolio | read | true / false / true | local stdio |
| get_case_study | Portfolio | read | true / false / true | local stdio |
| list_skills | Portfolio | read | true / false / true | local stdio |
| search_jobs | Marketplace | read | true / false / true | local stdio |
| get_job | Marketplace | read | true / false / true | local stdio |
| get_client_history | Marketplace | read | true / false / true | local stdio |
| get_connects_balance | Marketplace | read | true / false / true | local stdio |
| list_messages | Marketplace | read | true / false / true | local stdio |
| create_proposal_draft | Marketplace | write | false / true / false | host approval and durable effect/intent ledger |
| submit_proposal | Marketplace | write | false / true / false | host approval and durable effect/intent ledger |
| send_message | Marketplace | write | false / true / false | host approval and durable effect/intent ledger |
| free_calendar_slots | Workspace | read | true / false / true | local stdio |
| create_interview_hold | Workspace | write | false / false / true | tenant/run-bound stdio and exact approved preview |
| create_email_draft | Workspace | write | false / false / true | tenant/run-bound stdio and exact approved preview |

Workspace writes default to dry-run previews. Execution checks the latest human
decision, saved preview, tool arguments, idempotency key and current run state. One SQL
transaction records the local effect and its audit receipt. A per-account lock prevents
overlapping concurrent holds. Calendar availability is declared by the user. The slot
finder excludes holds and limits queries to 31 days. The reviewed MCP snapshot covers
the intentional schema and annotation changes. Simulator writes deduplicate upstream. Live Upwork preparation uses a durable send-once
intent: uncertain results are not retried, and final submissions/direct messages are disabled.

Every write eventually needs an authorization check at the server boundary, preview parity, an idempotency key, tenant-aware replay protection and an append-only audit record. Never expose arbitrary model-selected URLs or raw credentials as tool parameters.

Portfolio resource templates and prompt registration are in the Portfolio README. Actual prompt text lives under agent/prompts.

## Third-party servers to connect

- Official Upwork MCP: trust is restricted to the provider's own OAuth-authenticated service, scoped to the user's account; discover exact tools after authorization. Official reference: https://www.upwork.com/ai/mcp
- Official GitHub MCP: trust is restricted to GitHub's own server with least-privilege repository access; repository text/code remains untrusted data. Official reference: https://github.com/github/github-mcp-server

Both official servers were connected and tested. GitHub README ingestion and real Upwork OAuth/read-only verification are saved in `evals/results/public-integrations.json` and `evals/results/upwork-live-verification.json`. Upwork credentials are encrypted per user. See `UPWORK.md` for the exact verified tool/action mapping and write limitations.

## R&D question A - completed

Forty tasks across three tool designs produced 120 actual GPT-OSS 120B calls; all designs had perfect call/argument accuracy, with fine-grained tools using fewer tokens. Measurements and limitations are in `evals/results/student-tool-study-v3`. Registration tests are control checks, not behavioral measurements.

Upwork mappings: `find_jobs/search|get`, `get_freelancer_financials/connects_balance`, `get_messages/list_messages`, and approval-gated `manage_proposals/create`. The provider prefixes tool names with `upwork__`. Public client history comes from job detail, not an invented client-history tool. `confirm_preview`, `send_proposal` and direct `send_message` actions are not exposed.
