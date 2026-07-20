"""Prediction Layer。"""
from __future__ import annotations

from typing import Any

from quant_system.earnings_analytics.constants import DEFAULT_HORIZONS
from quant_system.earnings_analytics.fair_value.median_ey import MedianEyEstimator
from quant_system.earnings_analytics.fair_value.protocol import FairValueModel
from quant_system.earnings_analytics.regression.protocol import FittedModel, predict_row


def run_prediction(
    row: dict[str, Any],
    *,
    regression_by_horizon: dict[str, FittedModel],
    fair_model: FairValueModel,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expected: dict[str, float | None] = {}
    for h in DEFAULT_HORIZONS:
        key = f"ret_{h}d"
        fitted = regression_by_horizon.get(key)
        if fitted is None:
            expected[f"expected_return_{h}d"] = None
        else:
            expected[f"expected_return_{h}d"] = predict_row(fitted, row)

    fv = MedianEyEstimator().estimate(fair_model, row)
    return {
        **expected,
        "fair_ey": fv.fair_ey,
        "fair_pe": fv.fair_pe,
        "implied_fair_mcap": fv.implied_fair_mcap,
        "premium_pct": fv.premium_pct,
        "prediction_meta": {
            **(meta or {}),
            "fair_method": fv.method_meta,
        },
    }
