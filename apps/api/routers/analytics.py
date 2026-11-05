from fastapi import APIRouter, Depends

from apps.api.auth.dependencies import require_user

router = APIRouter(tags=["analytics"])


@router.get("/analytics", dependencies=[Depends(require_user)])
def analytics():
    raise NotImplementedError("Aggregate real outcomes, spend, latency and rejection reasons")
