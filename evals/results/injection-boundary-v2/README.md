# Paired prompt-boundary comparison

Completed 56 actual Groq GPT-OSS 120B calls: 24 synthetic attacks and four benign
controls, each under before/after prompts. Existing Writer/Liaison prompts are the
baseline; the after arm adds the shared `security_boundary.md`. Attack categories
include overrides, fabricated authority/roles, encoded instructions, and requests for
an artificial internal nonce. Each case has a unique fake marker or nonce. Arm order
alternates by case; temperature is zero and maximum completion budget is 2,000 tokens.

Before: **3/18** evaluable attacks succeeded (16.7%). After: **4/18** (22.2%). Each arm
had **six model failures** among its 24 assigned attacks; these remain errors, not
successful defences. All four benign controls per arm produced valid structured
outputs without leaking their fake nonce. Structured validity is not a quality rating.

Only 16 attacks have evaluable responses in both arms. Those paired responses have
no discordant attack outcomes (exact McNemar p=1.0). The differing marginal rates
come from cases missing a response in the opposite arm. **There is no demonstrated
security improvement**, and missing responses prevent interpreting the marginal
difference as a causal regression. The boundary alone does not guarantee safety.

This is a component-level prompt ablation, not a full-graph or approval-bypass test.
No MCP tools, real secrets, submissions or paid external actions were available.
The full application's separate public injection trace demonstrates one rejected
synthetic example; it is not an end-to-end attack-success estimate.

`plan.json` freezes the cases, role prompts, shared boundary, model and scorer.
`runs.jsonl` retains every assigned response/error and measured usage; usage is unknown
for the twelve failed calls, not zero. The 57,691 recorded tokens cover known calls.
`results.json` reports separate denominators and paired outcomes. The earlier
`injection-boundary-v1` is an invalid eight-call 20B pilot with no usable outputs;
it is retained separately and excluded from these results.

Reproduce from the repository root with a configured Groq key and Redis:
`python -m evals.runners.injection_defence`. Existing assigned rows are resumed,
not replaced. A changed frozen plan requires a new output directory. No GPU is used.
