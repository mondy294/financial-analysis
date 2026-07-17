from __future__ import annotations

from fastapi import APIRouter, Query

from quant_system.api.errors import raise_not_found
from quant_system.api.jobs.runner import get_job, job_to_dict, list_jobs
from quant_system.api.schemas.common import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
def jobs(limit: int = Query(20, ge=1, le=100)) -> list[JobOut]:
    return [JobOut(**job_to_dict(j)) for j in list_jobs(limit=limit)]


@router.get("/{job_id}", response_model=JobOut)
def job_detail(job_id: str) -> JobOut:
    job = get_job(job_id)
    if job is None:
        raise_not_found(f"任务不存在: {job_id}")
    return JobOut(**job_to_dict(job))
