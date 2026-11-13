# Redacted MCP read audits

MCP reads now have local durable receipts in `mcp_read_audits`, separate from the
metadata-only LangSmith spans and existing exact-preview write approval records.
Migration `0012_mcp_read_audits` is applied by the normal Compose migration service
before API/worker startup; existing manual installations must run `alembic upgrade head`.

## Coverage

- All validated Portfolio read tools: evidence search, case-study lookup and skill
  listing. Portfolio case/proposal resource reads are covered too.
- All validated Marketplace read tools: job search/details, client history,
  pricing statistics, Connects balance and conversation messages.
- Workspace availability reads.
- Official GitHub MCP repository lookup, immutable commit lookup and source-file
  reads used by portfolio import.
- Official Upwork MCP read-tool invocations, including the local sign-in helper's
  account lookup. Provider draft preparation keeps the existing write-review path.

Server-side wrappers cover calls from the graph, Inspector, authenticated HTTP
clients and in-process application clients. The account is host-bound, never a
tool argument. Reads associated with an agent run carry its ID; standalone and
provider-level calls have a null run ID. Separate outer Marketplace and inner
official Upwork receipts represent separate MCP boundaries, not duplicate sends.

Protocol discovery/initialization and SDK validation failures before tool dispatch
are not domain read-tool executions. Arbitrary external scripts, older installed
versions and historical calls are not retroactively audited. Research observations
and previously published traces remain unchanged.

## Receipt lifecycle

Before dispatch, commit a UUID receipt with account, optional run, server/tool,
timestamp, `started` status and redacted arguments. After execution, finalize it
once with redacted results, elapsed time and one of `completed`, `tool_error`,
`exception` or `cancelled`. An exception message is never copied into the audit.
Cancellation attempts to finish the receipt under a shield; a process crash can
leave `started`, meaning completion is unconfirmed. It never implies success.

Persistence failure blocks dispatch, or blocks returning an already-read result
if finalization fails. No automatic retry is introduced. Each call adds two small
database transactions; this deliberately trades some latency/availability for a
durable audit. Completed receipts cannot be finalized again through the auditor.

## Redaction and access

The policy retains reviewed field labels, booleans, whitelisted numerical fields
(counts, budgets, scores) and narrow enums. It suppresses all free-form strings,
including CVs, query text, names, contact details, identifiers, URLs, timestamps in
source data, filenames and exception messages. Credentials/account organization
IDs are suppressed as whole subtrees. Unknown mapping keys become anonymous field
ordinals because the keys themselves may contain private information.

SDK structured results and JSON text blocks follow the same recursive policy.
Binary/unknown objects are not stringified. Depth, node count, array length,
mapping width and final JSON size are bounded; truncation is explicit. Actual
tool arguments/results passed to inference remain unchanged. This conservative
policy permits structural debugging but deliberately prevents reconstruction of
the original queries or documents; it is not a replay archive.

Authenticated owners can inspect `GET /api/mcp/read-audits`, optionally with
`run_id`, `limit` (1–200) and `offset`. The endpoint always filters to the signed-in
account, rejects foreign runs, and offers no edit/delete operation. It is local
application data and is never exported to LangSmith/public traces. Account/run
deletion cascades to corresponding receipts; there is no automatic age-based purge.

## Verification

The available local backend suite passed: 210 tests, 24 skipped; the four replay
tests requiring stopped Postgres were excluded. SQLite migration, durable attempt
visibility, success/tool errors/exceptions/cancellation, audit-write failure,
cross-account/run isolation, standalone SDK calls, provider read coverage, nested
PII/secret/binary redaction and bounded storage were checked with fixtures.
Public MCP schema snapshots still match. API types, TypeScript checking, Ruff and
secret scans passed. No GPU, model API, live Upwork writes or research reruns were
used. Postgres-only validation remains a separate CI/environment check.
