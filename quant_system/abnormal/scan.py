"""Parameter Scan：由严到松，保留每只股票最严命中档。"""
from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from quant_system.abnormal.patterns.base import Pattern, PatternHit, ScanLevel

if TYPE_CHECKING:
    pass


def _to_float(x) -> float | None:
    if x is None:
        return None
    try:
        f = float(x)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def apply_common_excludes(df: pd.DataFrame) -> pd.DataFrame:
    """公共否决：一字板、非阳线（close>open）、缺失关键字段由各 Pattern 再判。"""
    if df.empty:
        return df
    out = df.copy()
    if "is_one_word" in out.columns:
        out = out[~out["is_one_word"].fillna(False)]
    if "is_yang" in out.columns:
        out = out[out["is_yang"].fillna(False)]
    if "is_st" in out.columns:
        out = out[~out["is_st"].fillna(False)]
    return out.reset_index(drop=True)


def mask_ge(df: pd.DataFrame, col: str, thr: float) -> pd.Series:
    s = pd.to_numeric(df[col], errors="coerce")
    return s >= thr


def mask_le(df: pd.DataFrame, col: str, thr: float) -> pd.Series:
    s = pd.to_numeric(df[col], errors="coerce")
    return s <= thr


def mask_true(df: pd.DataFrame, col: str) -> pd.Series:
    return df[col].fillna(False).astype(bool)


def run_pattern_scan(pattern: Pattern, df: pd.DataFrame) -> list[PatternHit]:
    """对单一 Pattern 跑全部 ScanLevel，保留 best level，再打分排序。"""
    base = apply_common_excludes(df)
    if base.empty:
        return []

    # code -> (level, row)
    best: dict[str, tuple[int, pd.Series]] = {}
    level_counts: dict[int, int] = {}

    for sl in sorted(pattern.scan_levels, key=lambda x: x.level):
        passed = pattern.filter(base, sl)
        level_counts[sl.level] = len(passed)
        if passed.empty:
            continue
        for _, row in passed.iterrows():
            code = str(row["code"])
            if code not in best or sl.level < best[code][0]:
                best[code] = (sl.level, row)

    hits: list[PatternHit] = []
    for code, (level, row) in best.items():
        score, comps, reasons = pattern.score_row(row)
        amount = _to_float(row.get("amount")) or 0.0
        snap = {
            "return_1d": _to_float(row.get("return_1d")),
            "volume_ratio": _to_float(row.get("volume_ratio")),
            "amount": amount,
            "relative_return": _to_float(row.get("relative_return")),
            "scan_level": level,
        }
        hits.append(PatternHit(
            code=code,
            pattern_id=pattern.pattern_id,
            scan_level=level,
            pattern_score=round(float(score), 2),
            reasons=reasons,
            score_components=comps,
            inputs_snapshot=snap,
            amount=amount,
        ))

    hits.sort(key=lambda h: (h.scan_level, -h.pattern_score, -h.amount))
    for i, h in enumerate(hits, start=1):
        h.pattern_rank = i
    return hits


def scan_level_stats(pattern: Pattern, df: pd.DataFrame) -> dict[str, int]:
    """dry-run 用：每档命中数（含降档重叠，非 best-only）。"""
    base = apply_common_excludes(df)
    stats: dict[str, int] = {}
    for sl in pattern.scan_levels:
        stats[f"L{sl.level}"] = int(len(pattern.filter(base, sl)))
    return stats
