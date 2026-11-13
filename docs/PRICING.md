# Budget-based pricing

New quotes use the host's read-only `get_pricing_statistics` MCP capability.
This is GigBid's own tool, not a claimed Upwork MCP capability. The tool resolves
the job through the original connected provider and checks the host-bound account.
No LLM, GPU, proposal submission or Connects expenditure is involved.

## Method

- Compare USD posting budgets of the same billing type with at least two matching
  skills (explicit tags or whole skill names in the job text). Exclude the current
  posting, duplicate IDs, malformed budgets and unknown provenance.
- Require five comparable records. Compute median and inclusive 25th/75th
  percentiles of posting budget midpoints. Prefer the historical cohort when it
  has five records; otherwise use explicitly labelled synthetic simulator records.
  These cohorts are never pooled.
- When five comparable postings for the same simulator client exist, blend
  75% market median and 25% client median, clipping the client median to the market
  interquartile range. Simulator client identity is fictional. Prepared historical
  data usually assigns a unique synthetic client per posting, so this adjustment
  will correctly be unavailable there. Live Upwork client paid-price history is
  currently unavailable and is never joined to simulator client IDs.
- Clamp the result to the current job's budget range. Hourly quotes must also meet
  the user's hourly floor and the policy floor; otherwise require review. Fixed
  totals are not treated as hourly rates; the user must still assess scope/effort.
- Sparse/unavailable statistics fall back explicitly to the posted budget and
  floor. Provider Connects cost and balance remain mandatory for provider drafts.
  Non-USD budgets require review rather than an invented exchange rate.

The existing proposal-review screen displays the quote rationale, sample count,
median, IQR, client adjustment and budget/floor constraints. Existing reviewed
quotes are not silently repriced; price remains part of exact-preview approval.

## Sources and limits

The simulator uses its actual configured catalogue. With the prepared dataset,
budget values come from Asaniczka's historical Upwork postings (ODC-By attribution
and preprocessing are in [DATA_CARD.md](DATA_CARD.md)); generated client context is
still synthetic. The generated development catalogue produces synthetic budget
statistics only. Neither source contains verified contract earnings.

For live Upwork jobs, the host reads only the prepared historical cohort at
`PRICING_CATALOGUE_PATH` (default `data/processed/student_jobs.json`). Compose mounts
that ignored data directory read-only into API and worker containers. Missing
files/skills/comparables produce an explicit fallback; no live price-history tool
or paid-rate field is invented. No historical file is published by this change.

This is a transparent pricing heuristic, not a trained valuation model: archived
and persona-filtered postings are biased, may be stale and may differ in scope.
Five observations is a minimum safeguard, not statistical proof of a fair price.
Client spending totals are not interpreted as hourly rates. Currency conversion,
reliable effort estimation and verified live contract-rate history remain absent.
Frozen research outputs predate this change and have not been rewritten or rerun.

## Verification

Local checks: 200 tests passed, 24 skipped, with the four Postgres-only replay
checks excluded because Docker/Postgres was off. A final focused run passed all
30 pricing, proposal-node, Marketplace MCP and schema/study-compatibility checks.
Coverage includes unit/currency/provenance separation, outlier-resistant medians,
sparse/outage fallback, bounded client influence, budget/floor constraints, live
history isolation and read-only Connects behavior. Ruff and secret scans passed.
No model API calls, GPU experiments or real Upwork writes were used.
