from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from quant_system.database.models import PatternEvent, PatternEventRun


def create_run(session: Session, row: PatternEventRun) -> PatternEventRun:
    session.add(row)
    session.flush()
    return row


def finish_run(
    session: Session,
    run_id: str,
    *,
    status: str,
    summary: dict[str, Any] | None,
    event_count: int,
    duration_ms: int,
    error_msg: str | None = None,
) -> None:
    run = session.get(PatternEventRun, run_id)
    if run is None:
        return
    run.status = status
    run.summary_json = summary
    run.event_count = event_count
    run.duration_ms = duration_ms
    run.error_msg = error_msg
    run.finished_at = datetime.utcnow()
    if status in ("SUCCESS", "FAILED", "CANCELLED"):
        run.progress = 1.0 if status == "SUCCESS" else run.progress
        if status == "CANCELLED" and not run.progress_msg:
            run.progress_msg = "已取消"
    session.flush()


def update_run_progress(
    session: Session,
    run_id: str,
    *,
    progress: float,
    message: str | None = None,
    job_id: str | None = None,
) -> None:
    run = session.get(PatternEventRun, run_id)
    if run is None:
        return
    run.progress = max(0.0, min(1.0, float(progress)))
    if message is not None:
        run.progress_msg = message[:256]
    if job_id:
        run.job_id = job_id
    session.flush()


def bind_run_job(session: Session, run_id: str, job_id: str) -> None:
    run = session.get(PatternEventRun, run_id)
    if run is None:
        return
    run.job_id = job_id
    session.flush()


def bulk_insert_events(session: Session, events: list[PatternEvent]) -> int:
    if not events:
        return 0
    session.add_all(events)
    session.flush()
    return len(events)


def get_run(session: Session, run_id: str) -> PatternEventRun | None:
    return session.get(PatternEventRun, run_id)


def delete_run(session: Session, run_id: str) -> bool:
    """删除 run 及其全部事件。不存在返回 False。"""
    run = session.get(PatternEventRun, run_id)
    if run is None:
        return False
    session.execute(delete(PatternEvent).where(PatternEvent.run_id == run_id))
    session.delete(run)
    session.flush()
    return True


def count_runs(session: Session) -> int:
    from sqlalchemy import func

    return int(session.scalar(select(func.count()).select_from(PatternEventRun)) or 0)


def list_runs(
    session: Session,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[PatternEventRun]:
    stmt = (
        select(PatternEventRun)
        .order_by(PatternEventRun.created_at.desc())
        .offset(max(0, int(offset)))
        .limit(limit)
    )
    return list(session.scalars(stmt).all())


def list_events(
    session: Session,
    run_id: str,
    *,
    limit: int = 100,
    offset: int = 0,
    order_by: str = "entry_similarity",
    descending: bool = True,
) -> list[PatternEvent]:
    col = getattr(PatternEvent, order_by, PatternEvent.entry_similarity)
    order = col.desc() if descending else col.asc()
    stmt = (
        select(PatternEvent)
        .where(PatternEvent.run_id == run_id)
        .order_by(order, PatternEvent.code.asc())
        .offset(offset)
        .limit(limit)
    )
    return list(session.scalars(stmt).all())


def count_events(session: Session, run_id: str) -> int:
    from sqlalchemy import func

    return int(
        session.scalar(
            select(func.count()).select_from(PatternEvent).where(PatternEvent.run_id == run_id)
        )
        or 0
    )


def events_as_dicts(session: Session, run_id: str) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(PatternEvent).where(PatternEvent.run_id == run_id)
    ).all()
    return [event_to_dict(r) for r in rows]


def event_to_dict(e: PatternEvent) -> dict[str, Any]:
    return {
        "event_id": e.event_id,
        "run_id": e.run_id,
        "code": e.code,
        "signal_date": e.signal_date.isoformat() if e.signal_date else None,
        "entry_similarity": float(e.entry_similarity) if e.entry_similarity is not None else None,
        "match_explain": e.match_explain_json,
        "entry_snapshot": e.entry_snapshot_json,
        "tags": e.tags_json or [],
        "return_1": _num(e.return_1),
        "return_3": _num(e.return_3),
        "return_5": _num(e.return_5),
        "return_10": _num(e.return_10),
        "return_20": _num(e.return_20),
        "return_60": _num(e.return_60),
        "return_horizon": _num(e.return_horizon),
        "mfe": _num(e.mfe),
        "mae": _num(e.mae),
        "max_drawdown": _num(e.max_drawdown),
        "volatility": _num(e.volatility),
        "bull_ratio": _num(e.bull_ratio),
        "up_days": e.up_days,
        "continuous_up_days": e.continuous_up_days,
        "highest_day": e.highest_day,
        "lowest_day": e.lowest_day,
        "time_to_mfe": e.time_to_mfe,
        "time_to_mae": e.time_to_mae,
        "forward_bars_available": e.forward_bars_available,
        "forward_status": e.forward_status,
        "extra_metrics": e.extra_metrics_json,
    }


def run_to_dict(r: PatternEventRun) -> dict[str, Any]:
    return {
        "run_id": r.run_id,
        "entry_pattern_id": r.entry_pattern_id,
        "entry_version": r.entry_version,
        "outcome_mode": r.outcome_mode,
        "universe_spec": r.universe_spec,
        "start_date": r.start_date.isoformat(),
        "end_date": r.end_date.isoformat(),
        "horizon_bars": r.horizon_bars,
        "return_horizons": r.return_horizons_json,
        "calendar": r.calendar,
        "anchor_mode": r.anchor_mode,
        "price_adj": r.price_adj,
        "dedup_policy": r.dedup_policy,
        "engine_version": r.engine_version,
        "code_hash": r.code_hash,
        "engine_config_hash": r.engine_config_hash,
        "aggregation_version": r.aggregation_version,
        "status": r.status,
        "error_msg": r.error_msg,
        "event_count": r.event_count,
        "summary": r.summary_json,
        "job_id": r.job_id,
        "progress": float(r.progress) if r.progress is not None else None,
        "progress_msg": r.progress_msg,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "duration_ms": r.duration_ms,
    }


def _num(v: Any) -> float | None:
    if v is None:
        return None
    return float(v)
