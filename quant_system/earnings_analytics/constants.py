"""EEA 常量与 scope 过滤规则。"""
from __future__ import annotations

from datetime import date
from typing import Any

DEFAULT_HORIZONS = (5, 10, 20)
DEFAULT_FEATURE_COLS = (
    "pe_ttm",
    "ln_mcap",
    "yoy_pct",
    "ey_event_pct",
    "range_pos_250d",
)
MODEL_SCOPES = ("all", "interim", "annual")
CLUSTER_MODES = ("none", "fixed_effect", "per_cluster")

# all scope 主池（季报默认不进主拟合）
ALL_SCOPE_KINDS = frozenset({"forecast", "express", "annual", "interim"})

MIN_SAMPLES_GLOBAL = 80
MIN_SAMPLES_PER_CLUSTER = 40


def report_progress_month(report_period: date | None) -> int | None:
    if report_period is None:
        return None
    return int(report_period.month)


def is_interim_season(event_kind: str, report_period: date | None) -> bool:
    """中报季节：正式中报，或预告/快报且报告期为 6-30。"""
    kind = (event_kind or "").lower()
    if kind == "interim":
        return True
    if kind in ("forecast", "express"):
        return report_progress_month(report_period) == 6
    return False


def is_annual_season(event_kind: str, report_period: date | None) -> bool:
    kind = (event_kind or "").lower()
    if kind == "annual":
        return True
    if kind in ("forecast", "express"):
        return report_progress_month(report_period) == 12
    return False


def row_matches_scope(row: dict[str, Any], scope: str) -> bool:
    kind = str(row.get("event_kind") or "")
    period = row.get("report_period")
    if isinstance(period, str):
        try:
            period = date.fromisoformat(period[:10])
        except Exception:
            period = None
    if scope == "all":
        return kind in ALL_SCOPE_KINDS
    if scope == "interim":
        return is_interim_season(kind, period if isinstance(period, date) else None)
    if scope == "annual":
        return is_annual_season(kind, period if isinstance(period, date) else None)
    return False


def filter_spec_for_scope(scope: str) -> dict[str, Any]:
    return {
        "model_scope": scope,
        "all_kinds": sorted(ALL_SCOPE_KINDS),
        "interim": "event_kind=interim OR ((forecast|express) AND report_period.month=6)",
        "annual": "event_kind=annual OR ((forecast|express) AND report_period.month=12)",
    }
