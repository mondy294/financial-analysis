from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from hashlib import sha1
import json
import time

from quant_system.data.repository import Repositories
from quant_system.patterns.context import build_pattern_context
from quant_system.patterns.definition import PatternDefinition
from quant_system.patterns.registry import get_definitions
from quant_system.patterns.runner import PatternRunner, rank_records


@dataclass
class PatternReport:
    pattern_id: str
    display_name: str
    matched_count: int
    written: int
    top_hits: list[dict] = field(default_factory=list)


@dataclass
class ScanReport:
    trade_date: date
    universe_size: int
    skipped: bool
    params_version: str
    feature_version: str | None
    market_median_return: float
    duration_ms: int
    per_pattern: list[PatternReport] = field(default_factory=list)


def build_patterns(
    repos: Repositories,
    *,
    trade_date: date,
    pattern_ids: list[str] | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> ScanReport:
    definitions = get_definitions(pattern_ids)
    params_version = _params_version(definitions)
    if not force and not dry_run and repos.abnormal.has_success_run(trade_date, params_version):
        return ScanReport(
            trade_date=trade_date,
            universe_size=0,
            skipped=True,
            params_version=params_version,
            feature_version=None,
            market_median_return=0.0,
            duration_ms=0,
        )

    t0 = time.perf_counter()
    # 形态窗 + context lookback（如 1Y / 全历史上限）统一驱动加载量
    max_bars = max((d.required_history_bars() for d in definitions), default=40)
    context = build_pattern_context(repos, trade_date, max_bars=max_bars)
    runner = PatternRunner(keep_unmatched=False)
    per_pattern: list[PatternReport] = []
    total_written = 0

    if not dry_run:
        cleanup_ids = None if pattern_ids is None else [d.id for d in definitions]
        repos.abnormal.replace_day(trade_date, cleanup_ids)

    for definition in definitions:
        run = runner.run(definition, trade_date, context)
        records = rank_records(run.results)
        written = 0 if dry_run else repos.abnormal.bulk_insert([
            {
                **record,
                "params_version": params_version,
                "feature_version": context.get("feature_version"),
            }
            for record in records
        ])
        total_written += written
        per_pattern.append(
            PatternReport(
                pattern_id=definition.id,
                display_name=definition.display_name,
                matched_count=run.stats.get("matched_count", 0),
                written=written,
                top_hits=records[:3],
            )
        )

    duration_ms = int((time.perf_counter() - t0) * 1000)
    if not dry_run:
        run_id = repos.abnormal.start_run(
            {
                "trade_date": trade_date,
                "patterns_enabled": [d.id for d in definitions],
                "params_version": params_version,
                "status": "RUNNING",
            }
        )
        repos.abnormal.finish_run(
            run_id,
            "SUCCESS",
            stats={
                "universe_size": context.get("universe_size", 0),
                "written_count": total_written,
                "per_pattern_stats": {
                    item.pattern_id: {
                        "matched_count": item.matched_count,
                        "written": item.written,
                    }
                    for item in per_pattern
                },
                "duration_ms": duration_ms,
            },
        )

    return ScanReport(
        trade_date=trade_date,
        universe_size=int(context.get("universe_size", 0)),
        skipped=False,
        params_version=params_version,
        feature_version=context.get("feature_version"),
        market_median_return=float(context.get("market_median_return", 0.0)),
        duration_ms=duration_ms,
        per_pattern=per_pattern,
    )


def _params_version(definitions: list[PatternDefinition]) -> str:
    payload = []
    for d in definitions:
        payload.append(
            {
                "id": d.id,
                "version": d.version,
                "threshold": d.threshold,
                "stage_weights": d.stage_weights,
                "timeline": [
                    {
                        "name": s.name,
                        "min": s.window.min_length,
                        "max": s.window.max_length,
                        "targets": {
                            k: {
                                "ideal": v.ideal,
                                "tolerance": v.tolerance,
                                "weight": v.weight,
                                "mode": v.mode,
                                "hard": v.hard,
                                "hard_min_similarity": v.hard_min_similarity,
                                "hard_min": v.hard_min,
                                "hard_max": v.hard_max,
                            }
                            for k, v in s.targets.items()
                        },
                    }
                    for s in d.timeline
                ],
                "relations": [
                    {
                        "name": r.name,
                        "attach": r.attach_to_stage,
                        "ideal": r.target.ideal,
                        "tolerance": r.target.tolerance,
                        "weight": r.target.weight,
                        "mode": r.target.mode,
                        "hard": r.target.hard,
                        "hard_min_similarity": r.target.hard_min_similarity,
                        "hard_min": r.target.hard_min,
                        "hard_max": r.target.hard_max,
                        "stage_map": r.stage_map,
                    }
                    for r in d.relations
                ],
                "context_features": [
                    {
                        "name": c.name,
                        "key": c.result_key,
                        "lookback_bars": c.lookback_bars,
                        "ideal": c.target.ideal,
                        "tolerance": c.target.tolerance,
                        "weight": c.target.weight,
                        "mode": c.target.mode,
                        "hard": c.target.hard,
                        "hard_min_similarity": c.target.hard_min_similarity,
                        "hard_min": c.target.hard_min,
                        "hard_max": c.target.hard_max,
                    }
                    for c in d.context_features
                ],
                "history_bars": d.history_bars,
            }
        )
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    return sha1(raw.encode("utf-8")).hexdigest()[:12]
