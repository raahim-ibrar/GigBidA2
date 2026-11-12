"""Derive final research tables from frozen observations; never rerun inference."""

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean, median

from evals.experiments import analyse_arms

ROOT = Path("evals/results/gemini-orchestration-v1")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def p95(values):
    return sorted(values)[math.ceil(len(values) * 0.95) - 1]


def failure_category(error):
    if not error:
        return None
    value = error.lower()
    if "budget" in value:
        return "token_or_step_budget"
    if "timeout" in value:
        return "provider_timeout"
    if "ground" in value or "verified" in value:
        return "grounding_guard"
    if "modelunavailable" in value or "gemini" in value:
        return "provider_or_structured_output"
    return "other_observed_stop"


def main():
    plan = read(ROOT / "plan.json")
    rows = [json.loads(x) for x in (ROOT / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    gold = {x["id"]: x["gold"]["bid"] for x in plan["jobs"]}
    scam_ids = {x["id"] for x in plan["jobs"] if x["gold"]["scam"]}
    expected = {(j, c) for j in gold for c in plan["conditions"]}
    assert len(rows) == 150 and {(r["id"], r["condition"]) for r in rows} == expected
    hashes = {
        name: hashlib.sha256((ROOT / "source-snapshot" / name).read_bytes()).hexdigest()
        for name in plan["source_hashes"]
    }
    assert hashes == plan["source_hashes"], "Frozen source snapshot is inconsistent"

    def summary(selected):
        measured = [r for r in selected if r["decision"] is not None]
        good = [r for r in selected if not r["error"]]

        def correct(r):
            return r["decision"] is not None and ((r["decision"] == "bid") == gold[r["id"]])

        return {
            "n": len(selected),
            "error_free": len(good),
            "errors": sum(bool(r["error"]) for r in selected),
            "error_categories": dict(
                Counter(failure_category(r["error"]) for r in selected if r["error"])
            ),
            "decision_observed_n": len(measured),
            "decision_stage_correct_n": sum(map(correct, selected)),
            "decision_stage_accuracy_all_assigned": sum(map(correct, selected)) / len(selected),
            "error_free_correct_decision_n": sum(map(correct, good)),
            "error_free_correct_decision_rate_all_assigned": sum(map(correct, good))
            / len(selected),
            "submissions": sum(r["outcome"]["submitted"] for r in selected),
            "replies": sum(r["outcome"]["replied"] for r in selected),
            "drafts_available": sum(bool(r["candidate"].get("text")) for r in selected),
            "measured_tokens_total": sum(r["measured_tokens"] for r in selected),
            "measured_tokens_mean": mean(r["measured_tokens"] for r in selected),
            "unknown_usage_calls": sum(r["unknown_usage_calls"] for r in selected),
            "wall_seconds_median": median(r["elapsed_seconds"] for r in selected),
            "wall_seconds_p95_nearest_rank": p95([r["elapsed_seconds"] for r in selected]),
            "draft_policy_flags": sum(len(r["policy_violations"]) for r in selected),
            "scam_controls_n": sum(r["id"] in scam_ids for r in selected),
            "scam_controls_rejected": sum(
                r["id"] in scam_ids and r["decision"] in {"skip", "watch"} for r in selected
            ),
            "scam_control_submissions": sum(
                r["id"] in scam_ids and r["outcome"]["submitted"] for r in selected
            ),
        }

    hand = [r for r in rows if r["condition"] == "hand_graph"]
    observations = [
        {
            "id": r["id"],
            "replied": r["outcome"]["replied"],
            "followup_complete": r["outcome"]["followup_complete"],
        }
        for r in hand
    ]
    result = {
        "data_origin": "fully synthetic research jobs, portfolios and rule-client outcomes",
        "n_jobs": 50,
        "n_runs": 150,
        "source_snapshot_verified": True,
        "raw_sha256": hashlib.sha256((ROOT / "runs.jsonl").read_bytes()).hexdigest(),
        "conditions": {
            c: summary([r for r in rows if r["condition"] == c]) for c in plan["conditions"]
        },
        "by_model_and_condition": {
            m: {
                c: summary([r for r in rows if r["condition"] == c and r["model"] == m])
                for c in plan["conditions"]
            }
            for m in plan["study_models"]
        },
        "x2_intention_to_treat": analyse_arms(plan["strategies"], observations),
        "x2_by_persona": {},
        "by_persona_and_condition": {
            persona: {
                c: summary([r for r in rows if r["condition"] == c and r["persona"] == persona])
                for c in plan["conditions"]
            }
            for persona in sorted({r["persona"] for r in rows})
        },
        "limits": [
            "Decision-stage accuracy includes decisions retained before "
            "later errors; it is not end-to-end success.",
            "All assigned jobs remain in outcome denominators. "
            "Failed/non-submitted jobs count as no reply.",
            "Rules, templates, model blocking, API outages and token "
            "reservations affect results; this is a systems comparison, not "
            "an isolated model-size effect.",
            "Successful-call tokens are measured; unknown failure usage is "
            "not fabricated. Hosted billing is unknown.",
            "Wall latency includes local request throttling and retries "
            "within a recorded attempt, but not all between-attempt "
            "daily-quota waits.",
            "Zero draft-policy flags is not zero attack success: injected "
            "jobs may be rejected before a draft exists. No before/after "
            "defence ablation was run.",
            "Pooled Fisher p-value ignores blocked assignment strata; "
            "per-persona arms are also reported. Rule-client reply is not a "
            "real client outcome.",
        ],
        "failures": [
            {
                "job_id": r["id"],
                "condition": r["condition"],
                "model": r["model"],
                "category": failure_category(r["error"]),
                "error": r["error"],
            }
            for r in rows
            if r["error"]
        ],
    }
    for persona in sorted({r["persona"] for r in hand}):
        ids = {r["id"] for r in hand if r["persona"] == persona}
        result["x2_by_persona"][persona] = analyse_arms(
            {k: v for k, v in plan["strategies"].items() if k in ids},
            [o for o in observations if o["id"] in ids],
        )
    (ROOT / "analysis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("conditions", "x2_intention_to_treat")}, indent=2))


if __name__ == "__main__":
    main()
