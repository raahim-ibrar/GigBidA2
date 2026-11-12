# Orchestration pilot verification

The technical pilot passed on November 11, 2026: one separate benign fictional job,
executed through ReAct, the actual `langgraph-supervisor` package, and the production
hand-built graph. All three used `openai/gpt-oss-120b`, retrieved actual indexed fictional
evidence through MCP, produced a bid candidate and completed without a runtime error.
The hand-built graph stopped at its real approval interrupt. No human approval was
created; candidates were scored only in the isolated research simulator.

Evidence is in `evals/results/pilot-validation-v1`: `verification.json`, `runs.jsonl`,
`plan.json`, and `source-manifest.json`. Snapshots preserve the hashed source files,
configuration and dependency lock from the successful run. Earlier failed diagnostics
remain in `work/orchestration-pilot-v1` through `v5`.

## Repairs

- Native agents require structured tool calls and have explicit analysis-report,
  candidate-recording and supervisor-finish tools.
- The transport can remove observed Harmony wrappers only from a tool name declared
  in the current request. Arguments remain unchanged and pass normal tool validation.
  The original HTTP failure and unknown usage remain recorded; no tokens or decisions
  are invented by the repair.
- Native calls and optional verification share one atomic per-run token budget.
- The pilot default is the verified GPT-OSS 120B configuration. Smaller-model failures
  remain failures. Future source freezes also include the configuration file.

## Scope and rerun

This is three executions of **one** job, not the fifty-job/150-run comparison. It proves
connectivity, structured handoffs and termination, not general reliability or comparative
quality. Other candidate models have not passed this pilot. The full study is unstarted.

Install research dependencies with `uv sync --frozen --extra dev --extra research`.
Use a new study ID and output directory for an independent pilot:

```text
python -m evals.runners.student_orchestration --pilot --pilot-model openai/gpt-oss-120b --study-id pilot_check --output work/orchestration-pilot-check
```

Frozen output refuses resumption after relevant source/configuration changes. Do not
overwrite old results or mix pilot cases into the final evaluation cohort.
