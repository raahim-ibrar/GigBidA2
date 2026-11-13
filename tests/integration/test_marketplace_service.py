from uuid import uuid4

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agent.handoffs import PriceQuote, ProposalDraft, WritePreview
from agent.marketplace_client import MarketplaceMCP
from agent.marketplace_port import ProposalWrite
from agent.proposal_nodes import draft_digest
from agent.run_store import RunConflict, RunStore
from apps.api.models import FreelancerProfile, MarketplaceWrite
from apps.api.schemas.proposals import ReviewRun
from mcp_servers.marketplace.adapters.student_sim import MarketplaceRejected, StudentSimAdapter
from mcp_servers.marketplace.factory import create_marketplace_server
from mcp_servers.marketplace.service import MarketplaceService
from simulator.app import create_app
from tests.integration.test_runs import register


@pytest.fixture
def market(client, account_app, tmp_path):
    user = register(client, "marketplace-fixture@example.org")
    tenant = user["id"]
    sim = create_app(tmp_path / "sim.sqlite", api_key="test-only", per_persona=3)
    adapter = StudentSimAdapter(
        "http://sim", "test-only", tenant, transport=httpx.ASGITransport(app=sim)
    )
    accounts = account_app.state.marketplace
    accounts.set_mode(tenant, "student_sim")
    raw = {
        key: value
        for key, value in sim.state.store.jobs["student-4016-ai_ml-001"].items()
        if key != "gold"
    }
    job = accounts.import_job(tenant, raw)
    store = RunStore(account_app.state.engine)
    run = store.create_run(tenant, job.id, str(uuid4()))
    token = "fixture-worker"
    store.claim(tenant, run.id, token)
    draft = ProposalDraft(
        text="I propose a Python document search using embeddings and retrieval. "
        "I would validate inputs and add tests before implementation."
    )
    price = PriceQuote(
        amount=raw["budget_min"], billing_type="fixed", connects=6, rationale="Fixture"
    )
    state = {"draft": draft, "price": price, "raw_job": job.raw, "status": "awaiting_approval"}
    request = ProposalWrite(
        job_id=raw["id"],
        text=draft.text,
        bid_amount=price.amount,
        idempotency_key="fixture-key-" + run.id,
    )
    service = MarketplaceService(
        store.engine, account_app.state.settings, tenant, run.id, adapter=adapter
    )
    store.save(tenant, run.id, token, state)
    return user, store, run, token, draft, state, request, service, sim


async def approve(market):
    user, store, run, token, draft, state, request, service, _ = market
    result = await service.write("submit_proposal", request)
    preview = WritePreview(
        tool="submit_proposal",
        arguments=result.data["arguments"],
        connects_cost=result.data["connects_cost"],
        idempotency_key=request.idempotency_key,
    )
    state["preview"] = preview
    review = {
        "draft": draft.model_dump(),
        "preview": preview.model_dump(),
        "interrupt_id": "fixture-pause",
    }
    store.save(user["id"], run.id, token, state, review, complete=True)
    current = store.run(user["id"], run.id)
    store.review(
        user["id"],
        ReviewRun(
            run_id=run.id,
            version=current.version,
            draft_digest=draft_digest(draft),
            action="approve",
        ),
    )
    return request.model_copy(update={"dry_run": False})


@pytest.mark.asyncio
async def test_actual_mcp_approval_idempotency_and_commit_recovery(market):
    user, store, run, token, _, _, request, service, sim = market
    server = create_marketplace_server(service, user["id"], run.id)
    async with create_connected_server_and_client_session(server) as session:
        reader = MarketplaceMCP(session)
        assert (await reader.balance())["connects"] == 100
        statistics = await reader.pricing_statistics(request.job_id)
        assert statistics["currency"] == "USD"
        assert statistics["market"]["source"] == "synthetic_posted_budgets"
        assert statistics["client"]["count"] == 0
        assert (await reader.balance())["connects"] == 100  # Read tool never spends.
        with pytest.raises(MarketplaceRejected, match="approval"):
            await reader.proposal(request.model_copy(update={"dry_run": False}))
        approved = await approve(market)
        result = await reader.proposal(approved)
        assert (await reader.proposal(approved))["id"] == result["id"]
        assert (await reader.balance())["connects"] == 94
    with Session(store.engine) as db:
        assert db.scalar(select(func.count()).select_from(MarketplaceWrite)) == 1
    store.claim(user["id"], run.id, token)
    assert store.recover_local(user["id"], run.id, token)
    assert store.run(user["id"], run.id).status == "submitted"
    assert (
        len(
            [event for event in sim.state.store.events(user["id"]) if event["stage"] == "submitted"]
        )
        == 1
    )


@pytest.mark.asyncio
async def test_modified_arguments_and_budget_changes_cannot_bypass_approval(market):
    user, store, _, _, _, _, _, service, sim = market
    approved = await approve(market)
    with pytest.raises(RunConflict):
        await service.write(
            "submit_proposal", approved.model_copy(update={"text": "Changed after approval"})
        )
    with Session(store.engine) as db, db.begin():
        db.get(FreelancerProfile, user["id"]).weekly_connects_budget = 1
    with pytest.raises(RunConflict, match="Weekly"):
        await service.write("submit_proposal", approved)
    assert sim.state.store.balance(user["id"]) == 100


@pytest.mark.asyncio
async def test_disconnect_blocks_new_effect_but_preserves_saved_job(market, account_app):
    user, store, run, _, _, _, _, service, sim = market
    approved = await approve(market)
    account_app.state.marketplace.set_mode(user["id"], "manual")
    with pytest.raises(RunConflict, match="Connect"):
        await service.write("submit_proposal", approved)
    assert store.job(user["id"], run.job_id).raw["source"] == "student_sim"
    assert sim.state.store.balance(user["id"]) == 100
