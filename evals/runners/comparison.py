"""Compare aligned recorded conditions; does not synthesize or execute experiments."""

import argparse
import math
from pathlib import Path
from statistics import median
from typing import Literal

from pydantic import Field, model_validator

from agent.handoffs import Contract
from evals.contracts import GoldJob, Outcome, Prediction
from evals.io import align, read_rows, write_result
from evals.scoring import decision_scores


class Condition(Contract):
    predictions: str
    outcomes: str


class Comparison(Contract):
    data_origin: Literal["supplied", "development"]
    gold: str
    conditions: dict[str, Condition] = Field(min_length=2)
    min_cases: int = Field(default=50, ge=1)


class ToolCase(Contract):
    id: str = Field(min_length=1)
    success: bool = Field(strict=True)
    correct_arguments: bool = Field(strict=True)
    invalid_calls: int = Field(ge=0, strict=True)
    tool_calls: int = Field(ge=0, strict=True)
    measured_tokens: int = Field(ge=0, strict=True)
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_calls(self):
        if self.invalid_calls > self.tool_calls:
            raise ValueError("Invalid calls cannot exceed all tool calls")
        return self


class ToolStudy(Contract):
    data_origin: Literal["supplied", "development"]
    conditions: dict[str, str] = Field(min_length=2)
    min_cases: int = Field(default=40, ge=1)


def p95(values):
    return sorted(values)[math.ceil(0.95 * len(values)) - 1] if values else None


def compare(manifest, kind):
    path = Path(manifest)
    inputs, result = {}, {}
    if kind == "tool_granularity":
        spec = ToolStudy.model_validate_json(path.read_text(encoding="utf-8-sig"))
        reference = None
        for name, filename in spec.conditions.items():
            source = (path.parent / filename).resolve()
            rows, meta = read_rows(source, ToolCase)
            ids = {row.id for row in rows}
            if reference is not None and ids != reference:
                raise ValueError("Every tool condition must evaluate exactly the same task IDs")
            reference = ids
            if len(rows) < spec.min_cases:
                raise ValueError("Tool study has fewer than its predeclared tasks")
            inputs[source] = meta
            calls = sum(row.tool_calls for row in rows)
            result[name] = {
                "tasks": len(rows),
                "success_rate": sum(row.success for row in rows) / len(rows),
                "correct_arguments_rate": sum(row.correct_arguments for row in rows) / len(rows),
                "invalid_calls": sum(row.invalid_calls for row in rows),
                "tool_calls": calls,
                "invalid_call_rate": sum(row.invalid_calls for row in rows) / calls
                if calls
                else None,
                "measured_tokens": sum(row.measured_tokens for row in rows),
                "median_seconds": median(row.elapsed_seconds for row in rows),
                "p95_seconds": p95([row.elapsed_seconds for row in rows]),
            }
    else:
        spec = Comparison.model_validate_json(path.read_text(encoding="utf-8-sig"))
        if kind == "orchestration_compare" and (
            set(spec.conditions) != {"react", "supervisor", "hand_graph"} or spec.min_cases < 50
        ):
            raise ValueError(
                "Orchestration study requires react, supervisor and hand_graph on at least 50 jobs"
            )
        if kind == "ablation" and "baseline" not in spec.conditions:
            raise ValueError("Ablations require a named baseline condition")
        gold_path = (path.parent / spec.gold).resolve()
        gold, meta = read_rows(gold_path, GoldJob)
        inputs[gold_path] = meta
        if len(gold) < spec.min_cases:
            raise ValueError("Comparison has fewer than its predeclared jobs")
        for name, condition in spec.conditions.items():
            predicted_path = (path.parent / condition.predictions).resolve()
            outcomes_path = (path.parent / condition.outcomes).resolve()
            predictions, meta = read_rows(predicted_path, Prediction)
            inputs[predicted_path] = meta
            outcomes, meta = read_rows(outcomes_path, Outcome)
            inputs[outcomes_path] = meta
            align(gold, outcomes)
            if len({row.event_id for row in outcomes}) != len(outcomes):
                raise ValueError("Duplicate outcome events cannot be counted")
            scored = decision_scores(gold, predictions)
            submitted = [row for row in outcomes if row.submitted]
            decisions = {row.id: row.bid for row in predictions}
            if any(not decisions[row.id] for row in submitted):
                raise ValueError("A submission conflicts with a recorded skip decision")
            times = [row.elapsed_seconds for row in predictions if row.elapsed_seconds is not None]
            tokens = [row.measured_tokens for row in predictions if row.measured_tokens is not None]
            compliance = [
                row.compliance_violations_caught
                for row in predictions
                if row.compliance_violations_caught is not None
            ]
            result[name] = {
                "decisions": scored,
                "submitted": len(submitted),
                "reply_rate": sum(row.replied for row in submitted) / len(submitted)
                if submitted
                else None,
                "measured_token_jobs": len(tokens),
                "measured_latency_jobs": len(times),
                "measured_tokens": sum(tokens) if len(tokens) == len(gold) else None,
                "median_seconds": median(times) if len(times) == len(gold) else None,
                "p95_seconds": p95(times) if len(times) == len(gold) else None,
                "compliance_violations_caught": sum(compliance)
                if len(compliance) == len(gold)
                else None,
            }
    return spec.data_origin, inputs, result


def main(kind):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        origin, inputs, result = compare(args.manifest, kind)
        import hashlib

        raw = Path(args.manifest).read_bytes()
        inputs[Path(args.manifest).resolve()] = {
            "name": Path(args.manifest).name,
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        write_result(args.output, metric=kind, data_origin=origin, inputs=inputs, results=result)
        print(f"Recorded {len(result)} conditions; data origin: {origin}")
    except (OSError, ValueError) as error:
        parser.exit(2, f"Comparison unavailable: {error}\n")
