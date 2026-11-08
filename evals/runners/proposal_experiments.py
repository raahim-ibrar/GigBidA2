"""Create a frozen X2 assignment plan or analyse completed recorded follow-up."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from agent.handoffs import Contract
from evals.experiments import analyse_arms, assign_arms
from evals.io import read_rows, write_result


class ExperimentJob(Contract):
    id: str = Field(min_length=1)
    persona: str = Field(min_length=1)
    category: str = Field(min_length=1)


class Observation(Contract):
    id: str = Field(min_length=1)
    replied: bool = Field(strict=True)
    followup_complete: bool = Field(strict=True)
    followup_window: str = Field(min_length=1)


class Plan(Contract):
    assignments: dict[str, Literal["evidence_first", "problem_first"]]
    seed: int
    followup_window: str = Field(min_length=1)
    alpha: float = Field(gt=0, lt=1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("assign", "analyse"))
    parser.add_argument(
        "--input", required=True, help="Jobs JSONL for assign; frozen plan JSON for analyse"
    )
    parser.add_argument("--observations")
    parser.add_argument("--output", required=True)
    parser.add_argument("--data-origin", choices=("supplied", "development"), required=True)
    parser.add_argument("--seed", type=int, default=4016)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--followup-window", help="Predeclared, fixed simulator follow-up horizon")
    args = parser.parse_args()
    try:
        if args.mode == "assign":
            jobs, meta = read_rows(args.input, ExperimentJob)
            plan = Plan(
                assignments=assign_arms([item.model_dump() for item in jobs], args.seed),
                seed=args.seed,
                followup_window=args.followup_window or "",
                alpha=args.alpha,
            )
            if set(plan.assignments.values()) != {"evidence_first", "problem_first"}:
                raise ValueError("Plan must include both experiment arms")
            inputs, result = {args.input: meta}, plan.model_dump()
        else:
            raw = Path(args.input).read_bytes()
            saved = json.loads(raw)
            if saved["data_origin"] != args.data_origin or saved["metric"] != "x2_assignment":
                raise ValueError("Plan provenance or metric does not match")
            plan = Plan.model_validate(saved["results"])
            observations, meta = read_rows(args.observations or "", Observation)
            if any(item.followup_window != plan.followup_window for item in observations):
                raise ValueError("Follow-up windows differ from the predeclared plan")
            inputs = {
                args.input: {
                    "name": Path(args.input).name,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                },
                args.observations: meta,
            }
            result = analyse_arms(
                plan.assignments, [item.model_dump() for item in observations], plan.alpha
            )
        write_result(
            args.output,
            metric="x2_assignment" if args.mode == "assign" else "x2_analysis",
            data_origin=args.data_origin,
            inputs=inputs,
            results=result,
        )
        print(json.dumps({"output": args.output, "data_origin": args.data_origin}))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f"Experiment unavailable: {error}\n")


if __name__ == "__main__":
    main()
