from fastapi import APIRouter, Depends

from apps.api.auth.dependencies import require_user

router = APIRouter(tags=["jobs"])


@router.get("/jobs", dependencies=[Depends(require_user)])
def list_jobs():
    raise NotImplementedError("Implement the tenant-scoped ranked job inbox")


@router.get("/jobs/{job_id}", dependencies=[Depends(require_user)])
def get_job(job_id: str):
    raise NotImplementedError("Load JobSpec, risk, fit and evidence for this job")
