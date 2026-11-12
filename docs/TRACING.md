# Trace correlation and privacy

The durable run UUID is the trace ID. The run creation response sends
`X-GigBid-Trace-ID`; the run viewer displays it. Audit events, approval rows and
marketplace writes refer to the same run. Each actual MCP call records its host-selected
server/tool name, elapsed time and protocol error flag. No tool arguments or results
are included. Model spans use measured provider/model/token usage and elapsed time;
unknown billing costs remain unknown.

`TRACE_EXPORT_ENABLED=true` enables explicit LangSmith export to `LANGSMITH_PROJECT`
using `LANGSMITH_API_KEY`. Leave `LANGSMITH_TRACING=false`: this implementation does
not need automatic prompt capture. Node and child spans are reconstructed from the
durable audit timestamps. The root begins when the run was saved; this includes queue
time, rather than pretending to measure HTTP request latency. An approval pause closes
the current root interval; resuming updates the same trace and stable child IDs.

Exports allow only timing, status, host-controlled role/tool/model names, token counts
and audit IDs. Inputs are replaced with a privacy notice. Prompts, source documents,
CVs, tool parameters/results, identities and exception messages are omitted. The
export cursor and span IDs make repeats idempotent. A provider outage leaves the
workflow state unchanged; the worker retries export on its next reconciliation pass.

Public sharing is separate from export. The three published examples come from
the isolated fictional demo account, with synthetic `student-4016-*` jobs. The
operator script `python -m scripts.publish_demo_traces` verifies the fixed demo account
and job provenance before sharing the prepared runs. It reuses existing share URLs.
Ordinary user traces are never automatically public. Do not place keys in source or
publish the ignored `work/public-demo` directory.

Current public URLs and actual chain/model/tool span counts are in
`evals/results/public-traces.json`. They remain viewable independently of the laptop
tunnel. The public app and MCP endpoint still require the laptop and Docker to run.
