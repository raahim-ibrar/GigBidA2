"""No real provider calls: exercise the production approval and send-once ledger."""

import pytest
from sqlalchemy.orm import Session

from agent.marketplace_port import MarketplaceResult
from agent.run_store import RunConflict
from apps.api.models import AgentRun, JobRecord, MarketplaceConnection, OAuthCredential
from mcp_servers.marketplace.service import MarketplaceService
from tests.integration.test_marketplace_service import approve
from tests.integration.test_marketplace_service import market as market


@pytest.fixture
def live_market(market, account_app):
    user, store, run, token, draft, state, request, _, sim = market
    raw = {
        **state["raw_job"],
        "source": "upwork",
        "synthetic": False,
        "connection_generation": "fixture-generation",
    }
    with Session(store.engine) as db, db.begin():
        db.get(JobRecord, run.job_id).raw = raw
        db.get(AgentRun, run.id).snapshot = {**db.get(AgentRun, run.id).snapshot, "raw_job": raw}
        db.get(MarketplaceConnection, user["id"]).mode = "upwork"
        db.add(
            OAuthCredential(
                user_id=user["id"],
                provider="upwork",
                encrypted_payload="unused-fixture",
                generation="fixture-generation",
                connected=True,
                schema_snapshot=[],
                capabilities={},
            )
        )

    class Adapter:
        calls = 0
        timeout = False

        async def create_proposal_draft(self, request):
            return MarketplaceResult(provider="upwork", data={"connects_cost": 6})

        async def prepare_approved_proposal(self, request, *, approved_cost):
            assert approved_cost == 6
            self.calls += 1
            if self.timeout:
                raise TimeoutError("Synthetic lost response")
            return {
                "provider": "upwork",
                "status": "pending_provider_confirmation",
                "preview_id": "fake-preview",
                "connects_spent": 0,
            }

    adapter = Adapter()
    state["raw_job"] = raw
    service = MarketplaceService(
        store.engine, account_app.state.settings, user["id"], run.id, adapter=adapter
    )
    store.save(user["id"], run.id, token, state)
    return (user, store, run, token, draft, state, request, service, sim), adapter


@pytest.mark.asyncio
async def test_live_prepare_requires_exact_approval_deduplicates_and_recovers_as_pending(
    live_market,
):
    items, adapter = live_market
    user, store, run, _, _, _, request, service, _ = items
    with pytest.raises(RunConflict, match="approval"):
        await service.write("submit_proposal", request.model_copy(update={"dry_run": False}))
    assert adapter.calls == 0
    approved = await approve(items)
    result = await service.write("submit_proposal", approved)
    assert result.provider == "upwork" and result.data["status"] == "pending_provider_confirmation"
    assert result.data["connects_spent"] == 0
    assert (await service.write("submit_proposal", approved)).data == result.data
    assert adapter.calls == 1
    store.claim(user["id"], run.id, "recover-live")
    assert store.recover_local(user["id"], run.id, "recover-live")
    recovered = store.run(user["id"], run.id)
    assert recovered.status == "pending_provider_confirmation"
    assert recovered.snapshot.provider_result["preview_id"] == "fake-preview"


@pytest.mark.asyncio
async def test_lost_provider_response_is_not_retried_or_recovered_as_submitted(live_market):
    items, adapter = live_market
    user, store, run, _, _, _, _, service, _ = items
    approved = await approve(items)
    adapter.timeout = True
    with pytest.raises(RunConflict, match="unknown"):
        await service.write("submit_proposal", approved)
    with pytest.raises(RunConflict, match="uncertain"):
        await service.write("submit_proposal", approved)
    assert adapter.calls == 1
    store.claim(user["id"], run.id, "recover-live")
    assert store.recover_local(user["id"], run.id, "recover-live")
    assert store.run(user["id"], run.id).status == "needs_attention"


@pytest.mark.asyncio
async def test_switch_or_reconnect_cannot_redirect_approved_live_run(live_market):
    items, adapter = live_market
    user, store, _, _, _, _, _, service, _ = items
    approved = await approve(items)
    with Session(store.engine) as db, db.begin():
        db.get(OAuthCredential, (user["id"], "upwork")).generation = "new-account-generation"
    with pytest.raises(RunConflict, match="authorization changed"):
        await service.write("submit_proposal", approved)
    assert adapter.calls == 0
