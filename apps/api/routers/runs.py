import asyncio

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from agent.run_store import TERMINAL
from apps.api.auth.dependencies import CurrentUser
from apps.api.schemas.proposals import CreateRun, RetryRun, RunView

router = APIRouter(tags=["runs"])


@router.post("/runs", response_model=RunView, status_code=202)
async def start_run(body: CreateRun, user: CurrentUser, request: Request):
    run = await run_in_threadpool(
        request.app.state.runs.create_run, user.id, str(body.job_id), str(body.idempotency_key)
    )
    if run.status == "queued":
        queued = await request.app.state.enqueue_run(user.id, run.id)
        if not queued:
            run.error = "Worker queue unavailable; the saved run will be retried automatically."
    return run


@router.get("/runs", response_model=list[RunView])
def list_runs(user: CurrentUser, request: Request, job_id: str | None = None):
    return request.app.state.runs.runs(user.id, job_id)


@router.get("/runs/{run_id}", response_model=RunView)
def get_run(run_id: str, user: CurrentUser, request: Request):
    return request.app.state.runs.run(user.id, run_id)


@router.post("/runs/{run_id}/retry", response_model=RunView, status_code=202)
async def retry_run(run_id: str, body: RetryRun, user: CurrentUser, request: Request):
    run = await run_in_threadpool(request.app.state.runs.retry, user.id, run_id, body.version)
    if not await request.app.state.enqueue_run(user.id, run_id):
        run.error = "Worker queue unavailable; the saved retry will be recovered automatically."
    return run


@router.get("/runs/{run_id}/events")
async def run_events(
    run_id: str,
    user: CurrentUser,
    request: Request,
    after: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None),
):
    store, tenant = request.app.state.runs, user.id
    await run_in_threadpool(store.run, tenant, run_id)
    try:
        cursor = max(after, int(last_event_id or 0))
    except ValueError:
        raise HTTPException(422, "Invalid event cursor") from None

    async def stream():
        nonlocal cursor
        for _ in range(60):
            if await request.is_disconnected():
                break
            events = await run_in_threadpool(store.events, tenant, run_id, cursor)
            for event in events:
                cursor = event.id
                yield f"id: {event.id}\nevent: progress\ndata: {event.model_dump_json()}\n\n"
            run = await run_in_threadpool(store.run, tenant, run_id)
            if len(events) < 200 and run.status in TERMINAL | {"awaiting_approval"}:
                yield f'event: done\ndata: {{"status":"{run.status}"}}\n\n'
                return
            if not events:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
