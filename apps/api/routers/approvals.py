from fastapi import APIRouter, Depends

from apps.api.auth.dependencies import require_user
from apps.api.schemas.requests import ApproveRun

router = APIRouter(tags=["approvals"])


@router.post("/approvals", dependencies=[Depends(require_user)])
def approve_run(body: ApproveRun):
    raise NotImplementedError("Validate ownership, enqueue Command(resume=...), audit the decision")
