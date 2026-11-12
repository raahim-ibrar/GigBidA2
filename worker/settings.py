"""Durable indexing, graph execution, reconciliation and search prerequisite checks."""

import asyncio
import os
from datetime import timedelta

from arq import Retry, cron
from arq.connections import RedisSettings
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from agent.memory.service import MemoryService
from agent.run_store import RunStore
from agent.runtime import process_bid
from apps.api.database import make_engine
from apps.api.models import AgentRun, PortfolioDocument, VectorCleanup, utcnow
from apps.api.settings import Settings
from rag.runtime import build_portfolio
from rag.service import MissingEvidence
from worker.search_schedules import check_search_schedules
from worker.simulator_sync import reconcile_simulator


async def startup(ctx):
    settings = Settings()
    ctx["engine"] = make_engine(settings.database_url)
    ctx["portfolio"] = build_portfolio(ctx["engine"], settings)
    ctx["settings"] = settings
    await asyncio.to_thread(MemoryService(ctx["engine"], settings.database_url).ensure)


async def shutdown(ctx):
    ctx["portfolio"].index.client.close()
    ctx["engine"].dispose()


async def index_portfolio(ctx, tenant_id: str, document_id: str):
    service = ctx["portfolio"]
    try:
        await asyncio.to_thread(service.index_document, tenant_id, document_id)
    except MissingEvidence:
        return {"status": "deleted"}
    except Exception:
        retrying = ctx.get("job_try", 1) < 3
        service.set_index_error(tenant_id, document_id, retrying=retrying)
        if retrying:
            raise Retry(defer=10) from None
        return {"status": "failed"}
    return {"status": "indexed"}


async def cleanup_portfolio(ctx, tenant_id: str, document_id: str):
    await asyncio.to_thread(ctx["portfolio"].cleanup_vectors, tenant_id, document_id)


async def reconcile_portfolio(ctx):
    # System-owned outbox scan: read IDs only, then all operations are tenant-scoped.
    with Session(ctx["engine"]) as db:
        docs = db.execute(
            select(PortfolioDocument.user_id, PortfolioDocument.id, PortfolioDocument.revision)
            .where(
                or_(
                    PortfolioDocument.status == "queued",
                    and_(
                        PortfolioDocument.status == "indexing",
                        PortfolioDocument.updated_at < utcnow() - timedelta(minutes=15),
                    ),
                )
            )
            .limit(100)
        ).all()
        deleted = db.execute(
            select(VectorCleanup.user_id, VectorCleanup.document_id).limit(100)
        ).all()
    for tenant, id, revision in docs:
        await ctx["redis"].enqueue_job(
            "index_portfolio", tenant, id, _job_id=f"portfolio:{id}:{revision}"
        )
    for tenant, id in deleted:
        await ctx["redis"].enqueue_job("cleanup_portfolio", tenant, id, _job_id=f"cleanup:{id}")


async def run_bid(ctx, tenant_id: str, run_id: str):
    try:
        return await process_bid(ctx["engine"], ctx["settings"], tenant_id, run_id)
    finally:
        await export_trace(ctx, tenant_id, run_id)


async def export_trace(ctx, tenant, run_id):
    from agent.tracing import export_run

    try:
        await asyncio.to_thread(export_run, ctx["engine"], ctx["settings"], tenant, run_id)
    except Exception:
        # Observability failure must never change the run's approval/execution state.
        import logging

        logging.getLogger(__name__).warning("Trace export deferred for %s", run_id)


async def reconcile_traces(ctx):
    if not ctx["settings"].trace_export_enabled:
        return
    with Session(ctx["engine"]) as db:
        rows = db.execute(
            select(AgentRun.user_id, AgentRun.id)
            .where(AgentRun.status.not_in(["queued", "running"]))
            .order_by(AgentRun.updated_at.desc())
            .limit(100)
        ).all()
    for tenant, run_id in rows:
        await export_trace(ctx, tenant, run_id)


async def reconcile_runs(ctx):
    for tenant, run_id in await asyncio.to_thread(RunStore(ctx["engine"]).pending):
        await ctx["redis"].enqueue_job("run_bid", tenant, run_id, _job_id=f"bid:{run_id}")


async def run_conversation(ctx, tenant_id: str, conversation_id: str):
    return await run_bid(ctx, tenant_id, conversation_id)


class WorkerSettings:
    handle_signals = os.name != "nt"
    functions = [index_portfolio, cleanup_portfolio, run_bid, run_conversation]
    cron_jobs = [
        cron(reconcile_traces, second=50, run_at_startup=True),
        cron(reconcile_portfolio, second={0, 30}, run_at_startup=True),
        cron(reconcile_runs, second={10, 40}, run_at_startup=True),
        cron(check_search_schedules, second=20, run_at_startup=True),
        cron(reconcile_simulator, second={5, 35}, run_at_startup=True),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))
    max_jobs = 4
    job_timeout = 600
    max_tries = 3
    keep_result = 0
