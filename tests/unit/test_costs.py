import pytest

from agent.costs import cost_summary, priced_usage


def usage(**kwargs):
    return {
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
        "role": "writer",
        "input_tokens": 1000,
        "output_tokens": 200,
        **kwargs,
    }


def test_decimal_rates_snapshot_and_actual_billing_separation():
    row = priced_usage(usage())
    assert row["estimated_usd"] == 0.00027 and row["usd"] is None
    assert row["input_usd_per_million"] == "0.15"
    assert row["rate_checked_on"] == "2026-11-13" and row["rate_source"].startswith(
        "https://console.groq.com/"
    )
    summary = cost_summary([row] * 1000, charged_tokens=1200000)
    assert summary.estimated_usd == 0.27 and summary.complete
    assert summary.actual_api_usd is None  # A list price does not prove an invoice.


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "unknown-model"},
        {"input_tokens": None},
        {"output_tokens": -1},
        {"input_tokens": True},
        {"usage_known": False},
    ],
)
def test_unknown_model_or_usage_is_not_priced_as_zero(changes):
    row = priced_usage(usage(**changes))
    assert row["estimated_usd"] is None
    result = cost_summary([row])
    assert result.estimated_usd is None and result.unknown_cost_calls == 1 and not result.complete


def test_mixed_partial_totals_legacy_events_and_reservations():
    known = priced_usage(usage())
    legacy = usage()  # No retrospective application of today's prices.
    summary = cost_summary([known, legacy], charged_tokens=3000)
    assert summary.estimated_usd == 0.00027 and summary.unknown_cost_calls == 1
    assert summary.unaccounted_tokens == 600 and not summary.complete
    assert cost_summary([known], active=True).complete is False
    assert cost_summary([]).estimated_usd is None


def test_local_api_zero_is_explicitly_distinct_from_hosted_estimate():
    row = priced_usage(usage(provider="ollama", model="qwen3.5:4b"))
    report = cost_summary([row], charged_tokens=1200)
    assert report.actual_api_usd == report.estimated_usd == 0 and report.complete
    assert "electricity excluded" in row["cost_basis"]
    assert (
        priced_usage(usage(provider="gemini", model="gemini-3.5-flash-lite"))["estimated_usd"]
        == 0.0008
    )
