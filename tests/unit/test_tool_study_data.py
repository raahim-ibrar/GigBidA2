import json
from pathlib import Path

from jsonschema import validate

from evals.runners.student_tools import dataset


def test_all_forty_gold_calls_are_valid_against_the_actual_mcp_schema_snapshot():
    registrations = json.loads(Path("tests/contract/mcp_schema.json").read_text(encoding="utf-8"))
    schemas = {tool["name"]: tool["inputSchema"] for tool in registrations["marketplace"]}
    tasks = dataset()
    assert len(tasks) == 40 and len({task["id"] for task in tasks}) == 40
    # Keep the measured forty-call cohort unchanged. Pricing statistics was
    # introduced afterward and has separate schema/host/adapter coverage.
    assert {task["expected"]["name"] for task in tasks} == set(schemas) - {
        "get_pricing_statistics"
    }
    for task in tasks:
        call = task["expected"]
        validate(call["arguments"], schemas[call["name"]])
