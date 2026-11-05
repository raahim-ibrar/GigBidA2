from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from apps.api.auth.security import AuthLimiter
from apps.api.database import make_engine
from apps.api.routers import (
    analytics,
    approvals,
    auth,
    jobs,
    messages,
    portfolio,
    profile,
    proposals,
    runs,
)
from apps.api.schemas.status import SkeletonStatus
from apps.api.settings import Settings
from rag.runtime import build_portfolio
from worker.queue import enqueue_portfolio


def create_app(
    settings: Settings | None = None, *, engine=None, portfolio_service=None, enqueue=None
) -> FastAPI:
    settings = settings or Settings()
    database = engine if engine is not None else make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        yield
        if engine is None:
            database.dispose()

    app = FastAPI(title="GigBid API", version="0.2.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = database
    app.state.auth_limiter = AuthLimiter()
    app.state.portfolio = portfolio_service or build_portfolio(database, settings)

    async def queue(tenant, document, revision):
        return await enqueue_portfolio(settings, tenant, document, revision)

    app.state.enqueue_portfolio = enqueue or queue
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    )

    @app.exception_handler(NotImplementedError)
    async def not_implemented(request: Request, exc: NotImplementedError):
        return JSONResponse(status_code=501, content={"detail": str(exc)})

    @app.exception_handler(SQLAlchemyError)
    async def database_unavailable(request: Request, exc: SQLAlchemyError):
        return JSONResponse(status_code=503, content={"detail": "Database operation unavailable"})

    @app.get("/health/live", tags=["health"])
    def liveness() -> dict[str, str]:
        # Process liveness only; this is deliberately not a dependency/readiness check.
        return {"status": "ok", "stage": "foundation"}

    @app.get("/health/ready", tags=["health"])
    def readiness() -> dict[str, str]:
        try:
            with database.connect() as connection:
                connection.execute(text("SELECT 1 FROM users LIMIT 1"))
        except SQLAlchemyError:
            raise HTTPException(503, "Database unavailable or migrations not applied") from None
        return {"status": "ready"}

    @app.get("/api/status", tags=["status"], response_model=SkeletonStatus)
    def status():
        return SkeletonStatus()

    for router in (auth, profile, portfolio, jobs, proposals, approvals, messages, runs, analytics):
        app.include_router(router.router, prefix="/api")
    return app


app = create_app()
