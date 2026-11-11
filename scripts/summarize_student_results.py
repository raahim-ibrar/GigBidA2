"""Render measured results and retained failures; incomplete studies stay incomplete."""

import json
import statistics
from collections import Counter
from pathlib import Path


def quantile(values, n):
    if not values:
        return None
    return (
        statistics.quantiles(values, n=100, method="inclusive")[n - 1]
        if len(values) > 1
        else values[0]
    )


def summarize():
    retrieval_path = Path("evals/results/student-retrieval/results.json")
    retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))["results"]
    lines = [
        "# Measured student studies",
        "",
        "## Controlled retrieval",
        "",
        "Real BGE-small embeddings and MiniLM reranking; 60 answerable synthetic tasks "
        "and six unrelated tasks. Project-identity gold is not human-labelled real-job relevance.",
        "",
        "| Variant | Recall@5 | MRR@5 | nDCG@10 | p95 seconds | "
        "Unanswerable tasks returning evidence |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, result in retrieval["variants"].items():
        a, b = result["at_5"]["overall"], result["at_10"]["overall"]
        lines.append(
            f"| {name.upper()} | {a['macro_recall_at_k']:.3f} | {a['macro_mrr_at_k']:.3f} | "
            f"{b['macro_ndcg_at_k']:.3f} | {result['p95_seconds']:.3f} | "
            f"{a['unanswerable_with_retrieval']}/6 |"
        )
    lines += [
        "",
        "H1 was not supported: V3 did not increase Recall@5 over V0; both reached 1.000 "
        "on this easy controlled cohort. V1 lost recall when generic requirements "
        "dominated the fusion. "
        "V3 improved ordering, while V8 abstained on the six unrelated tasks at greater latency.",
        "",
        "The predeclared selection rule (Recall@5, then nDCG@10, then p95) selects **V3**. "
        "V8 has better abstention but is slower. This is a limited synthetic-corpus choice, "
        "not proof of better real-job outcomes. V3→V2 removes reranking; V2→V0 removes lexical "
        "fusion; V8→V3 removes correction. The raw per-persona metrics and rankings remain in "
        "`evals/results/student-retrieval/`.",
        "",
        "## Open-model graph study",
        "",
    ]
    root = Path("work/generation-study-v3")
    public = Path("evals/results/student-generation-v3")
    public.mkdir(parents=True, exist_ok=True)
    summaries, failures = {}, []
    for source in sorted(root.glob("qwen*.jsonl")):
        rows = [
            json.loads(line)
            for line in source.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        times = [row["prediction"]["elapsed_seconds"] for row in rows]
        usage = [call for row in rows for call in row["usage"]]
        seconds = sum(call.get("generation_seconds", 0) for call in usage)
        generated = sum(call.get("output_tokens", 0) for call in usage)
        summary = {
            "recorded_jobs": len(rows),
            "planned_jobs": 30,
            "complete": len(rows) == 30,
            "statuses": dict(Counter(row["status"] for row in rows)),
            "p50_job_seconds": statistics.median(times) if times else None,
            "p95_job_seconds": quantile(times, 95),
            "measured_tokens": sum(row["prediction"]["measured_tokens"] or 0 for row in rows),
            "generation_tokens_per_second": generated / seconds if seconds else None,
            "inference_api_usd": sum(call.get("usd", 0) for call in usage),
            "cost_limit": "Hardware/electricity not monetised; failed usage may be unknown",
            "research_submissions": sum(row["outcome"]["submitted"] for row in rows),
            "research_replies": sum(row["outcome"]["replied"] for row in rows),
            "research_hires": sum(row["outcome"]["hired"] for row in rows),
            "claim_annotations": "not collected from a human/calibrated independent judge",
        }
        summaries[source.stem] = summary
        (public / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        for row in rows:
            if row["error"]:
                reason = row["error"]
                category = (
                    "screening grounding"
                    if "screening answer" in reason
                    else "cover grounding"
                    if "cover text" in reason
                    else "model/schema failure"
                    if "configured model" in reason
                    else "other runtime failure"
                )
                failures.append(
                    {
                        "model": source.stem,
                        "job_id": row["id"],
                        "run_id": row["run_id"],
                        "category": category,
                        "error": reason,
                    }
                )
        lines += [
            f"### {source.stem}",
            "",
            f"Recorded **{len(rows)}/30** jobs. "
            + (
                "This model cohort is complete."
                if len(rows) == 30
                else "Partial cohort: do not use it as a completed comparison."
            ),
            "",
            f"Statuses: `{json.dumps(summary['statuses'])}`. "
            f"Measured job p95: {summary['p95_job_seconds']:.2f}s. "
            f"Research-only candidate submissions: {summary['research_submissions']}; "
            f"rule-client replies: {summary['research_replies']}; "
            f"hires: {summary['research_hires']}.",
            "",
        ]
    plan = root / "plan.json"
    if plan.exists():
        (public / "plan.json").write_text(plan.read_text(encoding="utf-8"), encoding="utf-8")
    (public / "progress.json").write_text(
        json.dumps(
            {
                "data_origin": "synthetic",
                "complete": len(summaries) == 2
                and all(item["complete"] for item in summaries.values()),
                "models": summaries,
                "limitations": (
                    "Not instructor GigSim; rule-client outcomes; no human calibration/panel. "
                    "Candidates were scored in a separate research-only simulator "
                    "without forging application approvals."
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (public / "failures.json").write_text(json.dumps(failures, indent=2) + "\n", encoding="utf-8")
    lines += [
        "## Failure analysis",
        "",
        "Errors and skips stay in the cohort. The small-model "
        "runs often fail grounding; control tests do not establish proposal quality.",
        "",
        "| Model | Job | Category | Observed failure |",
        "|---|---|---|---|",
    ]
    for item in failures[:12]:
        lines.append(
            f"| {item['model']} | {item['job_id']} | {item['category']} | {item['error']} |"
        )
    lines += [
        "",
        "Diagnostic fixes before frozen v3: exclude exact trusted source UUIDs from "
        "numerical-achievement checks, keep source IDs out of prose, and request concise verifier "
        "reasons. Earlier setup/diagnostic runs are retained locally. Failures that remain in v3 "
        "are not erased or counted as improvements. These changes have not been isolated in a "
        "causal ablation.",
        "",
        "## Still missing",
        "",
        "Human calibration (30 items), a blind human panel, the 40-task tool-design comparison, "
        "and the 50-job ReAct/supervisor/hand-graph study are not completed here. No result is "
        "invented for them. Hidden-test measurements are unavailable before grading.",
    ]
    Path("docs/RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"Updated results: {len(summaries)} model files, {len(failures)} retained failures."
    )
    return summaries


if __name__ == "__main__":
    summarize()
