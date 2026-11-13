# USD inference cost calculation and reporting

New model-usage events carry a versioned standard text list-price estimate,
separate from recorded API charges. The calculator uses decimal arithmetic:

`estimated USD = (input tokens × input USD/million + output tokens × output USD/million) / 1,000,000`

For example, 1,000 input and 200 output tokens on Groq GPT-OSS 120B estimate to
`(1,000 × 0.15 + 200 × 0.60) / 1,000,000 = $0.00027`.

## Dated rate snapshot

`agent/cost_rates.json`, version `standard-text-2026-11-13`, checked November 13,
2026. Rates are USD per million tokens for standard uncached text requests:

| Provider | Model | Input | Output |
| --- | --- | ---: | ---: |
| Groq | openai/gpt-oss-20b | 0.075 | 0.30 |
| Groq | openai/gpt-oss-120b | 0.15 | 0.60 |
| Groq | qwen/qwen3.8-27b | 0.80 | 4.00 |
| Gemini | gemini-3.1-flash-lite | 0.25 | 1.50 |
| Gemini | gemini-3.5-flash-lite | 0.30 | 2.50 |

Sources: [official Groq models/prices](https://console.groq.com/docs/models),
[official Gemini Developer API pricing](https://aistudio.google.com/docs/pricing).
Each new priced event records its input/output rates, source URL, check date and
version. Catalogue edits affect future events, not stored estimates. The rate
file is included in the Python wheel; unknown model/provider pairs stay unknown.

## What a dollar amount means

- Hosted estimates are paid-list-price equivalents, not invoices. Free-tier calls
  may actually cost zero. The app does not infer billing tier from keys or quota,
  enable paid billing, or claim paid charges from token usage.
- Local Ollama inference records zero API fee, explicitly excluding hardware,
  electricity and infrastructure. This is not zero total operating cost.
- Separate provider-reported input/output counts are required for hosted pricing.
  Missing, negative, boolean or otherwise invalid counts remain unpriced. Token
  reservations are safety-budget estimates and are never converted into dollars.
- Unknown-usage failures are recorded. Known-usage schema failures still count
  toward cost. Gemini's transient HTTP retry attempts also get unknown-cost
  records; they are not hidden behind the eventual successful call. These retry
  entries use role `transport_retry`, since the lower transport does not identify
  the graph role. Their timing is included in the enclosing model call, avoiding
  duplicate latency totals.
- Estimates exclude cache discounts, batch/flex tiers, taxes, credits, tool fees,
  storage, Connects, portfolio bid amounts and local infrastructure. They use
  provider-reported completion counts, including any thinking counted there.
  Multimodal billing is outside the current text-only calculator.

## Reports and completeness

Authenticated owners can use `GET /api/runs/{run_id}/cost`. The run's proposal/
activity screen and Analytics show estimated USD, recorded attempts, input/output
tokens, unknown-cost attempts, unmatched/reserved tokens and provider/model/role
breakdowns. Analytics uses the selected run-creation cohort, not a billing-period
invoice. Cost totals cover the entire selected cohort, even when the run table is
limited to its latest 200 rows. The owner checks also apply to the cost endpoint.

An estimate subtotal may be available while completeness is false. Active runs,
unpriced calls, unknown usage or tokens not matched to measured records prevent
the report from claiming full coverage. Hosted recorded charges remain unknown;
local API-only zeros are distinguished from missing values. Tiny nonzero amounts
are displayed without rounding them to zero.

Older events without a saved estimate are not silently repriced at today's rates.
They remain unpriced (except the inherent zero local API fee). Frozen research
observations, reports and historical dollar fields have not been rewritten, and
no model experiments were rerun for this feature. Rates can change; review the
dated catalogue before using the estimate for a financial decision.

Public tracing exports only numeric usage/cost metadata. Unknown usage is flagged
and omitted from token-count metadata, rather than exported as a zero-token call.
Prompts, CVs, tool arguments/results and credentials remain excluded.

## Verification

Available backend suite: 220 passed, 24 skipped; four Postgres-only replay checks
were excluded because Postgres was off. After final review, 37 focused checks
passed, including additional reservation-cleanup and unknown-trace-usage cases.
The Chromium dashboard regression passed for partial totals, tiny prices, unknown
billing and local zero display. API types, TypeScript and Ruff passed. No model
API, GPU or real marketplace write was used. Postgres-only checks remain a
separate environment/CI check.
