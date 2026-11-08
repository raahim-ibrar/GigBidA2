from fastapi import APIRouter, Query, Request

from apps.api.auth.dependencies import CurrentUser
from apps.api.schemas.dashboard import AnalyticsView, PipelineView

router = APIRouter(tags=["analytics"])


@router.get("/analytics", response_model=AnalyticsView)
def analytics(user: CurrentUser, request: Request, days: int = Query(default=30, ge=1, le=365)):
    return request.app.state.dashboard.analytics(user.id, days)


@router.get("/pipeline", response_model=PipelineView)
def pipeline(user: CurrentUser, request: Request):
    return request.app.state.dashboard.pipeline(user.id)
