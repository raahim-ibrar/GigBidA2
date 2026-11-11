from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from agent.marketplace_port import ProposalWrite, SearchJobs
from mcp_servers.marketplace.adapters.student_sim import MarketplaceUnavailable, StudentSimAdapter
from simulator.app import create_app
from simulator.catalogue import jobs
from simulator.client import tick
from simulator.store import SimConflict, SimStore


@pytest.fixture
def sim(tmp_path):
    app = create_app(tmp_path / "sim.sqlite", api_key="test-only", per_persona=10)
    tenant = str(uuid4())
    headers = {"Authorization": "Bearer test-only", "X-Tenant-ID": tenant}
    return app, tenant, headers


def proposal(job, key="test-operation-key"):
    return ProposalWrite(
        job_id=job["id"],
        text=(
            "I propose a Python document search baseline using embeddings and retrieval. "
            "I would first validate inputs and add tests before implementation."
        ),
        bid_amount=job["budget_min"],
        idempotency_key=key,
        dry_run=False,
    )


@pytest.mark.asyncio
async def test_llm_client_outbox_is_durable_and_outages_do_not_invent_outcomes(tmp_path):
    catalogue = jobs(per_persona=3)
    tenant = str(uuid4())
    path = tmp_path / "llm-client.sqlite"
    store = SimStore(path, catalogue, client_mode="llm")
    request = proposal(catalogue[1]).model_dump(exclude={"dry_run"})
    effect = store.write(tenant, "submit_proposal", request)
    assert [row["stage"] for row in store.events(tenant)] == ["submitted"]

    async def outage(claim):
        raise ConnectionError("Fixture outage")

    assert await tick(store, resolver=outage)
    assert [row["stage"] for row in store.events(tenant)] == ["submitted"]
    restored = SimStore(path, catalogue, client_mode="llm")
    with restored.db() as db:
        db.execute("UPDATE pending_clients SET next_at=0")

    async def client_model(claim):
        assert claim["proposal_id"] == effect["id"]
        return "hire", {"model": "deterministic-control-fixture", "output_tokens": 3}

    assert await tick(restored, resolver=client_model)
    assert restored.events(tenant)[-1]["stage"] == "hired"
    assert not await tick(restored, resolver=client_model)
    assert len(restored.messages(tenant, effect["id"])) == 1
    assert restored.balance(tenant) == 94
    assert restored.write(tenant, "submit_proposal", request)["id"] == effect["id"]


def test_authenticated_reads_do_not_leak_gold_and_preview_spends_nothing(sim):
    app, tenant, headers = sim
    with TestClient(app) as client:
        assert client.get("/jobs").status_code == 401
        response = client.get("/jobs", headers=headers).json()
        assert response["source"] == "student_sim"
        assert "gold" not in response["items"][0]
        job = response["items"][1]
        body = proposal(job).model_copy(update={"dry_run": True}).model_dump()
        assert (
            client.post("/proposals", json=body, headers=headers).json()["connects_cost"]
            == job["connects_cost"]
        )
        assert client.get("/balance", headers=headers).json()["connects"] == 100
        assert client.get("/events", headers=headers).json()["items"] == []


def test_concurrent_idempotency_debits_once_and_persists_after_restart(tmp_path):
    catalogue = jobs(per_persona=3)
    store = SimStore(tmp_path / "sim.sqlite", catalogue)
    tenant = str(uuid4())
    body = proposal(catalogue[1]).model_dump(exclude={"dry_run"})
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: store.write(tenant, "submit_proposal", body), range(4)))
    assert len({result["id"] for result in results}) == 1
    assert store.balance(tenant) == 100 - catalogue[1]["connects_cost"]
    restored = SimStore(tmp_path / "sim.sqlite", catalogue)
    assert restored.write(tenant, "submit_proposal", body) == results[0]
    assert store.messages(tenant, results[0]["id"])[0]["sender"] == "client"
    assert store.events(tenant)[-1]["stage"] == "hired"
    with pytest.raises(SimConflict):
        store.write(tenant, "submit_proposal", {**body, "text": "Changed"})
    with pytest.raises(KeyError):
        store.messages(str(uuid4()), results[0]["id"])


@pytest.mark.asyncio
async def test_http_adapter_protocol_and_outage_recovery(sim):
    app, tenant, _ = sim
    adapter = StudentSimAdapter(
        "http://sim", "test-only", tenant, transport=httpx.ASGITransport(app=app)
    )
    found = await adapter.search_jobs(SearchJobs(query="document search"))
    job = next(item for item in found.data["items"] if not item["description"].startswith("unpaid"))
    # Choose the known non-scam scenario rather than relying on the search ordering.
    job = app.state.store.jobs["student-4016-ai_ml-001"]
    result = await adapter.submit_proposal(proposal(job))
    assert result.provider == "student_sim"
    assert (await adapter.list_messages(result.data["id"])).data["items"]
    app.state.fault = "unavailable"
    with pytest.raises(MarketplaceUnavailable):
        await adapter.get_connects_balance()
    app.state.fault = "normal"
    assert (await adapter.get_connects_balance()).data["connects"] == 94


def test_insufficient_balance_rolls_back_all_effects(tmp_path):
    catalogue = jobs(per_persona=3)
    store = SimStore(tmp_path / "poor.sqlite", catalogue, starting_connects=1)
    tenant = str(uuid4())
    with pytest.raises(SimConflict, match="Insufficient"):
        store.write(
            tenant, "submit_proposal", proposal(catalogue[1]).model_dump(exclude={"dry_run"})
        )
    assert store.balance(tenant) == 1 and store.events(tenant) == []
