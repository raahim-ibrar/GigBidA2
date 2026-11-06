from fastapi import APIRouter, Request

from apps.api.auth.dependencies import CurrentUser
from apps.api.schemas.workspace import AvailabilityView, SlotList, WorkspaceActionView
from mcp_servers.workspace.tools import SlotRequest, TimeWindow

router = APIRouter(tags=["workspace"])


@router.get("/workspace/availability", response_model=list[AvailabilityView])
def availability(user: CurrentUser, request: Request):
    return request.app.state.workspace.availability(user.id)


@router.post("/workspace/availability", response_model=AvailabilityView, status_code=201)
def add_availability(body: TimeWindow, user: CurrentUser, request: Request):
    return request.app.state.workspace.add_availability(user.id, body.start, body.end)


@router.delete("/workspace/availability/{id}", status_code=204)
def remove_availability(id: str, user: CurrentUser, request: Request):
    request.app.state.workspace.remove_availability(user.id, id)


@router.get("/workspace/actions", response_model=list[WorkspaceActionView])
def workspace_actions(user: CurrentUser, request: Request):
    return request.app.state.workspace.actions(user.id)


@router.post("/workspace/slots", response_model=SlotList)
def free_slots(body: SlotRequest, user: CurrentUser, request: Request):
    return request.app.state.workspace.free_slots(user.id, body)
