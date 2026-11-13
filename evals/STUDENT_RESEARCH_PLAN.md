# Student simulator study plan — declared before execution

The instructor's follow-up permits approved Kaggle jobs and realistic, labelled synthetic
data. This study uses our independent simulator. It is not the provided GigSim or hidden test.

## Retrieval hypothesis and selection

H1: hybrid retrieval plus cross-encoder reranking (V3) improves mean evidence Recall@5
over dense V0 on industry-specific, multi-requirement synthetic tasks. A negative result
must remain in the table. Compare V0, V1, V2, V3 and V8 on the identical cohort.

The controlled corpus has three fictional personas, 20 fictional case studies per persona,
one CV, three duplicate README representations and 150 synthetic historical proposals.
Gold relevance means a chunk belongs to the requested case-study project or its duplicate
README. It is generated from project identity, not inferred by the retrieval method.
Sixty answerable tasks and six unrelated tasks are frozen before retrieval. No generated
proposal is gold evidence for these tasks. This controlled sample is smaller and easier
than an independently labelled real marketplace evaluation.

Report Recall@5, MRR@5, nDCG@10, unanswerable retrieval, p50/p95 wall-clock seconds,
model identifiers and raw query/evidence-ID results. First-use model loading is reported
separately. Choose the highest Recall@5; break ties with nDCG@10 and then p95 latency.
Compare V3→V2 (remove reranking), V2→V0 (remove lexical fusion), and V8→V3
(remove correction). No hypothesis about client reply rates follows from this study.

## Generation and outcomes

Compare two open model configurations on the same frozen job IDs. Preserve errors and
skips in the denominator. Claim checks by an uncalibrated model are explicitly diagnostic;
they cannot stand in for the required 30 human labels or a blind classmate panel.
Simulator replies/hires are produced by a declared rule model using budget, skill coverage
and proposal length. These numbers measure that model's behaviour, not real client success.
Synthetic historical won/replied labels are never presented as measured experiments.

## X2

Assign evidence-first versus problem-first openings before inspecting any outcome, using
seed 4016 and the existing balanced persona/category stratification. Fix retrieval, model,
budget and memory. The rule simulator resolves all its lifecycle events synchronously, so
its follow-up horizon is one completed simulation transaction. This differs from real time
follow-up. Report arm counts and uncertainty; do not claim causality beyond this simulator.

## Required human/external evidence

Human judge calibration, classmates' blind ratings, actual public uptime, external MCP OAuth
and the hidden test require observations or account access that code cannot manufacture.
Prepare review materials and record these as missing until actually collected.


## Supplemental completion diagnostics (November 12)

The completed 150-run cohort is preserved. A separate pre-call paired plan in
`results/rag-end-to-end-v1/paired-plan.json` fixes nine matched jobs per V0/V3 variant,
models, budgets, hypothesis and selection before the 18 new hosted-open runs. Its
source snapshot is immutable. It is a small reused development cohort, not a new
confirmatory or held-out study. Final scoring reuses the calibrated independent rubric.

`results/verification-before-after-v1` retrospectively selects the first three paired
checkpoint jobs per persona. All nine pairs happened to have unchanged text; judge
variation is reported as such. `results/verification-changed-v1` separately includes
all four completed passes that removed text, selected by filter activity before judging.
No causal population claim or successful-verification claim for failed/unpaired cases is made.


## Evaluation fidelity correction (November 13)

`results/evaluation-fidelity-v1/` retains a new pre-call client plan: fixed free LLM,
one-pass blinded batches of ten, maximum twelve requests, no paid or rule fallback.
It replays only the 89 previously submitted architecture proposals and three RAG
submissions; all original generation runs and rule-client controls remain unchanged.
Primary outcome and X2 tables now use these LLM decisions plus existing eligibility guards.

Before retrieval replay, the nine actual V0/V3 job IDs, exact raw-post query recipe,
corpus-generator hash, k=5/10 depths, and synthetic topic-family relevance annotations
were frozen. Retrieval and proposal columns now share job IDs and corpus; retrieval is
retrospective, not a claim of newly regenerated proposals or independent human gold.
