# GigBid data card

## Scope and provenance

The instructor's follow-up authorises Kaggle datasets plus clearly distinguished synthetic
fields. The instructor did not deliver a running simulator; the user confirmed students
must build it. `simulator/` is our independent implementation, version `student-v1`.
It is not claimed to be the original GigSim or a compatible hidden-test implementation.

## Selected source

Asaniczka, **Upwork Job Postings Dataset 2024 (50K records)**, Kaggle version 1:
https://www.kaggle.com/datasets/asaniczka/upwork-job-postings-dataset-2024-50k-records

Uploader-declared license: ODC Attribution License (ODC-By 1.0),
https://opendatacommons.org/licenses/by/1-0/ . The database license does not independently
establish rights in every job's text or remove privacy obligations. Attribution is included
in the app and this document. No Upwork website is scraped. Raw and derived job text is
kept under ignored `data/processed/`; the public repository contains processing code and
hashes, not the archive.

Pinned archive SHA256:
`3f40f06c267f6429e6c9fdd9a81c0c9bb3a3c9eb85edadb1d6638394e9ce5b35`.
The archive has 53,058 CSV rows. Reproduce with:

```text
python -m scripts.download_student_data
```

The script pins version 1, checks the hash and limits download/archive sizes. Preprocessing
keeps descriptions of 80-5,000 characters, deduplicates normalized title/description,
requires usable positive budgets, and assigns personas by at least two skill keywords.
It selects 200 cases per persona by deterministic hash order with seed 4016.

| Preprocessing category | Count |
|---|---:|
| Input rows | 53,058 |
| Excluded outside target personas | 42,185 |
| Missing/invalid/unknown budgets | 8,196 |
| Text outside bounds | 101 |
| Duplicate content | 23 |
| Eligible AI/ML / full-stack / analyst | 475 / 1,125 / 953 |
| Selected AI/ML / full-stack / analyst | 200 / 200 / 200 |
| Eligible records with redacted contact information | 10 |

Output SHA256 after preprocessing:
`5938ca6deff4153f8a86f726e70da3e2104b773bb9f5c1afcf069ac03a779022`.
The generated manifest records source version, counts and caveats. These historical
February 2024 records are not current opportunities. Client-posted budgets are not a
human-validated fair-price gold standard; USD is an explicit assumption because the
export lacks currency. Persona/skill assignment is heuristic.

## Real versus generated fields

Real historical fields: base title, base description, publication date, posted budget.
Generated/derived: persona/category, skill labels, client IDs/history, Connects cost,
screening questions, controlled scam/injection perturbations and scenario labels.
All replies, interviews, hires and losses are synthetic. Public job responses remove gold
labels. Every job carries provenance; the UI identifies the simulator connection.
Perturbation labels describe our inserted scenarios, not accusations about original authors.

The fallback catalogue is 600 fully synthetic jobs. `/health` reports whether historical
text or the fallback is loaded. An explicitly configured missing file fails rather than
silently claiming historical data was loaded.

## Other approved datasets inspected

| Kaggle dataset | Declared license | Decision |
|---|---|---|
| asaniczka/all-jobs-on-upwork-200k-plus, v4 | ODC-By | Not needed; overlaps jobs already selected |
| ahmedmyalo/upwork-freelance-jobs-60k, v5 | Apache 2.0 | Not selected; avoid adding overlapping unaligned jobs |
| asaniczka/freelance-contracts-dataset-1-3-million-entries, v1 | ODC-By | Not selected; no justified mapping from contracts to these personas |
| sarveshchhetri/freelancer-success-earnings-and-churn-prediction, v2 | Apache 2.0 | Not treated as observed history; description says realistic generated records |
| adityammantri/trial-1, v1 | Unknown in inspected metadata | Excluded until permission/license is clear |

Metadata was inspected through Kaggle's dataset API. Licenses are uploader declarations,
not an independent audit of downstream rights.

## Fictional portfolios and controlled evaluation

`scripts/student_personas.py` defines three fictional personas with 20 case studies,
three duplicate README representations, one CV and 150 generated past proposals each.
Every source explicitly states it is fictional coursework. Generated won/replied/ignored
labels are not measured outcomes and must not become resume or report success statistics.
The seed command creates separate demo accounts; it does not overwrite the user's profile.

The retrieval study freezes 60 answerable industry/project tasks plus six unrelated tasks.
Gold IDs come from the target case-study project and its README, excluding synthetic past
proposals. This tests controlled project retrieval, not independently adjudicated relevance
on real job posts. The cohort, raw rankings, model IDs and measured times are retained.
There is no hidden-test data, no claim of 200 human-labelled jobs per persona, and no blind
human ratings until actual reviewers supply them. The historical catalogue is separate
from these controlled retrieval queries. See `evals/STUDENT_RESEARCH_PLAN.md`.

## Client model limits

The current deterministic client model uses whether the scenario is eligible, bid within
budget, proposal length, and required-skill coverage to generate replies and hires. It is
transparent and repeatable, but rewards keyword coverage and cannot measure persuasive
writing, realistic competition or real hiring. It also differs from the document's proposed
LLM client. All outcome tables must state this limitation.
