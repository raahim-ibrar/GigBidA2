from fastapi import APIRouter, Depends

from apps.api.auth.dependencies import require_user
from apps.api.schemas.requests import EditDraft

router = APIRouter(tags=["proposals"])


@router.get("/proposals/{proposal_id}", dependencies=[Depends(require_user)])
def get_proposal(proposal_id: str):
    raise NotImplementedError("Load a persisted proposal and its claim evidence")


@router.patch("/proposals/{proposal_id}", dependencies=[Depends(require_user)])
def edit_proposal(proposal_id: str, body: EditDraft):
    raise NotImplementedError("Diff edits and reverify before creating a new approval")
