# Signature extension - X2 analysis tooling

Selected direction: proposal experiments in GigSim. Frozen assignment plans and
offline analysis are implemented. Runtime strategy wiring, actual simulator trials
and measured results remain pending; the extension is not yet assignment-complete.

Compare two grounded proposal strategies: an evidence-first opening and a concise problem-first opening. Hold model configuration, retrieval, pricing and compliance constant. Predeclare the primary metric as reply rate, randomization seed and sample size; assign jobs to arms within persona/category strata. Keep the held-out evaluation separate from prompt iteration.

Report arm sizes, replies, effect size with confidence interval and a Fisher exact
significance test when counts are small. A non-significant difference is a valid
result. Neither arm can bypass approval or use fabricated evidence. Capture the
setup and raw outcomes under evals/results before writing conclusions.

Create jobs JSONL with `id`, `persona`, `category`. Before outcomes exist:

```text
python -m evals.runners.proposal_experiments assign --input PATH/jobs.jsonl --seed 4016 --alpha 0.05 --followup-window FIXED_SIMULATOR_HORIZON --data-origin supplied --output evals/results/EXPERIMENT/plan.json
```

Each persona/category stratum is shuffled deterministically and assigned nearly
equally to `evidence_first` and `problem_first`. Reordering the input does not change
assignments. Save the plan before running either strategy. Use distinct clients/jobs
where possible; repeated-client interactions can break independent-observation
assumptions. Freeze models, retrieval, pricing, memory and policy between arms.

Then collect JSONL with `id`, boolean `replied`, `followup_complete: true`, and the
same `followup_window` string. Every assigned job must appear exactly once after
the fixed horizon; no selective deletion of failures or pending cases is allowed.

```text
python -m evals.runners.proposal_experiments analyse --input evals/results/EXPERIMENT/plan.json --observations PATH/followup.jsonl --data-origin supplied --output evals/results/EXPERIMENT/analysis.json
```

The report includes arm counts/rates, evidence-first minus problem-first reply-rate
difference, a two-sided fixed-margin Fisher exact p-value and a conservative
Hoeffding/union-bound confidence interval. The interval assumes independent bounded
observations and can be wide. The pooled Fisher test is not adjusted for strata;
inspect heterogeneous effects and do not treat one pooled p-value as proof that a
strategy works for every persona. No significant-result claim exists yet.
