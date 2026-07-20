"""Fair Value Estimator 协议。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class FairValueResult:
    fair_ey: float | None
    fair_pe: float | None = None
    implied_fair_mcap: float | None = None  # 亿元
    premium_pct: float | None = None
    method_meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class FairValueModel:
    estimator_id: str
    # key: event_kind or "_global_"
    fair_ey_by_key: dict[str, float] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "estimator_id": self.estimator_id,
            "fair_ey_by_key": self.fair_ey_by_key,
            "meta": self.meta,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> FairValueModel:
        return cls(
            estimator_id=str(data.get("estimator_id") or "median_ey"),
            fair_ey_by_key={
                str(k): float(v) for k, v in (data.get("fair_ey_by_key") or {}).items()
            },
            meta=dict(data.get("meta") or {}),
        )


class FairValueEstimator(Protocol):
    id: str

    def fit(self, rows: list[dict[str, Any]], context: dict[str, Any] | None = None) -> FairValueModel: ...

    def estimate(self, model: FairValueModel, row: dict[str, Any]) -> FairValueResult: ...
