from fastapi import APIRouter, Request

from apps.api.auth.dependencies import CurrentUser
from apps.api.schemas.proposals import LocalDraftView

router = APIRouter(tags=["proposals"])


@router.get("/proposals/{run_id}", response_model=LocalDraftView)
def get_proposal(run_id: str, user: CurrentUser, request: Request):
    return request.app.state.runs.local_draft(user.id, run_id)
