# Evaluation fidelity correction

Primary outcome source: `summary.json`. Previous generation observations, original
rule-client outcomes and the earlier 60-task retrieval study remain untouched.

- Frozen agent observations: 150 architecture cases and 18 V0/V3 cases; no agent reruns.
- Actual new client decisions: 92 submissions (89 architecture, three RAG), 12 bounded
  requests to the fixed free Nvidia model. No GPU, paid fallback or rule-only fallback.
- Simulator receipts: real `SimStore(client_mode="llm")` outbox resolution, with existing
  eligibility and budget guards. Raw and effective outcomes are retained separately.
- Matched B5 cohort: the same nine jobs, raw-post query recipe and persona corpus for
  both variants. CPU replay measures Recall@5 at k=5 and nDCG@10 at k=10.
- Relevance annotations are declared synthetic topic-family gold authored by Codex,
  saved before retrieval. They are not independent student/human labels. All matching
  industries are relevant because these jobs do not specify an industry.
- Proposal quality uses every available draft (five V0, two V3); failures remain in
  assigned-job denominators. One-pass batched clients are not real market demand and
  shared batch context can couple decisions. API billing remains unknown.

Regenerate the summary and primary README table without inference:

```text
python -m evals.fidelity_analysis
```

Plans, public-source provenance checks, complete raw responses (including two invalid
format attempts), accepted decisions, per-persona metrics and source-item rankings are
included. No private CV, credentials or real client data were sent or committed.

`fidelity_clients` can reconstruct simulator receipts from accepted decisions without
a key or network calls. Missing decisions require the configured free route, respect
the existing twelve-request cap and remain pending if unavailable. Accepted decisions
are never regenerated to seek a better result.
