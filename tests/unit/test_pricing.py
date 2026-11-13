from copy import deepcopy

import pytest

from agent.handoffs import JobSpec
from agent.pricing import budget_statistics, reference_price
from agent.proposal_nodes import ReviewRequired
from tests.unit.test_proposal_nodes import setup_nodes as base_setup_nodes

pricing_nodes = base_setup_nodes


def records():
    return [
        {
            "id": str(i),
            "client_id": "client",
            "currency": "USD",
            "billing_type": "hourly",
            "budget_min": n,
            "budget_max": n,
            "required_skills": ["Python", "pandas"],
            "synthetic": True,
        }
        for i, n in enumerate([20, 25, 30, 35, 1000, 40, 45, 50, 55, 60])
    ]


def target():
    return {
        "id": "current",
        "client_id": "client",
        "currency": "USD",
        "billing_type": "hourly",
        "required_skills": ["Python", "pandas"],
    }


def test_comparables_exclude_duplicates_self_wrong_units_and_currency():
    rows = records()
    valid = budget_statistics(target(), rows, provider="student_sim")
    invalid = []
    for change in (
        {"id": "current"},
        {"currency": "EUR"},
        {"billing_type": "fixed"},
        {"required_skills": ["Python"]},
        {"budget_max": float("nan")},
        {"budget_min": 80, "budget_max": 20},
        {"synthetic": False},
    ):
        invalid.append({**rows[0], "id": "bad" + str(len(invalid)), **change})
    assert budget_statistics(target(), rows + rows + invalid, provider="student_sim") == valid
    assert valid["market"]["median"] == 42.5
    assert valid["client"]["count"] == 10


def test_historical_and_generated_budgets_are_not_pooled_or_live_clients_joined():
    historical = [
        {
            **r,
            "id": "real" + r["id"],
            "budget_min": 80,
            "budget_max": 80,
            "provenance": {"base_text": "real_historical_job"},
        }
        for r in records()
    ]
    stats = budget_statistics(target(), records() + historical, provider="upwork")
    assert stats["market"]["count"] == 10 and stats["market"]["median"] == 80
    assert stats["client"]["count"] == 0


def test_sparse_history_falls_back_and_client_influence_is_bounded():
    assert (
        reference_price(
            budget_statistics(target(), records()[:4], provider="student_sim"), "hourly"
        )[0]
        is None
    )
    stats = budget_statistics(target(), records(), provider="student_sim")
    stats["client"]["median"] = 100000
    value, reason = reference_price(stats, "hourly")
    assert value == 0.75 * 42.5 + 0.25 * stats["market"]["p75"]
    assert "25% weight" in reason
    assert reference_price(stats, "fixed")[0] is None
    text_job = {**target(), "required_skills": [], "description": "Use Python and pandas"}
    assert budget_statistics(text_job, records(), provider="upwork")["market"]["count"] == 10


class Market:
    connects = 100

    async def pricing_statistics(self, job_id):
        assert job_id == "provider-job"
        return budget_statistics(target(), records(), provider="student_sim")

    async def balance(self):
        return {"connects": self.connects}


async def test_quote_uses_statistics_and_preserves_floor_budget_and_connects(pricing_nodes):
    nodes, state, *_ = pricing_nodes
    state["job"] = JobSpec(
        job_id="job1",
        title="Python",
        requirements=[],
        billing_type="hourly",
        budget_min=10,
        budget_max=50,
    )
    state["raw_job"].update(provider_job_id="provider-job", connects_cost=6)
    nodes.marketplace = Market()
    quote = (await nodes.pricing(state))["price"]
    assert quote.amount == 42.5 and "n=10" in quote.rationale
    state["job"].budget_max = 30
    assert (await nodes.pricing(state))["price"].amount == 30
    state["preferences"]["hourly_floor"] = 35
    with pytest.raises(ReviewRequired, match="minimum rate"):
        await nodes.pricing(state)
    state["preferences"]["hourly_floor"] = 20
    nodes.marketplace.connects = 0
    with pytest.raises(ReviewRequired, match="balance"):
        await nodes.pricing(state)
    nodes.marketplace.connects = 100
    state["raw_job"]["currency"] = "EUR"
    with pytest.raises(ReviewRequired, match="USD"):
        await nodes.pricing(state)


async def test_fixed_price_is_not_an_hourly_rate_and_outage_does_not_invent_history(pricing_nodes):
    from mcp_servers.marketplace.adapters.student_sim import MarketplaceUnavailable

    nodes, state, *_ = pricing_nodes
    state["job"] = JobSpec(
        job_id="job1",
        title="Fixed task",
        requirements=[],
        billing_type="fixed",
        budget_min=5,
        budget_max=10,
    )
    state["raw_job"].update(provider_job_id="provider-job", connects_cost=6)

    class Unavailable(Market):
        async def pricing_statistics(self, job_id):
            raise MarketplaceUnavailable("Offline")

    nodes.marketplace = Unavailable()
    quote = (await nodes.pricing(deepcopy(state)))["price"]
    assert quote.amount == 5 and "temporarily unavailable" in quote.rationale


async def test_live_host_statistics_never_use_synthetic_budgets_or_client_ids(tmp_path):
    import json
    from types import SimpleNamespace

    from agent.marketplace_port import MarketplaceResult
    from mcp_servers.marketplace.service import MarketplaceService

    class Adapter:
        async def get_job(self, job_id):
            assert job_id == "current"
            return MarketplaceResult(provider="upwork", data=target())

    service = MarketplaceService.__new__(MarketplaceService)
    service.provider, service.adapter = "upwork", Adapter()
    service.connected = lambda: None  # Account authorization has separate integration coverage.
    path = tmp_path / "historical.json"
    service.settings = SimpleNamespace(pricing_catalogue_path=path)
    for content in (None, "not JSON", json.dumps(records())):
        if content is not None:
            path.write_text(content)
        result = await service.pricing_statistics("current")
        assert result.data["market"]["count"] == 0
        assert result.data["client"]["count"] == 0
    rows = [{**r, "provenance": {"base_text": "real_historical_job"}} for r in records()]
    path.write_text(json.dumps(rows))
    result = await service.pricing_statistics("current")
    assert result.data["market"]["count"] == 10
    assert result.data["client"]["source"] == "unavailable_live_client_price_history"
