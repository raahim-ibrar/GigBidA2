from fastapi import APIRouter, Request

from apps.api.auth.dependencies import CurrentUser
from apps.api.schemas.schedules import ScheduleUpdate, ScheduleView

router = APIRouter(tags=["search schedules"])


@router.get("/search-schedule", response_model=ScheduleView)
def get_schedule(user: CurrentUser, request: Request):
    return request.app.state.search_schedules.get(user.id)


@router.put("/search-schedule", response_model=ScheduleView)
def update_schedule(body: ScheduleUpdate, user: CurrentUser, request: Request):
    return request.app.state.search_schedules.update(user.id, body)
