from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable

from quant_system.data.repository import Repositories
from quant_system.database.models import PatternEvent, PatternEventRun
from quant_system.eventstats.aggregate import aggregate_events
from quant_system.eventstats.constants import (
    AGGREGATION_VERSION,
    ANCHOR_MODE_V1,
    CALENDAR_V1,
    DEFAULT_DEDUP_POLICY,
    DEFAULT_HORIZON_BARS,
    DEFAULT_RETURN_HORIZONS,
    ENGINE_VERSION,
    OUTCOME_MODE_OBSERVATION,
    PRICE_ADJ_V1,
)
from quant_system.eventstats.discovery import EventStatsCancelled, discover_and_observe
from quant_system.eventstats.hashes import compute_code_hash, compute_engine_config_hash
from quant_system.eventstats import store
from quant_system.patterns.definition import PatternDefinition
from quant_system.patterns.registry import get_definitions
from quant_system.patterns.serde import definition_to_dict

ProgressCb = Callable[[float, str], None]
CancelCb = Callable[[], bool]


@dataclass
class EventStatsRequest:
    pattern_id: str
    start: date
    end: date
    universe_spec: dict[str, Any] = field(default_factory=lambda: {"kind": "all"})
    horizon_bars: int = DEFAULT_HORIZON_BARS
    return_horizons: list[int] = field(default_factory=lambda: list(DEFAULT_RETURN_HORIZONS))
    dedup_policy: str = DEFAULT_DEDUP_POLICY
    calendar: str = CALENDAR_V1
    entry_version: str | None = None  # None → 用 definition.version
    # 并发：日维度 / 日内匹配 / 远期 Observe（None=引擎默认）
    day_concurrency: int | None = None
    match_concurrency: int | None = None
    observe_concurrency: int | None = None


@dataclass
class EventStatsReport:
    run_id: str
    status: str
    event_count: int
    summary: dict[str, Any] | None
    duration_ms: int
    error_msg: str | None = None


def _normalize_universe(
    session: Any,  # Session
    spec: dict[str, Any] | None,
) -> dict[str, Any]:
    if not spec:
        return {"kind": "all"}
    kind = str(spec.get("kind") or "all").lower()
    if kind == "codes":
        codes = [str(c).strip().upper() for c in (spec.get("codes") or []) if str(c).strip()]
        if not codes:
            raise ValueError("universe_spec.kind=codes 时 codes 不能为空（最小 1 只）")
        return {"kind": "codes", "codes": codes}
    if kind == "pool":
        pool = str(spec.get("pool") or "").strip()
        if not pool:
            raise ValueError("universe_spec.kind=pool 时需要 pool")
        return {"kind": "pool", "pool": pool}
    if kind in ("cluster_sample", "clusters_sample", "sample_clusters"):
        from quant_system.eventstats.cluster_sample import expand_cluster_sample_spec

        return expand_cluster_sample_spec(session, spec)
    return {"kind": "all"}


def run_event_stats(
    repos: Repositories,
    req: EventStatsRequest,
    *,
    progress_cb: ProgressCb | None = None,
    cancel_cb: CancelCb | None = None,
    on_run_created: Callable[[str], None] | None = None,
    job_id: str | None = None,
) -> EventStatsReport:
    """P0：Discovery + Observation + Storage + Aggregation。"""
    t0 = time.perf_counter()
    session = repos.kline._session  # type: ignore[attr-defined]

    if req.calendar != CALENDAR_V1:
        raise ValueError(f"P0 仅支持 calendar={CALENDAR_V1}，收到 {req.calendar}")
    if req.start > req.end:
        raise ValueError("start 不能晚于 end")

    universe_spec = _normalize_universe(session, req.universe_spec)
    defs = get_definitions([req.pattern_id])
    if not defs:
        raise ValueError(f"未找到已发布 Pattern: {req.pattern_id}")
    definition: PatternDefinition = defs[0]
    entry_version = req.entry_version or definition.version

    body = definition_to_dict(definition)
    code_hash = compute_code_hash()
    config_hash = compute_engine_config_hash(
        definition_body=body,
        entry_version=entry_version,
        horizon_bars=req.horizon_bars,
        return_horizons=list(req.return_horizons),
        calendar=req.calendar,
        anchor_mode=ANCHOR_MODE_V1,
        price_adj=PRICE_ADJ_V1,
        dedup_policy=req.dedup_policy,
        providers=["standard@1.0.0"],
    )

    run_id = uuid.uuid4().hex[:16]
    run_row = PatternEventRun(
        run_id=run_id,
        entry_pattern_id=definition.id,
        entry_version=entry_version,
        outcome_mode=OUTCOME_MODE_OBSERVATION,
        outcome_version=None,
        universe_spec=universe_spec,
        start_date=req.start,
        end_date=req.end,
        horizon_bars=int(req.horizon_bars),
        return_horizons_json=list(req.return_horizons),
        calendar=req.calendar,
        anchor_mode=ANCHOR_MODE_V1,
        price_adj=PRICE_ADJ_V1,
        dedup_policy=req.dedup_policy,
        engine_version=ENGINE_VERSION,
        code_hash=code_hash,
        engine_config_hash=config_hash,
        aggregation_version=AGGREGATION_VERSION,
        status="RUNNING",
        job_id=job_id,
        progress=0.02,
        progress_msg="初始化…",
        created_at=datetime.utcnow(),
    )
    store.create_run(session, run_row)
    session.commit()
    if on_run_created is not None:
        on_run_created(run_id)

    _last_persist = [0.0]

    def _cb(p: float, msg: str) -> None:
        if progress_cb:
            progress_cb(p, msg)
        # 独立短事务写入进度，供离开页面 / 服务重启后展示
        now = time.monotonic()
        if now - _last_persist[0] < 0.4 and float(p) < 0.99:
            return
        _last_persist[0] = now
        try:
            from quant_system.infra.db import session_scope

            with session_scope() as prog_session:
                store.update_run_progress(
                    prog_session,
                    run_id,
                    progress=float(p),
                    message=msg,
                    job_id=job_id,
                )
                prog_session.commit()
        except Exception:  # noqa: BLE001
            pass

    try:
        _cb(0.02, "start discovery")
        events, disc_meta = discover_and_observe(
            repos,
            definition,
            start=req.start,
            end=req.end,
            universe_spec=universe_spec,
            horizon_bars=req.horizon_bars,
            return_horizons=list(req.return_horizons),
            dedup_policy=req.dedup_policy,
            progress_cb=_cb,
            cancel_cb=cancel_cb,
            day_concurrency=req.day_concurrency,
            match_concurrency=req.match_concurrency,
            observe_concurrency=req.observe_concurrency,
        )

        if cancel_cb and cancel_cb():
            raise EventStatsCancelled("用户取消")

        _cb(0.86, f"写入 {len(events)} 条事件…")
        orm_events = [_to_orm(run_id, e) for e in events]
        # 分批提交避免超大事务
        batch = 200
        n_batch = max(1, (len(orm_events) + batch - 1) // batch) if orm_events else 1
        for i in range(0, len(orm_events), batch):
            if cancel_cb and cancel_cb():
                raise EventStatsCancelled("用户取消")
            store.bulk_insert_events(session, orm_events[i : i + batch])
            session.commit()
            bi = i // batch + 1
            _cb(0.86 + 0.06 * (bi / n_batch), f"写入事件 {min(i + batch, len(orm_events))}/{len(orm_events)}")

        _cb(0.93, "聚合统计…")
        summary = aggregate_events(
            [
                {
                    "code": e.code,
                    "forward_status": e.metrics.get("forward_status"),
                    **{k: e.metrics.get(k) for k in e.metrics},
                }
                for e in events
            ],
            universe_size_hint=disc_meta.get("universe_size_hint"),
        )
        summary["discovery"] = disc_meta

        duration_ms = int((time.perf_counter() - t0) * 1000)
        store.finish_run(
            session,
            run_id,
            status="SUCCESS",
            summary=summary,
            event_count=len(events),
            duration_ms=duration_ms,
        )
        session.commit()
        _cb(1.0, "done")
        return EventStatsReport(
            run_id=run_id,
            status="SUCCESS",
            event_count=len(events),
            summary=summary,
            duration_ms=duration_ms,
        )
    except EventStatsCancelled as exc:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        store.finish_run(
            session,
            run_id,
            status="CANCELLED",
            summary=None,
            event_count=0,
            duration_ms=duration_ms,
            error_msg=str(exc) or "用户取消",
        )
        session.commit()
        raise
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.perf_counter() - t0) * 1000)
        store.finish_run(
            session,
            run_id,
            status="FAILED",
            summary=None,
            event_count=0,
            duration_ms=duration_ms,
            error_msg=str(exc),
        )
        session.commit()
        raise


def _to_orm(run_id: str, e: Any) -> PatternEvent:
    m = e.metrics
    return PatternEvent(
        run_id=run_id,
        code=e.code,
        signal_date=e.signal_date,
        entry_similarity=e.entry_similarity,
        match_explain_json=e.match_explain,
        entry_snapshot_json=e.entry_snapshot,
        tags_json=e.tags,
        return_1=m.get("return_1"),
        return_3=m.get("return_3"),
        return_5=m.get("return_5"),
        return_10=m.get("return_10"),
        return_20=m.get("return_20"),
        return_60=m.get("return_60"),
        return_horizon=m.get("return_horizon"),
        mfe=m.get("mfe"),
        mae=m.get("mae"),
        max_drawdown=m.get("max_drawdown"),
        volatility=m.get("volatility"),
        bull_ratio=m.get("bull_ratio"),
        up_days=m.get("up_days"),
        continuous_up_days=m.get("continuous_up_days"),
        highest_day=m.get("highest_day"),
        lowest_day=m.get("lowest_day"),
        time_to_mfe=m.get("time_to_mfe"),
        time_to_mae=m.get("time_to_mae"),
        forward_bars_available=m.get("forward_bars_available"),
        forward_status=str(m.get("forward_status") or "insufficient"),
        extra_metrics_json={},
        outcome_json=None,
    )


def reaggregate_run(repos: Repositories, run_id: str) -> dict[str, Any]:
    session = repos.kline._session  # type: ignore[attr-defined]
    run = store.get_run(session, run_id)
    if run is None:
        raise ValueError(f"run not found: {run_id}")
    rows = store.events_as_dicts(session, run_id)
    summary = aggregate_events(rows, universe_size_hint=(run.summary_json or {}).get("discovery", {}).get("universe_size_hint") if run.summary_json else None)
    run.summary_json = summary
    run.aggregation_version = AGGREGATION_VERSION
    session.commit()
    return summary
