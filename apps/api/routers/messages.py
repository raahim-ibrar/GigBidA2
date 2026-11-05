from fastapi import APIRouter, Depends

from apps.api.auth.dependencies import require_user

router = APIRouter(tags=["messages"])


@router.get("/messages", dependencies=[Depends(require_user)])
def list_messages():
    raise NotImplementedError("Load tenant-scoped conversations from persisted marketplace events")
