"""Join the frozen independent judge with every available architecture draft."""

import json
from collections import Counter
from pathlib import Path
from statistics import mean

from evals.research_judge import Batch, validate_batch


def main():
    root = Path("evals/results/judge-proposals-final")
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    labels = [
        json.loads(x)
        for x in (root / "model-labels.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    validate_batch(plan["items"], Batch.model_validate({"items": labels}))
    judged = {r["id"]: r for r in labels}
    runs = [
        json.loads(x)
        for x in Path("evals/results/gemini-orchestration-v1/runs.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]

    def summary(rows):
        counts = Counter(
            label["label"]
            for r in rows
            for label in judged[r["id"] + ":" + r["condition"]]["labels"]
        )
        scores = [judged[r["id"] + ":" + r["condition"]]["quality"] for r in rows]
        factual = counts["supported"] + counts["unsupported"]
        return {
            "n_drafts": len(rows),
            "mean_quality_1_to_5": mean(scores) if scores else None,
            "quality_distribution": dict(Counter(scores)),
            "claim_counts": dict(counts),
            "unsupported_per_factual_claim": counts["unsupported"] / factual if factual else None,
            "unsupported_per_all_claims": counts["unsupported"] / sum(counts.values())
            if counts
            else None,
            "drafts_with_unsupported_claim": sum(
                any(
                    label["label"] == "unsupported"
                    for label in judged[r["id"] + ":" + r["condition"]]["labels"]
                )
                for r in rows
            ),
        }

    results = {
        "judge": plan["model"],
        "generator_models": ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"],
        "data_origin": "synthetic",
        "all_available_drafts_including_failures": {},
        "research_submitted_drafts": {},
        "calibration": json.loads(
            Path("evals/results/judge-calibration-v4/agreement.json").read_text(encoding="utf-8")
        ),
        "limits": [
            "Judge predictions are proxy measurements, not ground truth: "
            "claim-label agreement with the single human is 60%, Cohen kappa"
            " about 0.403.",
            "Quality weighted kappa is about 0.681 on 30 purpose-built "
            "examples; this does not establish transfer to full architecture"
            " drafts.",
            "Only runs with nonempty drafts can be scored; missing drafts "
            "remain failures in the 150-run outcome tables, not zero-quality"
            " observations.",
            "Raw retained drafts from later-failing runs are scored "
            "separately from simulator-submitted drafts; the research does "
            "not forge app approval.",
            "Different generators and judge reduce direct self-evaluation "
            "but do not establish statistical independence or objective "
            "truth.",
        ],
    }
    for condition in ("react", "supervisor", "hand_graph"):
        selected = [r for r in runs if r["condition"] == condition and r["candidate"].get("text")]
        results["all_available_drafts_including_failures"][condition] = summary(selected)
        results["research_submitted_drafts"][condition] = summary(
            [r for r in selected if r["outcome"]["submitted"]]
        )
    (root / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results["all_available_drafts_including_failures"], indent=2))


if __name__ == "__main__":
    main()
