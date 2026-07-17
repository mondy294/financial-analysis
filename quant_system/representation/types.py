"""Market Representation 核心类型（16 v3）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any

import pandas as pd


@dataclass
class SeriesPanel:
    """任意齐整时间序列面板。"""

    series_kind: str
    codes: list[str]
    dates: list[date]
    values: pd.DataFrame  # index=dates, columns=codes
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dataframe(
        cls,
        df: pd.DataFrame,
        *,
        series_kind: str,
        meta: dict[str, Any] | None = None,
    ) -> SeriesPanel:
        if df is None or df.empty:
            return cls(series_kind=series_kind, codes=[], dates=[], values=pd.DataFrame(), meta=meta or {})
        out = df.copy()
        out.index = pd.to_datetime(out.index).date
        codes = [str(c) for c in out.columns]
        dates = list(out.index)
        return cls(
            series_kind=series_kind,
            codes=codes,
            dates=dates,
            values=out,
            meta=dict(meta or {}),
        )

    def to_dataframe(self) -> pd.DataFrame:
        return self.values


@dataclass
class RepresentationBundle:
    """股票向量/画像表示；β 只是 features 的子集。"""

    asof: date
    recipe_id: str
    codes: list[str]
    features: dict[str, dict[str, float]] | None = None
    embeddings: dict[str, list[float]] | None = None
    tags: dict[str, tuple[str, ...]] | None = None
    risk: dict[str, dict[str, float]] | None = None
    style: dict[str, dict[str, float]] | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class RelationKind(str, Enum):
    GRAPH = "GRAPH"
    DISTANCE = "DISTANCE"
    KERNEL = "KERNEL"
    AFFINITY = "AFFINITY"
    KNN = "KNN"
    DIRECTED_GRAPH = "DIRECTED_GRAPH"
    HYPERGRAPH = "HYPERGRAPH"


@dataclass(frozen=True)
class RelationshipObject:
    kind: RelationKind
    calc_date: date
    payload: Any
    sources: tuple[str, ...]
    meta: dict[str, Any] = field(default_factory=dict)
