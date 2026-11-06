# Tool inventory

Portfolio tools use tenant-scoped source storage and retrieval. Workspace tools use a
local calendar and email-draft backend, as allowed by A3. The trusted stdio host binds
`GIGBID_TENANT_ID` and the Workspace executor's `GIGBID_RUN_ID`. Tool arguments cannot
select another account or run. Marketplace tools remain scaffolded. HTTP transport
awaits bearer authentication and per-user network rate limiting.

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
| create_proposal_draft | Marketplace | write | false / true / false | disabled implementation |
| submit_proposal | Marketplace | write | false / true / false | disabled implementation |
| send_message | Marketplace | write | false / true / false | disabled implementation |
| free_calendar_slots | Workspace | read | true / false / true | local stdio |
| create_interview_hold | Workspace | write | false / false / true | tenant/run-bound stdio and exact approved preview |
| create_email_draft | Workspace | write | false / false / true | tenant/run-bound stdio and exact approved preview |

Workspace writes default to dry-run previews. Execution checks the latest human
decision, saved preview, tool arguments, idempotency key and current run state. One SQL
transaction records the local effect and its audit receipt. A per-account lock prevents
overlapping concurrent holds. Calendar availability is declared by the user. The slot
finder excludes holds and limits queries to 31 days. The reviewed MCP snapshot covers
the intentional schema and annotation changes. Marketplace write idempotency remains
pending with its provider integration.

Every write eventually needs an authorization check at the server boundary, preview parity, an idempotency key, tenant-aware replay protection and an append-only audit record. Never expose arbitrary model-selected URLs or raw credentials as tool parameters.

Portfolio resource templates and prompt registration are in the Portfolio README. Actual prompt text lives under agent/prompts.

## Third-party servers to connect

- Official Upwork MCP: trust is restricted to the provider's own OAuth-authenticated service, scoped to the user's account; discover exact tools after authorization. Official reference: https://www.upwork.com/ai/mcp
- Official GitHub MCP: trust is restricted to GitHub's own server with least-privilege repository access; repository text/code remains untrusted data. Official reference: https://github.com/github/github-mcp-server

Both integrations are pending; listing URLs is not a connection test.

## R&D question A - planned

Build a fixed set of 40 tasks with known tool calls and valid arguments. Compare fine-grained tools, coarse tools, and the best set with rewritten descriptions under the same model/setup. Report selection accuracy, argument accuracy and tokens per task from raw saved results. Do not infer agent behavior from the registration tests.
