"""突破近一年新高 ATH_250。"""
from __future__ import annotations

import pandas as pd

from quant_system.abnormal.patterns.base import ScanLevel
from quant_system.abnormal.scan import mask_ge, mask_true
from quant_system.abnormal.score_utils import (
    amount_score,
    break_distance_score,
    relative_return_score,
    volume_ratio_score,
    weighted_score,
)


class Ath250Pattern:
    pattern_id = "ATH_250"
    display_name = "突破一年新高"
    top_n = 10
    scan_levels = [
        ScanLevel(1, {"volume_ratio_min": 2.5, "amount_min": 8e8, "distance_min": 0.5}),
        ScanLevel(2, {"volume_ratio_min": 2.0, "amount_min": 5e8, "distance_min": 0.2}),
        ScanLevel(3, {"volume_ratio_min": 1.8, "amount_min": 5e8, "distance_min": 0.0}),
    ]

    def filter(self, df: pd.DataFrame, level: ScanLevel) -> pd.DataFrame:
        f = level.filters
        m = (
            mask_true(df, "break_high_250d")
            & mask_ge(df, "volume_ratio", f["volume_ratio_min"])
            & mask_ge(df, "amount", f["amount_min"])
            & mask_ge(df, "break_distance_250d", f["distance_min"])
        )
        return df[m].reset_index(drop=True)

    def score_row(self, row: pd.Series) -> tuple[float, dict, list[str]]:
        v = float(row.get("volume_ratio") or 0)
        amt = float(row.get("amount") or 0)
        d = float(row.get("break_distance_250d") or 0)
        rr = float(row.get("relative_return") or 0)
        parts = {
            "distance": (break_distance_score(d), 0.40),
            "amount": (amount_score(amt), 0.30),
            "volume": (volume_ratio_score(max(v, 2.0)), 0.15),
            "relative": (relative_return_score(rr), 0.15),
        }
        score, contrib = weighted_score(parts)
        order = sorted(contrib.items(), key=lambda x: -x[1])
        label = {
            "distance": f"突破幅度{d:.2f}ATR",
            "amount": f"成交额{amt/1e8:.1f}亿",
            "volume": f"放量{v:.1f}倍",
            "relative": f"强于市场{rr:+.1f}%",
        }
        sorted_reasons = ["突破近一年新高"] + [
            label[k] for k, _ in order if k in label
        ]
        comps = {"scores": {k: round(parts[k][0], 2) for k in parts}, "contribution": contrib}
        return score, comps, sorted_reasons
