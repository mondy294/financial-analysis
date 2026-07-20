from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from quant_system.api.errors import raise_bad_request, raise_not_found
from quant_system.api.jobs.runner import get_job, job_to_dict, list_jobs, request_cancel
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


@router.post("/{job_id}/cancel")
def job_cancel(job_id: str) -> dict[str, Any]:
    """请求取消运行中的任务（协作式，下一检查点生效）。"""
    job = get_job(job_id)
    if job is None:
        raise_not_found(f"任务不存在: {job_id}")
    if job.status not in ("PENDING", "RUNNING"):
        raise_bad_request(f"任务已结束（{job.status}），无法取消")
    request_cancel(job_id)
    updated = get_job(job_id)
    return job_to_dict(updated) if updated else job_to_dict(job)
