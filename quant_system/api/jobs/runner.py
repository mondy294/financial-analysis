from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable


@dataclass
class JobRecord:
    job_id: str
    kind: str
    status: str = "PENDING"
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress: float = 0.0
    message: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None


_LOCK = threading.Lock()
_JOBS: dict[str, JobRecord] = {}


def list_jobs(limit: int = 20) -> list[JobRecord]:
    with _LOCK:
        items = sorted(_JOBS.values(), key=lambda j: j.created_at, reverse=True)
        return items[:limit]


def get_job(job_id: str) -> JobRecord | None:
    with _LOCK:
        return _JOBS.get(job_id)


def submit_job(kind: str, fn: Callable[[JobRecord], None]) -> JobRecord:
    job = JobRecord(job_id=uuid.uuid4().hex[:12], kind=kind)
    with _LOCK:
        _JOBS[job.job_id] = job

    def _run() -> None:
        with _LOCK:
            job.status = "RUNNING"
            job.started_at = datetime.utcnow()
            job.message = "running"
        try:
            fn(job)
            with _LOCK:
                if job.status != "FAILED":
                    job.status = "SUCCESS"
                    job.progress = 1.0
                    job.finished_at = datetime.utcnow()
                    job.message = job.message or "done"
        except Exception as exc:  # noqa: BLE001
            with _LOCK:
                job.status = "FAILED"
                job.error = str(exc)
                job.finished_at = datetime.utcnow()
                job.message = "failed"

    threading.Thread(target=_run, daemon=True).start()
    return job


def job_to_dict(job: JobRecord) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "kind": job.kind,
        "status": job.status,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "progress": job.progress,
        "message": job.message,
        "error": job.error,
        "result": job.result,
    }


def run_pattern_scan_job(
    job: JobRecord,
    *,
    trade_date: date,
    pattern_ids: list[str] | None,
    force: bool,
) -> None:
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope
    from quant_system.patterns.service import build_patterns

    job.message = f"scanning {trade_date.isoformat()}"
    job.progress = 0.02

    def _progress(p: float, msg: str) -> None:
        job.progress = max(0.0, min(0.99, float(p)))
        job.message = msg

    with session_scope() as session:
        repos = build_repositories(session)
        report = build_patterns(
            repos,
            trade_date=trade_date,
            pattern_ids=pattern_ids,
            dry_run=False,
            force=force,
            progress_cb=_progress,
        )
    job.progress = 1.0
    job.message = (
        "已跳过（已有成功扫描）" if report.skipped else "scan finished"
    )
    job.result = {
        "trade_date": report.trade_date.isoformat(),
        "universe_size": report.universe_size,
        "skipped": report.skipped,
        "duration_ms": report.duration_ms,
        "params_version": report.params_version,
        "per_pattern": [
            {
                "pattern_id": p.pattern_id,
                "display_name": p.display_name,
                "matched_count": p.matched_count,
                "written": p.written,
            }
            for p in report.per_pattern
        ],
    }


def run_pattern_dry_scan_job(
    job: JobRecord,
    *,
    pattern_id: str,
    trade_date: date,
    limit: int,
    body: dict[str, Any] | None = None,
) -> None:
    """草稿试扫：不写 abnormal_signal。"""
    from quant_system.api.services import definitions as def_svc
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope

    def _progress(p: float, msg: str) -> None:
        job.progress = max(0.0, min(0.95, float(p)))
        job.message = msg

    job.message = f"dry-scan {pattern_id} @ {trade_date.isoformat()}"
    job.progress = 0.05
    with session_scope() as session:
        repos = build_repositories(session)
        result = def_svc.run_dry_scan(
            repos,
            pattern_id,
            trade_date=trade_date,
            limit=limit,
            body=body,
            progress_cb=_progress,
        )
    job.progress = 1.0
    job.message = "dry-scan finished (not persisted)"
    job.result = result
