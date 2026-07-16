"""横盘放量突破 RANGE_BREAKOUT。"""
from __future__ import annotations

import pandas as pd

from quant_system.abnormal.patterns.base import ScanLevel
from quant_system.abnormal.scan import mask_ge, mask_le, mask_true
from quant_system.abnormal.score_utils import (
    amount_score,
    break_distance_score,
    relative_return_score,
    volume_ratio_score,
    weighted_score,
)


class RangeBreakoutPattern:
    pattern_id = "RANGE_BREAKOUT"
    display_name = "横盘放量突破"
    top_n = 10
    scan_levels = [
        # A 股短线波动大，振幅档位比教科书略宽，否则几乎筛不出
        ScanLevel(1, {
            "amplitude_20d_max": 15.0, "volume_ratio_min": 3.0,
            "return_1d_min": 5.0, "amount_min": 3e8,
        }),
        ScanLevel(2, {
            "amplitude_20d_max": 22.0, "volume_ratio_min": 2.5,
            "return_1d_min": 4.0, "amount_min": 2e8,
        }),
        ScanLevel(3, {
            "amplitude_20d_max": 30.0, "volume_ratio_min": 2.0,
            "return_1d_min": 3.0, "amount_min": 1.5e8,
        }),
    ]

    def filter(self, df: pd.DataFrame, level: ScanLevel) -> pd.DataFrame:
        f = level.filters
        m = (
            mask_le(df, "amplitude_20d", f["amplitude_20d_max"])
            & mask_ge(df, "volume_ratio", f["volume_ratio_min"])
            & mask_true(df, "break_high_20d")
            & mask_ge(df, "return_1d", f["return_1d_min"])
            & mask_ge(df, "amount", f["amount_min"])
        )
        return df[m].reset_index(drop=True)

    def score_row(self, row: pd.Series) -> tuple[float, dict, list[str]]:
        v = float(row.get("volume_ratio") or 0)
        amt = float(row.get("amount") or 0)
        d = float(row.get("break_distance_20d") or 0)
        rr = float(row.get("relative_return") or 0)
        r1 = float(row.get("return_1d") or 0)
        amp = float(row.get("amplitude_20d") or 0)

        parts = {
            "volume": (volume_ratio_score(v), 0.40),
            "distance": (break_distance_score(d), 0.30),
            "return": (min(100.0, r1 * 12), 0.15),
            "amount": (amount_score(amt), 0.15),
        }
        score, contrib = weighted_score(parts)
        reasons = [
            f"振幅{amp:.1f}%",
            f"放量{v:.1f}倍",
            "突破20日新高",
            f"突破幅度{d:.2f}ATR" if d > 0 else "突破20日新高",
            f"涨幅{r1:.1f}%",
            f"成交额{amt/1e8:.1f}亿",
        ]
        if rr > 0:
            reasons.append(f"强于市场{rr:+.1f}%")
        # 按贡献排序主因
        order = sorted(contrib.items(), key=lambda x: -x[1])
        label = {
            "volume": f"放量{v:.1f}倍",
            "distance": f"突破幅度{d:.2f}ATR",
            "return": f"涨幅{r1:.1f}%",
            "amount": f"成交额{amt/1e8:.1f}亿",
        }
        sorted_reasons = [label[k] for k, _ in order if k in label]
        for extra in [f"振幅{amp:.1f}%", "突破20日新高"]:
            if extra not in sorted_reasons:
                sorted_reasons.append(extra)
        if rr > 1:
            sorted_reasons.append(f"强于市场{rr:+.1f}%")
        comps = {"scores": {k: round(parts[k][0], 2) for k in parts}, "contribution": contrib}
        return score, comps, sorted_reasons
