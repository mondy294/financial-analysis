from __future__ import annotations

from typing import Any, Iterable

import numpy as np

from quant_system.eventstats.constants import AGGREGATION_VERSION, STANDARD_METRIC_COLUMNS


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "mean": None,
            "median": None,
            "p10": None,
            "p90": None,
            "win_rate": None,
            "n_valid": 0,
        }
    arr = np.asarray(values, dtype=float)
    return {
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "p10": float(np.percentile(arr, 10)),
        "p90": float(np.percentile(arr, 90)),
        "win_rate": float(np.mean(arr > 0)),
        "n_valid": int(len(arr)),
    }


def aggregate_events(
    events: Iterable[dict[str, Any]],
    *,
    universe_size_hint: int | None = None,
) -> dict[str, Any]:
    rows = list(events)
    codes = {r["code"] for r in rows if r.get("code")}
    status_counts: dict[str, int] = {}
    for r in rows:
        st = str(r.get("forward_status") or "unknown")
        status_counts[st] = status_counts.get(st, 0) + 1

    # 收益 / 路径：完整分位；时间结构：均值中位数 + 分位（便于看分布）
    full_stat_keys = [
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
        "volatility",
        "bull_ratio",
        "up_days",
        "continuous_up_days",
        "highest_day",
        "lowest_day",
        "time_to_mfe",
        "time_to_mae",
        "forward_bars_available",
    ]
    # 保持与宽列一致的顺序
    ordered = [c for c in STANDARD_METRIC_COLUMNS if c in full_stat_keys and c != "forward_status"]

    metrics_summary: dict[str, Any] = {}
    for key in ordered:
        vals: list[float] = []
        for r in rows:
            v = r.get(key)
            if v is None:
                continue
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                continue
        metrics_summary[key] = _stats(vals)

    coverage = {
        "event_count": len(rows),
        "stock_count": len(codes),
        "universe_size_hint": universe_size_hint,
        "coverage_rate": (
            (len(codes) / universe_size_hint) if universe_size_hint and universe_size_hint > 0 else None
        ),
        "forward_status_counts": status_counts,
    }

    return {
        "aggregation_version": AGGREGATION_VERSION,
        "coverage": coverage,
        "metrics": metrics_summary,
    }
