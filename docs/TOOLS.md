# Tool inventory

Portfolio tools are implemented against tenant-scoped source storage and retrieval. The trusted stdio host binds `GIGBID_TENANT_ID`; the tool schema cannot select another tenant. Marketplace and Workspace tools remain scaffolded. HTTP MCP refuses to start until bearer auth is implemented. Per-user network rate limiting and audit are still pending. The search tool accepts a Pydantic `request` object, including the configurable retrieval variant.

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
| create_interview_hold | Workspace | write | false / true / false | disabled implementation |
| create_email_draft | Workspace | write | false / true / false | disabled implementation |

Write annotations deliberately do not claim idempotency yet. Once a durable ledger and upstream retry behavior are implemented and tested, change those annotations and review the resulting schema snapshot. A client-supplied key alone does not make a write idempotent.

Every write eventually needs an authorization check at the server boundary, preview parity, an idempotency key, tenant-aware replay protection and an append-only audit record. Never expose arbitrary model-selected URLs or raw credentials as tool parameters.

Portfolio resource templates and prompt registration are in the Portfolio README. Actual prompt text lives under agent/prompts.

## Third-party servers to connect

- Official Upwork MCP: trust is restricted to the provider's own OAuth-authenticated service, scoped to the user's account; discover exact tools after authorization. Official reference: https://www.upwork.com/ai/mcp
- Official GitHub MCP: trust is restricted to GitHub's own server with least-privilege repository access; repository text/code remains untrusted data. Official reference: https://github.com/github/github-mcp-server

Both integrations are pending; listing URLs is not a connection test.

## R&D question A - planned

Build a fixed set of 40 tasks with known tool calls and valid arguments. Compare fine-grained tools, coarse tools, and the best set with rewritten descriptions under the same model/setup. Report selection accuracy, argument accuracy and tokens per task from raw saved results. Do not infer agent behavior from the registration tests.
