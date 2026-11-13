"""Publish matched-job retrieval and LLM-client outcomes without changing legacy records."""

import copy
import json
from pathlib import Path

from evals.experiments import analyse_arms
from evals.fidelity_clients import ROOT, frozen_rows, read_lines


def require_matched(cohorts):
    if any(len(rows) != len(set(rows)) for rows in cohorts.values()):
        raise ValueError("Duplicate jobs are not independent cohort members")
    ids = [set(rows) for rows in cohorts.values()]
    if not ids or not ids[0] or any(x != ids[0] for x in ids[1:]):
        raise ValueError("Every variant must use exactly the same job cohort")


def validate_outcomes(source, outcomes):
    lookup = {(r["group"], r["condition"], r["id"]): r for r in source}
    actual = {(r["group"], r["condition"], r["id"]) for r in outcomes}
    if set(lookup) != actual or len(outcomes) != len(lookup):
        raise ValueError("LLM outcome follow-up incomplete or duplicated; no final table")
    for row in outcomes:
        original = lookup[(row["group"], row["condition"], row["id"])]
        if original["outcome"]["submitted"] != row["submitted"]:
            raise ValueError("Frozen submission status cannot be changed by client replay")
        if not row["followup_complete"] or (row["submitted"] and not row["client_model_called"]):
            raise ValueError("A missing model decision cannot be counted as a negative outcome")


def run():
    outcomes = read_lines(ROOT / "llm-outcomes.jsonl")
    source, _, _ = frozen_rows()
    validate_outcomes(source, outcomes)
    retrieval_plan = json.loads((ROOT / "retrieval-plan.json").read_text(encoding="utf-8"))
    retrieval = json.loads((ROOT / "retrieval.json").read_text(encoding="utf-8"))
    original_rag = json.loads(
        Path("evals/results/rag-end-to-end-v1/analysis.json").read_text(encoding="utf-8")
    )
    rag = copy.deepcopy(original_rag["variants"])
    cohorts = {
        v: [r["id"] for r in outcomes if r["group"] == "rag" and r["condition"] == v] for v in rag
    }
    require_matched({**cohorts, "retrieval": retrieval_plan["job_ids"]})
    for variant, row in rag.items():
        observed = [r for r in outcomes if r["group"] == "rag" and r["condition"] == variant]
        row.pop("separate_retrieval_cohort")
        row["same_cohort_retrieval"] = {
            "jobs": len(observed),
            "recall_at_5": retrieval[variant]["at_5"]["overall"]["macro_recall_at_k"],
            "mrr_at_5": retrieval[variant]["at_5"]["overall"]["macro_mrr_at_k"],
            "ndcg_at_10": retrieval[variant]["at_10"]["overall"]["macro_ndcg_at_k"],
            "by_persona": {
                p: {"at_5": m, "at_10": retrieval[variant]["at_10"]["by_persona"][p]}
                for p, m in retrieval[variant]["at_5"]["by_persona"].items()
            },
        }
        row["replies"] = sum(r["replied"] for r in observed)
        row["hires"] = sum(r["hired"] for r in observed)
        row["reply_rate_per_assigned_job"] = row["replies"] / row["jobs"]
        row["reply_rate_per_submission"] = row["replies"] / row["submissions"]
        row["hire_rate_per_submission"] = row["hires"] / row["submissions"]
        for persona, metrics in row["by_persona"].items():
            metrics["replies"] = sum(r["replied"] for r in observed if r["persona"] == persona)
            metrics["hires"] = sum(r["hired"] for r in observed if r["persona"] == persona)
    original_arch = json.loads(
        Path("evals/results/gemini-orchestration-v1/analysis.json").read_text(encoding="utf-8")
    )
    architecture = copy.deepcopy(original_arch["conditions"])
    for condition, metrics in architecture.items():
        observed = [
            r for r in outcomes if r["group"] == "architecture" and r["condition"] == condition
        ]
        assert len(observed) == 50
        metrics["replies"] = sum(r["replied"] for r in observed)
        metrics["hires"] = sum(r["hired"] for r in observed)
        metrics["reply_rate_all_assigned"] = metrics["replies"] / 50
        metrics["hire_rate_all_assigned"] = metrics["hires"] / 50
    hand = [r for r in outcomes if r["group"] == "architecture" and r["condition"] == "hand_graph"]
    assignments = {r["id"]: r["strategy"] for r in hand}
    x2 = analyse_arms(assignments, hand)
    by_persona = {}
    x2_by_persona = {}
    for persona in sorted({r["persona"] for r in hand}):
        group = [r for r in hand if r["persona"] == persona]
        x2_by_persona[persona] = analyse_arms({r["id"]: r["strategy"] for r in group}, group)
        by_persona[persona] = {}
        for condition in architecture:
            group = [
                r
                for r in outcomes
                if r["group"] == "architecture"
                and r["condition"] == condition
                and r["persona"] == persona
            ]
            by_persona[persona][condition] = {
                "jobs": len(group),
                "submissions": sum(r["submitted"] for r in group),
                "replies": sum(r["replied"] for r in group),
                "hires": sum(r["hired"] for r in group),
            }
    result = {
        "data_origin": "Synthetic jobs and portfolios, real LLM-driven client decisions",
        "generator_runs_repeated": 0,
        "client_mode": "llm with fixed budget/eligibility guards",
        "rag": rag,
        "architecture": architecture,
        "x2_intention_to_treat": x2,
        "x2_by_persona": x2_by_persona,
        "architecture_by_persona": by_persona,
        "client_requests": len(read_lines(ROOT / "client-attempts.jsonl")),
        "client_decisions": len(read_lines(ROOT / "client-decisions.jsonl")),
        "client_model": json.loads((ROOT / "client-plan.json").read_text(encoding="utf-8"))[
            "model"
        ],
        "limits": "Outcomes are one-pass LLM decisions plus fixed eligibility/budget guards; "
        "not real clients or longitudinal negotiations. Batch context can couple decisions. "
        "V0/V3 retrieval uses the same nine proposal jobs and original portfolio generator, "
        "replayed at k=5 and k=10; it is retrospective synthetic topic-family gold, not human "
        "annotation. Draft quality uses all available drafts (5 vs 2); failures remain in "
        "assigned-job denominators. Generator timings/tokens are reused, client usage is separate.",
    }
    (ROOT / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    table = [
        "| Variant | Recall@5 | nDCG@10 | Unsupported / available proposal | Judge / 5 | "
        "LLM-client reply / submitted | p95 agent/job seconds | USD/proposal |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for variant, row in rag.items():
        m = row["same_cohort_retrieval"]
        table.append(
            f"| {variant.upper()} | {m['recall_at_5']:.3f} | {m['ndcg_at_10']:.3f} | "
            f"{row['unsupported_claims_per_available_proposal']:.2f} "
            f"(n={row['available_drafts']}) | "
            f"{row['mean_judge_quality']:.2f} | {row['replies']}/{row['submissions']} | "
            f"{row['p95_job_seconds']:.2f} | unknown |"
        )
    table.extend(
        [
            "",
            "All columns use the same nine matched jobs per variant and portfolio corpus. "
            "Retrieval is a retrospective CPU replay (k=5/10, synthetic topic-family gold); "
            "Generation observations are frozen. Quality is conditional on available drafts; "
            "failures remain in assigned-job totals. LLM clients assess the "
            "three submissions. Non-submissions cannot receive replies. Billing is unknown.",
            "",
            f"Intention-to-treat LLM replies: V0 {rag['v0']['replies']}/9; "
            f"V3 {rag['v3']['replies']}/9. This small cohort establishes no reliable winner.",
        ]
    )
    rendered = "\n".join(table)
    (ROOT / "results-table.md").write_text(rendered + "\n", encoding="utf-8")
    readme = Path("README.md")
    content = readme.read_text(encoding="utf-8")
    start, end = "<!-- rag-e2e-table:start -->", "<!-- rag-e2e-table:end -->"
    prefix, rest = content.split(start)
    _, suffix = rest.split(end)
    content = prefix + start + "\n\n" + rendered + "\n\n" + end + suffix
    readme.write_text(content, encoding="utf-8")
    print(
        json.dumps(
            {
                "requests": result["client_requests"],
                "decisions": result["client_decisions"],
                "rag_replies": {k: v["replies"] for k, v in rag.items()},
                "architecture_replies": {k: v["replies"] for k, v in architecture.items()},
                "x2": x2,
            }
        )
    )


if __name__ == "__main__":
    run()
