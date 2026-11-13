from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from agent.tracing import TracedSession, build_spans


def test_recovery_trace_exports_observations_without_private_audit_details():
    start = datetime.now(UTC)
    run = SimpleNamespace(
        id=str(uuid4()),
        kind="bid",
        created_at=start,
        updated_at=start + timedelta(seconds=8),
        status="submitted",
        steps=2,
        tokens=50,
    )
    event = SimpleNamespace(
        id=1,
        kind="recovery_observed",
        created_at=start + timedelta(seconds=5),
        details={
            "elapsed_seconds": 3,
            "process_exit_observed": True,
            "readiness_observed": True,
            "pid": 123,
            "private": "PRIVATE_RECOVERY_CANARY",
        },
    )
    spans = build_spans(run, [event])
    assert spans[1]["name"] == "control:api_restart"
    assert spans[1]["end_time"] - spans[1]["start_time"] == timedelta(seconds=3)
    assert spans[1]["outputs"] == {"process_exit_observed": True, "readiness_observed": True}
    assert "PRIVATE_RECOVERY_CANARY" not in str(spans) and "pid" not in str(spans)


def test_export_contains_measured_spans_and_no_source_payload():
    start = datetime.now(UTC)
    run = SimpleNamespace(
        id=str(uuid4()),
        kind="bid",
        created_at=start,
        updated_at=start + timedelta(seconds=8),
        status="awaiting_approval",
        steps=1,
        tokens=50,
    )

    def event(identity, kind, second, **details):
        return SimpleNamespace(
            id=identity,
            kind=kind,
            created_at=start + timedelta(seconds=second),
            details={
                **details,
                "prompt": "PRIVATE_CV_CANARY",
                "key": "API_KEY_CANARY",
                "arguments": {"query": "PRIVATE_CV_CANARY"},
                "result": {"text": "PRIVATE_CV_CANARY"},
            },
        )

    spans = build_spans(
        run,
        [
            event(1, "node_started", 1, node="writer"),
            event(
                2,
                "mcp_call",
                2,
                server="portfolio",
                tool="search_evidence",
                elapsed_seconds=0.5,
                ok=True,
            ),
            event(
                3,
                "model_usage",
                5,
                role="writer",
                model="example-model",
                provider="groq",
                elapsed_seconds=2,
                input_tokens=30,
                output_tokens=20,
            ),
            event(4, "node_completed", 6, node="writer"),
        ],
    )
    assert len(spans) == 4
    assert {span["trace_id"] for span in spans} == {run.id}
    assert spans[-1]["parent_run_id"] == spans[1]["id"]
    assert spans[-1]["outputs"]["usage_metadata"]["total_tokens"] == 50
    assert spans[-1]["end_time"] - spans[-1]["start_time"] == timedelta(seconds=2)
    assert "PRIVATE_CV_CANARY" not in repr(spans) and "API_KEY_CANARY" not in repr(spans)
    assert build_spans(run, []) == build_spans(run, [])


@pytest.mark.asyncio
async def test_mcp_trace_records_no_arguments_or_results():
    calls = []

    class Session:
        async def call_tool(self, *args, **kwargs):
            return SimpleNamespace(isError=False, secret="PRIVATE_RESULT")

    class Store:
        def event(self, *args):
            calls.append(args)

    wrapped = TracedSession(Session(), Store(), "tenant", "run", "lease", "portfolio")
    await wrapped.call_tool("search_evidence", {"query": "PRIVATE_QUERY"})
    assert calls[0][3] == "mcp_call" and calls[0][4]["ok"]
    assert "PRIVATE_QUERY" not in repr(calls) and "PRIVATE_RESULT" not in repr(calls)


def test_unknown_model_usage_is_not_exported_as_zero_tokens():
    start = datetime.now(UTC)
    run = SimpleNamespace(
        id=str(uuid4()),
        kind="bid",
        created_at=start,
        updated_at=start,
        status="needs_attention",
        steps=1,
        tokens=100,
    )
    event = SimpleNamespace(
        id=1,
        kind="model_usage",
        created_at=start,
        details={
            "provider": "groq",
            "model": "fixture",
            "role": "writer",
            "usage_known": False,
            "input_tokens": None,
            "output_tokens": None,
            "usd": None,
            "estimated_usd": None,
        },
    )
    output = build_spans(run, [event])[-1]["outputs"]
    assert output["usage_known"] is False and "usage_metadata" not in output
    assert output["usd"] is None and output["estimated_usd"] is None
