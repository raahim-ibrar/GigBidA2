"""Student-built REST simulator. Its schema and outcome rules are our own."""

import asyncio
import hmac
import json
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agent.marketplace_port import MessageWrite, ProposalWrite
from simulator.catalogue import jobs, public_job
from simulator.store import SimConflict, SimStore


def create_app(
    path=None,
    *,
    api_key=None,
    seed=4016,
    per_persona=200,
    starting_connects=100,
    catalogue_path=None,
    client_mode="rule",
):
    @asynccontextmanager
    async def lifespan(app):
        from simulator.client import resolve_forever

        task = (
            asyncio.create_task(resolve_forever(app.state.store)) if client_mode == "llm" else None
        )
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(
        title="GigBid Student Simulator",
        version="student-v1",
        description="Independent synthetic development simulator; not instructor GigSim.",
        lifespan=lifespan,
    )
    catalogue = (
        json.loads(Path(catalogue_path).read_text(encoding="utf-8"))
        if catalogue_path
        else jobs(seed, per_persona)
    )
    if not isinstance(catalogue, list) or not catalogue or len(catalogue) > 10000:
        raise ValueError("Invalid student simulator catalogue")
    app.state.store = SimStore(
        path or os.getenv("STUDENT_SIM_DATABASE", "work/student-sim.sqlite"),
        catalogue,
        starting_connects=starting_connects,
        client_mode=client_mode,
    )
    app.state.api_key = api_key or os.getenv("STUDENT_SIM_API_KEY", "student_sim_local_only")
    app.state.fault = "normal"

    def identity(
        authorization: Annotated[str | None, Header()] = None,
        x_tenant_id: Annotated[str | None, Header()] = None,
    ):
        expected = "Bearer " + app.state.api_key
        if not authorization or not hmac.compare_digest(authorization.encode(), expected.encode()):
            raise HTTPException(401, "Simulator authentication required")
        try:
            tenant = str(UUID(x_tenant_id or ""))
        except ValueError:
            raise HTTPException(401, "Host-bound account identity required") from None
        return tenant

    def account(tenant=Depends(identity)):
        if app.state.fault == "unavailable":
            raise HTTPException(503, "Student simulator outage fixture")
        if app.state.fault == "rate_limit":
            raise HTTPException(
                429, "Student simulator rate-limit fixture", headers={"Retry-After": "2"}
            )
        return tenant

    @app.exception_handler(SimConflict)
    async def conflict(request: Request, error: SimConflict):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(KeyError)
    async def missing(request: Request, error: KeyError):
        return JSONResponse(status_code=404, content={"detail": "Simulator record not found"})

    @app.get("/health")
    def health():
        return {
            "provider": "student_sim",
            "synthetic": True,
            "client_mode": client_mode,
            "catalogue_origin": "historical_jobs_with_synthetic_context"
            if catalogue_path
            else "fully_synthetic",
            "jobs": len(catalogue),
            "scenario_version": "student-kaggle-v1" if catalogue_path else "student-v1",
        }

    @app.get("/jobs")
    def search(
        q: str = Query(default="", max_length=500),
        limit: int = Query(default=20, ge=1, le=100),
        tenant=Depends(account),
    ):
        terms = q.lower().split()
        found = [
            public_job(job)
            for job in catalogue
            if not terms
            or all(
                term in (job["title"] + " " + job["description"] + " " + job["category"]).lower()
                for term in terms
            )
        ]
        return {"items": found[:limit], "total": len(found), "source": "student_sim"}

    @app.get("/jobs/{job_id}")
    def job(job_id: str, tenant=Depends(account)):
        if job_id not in app.state.store.jobs:
            raise HTTPException(404, "Job not found")
        return public_job(app.state.store.jobs[job_id])

    @app.get("/clients/{client_id}")
    def client(client_id: str, tenant=Depends(account)):
        if client_id not in {job["client_id"] for job in catalogue}:
            raise HTTPException(404, "Client not found")
        return {
            "id": client_id,
            "completed_projects": 8,
            "payment_verified": True,
            "average_rating": 4.5,
            "synthetic": True,
        }

    @app.get("/jobs/{job_id}/pricing-statistics")
    def pricing_statistics(job_id: str, tenant=Depends(account)):
        from agent.pricing import budget_statistics

        if job_id not in app.state.store.jobs:
            raise HTTPException(404, "Job not found")
        return budget_statistics(app.state.store.jobs[job_id], catalogue, provider="student_sim")

    @app.get("/balance")
    def balance(tenant=Depends(account)):
        return {"connects": app.state.store.balance(tenant), "source": "student_sim"}

    @app.post("/proposals/preview")
    def preview(body: ProposalWrite, tenant=Depends(account)):
        job = app.state.store.jobs.get(body.job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        return {
            "tool": "submit_proposal",
            "arguments": body.model_dump(exclude={"dry_run", "idempotency_key"}),
            "connects_cost": job["connects_cost"],
            "idempotency_key": body.idempotency_key,
            "source": "student_sim",
            "balance": app.state.store.balance(tenant),
        }

    @app.post("/proposals")
    def submit(body: ProposalWrite, tenant=Depends(account)):
        if body.dry_run:
            return preview(body, tenant)
        return app.state.store.write(
            tenant, "submit_proposal", body.model_dump(exclude={"dry_run"})
        )

    @app.get("/proposals/{proposal_id}")
    def proposal(proposal_id: str, tenant=Depends(account)):
        with app.state.store.db() as db:
            row = db.execute(
                "SELECT body,job_id FROM proposals WHERE id=? AND tenant=?", (proposal_id, tenant)
            ).fetchone()
            if row is None:
                raise HTTPException(404, "Proposal not found")
            import json

            return {
                "id": proposal_id,
                "job_id": row[1],
                "request": json.loads(row[0]),
                "source": "student_sim",
            }

    @app.get("/conversations/{conversation_id}/messages")
    def messages(conversation_id: str, tenant=Depends(account)):
        return {"items": app.state.store.messages(tenant, conversation_id), "source": "student_sim"}

    @app.post("/messages")
    def send(body: MessageWrite, tenant=Depends(account)):
        app.state.store.messages(
            tenant, body.conversation_id
        )  # Ownership check, including previews.
        if body.dry_run:
            return {
                "tool": "send_message",
                "arguments": body.model_dump(exclude={"dry_run", "idempotency_key"}),
                "idempotency_key": body.idempotency_key,
                "connects_cost": 0,
                "source": "student_sim",
            }
        return app.state.store.write(tenant, "send_message", body.model_dump(exclude={"dry_run"}))

    @app.get("/events")
    def events(after: int = Query(default=0, ge=0), tenant=Depends(account)):
        return {"items": app.state.store.events(tenant, after), "source": "student_sim"}

    class Fault(BaseModel):
        mode: Literal["normal", "rate_limit", "unavailable"]

    @app.post("/admin/fault")
    def fault(body: Fault, tenant=Depends(identity)):
        if os.getenv("STUDENT_SIM_ALLOW_FAULTS") != "1":
            raise HTTPException(403, "Fault controls disabled")
        app.state.fault = body.mode
        return {"mode": body.mode}

    return app


configured_catalogue = os.getenv("STUDENT_SIM_CATALOGUE")
default_catalogue = Path("data/processed/student_jobs.json")
app = create_app(
    catalogue_path=None
    if configured_catalogue == "synthetic"
    else configured_catalogue or (default_catalogue if default_catalogue.is_file() else None),
    client_mode=os.getenv("STUDENT_SIM_CLIENT_MODE", "rule"),
)
