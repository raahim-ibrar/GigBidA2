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
