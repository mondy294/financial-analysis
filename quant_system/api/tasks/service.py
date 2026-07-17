"""任务提交：校验 + heavy 互斥 + submit_job。"""
from __future__ import annotations

from typing import Any

from quant_system.api.errors import raise_bad_request, raise_conflict
from quant_system.api.jobs.runner import JobRecord, job_to_dict, list_jobs, submit_job
from quant_system.api.tasks.catalog import get_task
from quant_system.api.tasks.runners import execute_task


def heavy_job_running() -> JobRecord | None:
    for job in list_jobs(limit=50):
        if job.status in ("PENDING", "RUNNING"):
            spec = get_task(job.kind)
            if spec is not None and spec.heavy:
                return job
            # pattern.scan / pattern.dry_scan 等也算重任务
            if job.kind.startswith(("update.", "pattern.", "relationship.", "pipeline", "feature", "select", "report", "quality", "init_db")):
                return job
    return None


def run_task(task_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = get_task(task_id)
    if spec is None:
        raise_bad_request(f"未知任务: {task_id}")

    params = dict(params or {})
    # 填默认值
    for p in spec.params:
        if p.name not in params or params[p.name] is None or params[p.name] == "":
            if p.default is not None:
                params[p.name] = p.default

    if spec.heavy:
        running = heavy_job_running()
        if running is not None:
            raise_conflict(
                f"已有重任务运行中: {running.kind} ({running.job_id})，请等待完成后再提交"
            )

    def _fn(job: JobRecord) -> None:
        execute_task(job, task_id, params)

    job = submit_job(task_id, _fn)
    return job_to_dict(job)


def catalog_payload() -> dict[str, Any]:
    from quant_system.api.tasks.catalog import GROUP_LABELS, GROUP_ORDER, list_tasks

    by_group: dict[str, list[dict[str, Any]]] = {g: [] for g in GROUP_ORDER}
    for item in list_tasks():
        by_group.setdefault(item["group"], []).append(item)
    return {
        "groups": [
            {
                "group": g,
                "label": GROUP_LABELS.get(g, g),
                "tasks": by_group.get(g, []),
            }
            for g in GROUP_ORDER
            if by_group.get(g)
        ],
        "heavy_running": (
            {
                "job_id": j.job_id,
                "kind": j.kind,
                "status": j.status,
                "message": j.message,
            }
            if (j := heavy_job_running()) is not None
            else None
        ),
    }
