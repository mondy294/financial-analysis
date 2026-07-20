"""Score Layer：mispricing_score / confidence / percentile。"""
from __future__ import annotations

from typing import Any

import numpy as np


def run_score(
    prediction: dict[str, Any],
    *,
    panel_ey_values: list[float] | None = None,
    row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    premium = prediction.get("premium_pct")
    e20 = prediction.get("expected_return_20d")

    # mispricing：贵=正；辅以预期收益偏弱
    if premium is None:
        mispricing = None
    else:
        mispricing = float(premium)
        if e20 is not None:
            # 小权重融合预期偏弱（百分点量级约数）
            mispricing = 0.7 * mispricing + 0.3 * (-float(e20) / 100.0)

    percentile = None
    ey = None if row is None else row.get("ey_event")
    if ey is not None and panel_ey_values:
        arr = np.array(panel_ey_values, dtype=float)
        arr = arr[np.isfinite(arr) & (arr > 0)]
        if arr.size > 0:
            percentile = float(np.mean(arr <= float(ey)))

    # confidence：特征完整度简单代理
    confidence = None
    if row is not None:
        keys = ("pe_ttm", "ln_mcap", "yoy_pct", "ey_event_pct", "range_pos_250d")
        present = sum(1 for k in keys if row.get(k) is not None)
        confidence = present / len(keys)

    return {
        "mispricing_score": mispricing,
        "confidence": confidence,
        "percentile": percentile,
        "score_meta": {
            "premium_pct": premium,
            "expected_return_20d": e20,
        },
    }
