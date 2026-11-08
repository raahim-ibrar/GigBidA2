import json

import pytest

from evals.runners.comparison import compare


def write_rows(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows))


def test_tool_comparisons_require_the_same_tasks_and_measure_invalid_calls(tmp_path):
    rows = [
        {
            "id": "a",
            "success": True,
            "correct_arguments": True,
            "invalid_calls": 0,
            "tool_calls": 2,
            "measured_tokens": 100,
            "elapsed_seconds": 1.0,
        },
        {
            "id": "b",
            "success": False,
            "correct_arguments": False,
            "invalid_calls": 1,
            "tool_calls": 1,
            "measured_tokens": 50,
            "elapsed_seconds": 3.0,
        },
    ]
    write_rows(tmp_path / "first.jsonl", rows)
    write_rows(tmp_path / "second.jsonl", list(reversed(rows)))
    manifest = tmp_path / "study.json"
    manifest.write_text(
        json.dumps(
            {
                "data_origin": "development",
                "min_cases": 2,
                "conditions": {"atomic": "first.jsonl", "coarse": "second.jsonl"},
            }
        )
    )
    origin, _, result = compare(manifest, "tool_granularity")
    assert origin == "development"
    assert result["atomic"]["success_rate"] == 0.5
    assert result["atomic"]["invalid_call_rate"] == pytest.approx(1 / 3)
    assert result["atomic"]["p95_seconds"] == 3
    write_rows(tmp_path / "second.jsonl", rows[:1])
    with pytest.raises(ValueError, match="same task IDs"):
        compare(manifest, "tool_granularity")


def test_ablation_retains_unknown_usage_and_rejects_missing_baseline(tmp_path):
    write_rows(
        tmp_path / "gold.jsonl", [{"id": "a", "persona": "fixture", "bid": True, "scam": False}]
    )
    write_rows(tmp_path / "predictions.jsonl", [{"id": "a", "bid": True, "scam": False}])
    write_rows(
        tmp_path / "outcomes.jsonl",
        [
            {
                "id": "a",
                "event_id": "fixture",
                "source": "gigsim",
                "submitted": True,
                "replied": False,
                "hired": False,
                "followup_complete": True,
            }
        ],
    )
    condition = {"predictions": "predictions.jsonl", "outcomes": "outcomes.jsonl"}
    manifest = tmp_path / "ablation.json"
    spec = {
        "data_origin": "development",
        "min_cases": 1,
        "gold": "gold.jsonl",
        "conditions": {"baseline": condition, "no_memory": condition},
    }
    manifest.write_text(json.dumps(spec))
    _, _, result = compare(manifest, "ablation")
    assert result["baseline"]["measured_tokens"] is None
    assert result["baseline"]["p95_seconds"] is None
    spec["conditions"] = {"condition_a": condition, "condition_b": condition}
    manifest.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="named baseline"):
        compare(manifest, "ablation")
    with pytest.raises(ValueError, match="at least 50"):
        compare(manifest, "orchestration_compare")
