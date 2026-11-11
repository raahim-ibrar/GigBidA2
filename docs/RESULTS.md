# Measured student studies

## Controlled retrieval

Real BGE-small embeddings and MiniLM reranking; 60 answerable synthetic tasks and six unrelated tasks. Project-identity gold is not human-labelled real-job relevance.

| Variant | Recall@5 | MRR@5 | nDCG@10 | p95 seconds | Unanswerable tasks returning evidence |
|---|---:|---:|---:|---:|---:|
| V0 | 1.000 | 0.987 | 0.990 | 0.050 | 6/6 |
| V1 | 0.725 | 0.529 | 0.631 | 0.068 | 6/6 |
| V2 | 0.983 | 0.858 | 0.894 | 0.061 | 6/6 |
| V3 | 1.000 | 1.000 | 1.000 | 3.342 | 6/6 |
| V8 | 1.000 | 1.000 | 1.000 | 10.715 | 0/6 |

H1 was not supported: V3 did not increase Recall@5 over V0; both reached 1.000 on this easy controlled cohort. V1 lost recall when generic requirements dominated the fusion. V3 improved ordering, while V8 abstained on the six unrelated tasks at greater latency.

The predeclared selection rule (Recall@5, then nDCG@10, then p95) selects **V3**. V8 has better abstention but is slower. This is a limited synthetic-corpus choice, not proof of better real-job outcomes. V3→V2 removes reranking; V2→V0 removes lexical fusion; V8→V3 removes correction. The raw per-persona metrics and rankings remain in `evals/results/student-retrieval/`.

## Open-model graph study

### qwen3-8b

Recorded **30/30** jobs. This model cohort is complete.

Statuses: `{"skip": 3, "needs_attention": 26, "watch": 1}`. Measured job p95: 35.74s. Research-only candidate submissions: 0; rule-client replies: 0; hires: 0.

### qwen3.5-4b

Recorded **30/30** jobs. This model cohort is complete.

Statuses: `{"skip": 3, "needs_attention": 27}`. Measured job p95: 30.27s. Research-only candidate submissions: 0; rule-client replies: 0; hires: 0.

## Failure analysis

Errors and skips stay in the cohort. The small-model runs often fail grounding; control tests do not establish proposal quality.

| Model | Job | Category | Observed failure |
|---|---|---|---|
| qwen3-8b | student-4016-ai_ml-001 | cover grounding | No verified cover text remains; add portfolio evidence or revise |
| qwen3-8b | student-4016-ai_ml-002 | cover grounding | No verified cover text remains; add portfolio evidence or revise |
| qwen3-8b | student-4016-ai_ml-003 | cover grounding | No verified cover text remains; add portfolio evidence or revise |
| qwen3-8b | student-4016-ai_ml-004 | cover grounding | No verified cover text remains; add portfolio evidence or revise |
| qwen3-8b | student-4016-ai_ml-005 | cover grounding | No verified cover text remains; add portfolio evidence or revise |
| qwen3-8b | student-4016-ai_ml-006 | cover grounding | No verified cover text remains; add portfolio evidence or revise |
| qwen3-8b | student-4016-ai_ml-007 | cover grounding | No verified cover text remains; add portfolio evidence or revise |
| qwen3-8b | student-4016-ai_ml-008 | cover grounding | No verified cover text remains; add portfolio evidence or revise |
| qwen3-8b | student-4016-ai_ml-009 | cover grounding | No verified cover text remains; add portfolio evidence or revise |
| qwen3-8b | student-4016-full_stack-001 | cover grounding | No verified cover text remains; add portfolio evidence or revise |
| qwen3-8b | student-4016-full_stack-002 | cover grounding | No verified cover text remains; add portfolio evidence or revise |
| qwen3-8b | student-4016-full_stack-003 | cover grounding | No verified cover text remains; add portfolio evidence or revise |

Diagnostic fixes before frozen v3: exclude exact trusted source UUIDs from numerical-achievement checks, keep source IDs out of prose, and request concise verifier reasons. Earlier setup/diagnostic runs are retained locally. Failures that remain in v3 are not erased or counted as improvements. These changes have not been isolated in a causal ablation.

## Still missing

Human calibration (30 items), a blind human panel, the 40-task tool-design comparison, and the 50-job ReAct/supervisor/hand-graph study are not completed here. No result is invented for them. Hidden-test measurements are unavailable before grading.
