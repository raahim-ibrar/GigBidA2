"""Derive the supplemental paired table without replacing any completed study."""

import argparse
import asyncio
import json
import math
from collections import Counter
from pathlib import Path

from evals.contracts import GoldJob, Prediction
from evals.judge_adaptive import main as judge
from evals.research_judge import proposal_inputs
from evals.scoring import decision_scores

ROOT = Path("evals/results/rag-end-to-end-v1")


def load_rows():
    rows = []
    for variant in ["v0", "v3"]:
        path = ROOT / variant / "hosted_open-routed.jsonl"
        cohort = list(map(json.loads, path.read_text(encoding="utf-8").splitlines()))
        if len(cohort) != 9 or len({r["id"] for r in cohort}) != 9:
            raise ValueError(f"{variant} is incomplete; do not publish a final table")
        rows.extend(
            {
                **r,
                "condition": variant,
                "candidate": r["snapshot"].get("draft") or {},
                "job": r["snapshot"].get("job") or {},
                "evidence": r["snapshot"].get("evidence") or [],
            }
            for r in cohort
        )
    path = ROOT / "judge-input-runs.jsonl"
    content = "".join(json.dumps(r) + "\n" for r in rows)
    if path.exists() and path.read_text(encoding="utf-8") != content:
        raise ValueError("Frozen judge inputs changed")
    path.write_text(content, encoding="utf-8")
    return rows, proposal_inputs(path)


def analyse(rows, items):
    labels = {
        r["id"]: r
        for r in map(
            json.loads, (ROOT / "judge/model-labels.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }
    if set(labels) != {r["id"] for r in items}:
        raise ValueError("Proposal judge incomplete; no completed summary is justified")
    retrieval = json.loads(
        Path("evals/results/student-retrieval/results.json").read_text(encoding="utf-8")
    )["results"]["variants"]
    results = {}
    for variant in ["v0", "v3"]:
        cohort = [r for r in rows if r["condition"] == variant]
        assessed = [
            labels[r["id"] + ":" + variant] for r in cohort if r["id"] + ":" + variant in labels
        ]
        claims = Counter(c["label"] for r in assessed for c in r["labels"])
        times = sorted(r["prediction"]["elapsed_seconds"] for r in cohort)
        submissions = sum(r["outcome"]["submitted"] for r in cohort)
        replies = sum(r["outcome"]["replied"] for r in cohort)
        by_persona = {}
        for persona in sorted({r["persona"] for r in cohort}):
            group = [r for r in cohort if r["persona"] == persona]
            elapsed = sorted(r["prediction"]["elapsed_seconds"] for r in group)
            by_persona[persona] = {
                "jobs": len(group),
                "statuses": dict(Counter(r["status"] for r in group)),
                "p50_job_seconds": elapsed[math.ceil(0.5 * len(elapsed)) - 1],
                "p95_job_seconds": elapsed[-1],
                "known_tokens": sum(r["prediction"]["measured_tokens"] for r in group),
                "replies": sum(r["outcome"]["replied"] for r in group),
            }
        results[variant] = {
            "jobs": len(cohort),
            "statuses": dict(Counter(r["status"] for r in cohort)),
            "decisions": decision_scores(
                [GoldJob.model_validate(r["gold"]) for r in cohort],
                [Prediction.model_validate(r["prediction"]) for r in cohort],
            ),
            "available_drafts": len(assessed),
            "mean_judge_quality": sum(r["quality"] for r in assessed) / len(assessed)
            if assessed
            else None,
            "claim_counts": dict(claims),
            "unsupported_claims_per_available_proposal": claims["unsupported"] / len(assessed)
            if assessed
            else None,
            "submissions": submissions,
            "replies": replies,
            "reply_rate_per_assigned_job": replies / len(cohort),
            "reply_rate_per_submission": replies / submissions if submissions else None,
            "p50_job_seconds": times[math.ceil(0.5 * len(times)) - 1],
            "p95_job_seconds": times[math.ceil(0.95 * len(times)) - 1],
            "known_tokens": sum(r["prediction"]["measured_tokens"] for r in cohort),
            "usd_per_proposal": None,
            "by_persona": by_persona,
            "positive_jobs": sum(r["gold"]["bid"] for r in cohort),
            "positive_jobs_priced_in_band": sum(
                r["gold"]["bid"]
                and r["prediction"]["price"] is not None
                and float(r["gold"]["price_min"])
                <= float(r["prediction"]["price"])
                <= float(r["gold"]["price_max"])
                for r in cohort
            ),
            "separate_retrieval_cohort": {
                "answerable_tasks": 60,
                "recall_at_5": retrieval[variant]["at_5"]["overall"]["macro_recall_at_k"],
                "ndcg_at_10": retrieval[variant]["at_10"]["overall"]["macro_ndcg_at_k"],
            },
        }
    result = {
        "kind": "Small paired V0/V3 supplemental end-to-end diagnostic",
        "data_origin": "synthetic",
        "variants": results,
        "limits": "Nine reused dev jobs per variant; same hosted open model profile. "
        "All errors retained. Judge scores cover every available draft, including later failures. "
        "Recall/nDCG use the separate 60-task retrieval cohort, not these nine jobs. "
        "No causal or real-client claim. Billing and hidden-test outcomes are unknown.",
    }
    (ROOT / "analysis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    table = [
        "| Variant | Recall@5* | nDCG@10* | Unsupported / available proposal | "
        "Judge / 5 | Reply / submitted | p95/job seconds | USD/proposal |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for variant, row in results.items():
        measured = row["separate_retrieval_cohort"]
        table.append(
            f"| {variant.upper()} | {measured['recall_at_5']:.3f} | "
            f"{measured['ndcg_at_10']:.3f} | "
            f"{row['unsupported_claims_per_available_proposal']:.2f} "
            f"(n={row['available_drafts']}) | {row['mean_judge_quality']:.2f} | "
            f"{row['replies']}/{row['submissions']} | {row['p95_job_seconds']:.2f} | unknown |"
        )
    table.extend(
        [
            "",
            "*Retrieval: separate 60-answerable-task cohort. Proposal columns: nine matched jobs "
            "per variant; every available draft judged, including later-failing runs. "
            "The columns do not establish a causal retrieval-to-reply relationship.",
            "",
            "Intention-to-treat replies were 2/9 (V0) versus 1/9 (V3). "
            "V3's shorter latency includes more early failures, "
            "not a demonstrated speed improvement. "
            "The sample is small; API billing remains unknown.",
        ]
    )
    rendered = "\n".join(table)
    (ROOT / "results-table.md").write_text(rendered + "\n", encoding="utf-8")
    readme = Path("README.md")
    content = readme.read_text(encoding="utf-8")
    start, end = "<!-- rag-e2e-table:start -->", "<!-- rag-e2e-table:end -->"
    if content.count(start) == content.count(end) == 1:
        prefix, rest = content.split(start)
        _, suffix = rest.split(end)
        readme.write_text(
            prefix + start + "\n\n" + rendered + "\n\n" + end + suffix, encoding="utf-8"
        )
    print(
        json.dumps(
            {
                v: {k: r[k] for k in ["jobs", "available_drafts", "submissions", "replies"]}
                for v, r in results.items()
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge", action="store_true")
    args = parser.parse_args()
    rows, inputs = load_rows()
    if args.judge:
        asyncio.run(judge(inputs, output=ROOT / "judge"))
    analyse(rows, inputs)
