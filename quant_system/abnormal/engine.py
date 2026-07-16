"""Pattern Engine 编排：扫全部 Pattern → 排名结果。"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

from loguru import logger

from quant_system.abnormal.context import build_scan_frame
from quant_system.abnormal.patterns.base import PatternHit
from quant_system.abnormal.registry import get_patterns
from quant_system.abnormal.scan import run_pattern_scan, scan_level_stats

if TYPE_CHECKING:
    from quant_system.data.repository import Repositories


def params_version(patterns: list) -> str:
    payload = []
    for p in patterns:
        payload.append({
            "id": p.pattern_id,
            "levels": [
                {"level": sl.level, "filters": sl.filters}
                for sl in p.scan_levels
            ],
        })
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode()).hexdigest()[:10]


@dataclass
class PatternReport:
    pattern_id: str
    display_name: str
    hits: list[PatternHit] = field(default_factory=list)
    level_stats: dict[str, int] = field(default_factory=dict)

    @property
    def written(self) -> int:
        return len(self.hits)


@dataclass
class ScanReport:
    trade_date: date
    universe_size: int = 0
    params_version: str = ""
    per_pattern: list[PatternReport] = field(default_factory=list)
    duration_ms: int = 0
    dry_run: bool = False
    skipped: bool = False
    market_median_return: float | None = None

    def all_hits(self) -> list[PatternHit]:
        out: list[PatternHit] = []
        for p in self.per_pattern:
            out.extend(p.hits)
        return out


def run_abnormal_scan(
    repos: "Repositories",
    trade_date: date,
    *,
    pattern_ids: list[str] | None = None,
    dry_run: bool = False,
    force: bool = False,
    use_hist_enrich: bool = True,
) -> ScanReport:
    t0 = time.monotonic()
    patterns = get_patterns(pattern_ids)
    ver = params_version(patterns)
    report = ScanReport(trade_date=trade_date, params_version=ver, dry_run=dry_run)

    if not dry_run and not force and repos.abnormal.has_success_run(trade_date, ver):
        logger.info("{} abnormal 已有 SUCCESS（同 params），跳过 --force 重跑", trade_date)
        report.skipped = True
        return report

    df = build_scan_frame(repos, trade_date, use_hist_enrich=use_hist_enrich)
    report.universe_size = len(df)
    if df.empty:
        return report
    if "market_median_return" in df.columns and len(df):
        report.market_median_return = float(df["market_median_return"].iloc[0])

    for pattern in patterns:
        level_stats = scan_level_stats(pattern, df)
        hits = run_pattern_scan(pattern, df)
        report.per_pattern.append(PatternReport(
            pattern_id=pattern.pattern_id,
            display_name=pattern.display_name,
            hits=hits,
            level_stats=level_stats,
        ))
        logger.info(
            "Pattern {}：档位 {} → 去重命中 {} 只",
            pattern.pattern_id, level_stats, len(hits),
        )

    report.duration_ms = int((time.monotonic() - t0) * 1000)
    return report
