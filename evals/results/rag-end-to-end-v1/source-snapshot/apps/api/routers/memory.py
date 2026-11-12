from fastapi import APIRouter, Request

from apps.api.auth.dependencies import CurrentUser
from apps.api.schemas.memory import (
    ConfirmStyle,
    EditView,
    Kind,
    MemoryList,
    RemoveMemory,
    StyleCandidate,
)

router = APIRouter(tags=["memory"])


@router.get("/memory", response_model=MemoryList)
def list_memory(user: CurrentUser, request: Request):
    return request.app.state.memory.list(user.id)


@router.get("/memory/style-candidates", response_model=list[StyleCandidate])
def style_candidates(user: CurrentUser, request: Request):
    return request.app.state.memory.candidates(user.id)


@router.get("/memory/edits", response_model=list[EditView])
def draft_edits(user: CurrentUser, request: Request):
    return request.app.state.memory.edits(user.id)


@router.post("/memory/style", response_model=MemoryList)
def confirm_style(body: ConfirmStyle, user: CurrentUser, request: Request):
    return request.app.state.memory.confirm_style(user.id, body.key, confirmed=body.confirmed)


@router.delete("/memory/{kind}/{key}", status_code=204)
def remove_memory(kind: Kind, key: str, body: RemoveMemory, user: CurrentUser, request: Request):
    request.app.state.memory.remove(user.id, kind, key, body.version)
