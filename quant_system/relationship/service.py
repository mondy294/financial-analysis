"""关系层编排：宇宙解析 → 算 → 组装 records → 写 + run 记录（含 dry-run）。

对齐现有 update / feature 编排风格：由 CLI 起 session + DI，本模块只吃 Repositories。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from loguru import logger

from quant_system.infra import board
from quant_system.infra.code_hash import hash_directory
from quant_system.relationship.calculator import LeadLagCalculator, get_calculator
from quant_system.relationship.returns_matrix import (
    WINDOW_DAYS,
    build_returns_matrix,
    max_window_days,
    parse_windows,
)

if TYPE_CHECKING:
    from quant_system.data.repository import Repositories

DEFAULT_WINDOWS = ["W60", "W250"]
DEFAULT_MIN_SAMPLE = 120
DEFAULT_VALUE_THRESHOLD = 0.63
DEFAULT_MAX_NEIGHBORS = 200
DEFAULT_FULL_LOOKBACK = 750

# Lead-Lag 默认
DEFAULT_LEADLAG_WINDOW = "W60"          # 先后关系用短窗更敏感
DEFAULT_LEADLAG_MAX_LAG = 5             # 搜索 ±5 个交易日
DEFAULT_LEADLAG_CANDIDATE_MIN = 0.5     # 候选对：同期 |corr| 门槛
DEFAULT_LEADLAG_THRESHOLD = 0.6         # 最优 lag 下相关度门槛
DEFAULT_LEADLAG_MIN_GAIN = 0.03         # 领先相关度需比同期至少高这么多


@dataclass
class WindowReport:
    window: str
    evaluated: int = 0
    written: int = 0
    capped: int = 0
    universe_effective: int = 0
    hist: dict = field(default_factory=dict)


@dataclass
class RunReport:
    calc_date: date
    relation_type: str
    windows: list[str]
    universe_size: int
    dry_run: bool = False
    skipped: bool = False
    run_id: Optional[int] = None
    pair_written_total: int = 0
    duration_ms: int = 0
    per_window: list[WindowReport] = field(default_factory=list)


def _resolve_universe(repos: "Repositories", pool_code: Optional[str],
                      board_filter: Optional[str], calc_date: date) -> tuple[list[str], str, str]:
    from quant_system.config.settings import get_settings

    settings = get_settings()
    raw_pool = (pool_code or settings.stock_pool.pool.value).upper()
    pool_code_db = "CUSTOM_DEFAULT" if raw_pool == "CUSTOM" else raw_pool
    board_filter = board_filter if board_filter is not None else settings.board_filter

    codes = repos.stock.list_pool_members(pool_code_db, as_of=calc_date)
    codes = board.filter_codes(codes, board_filter)
    codes = sorted(set(codes))
    return codes, pool_code_db, board_filter


def build_relationships(
    repos: "Repositories",
    *,
    calc_date: date,
    relation_type: str = "PEARSON",
    windows: Optional[list[str]] = None,
    pool_code: Optional[str] = None,
    board_filter: Optional[str] = None,
    min_sample: int = DEFAULT_MIN_SAMPLE,
    value_threshold: float = DEFAULT_VALUE_THRESHOLD,
    max_neighbors: int = DEFAULT_MAX_NEIGHBORS,
    full_lookback: int = DEFAULT_FULL_LOOKBACK,
    dry_run: bool = False,
    force: bool = False,
    use_cache: bool = True,
) -> RunReport:
    relation_type = relation_type.upper()
    windows = windows or list(DEFAULT_WINDOWS)
    parse_windows(windows)  # 提前校验窗口合法性
    calc = get_calculator(relation_type)

    t0 = time.monotonic()
    codes, pool_code_db, board_filter = _resolve_universe(
        repos, pool_code, board_filter, calc_date,
    )
    report = RunReport(
        calc_date=calc_date, relation_type=relation_type,
        windows=list(windows), universe_size=len(codes), dry_run=dry_run,
    )
    if len(codes) < 2:
        logger.warning("计算宇宙不足 2 只（{}），跳过", len(codes))
        return report

    # 幂等：非 dry-run、非 force，已有 SUCCESS 快照则跳过
    if not dry_run and not force and repos.relation.has_success_run(calc_date, relation_type):
        logger.info("{} {} 已有 SUCCESS 批次，跳过（--force 可强制重算）", calc_date, relation_type)
        report.skipped = True
        return report

    lookback = max_window_days(windows, full_lookback)
    matrix = build_returns_matrix(repos.relation, codes, calc_date, lookback, use_cache=use_cache)
    if matrix.empty:
        logger.warning("收益率宽表为空，终止")
        return report

    parsed = parse_windows(windows)
    window_results = [
        calc.compute_window(
            matrix, label, days,
            min_sample=min_sample, value_threshold=value_threshold,
            max_neighbors=max_neighbors,
        )
        for label, days in parsed
    ]

    # dry-run：只汇总分布，不建 run、不落库
    if dry_run:
        for wr in window_results:
            report.per_window.append(WindowReport(
                window=wr.window, evaluated=wr.evaluated,
                written=len(wr.pairs), capped=wr.capped,
                universe_effective=wr.universe_effective, hist=wr.hist,
            ))
        report.pair_written_total = sum(len(wr.pairs) for wr in window_results)
        report.duration_ms = int((time.monotonic() - t0) * 1000)
        return report

    # 正式落库
    run_id = repos.relation.start_run({
        "calc_date": calc_date, "relation_type": relation_type,
        "windows": list(windows), "pool_code": pool_code_db,
        "board_filter": board_filter, "min_sample": min_sample,
        "value_threshold": value_threshold, "max_neighbors": max_neighbors,
    })
    report.run_id = run_id
    try:
        ind_map = repos.relation.industry_map(codes)
        now = datetime.utcnow()
        total_written = 0
        total_evaluated = 0
        for wr in window_results:
            repos.relation.replace_snapshot(relation_type, wr.window)
            records = []
            for p in wr.pairs:
                a, b = p["code_a"], p["code_b"]
                ind_a, ind_b = ind_map.get(a), ind_map.get(b)
                records.append({
                    "relation_type": relation_type, "window": wr.window,
                    "stock_code_a": a, "stock_code_b": b,
                    "relation_value": p["value"], "sample_size": p["sample_size"],
                    "direction": 0,
                    "is_same_industry": bool(ind_a and ind_b and ind_a == ind_b),
                    "calc_date": calc_date, "created_at": now,
                })
            written = repos.relation.bulk_insert(records)
            total_written += written
            total_evaluated += wr.evaluated
            report.per_window.append(WindowReport(
                window=wr.window, evaluated=wr.evaluated, written=written,
                capped=wr.capped, universe_effective=wr.universe_effective, hist=wr.hist,
            ))

        report.pair_written_total = total_written
        report.duration_ms = int((time.monotonic() - t0) * 1000)
        repos.relation.finish_run(run_id, "SUCCESS", stats={
            "universe_size": len(codes),
            "pair_evaluated": total_evaluated,
            "pair_written": total_written,
            "code_hash": hash_directory(Path(__file__).resolve().parent, "*.py"),
            "duration_ms": report.duration_ms,
        })
        logger.info(
            "关系计算完成 {} {}：宇宙 {} 只，写入 {} 行，耗时 {}ms",
            calc_date, relation_type, len(codes), total_written, report.duration_ms,
        )
        return report
    except Exception as e:
        repos.relation.finish_run(run_id, "FAILED", error=str(e))
        raise


def build_lead_lag(
    repos: "Repositories",
    *,
    calc_date: date,
    window: str = DEFAULT_LEADLAG_WINDOW,
    base_relation_type: str = "PEARSON",
    candidate_min_abs: float = DEFAULT_LEADLAG_CANDIDATE_MIN,
    max_lag: int = DEFAULT_LEADLAG_MAX_LAG,
    value_threshold: float = DEFAULT_LEADLAG_THRESHOLD,
    min_lead_gain: float = DEFAULT_LEADLAG_MIN_GAIN,
    min_sample: int = DEFAULT_MIN_SAMPLE,
    full_lookback: int = DEFAULT_FULL_LOOKBACK,
    force: bool = False,
    use_cache: bool = True,
) -> RunReport:
    """领先-滞后计算：候选对取自已算好的 PEARSON 同期强相关对。

    依赖：需先跑过 `build_relationships`（同一 window 的 PEARSON 快照）。
    """
    relation_type = "LEAD_LAG"
    t0 = time.monotonic()
    report = RunReport(
        calc_date=calc_date, relation_type=relation_type,
        windows=[window], universe_size=0,
    )

    if not force and repos.relation.has_success_run(calc_date, relation_type):
        logger.info("{} LEAD_LAG 已有 SUCCESS 批次，跳过（--force 重算）", calc_date)
        report.skipped = True
        return report

    candidates = repos.relation.list_pairs(
        relation_type=base_relation_type, window=window,
        min_abs=candidate_min_abs, as_of=calc_date,
    )
    if not candidates:
        logger.warning(
            "无候选对：请先跑 PEARSON {} 快照（build --windows {}）", window, window[1:],
        )
        return report

    codes = sorted({c for pair in candidates for c in pair})
    report.universe_size = len(codes)
    days = WINDOW_DAYS.get(window)
    lookback = full_lookback if days is None else days + max_lag + 5
    matrix = build_returns_matrix(repos.relation, codes, calc_date, lookback, use_cache=use_cache)
    if matrix.empty:
        logger.warning("收益率宽表为空，终止")
        return report

    calc = LeadLagCalculator()
    pairs = calc.compute_pairs(
        matrix, candidates, days=days, max_lag=max_lag,
        min_sample=min_sample, value_threshold=value_threshold,
        min_lead_gain=min_lead_gain,
    )

    run_id = repos.relation.start_run({
        "calc_date": calc_date, "relation_type": relation_type,
        "windows": [window], "pool_code": None, "board_filter": None,
        "min_sample": min_sample, "value_threshold": value_threshold,
        "max_neighbors": 0,
    })
    report.run_id = run_id
    try:
        ind_map = repos.relation.industry_map(codes)
        now = datetime.utcnow()
        repos.relation.replace_snapshot(relation_type, window)
        records = []
        for p in pairs:
            a, b = p["code_a"], p["code_b"]
            ind_a, ind_b = ind_map.get(a), ind_map.get(b)
            records.append({
                "relation_type": relation_type, "window": window,
                "stock_code_a": a, "stock_code_b": b,
                "relation_value": p["value"], "sample_size": p["sample_size"],
                "direction": p["direction"],
                "is_same_industry": bool(ind_a and ind_b and ind_a == ind_b),
                "calc_date": calc_date, "created_at": now,
            })
        written = repos.relation.bulk_insert(records)
        report.pair_written_total = written
        report.duration_ms = int((time.monotonic() - t0) * 1000)
        report.per_window.append(WindowReport(
            window=window, evaluated=len(candidates), written=written,
            universe_effective=len(codes),
        ))
        repos.relation.finish_run(run_id, "SUCCESS", stats={
            "universe_size": len(codes),
            "pair_evaluated": len(candidates),
            "pair_written": written,
            "code_hash": hash_directory(Path(__file__).resolve().parent, "*.py"),
            "duration_ms": report.duration_ms,
        })
        logger.info(
            "Lead-Lag 完成 {} {}：候选 {} 对 → 领先对 {} 个，耗时 {}ms",
            calc_date, window, len(candidates), written, report.duration_ms,
        )
        return report
    except Exception as e:
        repos.relation.finish_run(run_id, "FAILED", error=str(e))
        raise
