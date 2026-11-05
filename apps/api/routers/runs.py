from fastapi import APIRouter, Depends

from apps.api.auth.dependencies import require_user
from apps.api.schemas.requests import StartRun

router = APIRouter(tags=["runs"])


@router.post("/runs", dependencies=[Depends(require_user)])
def start_run(body: StartRun):
    raise NotImplementedError("Enqueue a durable worker task; never run agents inside this request")


@router.get("/runs/{run_id}/events", dependencies=[Depends(require_user)])
def run_events(run_id: str):
    raise NotImplementedError("Bridge persisted graph events to SSE with reconnect support")
