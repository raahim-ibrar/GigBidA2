# Assignment-specific CI

The edited assignment's repository rules (section immediately after the fixed
tree), A7 schema-contract rule and E2 evaluation rule are enforced on pushes and
pull requests. These checks do not claim hidden-test success or full completion.

| Rule | Check |
| --- | --- |
| No committed secrets | Pinned Gitleaks scans publishable files and full Git history; private `.env`/key files fail the policy check. |
| Do not modify `gigsim/` | Compare the entire tree, including additions/deletions, with its original Git commit `e2596e9f2411fd7228a6ea1c6e68d08e9683df0e`. Full checkout history is required. |
| Prompts in `agent/prompts/` | Check active template locations, configured role files and literal Python system/prompt arguments/assignments. |
| README/report numbers trace to `evals/results/` | Reviewed section/page numeric-token inventories and evidence-file hashes reject undocumented/stale changes. |
| MCP signatures remain intentional | Existing SDK schema-snapshot contract test remains in the backend job. |
| Unit, contract and Playwright checks | Existing backend/Postgres and browser jobs remain enabled. |
| Fresh evaluation per PR | Existing deterministic control now runs through `make eval`: fresh jobs, production graphs, MCP and simulator, with decision/grounding/retrieval/reply gates. |

The `assignment-policy` job runs independently with only pypdf/PyYAML and standard
Python tools. Its mutation tests demonstrate rejection of protected-tree edits,
misplaced/inline prompts, missing role templates, altered numeric claims, changed/
missing/escaped evidence and committed credential files. Secret diagnostics expose
rule names and file locations only, never matched source lines or secret values.
Gitleaks is pinned to its official release and a verified archive SHA256. Detection
is pattern based, not a mathematical guarantee that no arbitrary secret exists.
The scanner exports only Git-tracked/publishable paths, excluding ignored private
workspace files; it also checks deleted historical content through Git history.
Secret findings are not uploaded as public CI artifacts.

The original `gigsim/` baseline currently contains only its placeholder. This check
protects that supplied repository boundary; it does not prove compatibility with
an unavailable instructor simulator. Our independent implementation stays in
`simulator/`. Its client prompt and the native research-agent templates were moved
unchanged into `agent/prompts/experiments/`. Frozen as-run snapshots were preserved;
they are historical evidence rather than active prompt-template locations.

## Numeric provenance review

`evals/results/numeric-claim-provenance.json` binds each numeric-containing README
section and engineering-report PDF page to committed evidence files and hashes.
`assignment-ci-context.json` separately identifies declared targets, configuration
and document metadata. Line endings are normalized for text evidence; PDF text is
extracted using the pinned pypdf version. Changes require deliberate review and
updated bindings; CI never auto-refreshes the ledger to bless a changed claim.

This is a traceability/change gate, not automatic semantic validation: it does not
recompute every number, verify that a citation logically proves a claim, detect
all spelled-out numerical assertions, validate statistical conclusions or turn a
historical milestone into a current status claim. Those still require review.
The published engineering PDF retains dated milestone descriptions; current
integration/deployment limitations are recorded separately in `SUBMISSION.md`.

Likewise the static prompt check is bounded to recognizable template names and
Python prompt constructs; it is not a general proof of arbitrary dynamic code.
No private CV or hidden grading data is used by these checks.

Run `make check-assignment` with Gitleaks installed, or use
`python -m scripts.check_assignment` and
`python -m scripts.scan_repository_secrets --binary PATH_TO_GITLEAKS`.
The existing smoke thresholds are bid F1 >= 0.98, unsupported factual claims <= 0,
Recall@5 >= 0.95 and reply rate >= 0.95 on deliberately easy control fixtures.
They are regression controls, not LLM-quality research or a replacement for the
recorded studies. No GPU or model API calls are made by these policy checks.

E6 uptime, human-rating independence, instructor policy-change timing, statistical
validity and live Upwork account eligibility cannot be certified by these checks.
The student's E6 exclusion and the live-preview blocker remain disclosed.

Local verification: the Postgres-backed suite passed 252 tests with five opt-in
skips. All seven policy mutation tests, whole-project Ruff, publishable-tree and
full-history Gitleaks scans passed. The text of all five relocated templates was
checked against the previous source and remained unchanged. Evidence is in
`evals/results/assignment-ci-verification.json`; this does not claim a remote CI
result before GitHub Actions has actually finished.
