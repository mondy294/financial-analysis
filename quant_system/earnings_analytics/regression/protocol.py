"""Regression Backend 协议。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np


@dataclass
class FittedModel:
    backend_id: str
    feature_cols: list[str]
    target_col: str
    intercept: float
    coefs: dict[str, float]
    means: dict[str, float]
    stds: dict[str, float]
    std_coefs: dict[str, float] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    n: int = 0
    cluster_intercepts: dict[str, float] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "feature_cols": self.feature_cols,
            "target_col": self.target_col,
            "intercept": self.intercept,
            "coefs": self.coefs,
            "means": self.means,
            "stds": self.stds,
            "std_coefs": self.std_coefs,
            "metrics": self.metrics,
            "n": self.n,
            "cluster_intercepts": self.cluster_intercepts,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> FittedModel:
        return cls(
            backend_id=str(data.get("backend_id") or "ols"),
            feature_cols=list(data.get("feature_cols") or []),
            target_col=str(data.get("target_col") or ""),
            intercept=float(data.get("intercept") or 0.0),
            coefs=dict(data.get("coefs") or {}),
            means=dict(data.get("means") or {}),
            stds=dict(data.get("stds") or {}),
            std_coefs=dict(data.get("std_coefs") or {}),
            metrics=dict(data.get("metrics") or {}),
            n=int(data.get("n") or 0),
            cluster_intercepts={
                str(k): float(v) for k, v in (data.get("cluster_intercepts") or {}).items()
            },
        )


class RegressionBackend(Protocol):
    id: str

    def fit(
        self,
        rows: list[dict[str, Any]],
        feature_cols: list[str],
        target_col: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> FittedModel: ...

    def predict(self, fitted: FittedModel, X_rows: list[dict[str, Any]]) -> np.ndarray: ...


def predict_row(fitted: FittedModel, row: dict[str, Any]) -> float:
    y = fitted.intercept
    for col in fitted.feature_cols:
        y += fitted.coefs.get(col, 0.0) * float(row.get(col) or 0.0)
    cid = row.get("cluster_id")
    if cid is not None and fitted.cluster_intercepts:
        y += fitted.cluster_intercepts.get(str(int(cid)), 0.0)
    return float(y)
