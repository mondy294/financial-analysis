"""Median EY Fair Value Estimator。"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from quant_system.earnings_analytics.fair_value.protocol import FairValueModel, FairValueResult


class MedianEyEstimator:
    id = "median_ey"

    def fit(
        self, rows: list[dict[str, Any]], context: dict[str, Any] | None = None
    ) -> FairValueModel:
        by_kind: dict[str, list[float]] = defaultdict(list)
        all_ey: list[float] = []
        for r in rows:
            ey = r.get("ey_event")
            ann = r.get("annualized_parent_np")
            if ey is None or ann is None or float(ann) <= 0:
                continue
            v = float(ey)
            if not np.isfinite(v) or v <= 0:
                continue
            kind = str(r.get("event_kind") or "_unknown_")
            by_kind[kind].append(v)
            all_ey.append(v)

        fair: dict[str, float] = {}
        for k, vals in by_kind.items():
            if vals:
                fair[k] = float(np.median(vals))
        if all_ey:
            fair["_global_"] = float(np.median(all_ey))
        return FairValueModel(
            estimator_id=self.id,
            fair_ey_by_key=fair,
            meta={"n": len(all_ey), "kinds": sorted(by_kind.keys())},
        )

    def estimate(self, model: FairValueModel, row: dict[str, Any]) -> FairValueResult:
        kind = str(row.get("event_kind") or "")
        fair_ey = model.fair_ey_by_key.get(kind) or model.fair_ey_by_key.get("_global_")
        ann = row.get("annualized_parent_np")
        mcap = row.get("mcap")
        implied = None
        premium = None
        fair_pe = None
        if fair_ey is not None and fair_ey > 0:
            fair_pe = 1.0 / fair_ey
            if ann is not None and float(ann) > 0:
                implied = (float(ann) / 1e8) / fair_ey
                if mcap is not None and implied > 0:
                    premium = float(mcap) / implied - 1.0
        return FairValueResult(
            fair_ey=fair_ey,
            fair_pe=fair_pe,
            implied_fair_mcap=implied,
            premium_pct=premium,
            method_meta={"estimator_id": model.estimator_id, "kind_key": kind},
        )


def get_estimator(estimator_id: str = "median_ey") -> MedianEyEstimator:
    if estimator_id != "median_ey":
        raise ValueError(f"未知 Fair Value Estimator: {estimator_id}（V1 仅 median_ey）")
    return MedianEyEstimator()
