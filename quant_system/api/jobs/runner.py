from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable


class JobCancelled(Exception):
    """协作式取消：任务在检查点抛出后进入 CANCELLED。"""


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
    params: dict[str, Any] | None = None
    cancel_requested: bool = False


_LOCK = threading.Lock()
_JOBS: dict[str, JobRecord] = {}


def list_jobs(limit: int = 20) -> list[JobRecord]:
    with _LOCK:
        items = sorted(_JOBS.values(), key=lambda j: j.created_at, reverse=True)
        return items[:limit]


def get_job(job_id: str) -> JobRecord | None:
    with _LOCK:
        return _JOBS.get(job_id)


def is_cancel_requested(job: JobRecord) -> bool:
    return bool(job.cancel_requested)


def request_cancel(job_id: str) -> JobRecord | None:
    """请求取消；返回 job，不存在或不在运行则 None / 原样。"""
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return None
        if job.status not in ("PENDING", "RUNNING"):
            return job
        job.cancel_requested = True
        job.message = "正在取消…（等待当前检查点）"
        return job


def submit_job(
    kind: str,
    fn: Callable[[JobRecord], None],
    *,
    params: dict[str, Any] | None = None,
) -> JobRecord:
    job = JobRecord(job_id=uuid.uuid4().hex[:12], kind=kind, params=params)
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
                if job.status not in ("FAILED", "CANCELLED"):
                    if job.cancel_requested:
                        job.status = "CANCELLED"
                        job.message = "已取消"
                    else:
                        job.status = "SUCCESS"
                        job.progress = 1.0
                        job.message = job.message or "done"
                    job.finished_at = datetime.utcnow()
        except JobCancelled as exc:
            with _LOCK:
                job.status = "CANCELLED"
                job.error = str(exc) or "用户取消"
                job.finished_at = datetime.utcnow()
                job.message = "已取消"
        except Exception as exc:  # noqa: BLE001
            with _LOCK:
                if job.cancel_requested:
                    job.status = "CANCELLED"
                    job.error = str(exc)
                    job.message = "已取消"
                else:
                    job.status = "FAILED"
                    job.error = str(exc)
                    job.message = "failed"
                job.finished_at = datetime.utcnow()

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
        "params": job.params,
        "cancel_requested": job.cancel_requested,
    }


def run_pattern_scan_job(
    job: JobRecord,
    *,
    trade_date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    pattern_ids: list[str] | None,
    force: bool,
) -> None:
    from quant_system.data.repository import build_repositories
    from quant_system.infra import trading_calendar as tc
    from quant_system.infra.db import session_scope
    from quant_system.patterns.service import build_patterns

    start = start_date or trade_date
    end = end_date or trade_date or start
    if start is None:
        start = end = tc.latest_trading_day()
    assert start is not None and end is not None
    if start > end:
        start, end = end, start
    days = tc.trading_days_between(start, end)
    if not days:
        job.progress = 1.0
        job.message = "区间内无交易日"
        job.result = {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "days": 0,
            "per_day": [],
        }
        return

    job.message = f"scanning {start.isoformat()} → {end.isoformat()} ({len(days)} 日)"
    job.progress = 0.01
    per_day: list[dict] = []
    n = len(days)

    for i, d in enumerate(days):
        if is_cancel_requested(job):
            raise JobCancelled("用户取消")

        day_lo = i / n
        day_hi = (i + 1) / n

        def _progress(
            p: float,
            msg: str,
            *,
            _lo=day_lo,
            _hi=day_hi,
            _d=d,
            _i=i,
            _n=n,
        ) -> None:
            job.progress = max(0.0, min(0.99, _lo + (_hi - _lo) * float(p)))
            job.message = f"[{_d.isoformat()} {_i + 1}/{_n}] {msg}"

        with session_scope() as session:
            repos = build_repositories(session)
            report = build_patterns(
                repos,
                trade_date=d,
                pattern_ids=pattern_ids,
                dry_run=False,
                force=force,
                progress_cb=_progress,
            )
        per_day.append(
            {
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
        )

    skipped_n = sum(1 for x in per_day if x.get("skipped"))
    job.progress = 1.0
    job.message = (
        f"scan finished · {n} 日"
        + (f"（跳过 {skipped_n}）" if skipped_n else "")
    )
    # 单日时保留旧字段，兼容前端/任务结果展示
    last = per_day[-1]
    job.result = {
        "trade_date": last["trade_date"] if n == 1 else None,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "days": n,
        "skipped_days": skipped_n,
        "universe_size": last.get("universe_size"),
        "skipped": last.get("skipped") if n == 1 else None,
        "duration_ms": sum(int(x.get("duration_ms") or 0) for x in per_day),
        "params_version": last.get("params_version"),
        "per_pattern": last.get("per_pattern") if n == 1 else None,
        "per_day": per_day,
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
