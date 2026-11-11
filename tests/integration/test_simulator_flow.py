"""Durable approval → actual simulator effect → events → reviewed outbound reply."""

import os
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.conversation_store import ConversationStore
from agent.marketplace_client import MarketplaceMCP
from agent.run_store import RunStore
from agent.runtime import process_run
from agent.workspace_client import WorkspaceMCP
from apps.api.models import ClientConversation, MarketplaceWrite, utcnow
from apps.api.schemas.proposals import ReviewRun
from mcp_servers.marketplace.adapters.student_sim import StudentSimAdapter
from mcp_servers.marketplace.factory import create_marketplace_server
from mcp_servers.marketplace.service import MarketplaceService
from mcp_servers.workspace.factory import create_workspace_server
from mcp_servers.workspace.service import WorkspaceService
from rag.contracts import DocumentMetadata, PortfolioSearch
from simulator.app import create_app
from tests.integration.test_durable_bid import execute
from tests.integration.test_runs import register
from tests.portfolio_fixtures import portfolio_fixture
from tests.proposal_fixtures import BrowserModels
from worker.simulator_sync import sync_account

pytestmark = pytest.mark.skipif(
    not os.getenv("GIGBID_TEST_DATABASE_URL"), reason="requires durable Postgres checkpoints"
)


def test_proposal_to_client_reply_with_actual_mcp_and_persistent_simulator(
    client, account_app, tmp_path
):
    tenant = register(client, "student-flow@example.org")["id"]
    engine, settings = account_app.state.engine, account_app.state.settings
    sim = create_app(tmp_path / "flow.sqlite", api_key="test-only", per_persona=3)
    adapter = StudentSimAdapter(
        "http://sim", "test-only", tenant, transport=httpx.ASGITransport(app=sim)
    )
    accounts = account_app.state.marketplace
    accounts.set_mode(tenant, "student_sim")
    job = accounts.import_job(tenant, execute(adapter.get_job("student-4016-ai_ml-001")).data)
    store = RunStore(engine)
    run = store.create_run(tenant, job.id, str(uuid4()))
    portfolio = portfolio_fixture(engine)
    doc = portfolio.ingest(
        tenant,
        "fixture.md",
        b"I built a Python API.",
        DocumentMetadata(type="case_study", project="Synthetic development portfolio"),
    )
    portfolio.index_document(tenant, doc.id)
    evidence = portfolio.search(tenant, PortfolioSearch(query="Python")).items[0].evidence

    class Reader:
        async def search(self, query, **kwargs):
            return [evidence]

        async def read(self, id):
            return portfolio.evidence(tenant, id)

    workspace = WorkspaceService(engine)
    start = (utcnow() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    workspace.add_availability(tenant, start, start + timedelta(hours=2))

    async def process(id):
        marketplace = create_marketplace_server(
            MarketplaceService(engine, settings, tenant, id, adapter=adapter), tenant, id
        )
        calendar = create_workspace_server(workspace, tenant, id)
        async with create_connected_server_and_client_session(marketplace) as market_session:
            async with create_connected_server_and_client_session(calendar) as calendar_session:
                return await process_run(
                    engine,
                    settings,
                    tenant,
                    id,
                    models_factory=BrowserModels,
                    portfolio_reader=Reader(),
                    workspace_reader=WorkspaceMCP(calendar_session),
                    marketplace_reader=MarketplaceMCP(market_session),
                )

    def approve(id):
        current = store.run(tenant, id)
        store.review(
            tenant,
            ReviewRun(
                run_id=id,
                version=current.version,
                action="approve",
                draft_digest=current.review["preview"]["arguments"]["draft_digest"],
            ),
        )

    try:
        result = execute(process(run.id))
        assert result["status"] == "awaiting_approval", (result, store.run(tenant, run.id).error)
        assert sim.state.store.balance(tenant) == 100
        approve(run.id)
        assert execute(process(run.id))["status"] == "submitted"
        assert execute(process(run.id))["status"] == "not_pending"
        assert store.run(tenant, run.id).status == "submitted"
        assert sim.state.store.balance(tenant) == 94
        synced = execute(sync_account(engine, settings, tenant, adapter=adapter))
        assert synced["messages"] == 1
        assert execute(sync_account(engine, settings, tenant, adapter=adapter))["events"] == 0
        with Session(engine) as db:
            conversation = db.scalar(
                select(ClientConversation).where(ClientConversation.user_id == tenant)
            )
            assert conversation.provider_id
            conversation_id, reply_run = conversation.id, conversation.run_id
        result = execute(process(reply_run))
        assert result["status"] == "awaiting_approval", (result, store.run(tenant, reply_run).error)
        approve(reply_run)
        assert execute(process(reply_run))["status"] == "sent"
        assert execute(process(reply_run))["status"] == "not_pending"
        assert store.run(tenant, reply_run).status == "sent"
        messages = execute(adapter.list_messages(conversation.provider_id)).data["items"]
        assert [message["sender"] for message in messages] == ["client", "freelancer"]
        assert "Interview options (UTC)" in messages[-1]["text"]
        assert len(ConversationStore(engine).local_replies(tenant, conversation_id)) == 1
        with Session(engine) as db:
            assert len(db.scalars(select(MarketplaceWrite)).all()) == 2
        assert sim.state.store.balance(tenant) == 94
    finally:
        portfolio.index.client.close()
