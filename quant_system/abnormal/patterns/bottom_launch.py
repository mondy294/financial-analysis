"""底部启动 BOTTOM_LAUNCH。"""
from __future__ import annotations

import pandas as pd

from quant_system.abnormal.patterns.base import ScanLevel
from quant_system.abnormal.scan import mask_ge, mask_le, mask_true
from quant_system.abnormal.score_utils import (
    relative_return_score,
    volume_ratio_score,
    weighted_score,
)


class BottomLaunchPattern:
    pattern_id = "BOTTOM_LAUNCH"
    display_name = "底部启动"
    top_n = 10
    scan_levels = [
        ScanLevel(1, {"range_pos_max": 0.25, "volume_ratio_min": 2.5, "return_1d_min": 5.0, "tier": 1}),
        ScanLevel(2, {"range_pos_max": 0.30, "volume_ratio_min": 2.0, "return_1d_min": 4.0, "tier": 2}),
        ScanLevel(3, {"range_pos_max": 0.35, "volume_ratio_min": 2.0, "return_1d_min": 4.0, "tier": 3}),
    ]

    def filter(self, df: pd.DataFrame, level: ScanLevel) -> pd.DataFrame:
        f = level.filters
        m = (
            mask_le(df, "range_pos_250d", f["range_pos_max"])
            & mask_ge(df, "volume_ratio", f["volume_ratio_min"])
            & mask_ge(df, "return_1d", f["return_1d_min"])
        )
        tier = f["tier"]
        if tier == 1:
            m = m & mask_true(df, "macd_golden_cross") & (
                mask_true(df, "ma5_cross_ma10") | (
                    pd.to_numeric(df["ma5"], errors="coerce")
                    > pd.to_numeric(df["ma10"], errors="coerce")
                )
            )
        elif tier == 2:
            m = m & (mask_true(df, "macd_golden_cross") | (
                pd.to_numeric(df["ma5"], errors="coerce")
                > pd.to_numeric(df["ma10"], errors="coerce")
            ))
        else:
            hist_ok = pd.to_numeric(df["macd_hist"], errors="coerce") > 0
            m = m & (hist_ok | mask_true(df, "ma_bull_arrange"))
        return df[m].reset_index(drop=True)

    def score_row(self, row: pd.Series) -> tuple[float, dict, list[str]]:
        pos = float(row.get("range_pos_250d") or 0.5)
        v = float(row.get("volume_ratio") or 0)
        rr = float(row.get("relative_return") or 0)
        r1 = float(row.get("return_1d") or 0)
        # 低位高分
        pos_score = max(0.0, min(100.0, (0.40 - pos) / 0.40 * 100))
        parts = {
            "position": (pos_score, 0.40),
            "volume": (volume_ratio_score(v), 0.30),
            "relative": (relative_return_score(rr), 0.20),
            "return": (min(100.0, r1 * 12), 0.10),
        }
        score, contrib = weighted_score(parts)
        reasons = [f"250日位{pos*100:.0f}%", f"放量{v:.1f}倍", f"涨幅{r1:.1f}%"]
        if bool(row.get("macd_golden_cross")):
            reasons.append("MACD金叉")
        if bool(row.get("ma5_cross_ma10")):
            reasons.append("MA5上穿MA10")
        if rr > 1:
            reasons.append(f"强于市场{rr:+.1f}%")
        order = sorted(contrib.items(), key=lambda x: -x[1])
        label = {
            "position": f"250日低位启动({pos*100:.0f}%)",
            "volume": f"放量{v:.1f}倍",
            "relative": f"强于市场{rr:+.1f}%",
            "return": f"涨幅{r1:.1f}%",
        }
        sorted_reasons = [label[k] for k, _ in order if k in label]
        for extra in reasons:
            if extra not in sorted_reasons:
                sorted_reasons.append(extra)
        comps = {"scores": {k: round(parts[k][0], 2) for k in parts}, "contribution": contrib}
        return score, comps, sorted_reasons
