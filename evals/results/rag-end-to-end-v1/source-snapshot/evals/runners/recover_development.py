"""Recover research-only approval checkpoints after the non-factual verdict guard fix.

This does not approve or send anything. It refuses to run an inference node, edit an
ordinary user's run, change a budget, or recover a checkpoint outside the approval gate.
"""

import asyncio
import json
from pathlib import Path

import httpx
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from mcp.shared.memory import create_connected_server_and_client_session
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from agent.config import AgentConfig
from agent.graphs.bid_graph import build_bid_graph
from agent.marketplace_client import MarketplaceMCP
from agent.portfolio_client import PortfolioMCP
from agent.run_store import RunStore
from agent.runtime import checkpoint_serializer, process_run
from apps.api.database import make_engine
from apps.api.models import AgentRun, RunEvent, User
from apps.api.settings import Settings
from mcp_servers.marketplace.adapters.student_sim import StudentSimAdapter
from mcp_servers.marketplace.factory import create_marketplace_server
from mcp_servers.marketplace.service import MarketplaceService
from mcp_servers.portfolio.factory import create_portfolio_server
from rag.runtime import build_portfolio
from simulator.app import create_app


class NoInference:
    def __init__(self, *args, **kwargs):
        pass

    async def complete(self, *args, **kwargs):
        raise AssertionError("Checkpoint recovery must not execute inference")


async def recover():
    root = Path("work/groq-development-v2")
    settings = Settings()
    schema = "gigbid_student_generation_hosted_v2"
    url = make_url(settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    settings = settings.model_copy(
        update={
            "database_url": url.update_query_dict(
                {"options": f"-csearch_path={schema}"}
            ).render_as_string(hide_password=False)
        }
    )
    engine, config = make_engine(settings.database_url), AgentConfig(profile_name="hosted_open")
    config.budgets.max_tokens_per_thread = 32000
    portfolio = build_portfolio(engine, settings)
    sim = create_app(root / "simulator.sqlite", api_key="research-only", per_persona=2)
    store, outcomes = RunStore(engine), []
    with Session(engine) as db:
        candidates = [
            (run.user_id, run.id)
            for run, user in db.execute(
                select(AgentRun, User)
                .join(User, AgentRun.user_id == User.id)
                .where(
                    AgentRun.status == "needs_attention",
                    User.password_hash == "disabled-research",
                )
            )
            if run.snapshot.get("preview")
        ]
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    try:
        for tenant, run_id in candidates:
            async with AsyncPostgresSaver.from_conn_string(
                dsn, serde=checkpoint_serializer()
            ) as saver:
                graph = build_bid_graph(checkpointer=saver)
                state = await graph.aget_state(
                    {"configurable": {"thread_id": f"{tenant}:{run_id}"}}
                )
                if state.next != ("approval",) or state.interrupts:
                    continue
            before = store.run(tenant, run_id)
            draft = before.snapshot.draft
            if (
                not draft
                or not before.snapshot.compliance
                or not before.snapshot.compliance.allowed
            ):
                continue
            with Session(engine) as db, db.begin():
                row = db.get(AgentRun, run_id)
                # Reuse the exact normal execution-boundary verifier; source locks
                # and the original cumulative token/step budgets are preserved.
                store._check_evidence(db, tenant, draft)
                row.retryable = True
                db.add(
                    RunEvent(
                        run_id=run_id,
                        kind="development_guard_fix_recovery",
                        details={"scope": "research-only", "approval_granted": False},
                    )
                )
            store.retry(tenant, run_id, before.version)
            adapter = StudentSimAdapter(
                "http://research", "research-only", tenant, transport=httpx.ASGITransport(app=sim)
            )
            market = create_marketplace_server(
                MarketplaceService(engine, settings, tenant, run_id, adapter=adapter),
                tenant,
                run_id,
            )
            async with (
                create_connected_server_and_client_session(market) as marketplace,
                create_connected_server_and_client_session(
                    create_portfolio_server(portfolio, tenant)
                ) as sources,
            ):
                result = await process_run(
                    engine,
                    settings,
                    tenant,
                    run_id,
                    config=config,
                    models_factory=NoInference,
                    portfolio_reader=PortfolioMCP(sources),
                    marketplace_reader=MarketplaceMCP(marketplace),
                )
            after = store.run(tenant, run_id)
            assert after.tokens == before.tokens
            assert after.snapshot.draft == before.snapshot.draft
            record = {
                "run_id": run_id,
                "before": before.status,
                "after": result["status"],
                "model_calls": 0,
                "additional_tokens": after.tokens - before.tokens,
                "approval_still_required": after.status == "awaiting_approval",
            }
            outcomes.append(record)
            print(json.dumps(record), flush=True)
        target = Path("evals/results/hosted-development-recovery.json")
        target.write_text(
            json.dumps(
                {
                    "data_origin": "synthetic",
                    "results": outcomes,
                    "scope": "Guard-fix recovery, not new model-quality trials",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    finally:
        portfolio.index.client.close()
        engine.dispose()


if __name__ == "__main__":
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        runner.run(recover())
