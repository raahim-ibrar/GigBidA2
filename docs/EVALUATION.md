# Evaluation workflow

The scoring tools run without the instructor assets. Actual assignment experiments do
not. No research results have been generated: unit-test observations are artificial
fixtures stored in disposable test directories, never reported as GigSim performance.

These are **our normalized input formats**, not claims about the instructor's file or
REST schemas. Inspect the supplied kit and write a mapping when it is available. Do
not rename grading labels, silently drop difficult jobs, modify `gigsim/`, or put the
hidden test set in this repository.

## Collect and validate

Use one JSON object per line, UTF-8. IDs must be unique within a file and must match
exactly across gold, predictions and outcomes. Missing jobs fail evaluation. Every
output records input names, SHA-256 hashes, data origin and its creation time. Use a
new output directory for each experiment. `supplied` is a declaration of provenance,
not automatic certification that a file really came from the instructor.

Gold records (`evals.contracts.GoldJob`):

| Field | Meaning |
| --- | --- |
| `id`, `persona` | Stable job ID and `ai_ml`, `full_stack` or `data_analyst` |
| `bid`, `scam` | Gold boolean labels |
| `relevant_ids` | Gold relevant portfolio evidence IDs |
| `price_min`, `price_max` | Optional fair-price band; both or neither |

Prediction records (`Prediction`):

| Field | Meaning |
| --- | --- |
| `id`, `bid`, `scam` | Same ID and actual recorded decisions |
| `ranked_ids` | Ordered retrieved evidence IDs; duplicates are rejected |
| `price` | Actual proposed price, if any |
| `claim_labels` | External labels: `supported`, `unsupported`, `ambiguous` |
| `claim_label_source` | Human annotator or calibrated judge/version identifier |
| `measured_tokens`, `elapsed_seconds` | Actual usage and active execution latency, if measured |
| `compliance_violations_caught` | Actual observed count, if independently checked |

Do not label a claim supported merely because the writer or verifier said it was.
Use blinded human annotations or a judge calibrated against the required human panel.
Absent annotations remain unknown. Ambiguous claims count as unsupported for the gate.
An omitted price counts as a miss when a gold price band exists.

Outcome records (`Outcome`) need `id`, a unique `event_id`, `source: "gigsim"`, and
boolean `submitted`, `replied`, `hired`. `connects` is optional measured spend.
Submitted proposals require `followup_complete: true`: only use a completed,
predeclared fixed simulator follow-up horizon. Hires count as replies. Record all
cohort jobs, including skips and submission failures; do not keep only successful
submissions. No-submission records must have no replies, hires or spend.

## Score individual measurements

Run from the repository root with the project environment:

```text
python -m evals.runners.rag_eval --gold PATH/gold.jsonl --predictions PATH/predictions.jsonl --k 5 --min-cases 30 --data-origin supplied --output evals/results/EXPERIMENT/retrieval.json
python -m evals.runners.decision_eval --gold PATH/gold.jsonl --predictions PATH/predictions.jsonl --min-cases 30 --data-origin supplied --output evals/results/EXPERIMENT/decisions.json
python -m evals.runners.gigsim_outcomes --observations PATH/outcomes.jsonl --min-cases 30 --data-origin supplied --output evals/results/EXPERIMENT/outcomes.json
python -m evals.runners.judge_calibration --observations PATH/judge-labels.jsonl --min-cases 30 --data-origin supplied --output evals/results/EXPERIMENT/judge.json
```

Retrieval reports macro Recall@k, binary nDCG@k, MRR@k and Precision@k, overall and
by persona. Precision divides by k, including short result lists. Unanswerable jobs
are excluded from recall/MRR/nDCG means and reported separately, including how often
they nevertheless returned evidence.

Decision reports include confusion matrices, accuracy, precision, recall, F1, price
band accuracy and annotation coverage. Undefined metrics are `null`. Unsupported
claim rate is `null` unless every job has external claim annotations and there is at
least one labelled claim. `[]` is valid only for an inspected draft with no claims.

Judge inputs have `id`, boolean `human`, boolean `judge`, where true has the same
meaning for both raters (for example, claim supported). The tool reports raw
agreement and Cohen's kappa. Kappa is undefined when expected agreement is 1.
The assignment still requires collecting the labels and documenting the human panel.

## Quality gate and CI

`python -m evals.runners.suite` (also `make eval`) requires a JSON manifest.
File paths resolve relative to that manifest. Structure:

```json
{
  "data_origin": "supplied",
  "experiment_id": "choose-before-running",
  "gold": "gold.jsonl",
  "predictions": "predictions.jsonl",
  "outcomes": "outcomes.jsonl",
  "min_cases": 30,
  "k": 5,
  "bid_f1_floor": 0.8,
  "unsupported_claim_rate_ceiling": 0.02
}
```

The two numeric thresholds above illustrate configuration; they are not measured
performance or established grading cutoffs. Predeclare justified thresholds before
examining results. The smoke gate requires at least 30 jobs, all three personas,
exact ID alignment, complete claim annotations and observed submissions. Missing or
undefined metrics fail the gate. A failed gate writes its failed checks and exits 1;
invalid/missing inputs exit 2.

```text
python -m evals.runners.suite --manifest PATH/manifest.json --require-supplied --output-dir evals/results/EXPERIMENT
```

The manual evaluation GitHub Action runs this gate and uploads its output. It remains
manual because the supplied kit, generation runner and real fixed GigSim run are
absent. This is **not yet E2's automatic 30-job PR experiment**. Unit tests for the
metric/gate code run in the ordinary Python CI job. `make eval` never substitutes
development fixtures when a real experiment bundle is absent.

## Compare tool designs, orchestration and ablations

All three runners take `--manifest PATH --output PATH`:

```text
python -m evals.runners.tool_granularity --manifest PATH/tools.json --output evals/results/EXPERIMENT/tools.json
python -m evals.runners.orchestration_compare --manifest PATH/orchestration.json --output evals/results/EXPERIMENT/orchestration.json
python -m evals.runners.ablation --manifest PATH/ablation.json --output evals/results/EXPERIMENT/ablation.json
```

A tool manifest has `data_origin`, `min_cases` (default 40), and `conditions` mapping
condition names to JSONL paths. Each task record contains `id`, boolean `success`,
boolean `correct_arguments`, `invalid_calls`, `tool_calls`, `measured_tokens`, and
`elapsed_seconds`. Every condition must contain exactly the same task IDs. Invalid
calls cannot exceed all calls. Output includes success/argument accuracy, invalid
call rate, total usage, median and nearest-rank p95 latency.

An orchestration/ablation manifest has `data_origin`, `gold`, `min_cases`, and
`conditions` mapping names to objects with `predictions` and `outcomes` paths.
Orchestration requires exactly `react`, `supervisor`, `hand_graph` on at least 50
jobs. Ablations require a condition named `baseline`. All conditions must match the
same gold IDs. Missing usage or latency measurements remain unknown rather than
being reported as zero. Only complete usage cohorts receive aggregate totals.

These tools **analyse recorded experiments**. They do not implement a ReAct agent,
supervisor baseline, tool-calling trial driver, or model/retrieval ablation executor.
Those runs and the required real measurements are still outstanding.

## X2 proposal experiment

See [EXTENSION.md](EXTENSION.md). The assignment-plan and statistical analysis code
is implemented, but provider execution and collecting real outcomes remain pending.
Keep plans fixed and commit them before inspecting any outcomes. Do not select a
winner from development fixtures or repeatedly test until a desired p-value appears.
