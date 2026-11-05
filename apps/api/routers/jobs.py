from fastapi import APIRouter, Request

from apps.api.auth.dependencies import CurrentUser
from apps.api.schemas.proposals import JobView, ManualJob

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=list[JobView])
def list_jobs(user: CurrentUser, request: Request):
    return request.app.state.runs.jobs(user.id)


@router.post("/jobs", response_model=JobView, status_code=201)
def create_job(body: ManualJob, user: CurrentUser, request: Request):
    return request.app.state.runs.create_job(user.id, body)


@router.get("/jobs/{job_id}", response_model=JobView)
def get_job(job_id: str, user: CurrentUser, request: Request):
    return request.app.state.runs.job(user.id, job_id)
