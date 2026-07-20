from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable

import pandas as pd

from quant_system.data.repository import Repositories, build_repositories
from quant_system.eventstats.explain import build_entry_snapshot, build_match_explain
from quant_system.eventstats.observe import compute_observation
from quant_system.eventstats.tags import enrich_tags
from quant_system.infra.db import session_scope
from quant_system.infra.trading_calendar import trading_days_between
from quant_system.patterns.context import build_pattern_context
from quant_system.patterns.definition import PatternDefinition
from quant_system.patterns.result import PatternMatchResult
from quant_system.patterns.runner import PatternRunner

ProgressCb = Callable[[float, str], None]
CancelCb = Callable[[], bool]


class EventStatsCancelled(Exception):
    """用户取消事件统计。"""


@dataclass
class RawEvent:
    code: str
    signal_date: date
    entry_similarity: float
    match_explain: dict[str, Any]
    entry_snapshot: dict[str, Any]
    tags: list[str]
    metrics: dict[str, Any]


def resolve_universe_codes(
    repos: Repositories,
    trade_date: date,
    universe_spec: dict[str, Any],
) -> list[str] | None:
    """返回限定 codes；None 表示当日有 K 线的全宇宙（再经 context 过滤）。"""
    kind = str(universe_spec.get("kind") or "all")
    if kind in ("codes", "cluster_sample", "clusters_sample", "sample_clusters"):
        # cluster_sample 在 runner 规范化时已锁定 codes
        codes = universe_spec.get("codes") or []
        return [str(c).strip().upper() for c in codes if str(c).strip()]
    if kind == "pool":
        pool = str(universe_spec.get("pool") or "").strip()
        if not pool:
            return []
        return list(repos.stock.list_pool_members(pool, as_of=trade_date))
    return None  # all


def apply_dedup(
    events: list[RawEvent],
    *,
    policy: str,
    cooldown_bars: int,
) -> list[RawEvent]:
    if policy in ("", "none") or cooldown_bars <= 0:
        return events
    events_sorted = sorted(events, key=lambda e: (e.code, e.signal_date))
    last_kept: dict[str, date] = {}
    out: list[RawEvent] = []
    for ev in events_sorted:
        prev = last_kept.get(ev.code)
        if prev is not None:
            gap = len(trading_days_between(prev, ev.signal_date)) - 1
            if gap < cooldown_bars:
                continue
        out.append(ev)
        last_kept[ev.code] = ev.signal_date
    return out


def _clamp_workers(n: int, *, lo: int = 1, hi: int = 32) -> int:
    return max(lo, min(hi, int(n)))


def _anchor_and_forward(
    repos: Repositories,
    code: str,
    signal_date: date,
    horizon_bars: int,
) -> tuple[float | None, pd.DataFrame]:
    end = signal_date + timedelta(days=max(40, int(horizon_bars * 2.2) + 30))
    df = repos.kline.read_kline(code, start=signal_date, end=end, adj="qfq")
    if df.empty:
        return None, pd.DataFrame()
    sig = df[df["trade_date"] == signal_date]
    if sig.empty:
        return None, pd.DataFrame()
    anchor = float(sig.iloc[0]["close"])
    forward = df[df["trade_date"] > signal_date].reset_index(drop=True)
    return anchor, forward


def _to_raw_event(
    repos: Repositories,
    definition: PatternDefinition,
    result: PatternMatchResult,
    stock_meta: dict[str, Any],
    horizon_bars: int,
    return_horizons: list[int],
) -> RawEvent:
    meta = stock_meta.get(result.code) or {}
    tags = enrich_tags(result.code, meta)
    explain = build_match_explain(result, definition)
    snapshot = build_entry_snapshot(result)
    anchor, forward = _anchor_and_forward(repos, result.code, result.trade_date, horizon_bars)
    if anchor is None:
        metrics = compute_observation(
            pd.DataFrame(),
            anchor_close=0.0,
            horizon_bars=horizon_bars,
            return_horizons=return_horizons,
        )
    else:
        metrics = compute_observation(
            forward,
            anchor_close=anchor,
            horizon_bars=horizon_bars,
            return_horizons=return_horizons,
        )
    return RawEvent(
        code=result.code,
        signal_date=result.trade_date,
        entry_similarity=float(result.similarity),
        match_explain=explain,
        entry_snapshot=snapshot,
        tags=tags,
        metrics=metrics,
    )


def _observe_with_own_session(
    definition: PatternDefinition,
    result: PatternMatchResult,
    stock_meta: dict[str, Any],
    horizon_bars: int,
    return_horizons: list[int],
) -> RawEvent:
    """Observe 使用独立 session，避免跨线程共享 SQLAlchemy Session。"""
    with session_scope() as session:
        repos = build_repositories(session)
        return _to_raw_event(
            repos, definition, result, stock_meta, horizon_bars, return_horizons
        )


def _observe_batch(
    repos: Repositories | None,
    definition: PatternDefinition,
    matched: list[PatternMatchResult],
    stock_meta: dict[str, Any],
    horizon_bars: int,
    return_horizons: list[int],
    *,
    observe_concurrency: int,
    progress: Callable[[float, str], None] | None,
) -> list[RawEvent]:
    if not matched:
        return []
    workers = _clamp_workers(observe_concurrency)
    out: list[RawEvent] = []

    if workers <= 1 and repos is not None:
        for j, result in enumerate(matched):
            if progress:
                progress(
                    (j + 1) / len(matched),
                    f"Observe {result.code} ({j + 1}/{len(matched)})",
                )
            out.append(
                _to_raw_event(
                    repos, definition, result, stock_meta, horizon_bars, return_horizons
                )
            )
        return out

    done = 0
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [
            pool.submit(
                _observe_with_own_session,
                definition,
                result,
                stock_meta,
                horizon_bars,
                return_horizons,
            )
            for result in matched
        ]
        for fut in as_completed(futs):
            out.append(fut.result())
            with lock:
                done += 1
                if progress:
                    progress(done / len(matched), f"Observe {done}/{len(matched)} x{workers}")
    return out


def _process_one_day(
    d: date,
    definition: PatternDefinition,
    universe_spec: dict[str, Any],
    horizon_bars: int,
    return_horizons: list[int],
    *,
    match_concurrency: int,
    observe_concurrency: int,
    repos: Repositories | None,
    progress: Callable[[float, str], None] | None,
    cancel_cb: CancelCb | None = None,
) -> tuple[list[RawEvent], int]:
    """处理单日：context → match → observe。repos=None 时自建 session。"""

    def _check_cancel() -> None:
        if cancel_cb and cancel_cb():
            raise EventStatsCancelled("用户取消")

    def _run(with_repos: Repositories) -> tuple[list[RawEvent], int]:
        _check_cancel()
        if progress:
            progress(0.02, f"加载上下文 {d.isoformat()}")
        codes = resolve_universe_codes(with_repos, d, universe_spec)
        ctx = build_pattern_context(
            with_repos,
            d,
            codes=codes,
            max_bars=definition.required_history_bars(),
        )
        uni = int(ctx.get("universe_size") or 0)
        if not ctx.get("kline_by_code"):
            if progress:
                progress(1.0, f"{d.isoformat()} 宇宙为空")
            return [], uni

        _check_cancel()

        def _match_progress(frac: float, msg: str) -> None:
            _check_cancel()
            if progress:
                progress(0.08 + 0.62 * frac, f"{d.isoformat()} {msg}")

        runner = PatternRunner(
            show_progress=False,
            concurrency=match_concurrency,
            progress_cb=_match_progress if progress is not None else None,
        )
        run = runner.run(definition, d, ctx)
        matched = [r for r in run.results if r.matched]
        stock_meta = ctx.get("stock_meta") or {}
        _check_cancel()
        if progress:
            progress(0.72, f"{d.isoformat()} 命中 {len(matched)}，Observe x{observe_concurrency}")

        def _obs_progress(frac: float, msg: str) -> None:
            _check_cancel()
            if progress:
                progress(0.72 + 0.28 * frac, f"{d.isoformat()} {msg}")

        # 并发 Observe 始终用独立 session，避免与 match 线程争用
        events = _observe_batch(
            None if observe_concurrency > 1 else with_repos,
            definition,
            matched,
            stock_meta,
            horizon_bars,
            return_horizons,
            observe_concurrency=observe_concurrency,
            progress=_obs_progress if progress is not None else None,
        )
        if progress:
            progress(1.0, f"{d.isoformat()} 完成 hit={len(matched)}")
        return events, uni

    if repos is not None:
        return _run(repos)
    with session_scope() as session:
        return _run(build_repositories(session))


def discover_and_observe(
    repos: Repositories,
    definition: PatternDefinition,
    *,
    start: date,
    end: date,
    universe_spec: dict[str, Any],
    horizon_bars: int,
    return_horizons: list[int],
    dedup_policy: str,
    progress_cb: ProgressCb | None = None,
    cancel_cb: CancelCb | None = None,
    day_concurrency: int | None = None,
    match_concurrency: int | None = None,
    observe_concurrency: int | None = None,
) -> tuple[list[RawEvent], dict[str, Any]]:
    days = trading_days_between(start, end)
    if not days:
        return [], {"trading_days": 0, "universe_size_hint": 0}

    def _check() -> None:
        if cancel_cb and cancel_cb():
            raise EventStatsCancelled("用户取消")

    cpu = os.cpu_count() or 4
    day_workers = _clamp_workers(
        day_concurrency if day_concurrency is not None else min(6, cpu),
        hi=16,
    )
    match_workers = _clamp_workers(
        match_concurrency if match_concurrency is not None else 8,
        hi=16,
    )
    observe_workers = _clamp_workers(
        observe_concurrency if observe_concurrency is not None else 8,
        hi=32,
    )

    # 防止日并发 × 匹配并发爆炸
    budget = max(8, cpu * 2)
    if day_workers * match_workers > budget:
        match_workers = max(1, budget // day_workers)

    total_days = len(days)
    span = 0.79
    raw: list[RawEvent] = []
    uni_hint = 0
    progress_lock = threading.Lock()
    done_days = 0

    def _day_progress_factory(day_index: int, d: date) -> Callable[[float, str], None] | None:
        if progress_cb is None:
            return None
        # 日并发>1 时用全局完成度，避免多日进度互相覆盖乱跳
        if day_workers > 1:
            return None

        day_lo = 0.05 + span * (day_index / max(total_days, 1))
        day_hi = 0.05 + span * ((day_index + 1) / max(total_days, 1))

        def _emit(local: float, msg: str) -> None:
            p = day_lo + (day_hi - day_lo) * max(0.0, min(1.0, local))
            with progress_lock:
                progress_cb(p, msg)

        return _emit

    def _on_day_finished(d: date, n_events: int) -> None:
        nonlocal done_days, uni_hint
        with progress_lock:
            done_days += 1
            if progress_cb is not None and day_workers > 1:
                p = 0.05 + span * (done_days / max(total_days, 1))
                progress_cb(
                    p,
                    f"日进度 {done_days}/{total_days} · {d.isoformat()} +{n_events} 事件 "
                    f"(day×{day_workers} match×{match_workers} obs×{observe_workers})",
                )

    if progress_cb:
        progress_cb(
            0.03,
            f"并发启动 day×{day_workers} match×{match_workers} observe×{observe_workers} · {total_days} 日",
        )

    if day_workers <= 1:
        for i, d in enumerate(days):
            _check()
            day_prog = _day_progress_factory(i, d)
            events, uni = _process_one_day(
                d,
                definition,
                universe_spec,
                horizon_bars,
                return_horizons,
                match_concurrency=match_workers,
                observe_concurrency=observe_workers,
                repos=repos,
                progress=day_prog,
                cancel_cb=cancel_cb,
            )
            uni_hint = max(uni_hint, uni)
            raw.extend(events)
            _on_day_finished(d, len(events))
    else:
        with ThreadPoolExecutor(max_workers=day_workers) as pool:
            futs = {
                pool.submit(
                    _process_one_day,
                    d,
                    definition,
                    universe_spec,
                    horizon_bars,
                    return_horizons,
                    match_concurrency=match_workers,
                    observe_concurrency=observe_workers,
                    repos=None,  # 独立 session
                    progress=None,
                    cancel_cb=cancel_cb,
                ): d
                for d in days
            }
            try:
                for fut in as_completed(futs):
                    _check()
                    d = futs[fut]
                    events, uni = fut.result()
                    uni_hint = max(uni_hint, uni)
                    raw.extend(events)
                    _on_day_finished(d, len(events))
            except EventStatsCancelled:
                for fut in futs:
                    fut.cancel()
                raise

    if progress_cb:
        progress_cb(0.85, f"Dedup policy={dedup_policy}")

    cooldown = horizon_bars if dedup_policy.startswith("cooldown") else 0
    kept = apply_dedup(raw, policy=dedup_policy, cooldown_bars=cooldown)
    meta = {
        "trading_days": total_days,
        "universe_size_hint": uni_hint,
        "discovered": len(raw),
        "after_dedup": len(kept),
        "day_concurrency": day_workers,
        "match_concurrency": match_workers,
        "observe_concurrency": observe_workers,
    }
    return kept, meta
