"""Strict file scoring; running this does not execute agents or a marketplace."""

import argparse
import json

from evals.contracts import GoldJob, JudgeLabel, Outcome, Prediction
from evals.io import read_rows, write_result
from evals.metrics import cohen_kappa
from evals.scoring import decision_scores, rag_scores


def main(kind):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--data-origin", choices=("supplied", "development"), required=True)
    parser.add_argument("--min-cases", type=int, default=1)
    if kind in {"retrieval", "decisions"}:
        parser.add_argument("--gold", required=True)
        parser.add_argument("--predictions", required=True)
        parser.add_argument("--k", type=int, default=5)
    else:
        parser.add_argument("--observations", required=True)
    args = parser.parse_args()
    try:
        if args.min_cases < 1:
            raise ValueError("Minimum case count must be positive")
        if kind in {"retrieval", "decisions"}:
            gold, gold_meta = read_rows(args.gold, GoldJob)
            predictions, predicted_meta = read_rows(args.predictions, Prediction)
            rows = gold
            inputs = {args.gold: gold_meta, args.predictions: predicted_meta}
            result = (
                rag_scores(gold, predictions, args.k)
                if kind == "retrieval"
                else decision_scores(gold, predictions)
            )
        else:
            rows, meta = read_rows(
                args.observations, JudgeLabel if kind == "judge_calibration" else Outcome
            )
            inputs = {args.observations: meta}
            if kind == "judge_calibration":
                result = cohen_kappa([item.human for item in rows], [item.judge for item in rows])
            else:
                if len({item.event_id for item in rows}) != len(rows):
                    raise ValueError("Outcome event IDs must be unique")
                submitted = [item for item in rows if item.submitted]
                known_spend = [item.connects for item in submitted if item.connects is not None]
                result = {
                    "observed_jobs": len(rows),
                    "submitted": len(submitted),
                    "replies": sum(item.replied for item in submitted),
                    "hires": sum(item.hired for item in submitted),
                    "reply_rate": sum(item.replied for item in submitted) / len(submitted)
                    if submitted
                    else None,
                    "hire_rate": sum(item.hired for item in submitted) / len(submitted)
                    if submitted
                    else None,
                    "known_connects_spend": sum(known_spend) if known_spend else None,
                    "submissions_with_known_spend": len(known_spend),
                }
        if len(rows) < args.min_cases:
            raise ValueError(f"Expected at least {args.min_cases} cases; found {len(rows)}")
        write_result(
            args.output, metric=kind, data_origin=args.data_origin, inputs=inputs, results=result
        )
        print(
            json.dumps({"output": args.output, "cases": len(rows), "data_origin": args.data_origin})
        )
    except (OSError, ValueError) as error:
        parser.exit(2, f"Evaluation unavailable: {error}\n")
