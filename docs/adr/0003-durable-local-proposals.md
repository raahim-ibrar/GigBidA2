# Durable local proposals while marketplace assets are unavailable

Date: 2026-11-05

Manual job entry enables the real analysis/drafting workflow without inventing a
GigSim contract. The source is explicitly `manual`; client history and Connects cost
remain unknown. A reviewed draft can be saved locally. This is not an application
submission and cannot establish marketplace outcomes.

The API saves a job/run before enqueueing. SQL pending-run scans recover work when
Redis is unavailable or a worker disappears. An Arq job ID deduplicates normal queue
deliveries. A Postgres session advisory lock serializes execution per tenant/run, and
a separate worker token fences stale metadata/local-write updates. The same database
session holds the advisory lock and LangGraph saver; its loss prevents stale checkpoint
publication. All checkpoint handoff types are explicitly allowlisted, with no pickle
fallback.

Approval records bind the tenant, run version, draft digest and interrupt ID. Resuming
uses an ID-keyed LangGraph Command. If a process dies after reaching a new interrupt
but before publishing its review, the prior decision cannot resume that new interrupt.
Edits re-enter verification, critique and local compliance, then request fresh approval.

The local-save transaction locks the run, checks the latest human approval, then locks
referenced portfolio source rows and checks their active chunk revisions. A unique
artifact per run and a unique preview key prevent duplicate local effects. If SQL
commit succeeds but the execute checkpoint is lost, the committed artifact provides
authoritative recovery. This argument applies to one local SQL transaction; external
marketplace writes will need provider idempotency and reconciliation separately.

Before model calls, token estimates including output allowance are reserved in SQL.
Actual usage settles them. A process crash leaves an outstanding reservation charged
conservatively. Business-node attempts also consume a durable step budget. This can
stop a run early after failures; it avoids silently restoring a fresh budget on retry.

Persisted progress events contain node names, measured usage and safe error types,
with PII redaction. Source text stays in tenant-scoped state and source records, not
progress events. SSE replays events after a persisted ID and reconnects on bounded
connections. No public traces or production security claim is established by this design.
