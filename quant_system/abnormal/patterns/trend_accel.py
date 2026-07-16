"""趋势加速 TREND_ACCEL。"""
from __future__ import annotations

import pandas as pd

from quant_system.abnormal.patterns.base import ScanLevel
from quant_system.abnormal.scan import mask_ge, mask_true
from quant_system.abnormal.score_utils import (
    break_distance_score,
    relative_return_score,
    volume_ratio_score,
    weighted_score,
)


class TrendAccelPattern:
    pattern_id = "TREND_ACCEL"
    display_name = "趋势加速"
    top_n = 10
    scan_levels = [
        ScanLevel(1, {
            "return_5d_min": 12.0, "volume_ratio_min": 2.5,
            "require_strict_ma": True, "break_col": "break_high_60d",
            "vol_streak_min": 2,
        }),
        ScanLevel(2, {
            "return_5d_min": 8.0, "volume_ratio_min": 2.0,
            "require_strict_ma": True, "break_col": "break_high_60d",
            "vol_streak_min": 1,
        }),
        ScanLevel(3, {
            "return_5d_min": 8.0, "volume_ratio_min": 1.8,
            "require_strict_ma": False, "break_col": "break_high_20d",
            "vol_streak_min": 1,
        }),
    ]

    def filter(self, df: pd.DataFrame, level: ScanLevel) -> pd.DataFrame:
        f = level.filters
        m = mask_ge(df, "return_5d", f["return_5d_min"]) & mask_ge(
            df, "volume_ratio", f["volume_ratio_min"],
        )
        if f["require_strict_ma"]:
            ma5 = pd.to_numeric(df["ma5"], errors="coerce")
            ma10 = pd.to_numeric(df["ma10"], errors="coerce")
            ma20 = pd.to_numeric(df["ma20"], errors="coerce")
            close = pd.to_numeric(df["close"], errors="coerce")
            m = m & (close > ma5) & (ma5 > ma10) & (ma10 > ma20)
        else:
            m = m & mask_true(df, "ma_bull_arrange")
        m = m & mask_true(df, f["break_col"])
        if "vol_streak" in df.columns:
            m = m & mask_ge(df, "vol_streak", f["vol_streak_min"])
        return df[m].reset_index(drop=True)

    def score_row(self, row: pd.Series) -> tuple[float, dict, list[str]]:
        r5 = float(row.get("return_5d") or 0)
        v = float(row.get("volume_ratio") or 0)
        d60 = float(row.get("break_distance_60d") or row.get("break_distance_20d") or 0)
        rr = float(row.get("relative_return") or 0)
        streak = int(row.get("vol_streak") or 1)
        parts = {
            "momentum": (min(100.0, r5 * 6), 0.35),
            "volume": (volume_ratio_score(v), 0.25),
            "distance": (break_distance_score(d60), 0.25),
            "relative": (relative_return_score(rr), 0.15),
        }
        score, contrib = weighted_score(parts)
        reasons = [f"5日涨{r5:.1f}%", f"放量{v:.1f}倍"]
        if bool(row.get("break_high_60d")):
            reasons.append("突破60日新高")
        elif bool(row.get("break_high_20d")):
            reasons.append("突破20日新高")
        if streak >= 2:
            reasons.append(f"连续{streak}日放量")
        if rr > 1:
            reasons.append(f"强于市场{rr:+.1f}%")
        order = sorted(contrib.items(), key=lambda x: -x[1])
        label = {
            "momentum": f"5日涨{r5:.1f}%",
            "volume": f"放量{v:.1f}倍",
            "distance": f"突破幅度{d60:.2f}ATR",
            "relative": f"强于市场{rr:+.1f}%",
        }
        sorted_reasons = [label[k] for k, _ in order if k in label]
        for extra in reasons:
            if extra not in sorted_reasons:
                sorted_reasons.append(extra)
        comps = {"scores": {k: round(parts[k][0], 2) for k in parts}, "contribution": contrib}
        return score, comps, sorted_reasons
