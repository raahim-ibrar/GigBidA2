import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from agent.conversation_store import ConversationStore
from agent.memory.service import MemoryService, MemoryUnavailable
from agent.proposal_nodes import ReviewRequired
from agent.run_store import RunConflict, RunNotFound, RunStore
from apps.api.auth.security import AuthLimiter
from apps.api.auth.token_store import OAuthUnavailable
from apps.api.dashboard import Dashboard
from apps.api.database import make_engine
from apps.api.marketplace import MarketplaceAccounts
from apps.api.routers import (
    analytics,
    approvals,
    auth,
    jobs,
    marketplace,
    memory,
    messages,
    portfolio,
    profile,
    proposals,
    runs,
    schedules,
    workspace,
)
from apps.api.schemas.status import SkeletonStatus
from apps.api.settings import Settings
from mcp_servers.marketplace.adapters.student_sim import MarketplaceRejected, MarketplaceUnavailable
from mcp_servers.workspace.service import WorkspaceService
from rag.runtime import build_portfolio
from worker.queue import enqueue_bid, enqueue_portfolio
from worker.search_schedules import SearchSchedules


def create_app(
    settings: Settings | None = None, *, engine=None, portfolio_service=None, enqueue=None
) -> FastAPI:
    settings = settings or Settings()
    database = engine if engine is not None else make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        try:
            await asyncio.to_thread(app.state.memory.ensure)
        except MemoryUnavailable:
            pass  # Accounts still work; memory endpoints expose pending synchronization.
        yield
        if engine is None:
            database.dispose()

    app = FastAPI(title="GigBid API", version="0.2.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = database
    app.state.auth_limiter = AuthLimiter()
    app.state.portfolio = portfolio_service or build_portfolio(database, settings)
    app.state.runs = RunStore(database)
    app.state.memory = MemoryService(database, settings.database_url)
    app.state.workspace = WorkspaceService(database)
    app.state.conversations = ConversationStore(database)
    app.state.search_schedules = SearchSchedules(database)
    app.state.dashboard = Dashboard(database)
    app.state.marketplace = MarketplaceAccounts(database, settings)

    async def queue(tenant, document, revision):
        return await enqueue_portfolio(settings, tenant, document, revision)

    app.state.enqueue_portfolio = enqueue or queue

    async def queue_run(tenant, run_id):
        return await enqueue_bid(settings, tenant, run_id)

    app.state.enqueue_run = queue_run
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token", "Last-Event-ID"],
    )

    @app.exception_handler(NotImplementedError)
    async def not_implemented(request: Request, exc: NotImplementedError):
        return JSONResponse(status_code=501, content={"detail": str(exc)})

    @app.exception_handler(SQLAlchemyError)
    async def database_unavailable(request: Request, exc: SQLAlchemyError):
        return JSONResponse(status_code=503, content={"detail": "Database operation unavailable"})

    @app.exception_handler(RunNotFound)
    async def run_not_found(request: Request, exc: RunNotFound):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(RunConflict)
    @app.exception_handler(ReviewRequired)
    async def run_conflict(request: Request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(MarketplaceRejected)
    async def marketplace_rejected(request: Request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(OAuthUnavailable)
    @app.exception_handler(MarketplaceUnavailable)
    async def marketplace_unavailable(request: Request, exc):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.get("/health/live", tags=["health"])
    def liveness() -> dict[str, str]:
        # Process liveness only; this is deliberately not a dependency/readiness check.
        return {"status": "ok", "stage": "foundation"}

    @app.get("/health/ready", tags=["health"])
    def readiness() -> dict[str, str]:
        try:
            with database.connect() as connection:
                connection.execute(text("SELECT 1 FROM users LIMIT 1"))
                connection.execute(text("SELECT 1 FROM agent_runs LIMIT 1"))
        except SQLAlchemyError:
            raise HTTPException(503, "Database unavailable or migrations not applied") from None
        return {"status": "ready"}

    @app.get("/api/status", tags=["status"], response_model=SkeletonStatus)
    def status():
        return SkeletonStatus()

    for router in (
        auth,
        profile,
        portfolio,
        jobs,
        marketplace,
        proposals,
        approvals,
        messages,
        runs,
        schedules,
        analytics,
        memory,
        workspace,
    ):
        app.include_router(router.router, prefix="/api")
    return app


app = create_app()
