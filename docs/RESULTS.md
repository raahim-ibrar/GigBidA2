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

The predeclared selection rule (Recall@5, then nDCG@10, then p95) selects **V3**. V8 has better abstention but is slower. This is a limited synthetic-corpus choice, not proof of better real-job outcomes. V3â†’V2 removes reranking; V2â†’V0 removes lexical fusion; V8â†’V3 removes correction. The raw per-persona metrics and rankings remain in `evals/results/student-retrieval/`.

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

## Tool design: 120 native calls

Forty known-call tasks were run with fine, coarse and rewritten tools using GPT-OSS 120B. Each condition scored 100% tool-selection and argument accuracy. Mean tokens/task were 617.675, 988.750 and 690.575 respectively. This easy synthetic cohort has a ceiling effect. Evidence: `evals/results/student-tool-study-v3/results.json`.

## Completed 150-run architecture comparison

Fifty identical fully fictional jobs, matched model assignment per job (Gemini 3.1/3.5 Flash-Lite), 20,000-token caps. This optional closed-model experiment does not replace the open-weight configurations above. All 150 observations remain, including 48 failures. Frozen source snapshots were hash-verified.

| Architecture | Error-free / 50 | Correct intermediate decisions / 50 | Error-free correct decisions / 50 | Simulator submissions | Replies / 50 | p95 seconds | Mean measured tokens/job | Scam rejection / 6 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| react | 41 | 36 | 36 | 40 | 35 | 138.55 | 8376.96 | 1 |
| supervisor | 24 | 24 | 23 | 19 | 18 | 186.13 | 10330.04 | 5 |
| hand_graph | 37 | 49 | 36 | 30 | 29 | 178.69 | 8662.28 | 6 |

The custom graph's 98% intermediate decision accuracy is not 98% completion: thirteen runs failed later. ReAct's higher completion rate includes five scam-control submissions to the isolated research simulator; supervisor had one, custom graph zero. No application approval was forged and no real client was contacted. Zero final draft policy flags must not be misreported as zero attack success.

Failure taxonomy: 39 budget stops, four timeouts, three provider/structured-output failures, and two other stops. Successful-call tokens total 1,368,464; 58 native calls have unknown usage. API billing is unknown. Latency includes waits within attempts but not all between-attempt daily-quota waits. Baselines, models, retrieval, step limits, prompts and API outages are part of the systems comparison, not an isolated model-size effect. Source: `evals/results/gemini-orchestration-v1/{analysis,plan,progress}.json`, `runs.jsonl`, and `source-snapshot/`. The earlier incomplete Groq run remains separate.

## Independent proposal judge and actual human calibration

The frozen Nvidia Nemotron 3.5 Lightning rubric was compared with thirty actual student labels: support agreement 60%, Cohen kappa 0.402985; quality exact agreement 46.7%, quadratic weighted kappa 0.681128. These are limited single-human calibration results, not objective gold. The final protocol preserves validated assessments and retries only malformed items; no accepted label was replaced based on score. Earlier invalid array/keyed-output trials and unavailable Google trials remain diagnostic records. The final rubric is unchanged.

| All available drafts, including failures | Drafts | Mean quality / 5 | Unsupported / factual claims | Drafts with unsupported claim |
|---|---:|---:|---:|---:|
| react | 40 | 3.650 | 19/222 | 14 |
| supervisor | 20 | 3.750 | 12/105 | 6 |
| hand_graph | 43 | 3.884 | 11/210 | 8 |

All 103 nonempty drafts were assessed. The remaining 47 runs have no draft and remain in failure/outcome denominators; missing drafts are not silently assigned a quality score. Submitted-only results are also saved. Model-judge estimates remain uncertain given claim agreement of only 60%. Evidence: `evals/results/judge-proposals-final/{plan,model-labels,results}.json*` and `judge-calibration-v4/{agreement,human-labels}.json`.

## Classmate blind panel

Two user-supplied reviewers, twelve blinded raw local-model pairs, 24 ratings: 4B received 13 votes and 8B 11. Agreement 11/12, kappa 0.833333. A convenience panel of twelve repeated jobs cannot establish a population winner. The second response was reconstructed from the user's stated last-choice difference; identities and independence were not verified. This panel does not evaluate the later Gemini generators. Evidence: `evals/results/human-panel-v1/results.json`.

## X2: intention-to-treat opening strategy

The hand-graph jobs were preassigned 25 per arm: evidence-first had 12 replies (48%), problem-first 17 (68%). Difference -20 percentage points; two-sided Fisher p=0.251590; conservative 95% Hoeffding interval [-79.208, +39.208] percentage points. No significant strategy benefit is established. Non-submissions count as no reply. The pooled test ignores assignment strata; per-persona counts and model/condition tables are retained in `analysis.json`. All replies are rule-simulator outcomes, not real-client behavior.

## Limits and unmeasured requirements

Hidden-test performance, real-client response and instructor-policy-change implementation timing remain unmeasured. A separate 56-call component-level injection-boundary comparison completed: before 3/18 and after 4/18 evaluable attacks disclosed fake markers/nonces, with six model errors per arm. Sixteen fully observed pairs had no discordant outcomes; no improvement was established. This does not measure end-to-end approval bypass. Temporary laptop-backed public hosting, an authenticated Portfolio MCP endpoint, GitHub README ingestion and three public metadata-only traces are verified. Real Upwork OAuth and live reads are now verified separately in upwork-live-verification.json; no live writes were tested, and final submissions/direct messages remain disabled. Always-on hosting remains a gap. The local hardware inventory was captured after the study, not as an as-run trace: see `evals/results/local-hardware-inventory.json`. Local output throughput was 79.324 tokens/s for Qwen4B and 64.396 for Qwen8B; API cost was zero for local inference but hardware/electricity was not priced.


## Supplemental V0/V3 end-to-end diagnostic

Eighteen real routed hosted-open runs completed on nine matched synthetic development jobs
per retrieval variant, with the same three persona portfolios, 32,000-token caps and no
fallback. The original 150-run study was not rerun. The pre-call paired plan and as-run
source snapshot are in `evals/results/rag-end-to-end-v1/`.

| Variant | Recall@5* | nDCG@10* | Unsupported / available proposal | Judge / 5 | Reply / submitted | p95/job seconds | USD/proposal |
|---|---:|---:|---:|---:|---:|---:|---:|
| V0 | 1.000 | 0.990 | 0.00 (n=5) | 3.80 | 2/2 | 368.16 | unknown |
| V3 | 1.000 | 1.000 | 0.00 (n=2) | 4.00 | 1/1 | 124.43 | unknown |

*Retrieval: separate 60-answerable-task cohort. Proposal columns: nine matched jobs per variant; every available draft judged, including later-failing runs. The columns do not establish a causal retrieval-to-reply relationship.

Intention-to-treat replies were 2/9 (V0) versus 1/9 (V3). V3's shorter latency includes more early failures, not a demonstrated speed improvement. The sample is small; API billing remains unknown.


Intermediate bid F1 was 0.909 for V0 and 1.000 for V3, but only two versus one candidates
reached the approval interrupt. V0 statuses: three skip, two awaiting approval, three needs
attention and one watch. V3: three skip, one awaiting approval and five needs attention.
Generation/context and provider TPM reservations dominate the failures. Known tokens total
112,773 versus 56,249; unknown/failed-call usage and billing cannot be treated as zero.
A faster failing cohort does not prove an optimization. Per-persona decisions, latency,
price coverage and raw errors remain in `analysis.json` and the unedited observations.

The prototype runner's legacy caveat text predates the completed human calibration; the
independent scoring used the existing frozen calibrated Nvidia rubric. It did not change
or regenerate the student's human answers. Regenerate with
`python -m evals.analyse_rag_end_to_end` (no inference); `--judge` resumes only missing labels.

## Before/after claim verification

A retrospective checkpoint extraction found 54 completed verifier passes assessing 272
sentences; four sentences were removed. These are the verifier's own decisions, not gold.
Failed/unpaired attempts are not counted as successful passes.

The first three paired jobs per persona produced nine unchanged-text pairs. A blinded
independent judge called one factual claim unsupported in each phase, with different factual
denominators (1/32 versus 1/13). Because all nine texts were unchanged, this variation is
judge inconsistency, not a filtering effect. The human calibration kappa of 0.403 cautions
against interpreting these labels as truth.

A separately declared exploratory stratum includes all four completed passes that actually
changed text, selected by filter activity before their judging, not by scores. Unsupported
factual claims: **2/22 (9.1%) before, 1/13 (7.7%) after**. Mean quality remained **3.75/5**.
This tiny conditional sample does not establish a general improvement. Pair order was
shuffled and phase labels hidden; accepted labels were never revised. Evidence:
`evals/results/verification-before-after-v1/` and `verification-changed-v1/`.
