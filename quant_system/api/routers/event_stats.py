from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from quant_system.api.deps import get_repos
from quant_system.api.errors import ApiError
from quant_system.api.jobs.runner import get_job, job_to_dict, submit_job
from quant_system.data.repository import Repositories
from quant_system.eventstats import store
from quant_system.eventstats.constants import (
    CALENDAR_V1,
    DEFAULT_DEDUP_POLICY,
    DEFAULT_HORIZON_BARS,
    DEFAULT_RETURN_HORIZONS,
)
from quant_system.eventstats.runner import EventStatsRequest, reaggregate_run, run_event_stats

router = APIRouter(prefix="/event-stats", tags=["event-stats"])


class UniverseSpecIn(BaseModel):
    kind: str = Field(
        "all",
        description="all | codes | pool | cluster_sample",
    )
    codes: list[str] | None = None
    pool: str | None = None
    # cluster_sample：用户只设大概样本数；每簇几只由算法轮询决定
    profile: str | None = Field(None, description="聚类 profile，如 pearson_w60")
    target_samples: int | None = Field(None, ge=1, le=2000, description="大概抽取样本数")
    max_total: int | None = Field(
        None, ge=1, le=2000, description="兼容旧字段，等同 target_samples"
    )
    per_cluster: int | None = Field(
        None, ge=1, le=20, description="可选覆盖；默认不传，由算法决定"
    )
    min_cluster_size: int | None = Field(None, ge=1, le=50, description="最小簇规模（默认 2）")
    seed: int | None = Field(None, description="随机种子（可复现）")
    prefer: str | None = Field(None, description="central | uniform")


class EventStatsRunIn(BaseModel):
    pattern_id: str
    start: date
    end: date
    universe: UniverseSpecIn | None = None
    codes: str | None = Field(None, description="便捷：逗号分隔代码，等价 universe.kind=codes")
    horizon_bars: int = DEFAULT_HORIZON_BARS
    return_horizons: list[int] | None = None
    dedup_policy: str = DEFAULT_DEDUP_POLICY
    calendar: str = CALENDAR_V1
    day_concurrency: int | None = Field(None, ge=1, le=16, description="按交易日并行")
    match_concurrency: int | None = Field(None, ge=1, le=16, description="日内股票匹配并行")
    observe_concurrency: int | None = Field(None, ge=1, le=32, description="远期指标计算并行")


def _universe_from_body(body: EventStatsRunIn) -> dict[str, Any]:
    if body.universe is not None and str(body.universe.kind).lower() in (
        "cluster_sample",
        "clusters_sample",
        "sample_clusters",
    ):
        return body.universe.model_dump(exclude_none=True)
    if body.codes and body.codes.strip():
        codes = [c.strip().upper() for c in body.codes.split(",") if c.strip()]
        return {"kind": "codes", "codes": codes}
    if body.universe is not None:
        return body.universe.model_dump(exclude_none=True)
    return {"kind": "all"}


@router.post("/runs")
def create_run(body: EventStatsRunIn) -> dict[str, Any]:
    """异步启动事件统计 Job。"""
    universe = _universe_from_body(body)
    horizons = body.return_horizons or list(DEFAULT_RETURN_HORIZONS)

    job_params: dict[str, Any] = {
        "pattern_id": body.pattern_id.strip().upper(),
        "start": body.start.isoformat(),
        "end": body.end.isoformat(),
        "universe": universe,
        "horizon_bars": body.horizon_bars,
        "return_horizons": horizons,
        "dedup_policy": body.dedup_policy,
        "calendar": body.calendar,
        "day_concurrency": body.day_concurrency,
        "match_concurrency": body.match_concurrency,
        "observe_concurrency": body.observe_concurrency,
    }

    def _fn(job: Any) -> None:
        from quant_system.api.jobs.runner import JobCancelled, is_cancel_requested
        from quant_system.data.repository import build_repositories
        from quant_system.eventstats.discovery import EventStatsCancelled
        from quant_system.infra.db import session_scope

        job.progress = 0.01
        job.message = "初始化…"

        def _progress(p: float, msg: str) -> None:
            job.progress = max(0.0, min(0.99, float(p)))
            job.message = msg

        def _cancel() -> bool:
            return is_cancel_requested(job)

        def _on_run_created(run_id: str) -> None:
            base = dict(job.params or {})
            base["run_id"] = run_id
            job.params = base
            job.result = {"run_id": run_id, "status": "RUNNING"}

        try:
            with session_scope() as session:
                repos = build_repositories(session)
                report = run_event_stats(
                    repos,
                    EventStatsRequest(
                        pattern_id=body.pattern_id.strip().upper(),
                        start=body.start,
                        end=body.end,
                        universe_spec=universe,
                        horizon_bars=body.horizon_bars,
                        return_horizons=horizons,
                        dedup_policy=body.dedup_policy,
                        calendar=body.calendar,
                        day_concurrency=body.day_concurrency,
                        match_concurrency=body.match_concurrency,
                        observe_concurrency=body.observe_concurrency,
                    ),
                    progress_cb=_progress,
                    cancel_cb=_cancel,
                    on_run_created=_on_run_created,
                    job_id=job.job_id,
                )
        except EventStatsCancelled as exc:
            raise JobCancelled(str(exc) or "用户取消") from exc
        job.result = {
            "run_id": report.run_id,
            "status": report.status,
            "event_count": report.event_count,
            "duration_ms": report.duration_ms,
            "summary": report.summary,
        }
        job.message = f"done events={report.event_count}"

    job = submit_job("pattern.event_stats", _fn, params=job_params)
    return job_to_dict(job)


@router.get("/runs")
def list_runs(
    limit: int = Query(10, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    session = repos.kline._session  # type: ignore[attr-defined]
    total = store.count_runs(session)
    rows = store.list_runs(session, limit=limit, offset=offset)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "runs": [store.run_to_dict(r) for r in rows],
    }


@router.get("/runs/{run_id}")
def get_run(run_id: str, repos: Repositories = Depends(get_repos)) -> dict[str, Any]:
    session = repos.kline._session  # type: ignore[attr-defined]
    row = store.get_run(session, run_id)
    if row is None:
        raise ApiError("run_not_found", f"run {run_id} not found", status_code=404)
    out = store.run_to_dict(row)
    # 附带内存 Job 是否仍存活（服务重启后为 false）
    live = None
    if row.job_id:
        live = get_job(row.job_id)
    if live is None:
        from quant_system.api.jobs.runner import list_jobs

        for j in list_jobs(limit=50):
            if j.kind != "pattern.event_stats":
                continue
            rid = (j.params or {}).get("run_id") or (j.result or {}).get("run_id")
            if rid == run_id:
                live = j
                break
    out["job_alive"] = live is not None and live.status in ("PENDING", "RUNNING")
    if live is not None:
        out["live_job"] = job_to_dict(live)
    return out


@router.delete("/runs/{run_id}")
def delete_run(run_id: str, repos: Repositories = Depends(get_repos)) -> dict[str, Any]:
    """删除历史任务及其事件明细。进行中且 Job 仍存活时禁止删除（请先取消）。"""
    from quant_system.api.jobs.runner import list_jobs

    session = repos.kline._session  # type: ignore[attr-defined]
    row = store.get_run(session, run_id)
    if row is None:
        raise ApiError("run_not_found", f"run {run_id} not found", status_code=404)

    live = get_job(row.job_id) if row.job_id else None
    if live is None:
        for j in list_jobs(limit=50):
            if j.kind != "pattern.event_stats":
                continue
            rid = (j.params or {}).get("run_id") or (j.result or {}).get("run_id")
            if rid == run_id:
                live = j
                break
    if live is not None and live.status in ("PENDING", "RUNNING"):
        raise ApiError(
            "bad_request",
            "任务仍在运行，请先取消后再删除",
            status_code=400,
        )

    ok = store.delete_run(session, run_id)
    if not ok:
        raise ApiError("run_not_found", f"run {run_id} not found", status_code=404)
    session.commit()
    return {"ok": True, "run_id": run_id}


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, repos: Repositories = Depends(get_repos)) -> dict[str, Any]:
    """取消运行中任务：优先协作取消内存 Job；若进程已丢则直接标记 CANCELLED。"""
    from quant_system.api.jobs.runner import list_jobs, request_cancel

    session = repos.kline._session  # type: ignore[attr-defined]
    row = store.get_run(session, run_id)
    if row is None:
        raise ApiError("run_not_found", f"run {run_id} not found", status_code=404)
    if row.status not in ("PENDING", "RUNNING"):
        raise ApiError("bad_request", f"任务已结束（{row.status}），无法取消", status_code=400)

    live = get_job(row.job_id) if row.job_id else None
    if live is None:
        for j in list_jobs(limit=50):
            if j.kind != "pattern.event_stats":
                continue
            rid = (j.params or {}).get("run_id") or (j.result or {}).get("run_id")
            if rid == run_id:
                live = j
                break

    if live is not None and live.status in ("PENDING", "RUNNING"):
        request_cancel(live.job_id)
        store.update_run_progress(
            session,
            run_id,
            progress=float(row.progress or live.progress or 0),
            message="正在取消…",
            job_id=live.job_id,
        )
        session.commit()
        return {
            **store.run_to_dict(store.get_run(session, run_id)),  # type: ignore[arg-type]
            "cancel_mode": "job",
            "job_id": live.job_id,
        }

    # 孤儿任务：内存 Job 已不存在（常见于热重载）
    store.finish_run(
        session,
        run_id,
        status="CANCELLED",
        summary=None,
        event_count=int(row.event_count or 0),
        duration_ms=int(row.duration_ms or 0),
        error_msg="后台任务已丢失（服务重启），已标记取消",
    )
    session.commit()
    return {
        **store.run_to_dict(store.get_run(session, run_id)),  # type: ignore[arg-type]
        "cancel_mode": "orphan",
    }


@router.get("/runs/{run_id}/events")
def get_events(
    run_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    order_by: str = Query("entry_similarity"),
    desc: bool = Query(True),
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    session = repos.kline._session  # type: ignore[attr-defined]
    if store.get_run(session, run_id) is None:
        raise ApiError("run_not_found", f"run {run_id} not found", status_code=404)
    allowed = {
        "entry_similarity",
        "signal_date",
        "return_1",
        "return_3",
        "return_5",
        "return_10",
        "return_20",
        "return_60",
        "return_horizon",
        "mfe",
        "mae",
        "max_drawdown",
        "code",
    }
    if order_by not in allowed:
        order_by = "entry_similarity"
    total = store.count_events(session, run_id)
    rows = store.list_events(
        session,
        run_id,
        limit=limit,
        offset=offset,
        order_by=order_by,
        descending=desc,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": [store.event_to_dict(e) for e in rows],
    }


@router.post("/runs/{run_id}/reaggregate")
def post_reaggregate(run_id: str, repos: Repositories = Depends(get_repos)) -> dict[str, Any]:
    try:
        summary = reaggregate_run(repos, run_id)
    except ValueError as exc:
        raise ApiError("run_not_found", str(exc), status_code=404) from exc
    return {"run_id": run_id, "summary": summary}


@router.get("/jobs/{job_id}")
def get_event_job(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if job is None:
        raise ApiError("job_not_found", f"job {job_id} not found", status_code=404)
    return job_to_dict(job)
