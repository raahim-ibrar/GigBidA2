"""Score an explicit experiment bundle and enforce predeclared quality gates.

This evaluates recorded outputs; it does not generate predictions or execute GigSim.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import Field

from agent.handoffs import Contract
from evals.contracts import GoldJob, Outcome, Prediction
from evals.io import align, read_rows, write_result
from evals.scoring import decision_scores, rag_scores


class Manifest(Contract):
    data_origin: Literal["supplied", "development"]
    gold: str
    predictions: str
    outcomes: str
    experiment_id: str = Field(min_length=1)
    min_cases: int = Field(default=30, ge=30)
    k: int = Field(default=5, ge=1, le=50)
    bid_f1_floor: float = Field(ge=0, le=1)
    unsupported_claim_rate_ceiling: float = Field(ge=0, le=1)


def evaluate_bundle(manifest_path, output_dir, *, require_supplied=False):
    path = Path(manifest_path)
    spec = Manifest.model_validate_json(path.read_text(encoding="utf-8-sig"))
    if require_supplied and spec.data_origin != "supplied":
        raise ValueError(
            "This gate requires supplied data; development fixtures are not research results"
        )
    gold_path, predicted_path, outcomes_path = [
        (path.parent / value).resolve() for value in (spec.gold, spec.predictions, spec.outcomes)
    ]
    gold, gold_meta = read_rows(gold_path, GoldJob)
    predictions, predicted_meta = read_rows(predicted_path, Prediction)
    outcomes, outcomes_meta = read_rows(outcomes_path, Outcome)
    align(gold, predictions)
    align(gold, outcomes)
    if len(gold) < spec.min_cases:
        raise ValueError(f"Expected at least {spec.min_cases} gold jobs; found {len(gold)}")
    if not {"ai_ml", "full_stack", "data_analyst"}.issubset({row.persona for row in gold}):
        raise ValueError("The smoke cohort must include all three supplied personas")
    if len({item.event_id for item in outcomes}) != len(outcomes):
        raise ValueError("Outcome event IDs must be unique")
    decisions = decision_scores(gold, predictions)
    rag = rag_scores(gold, predictions, spec.k)
    submitted = [item for item in outcomes if item.submitted]
    predicted = {item.id: item for item in predictions}
    if any(not predicted[item.id].bid for item in submitted):
        raise ValueError("A submitted proposal conflicts with its recorded skip decision")
    known_spend = [item.connects for item in submitted if item.connects is not None]
    observed = {
        "jobs": len(outcomes),
        "submitted": len(submitted),
        "reply_rate": sum(item.replied for item in submitted) / len(submitted)
        if submitted
        else None,
        "hire_rate": sum(item.hired for item in submitted) / len(submitted) if submitted else None,
        "known_connects_spend": sum(known_spend) if known_spend else None,
        "submissions_with_known_spend": len(known_spend),
    }
    overall = decisions["overall"]
    checks = {
        "bid_f1": overall["bid"]["f1"] is not None and overall["bid"]["f1"] >= spec.bid_f1_floor,
        "claim_annotations_complete": overall["claim_annotations_complete"],
        "unsupported_claim_rate": overall["unsupported_claim_rate"] is not None
        and overall["unsupported_claim_rate"] <= spec.unsupported_claim_rate_ceiling,
        "observed_submissions": bool(submitted),
    }
    inputs = {
        path.resolve(): {
            "name": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
        gold_path: gold_meta,
        predicted_path: predicted_meta,
        outcomes_path: outcomes_meta,
    }
    output = Path(output_dir)
    if any(
        (output / name).resolve() in inputs
        for name in ("retrieval.json", "decisions.json", "outcomes.json", "gate.json")
    ):
        raise ValueError("Output directory would overwrite an experiment input")
    for filename, kind, result in (
        ("retrieval.json", "retrieval", rag),
        ("decisions.json", "decisions", decisions),
        ("outcomes.json", "gigsim_outcomes", observed),
    ):
        write_result(
            output / filename,
            metric=kind,
            data_origin=spec.data_origin,
            inputs=inputs,
            results=result,
        )
    report = write_result(
        output / "gate.json",
        metric="quality_gate",
        data_origin=spec.data_origin,
        inputs=inputs,
        results={
            "experiment_id": spec.experiment_id,
            "checks": checks,
            "passed": all(checks.values()),
            "bid_f1_floor": spec.bid_f1_floor,
            "unsupported_claim_rate_ceiling": spec.unsupported_claim_rate_ceiling,
        },
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=os.getenv("GIGBID_EVAL_MANIFEST"))
    parser.add_argument("--output-dir", default="evals/results/latest")
    parser.add_argument("--require-supplied", action="store_true")
    args = parser.parse_args()
    if not args.manifest:
        parser.error(
            "Supply --manifest or GIGBID_EVAL_MANIFEST after collecting "
            "labelled outputs and simulator receipts"
        )
    try:
        report = evaluate_bundle(
            args.manifest, args.output_dir, require_supplied=args.require_supplied
        )
    except (OSError, ValueError) as error:
        parser.exit(2, f"Evaluation unavailable: {error}\n")
    print(json.dumps(report["results"]))
    if not report["results"]["passed"]:
        parser.exit(1, "Quality gate failed; inspect the recorded measurements.\n")


if __name__ == "__main__":
    main()
