from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from apps.api.auth.dependencies import CurrentUser
from apps.api.schemas.proposals import ReviewRun, RunView

router = APIRouter(tags=["approvals"])


@router.post("/approvals", response_model=RunView, status_code=202)
async def approve_run(body: ReviewRun, user: CurrentUser, request: Request):
    run = await run_in_threadpool(request.app.state.runs.review, user.id, body)
    if not await request.app.state.enqueue_run(user.id, run.id):
        run.error = "Worker queue unavailable; your saved decision will be retried automatically."
    return run
