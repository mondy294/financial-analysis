"""异动扫描业务编排：engine → 落库。"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from loguru import logger

from quant_system.abnormal.engine import ScanReport, run_abnormal_scan
from quant_system.abnormal.registry import get_patterns

if TYPE_CHECKING:
    from quant_system.data.repository import Repositories


def build_abnormal(
    repos: "Repositories",
    *,
    trade_date: date,
    pattern_ids: list[str] | None = None,
    dry_run: bool = False,
    force: bool = False,
    persist_all: bool = True,
) -> ScanReport:
    """跑 Pattern Engine；非 dry_run 时幂等落库。"""
    patterns = get_patterns(pattern_ids)
    report = run_abnormal_scan(
        repos, trade_date,
        pattern_ids=pattern_ids, dry_run=dry_run, force=force,
    )
    if report.skipped or dry_run or report.universe_size == 0:
        return report

    run_id = repos.abnormal.start_run({
        "trade_date": trade_date,
        "patterns_enabled": [p.pattern_id for p in patterns],
        "params_version": report.params_version,
    })
    try:
        pids = [p.pattern_id for p in patterns]
        repos.abnormal.replace_day(trade_date, pids)
        records = []
        per_stats: dict = {}
        from quant_system.abnormal.registry import PATTERN_REGISTRY
        for pr in report.per_pattern:
            top_n = PATTERN_REGISTRY[pr.pattern_id].top_n  # type: ignore[attr-defined]
            hits = pr.hits if persist_all else pr.hits[:top_n]
            level_best: dict[str, int] = {}
            for h in hits:
                level_best[f"L{h.scan_level}"] = level_best.get(f"L{h.scan_level}", 0) + 1
                records.append({
                    "trade_date": trade_date,
                    "code": h.code,
                    "pattern_id": h.pattern_id,
                    "scan_level": h.scan_level,
                    "pattern_score": h.pattern_score,
                    "pattern_rank": h.pattern_rank,
                    "global_rank": None,
                    "reasons": h.reasons,
                    "risk_flags": h.risk_flags,
                    "score_components": h.score_components,
                    "inputs_snapshot": h.inputs_snapshot,
                    "params_version": report.params_version,
                    "feature_version": None,
                })
            per_stats[pr.pattern_id] = {
                "level_raw": pr.level_stats,
                "best_level": level_best,
                "written": len(hits),
            }
        written = repos.abnormal.bulk_insert(records)
        repos.abnormal.finish_run(run_id, "SUCCESS", stats={
            "universe_size": report.universe_size,
            "written_count": written,
            "per_pattern_stats": per_stats,
            "duration_ms": report.duration_ms,
        })
        logger.info(
            "abnormal 落库完成 {}：{} 行，耗时 {}ms",
            trade_date, written, report.duration_ms,
        )
        return report
    except Exception as e:
        repos.abnormal.finish_run(run_id, "FAILED", error=str(e))
        raise
