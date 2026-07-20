from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class BuildEventsIn(BaseModel):
    start_date: date
    end_date: date
    main_only: bool = True


class BuildPanelIn(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    panel_tag: str = "default"
    cluster_run_id: str | None = None
    # 若为 True，先跑 Event Builder（同区间）
    build_events: bool = False
    main_only: bool = True


class FitIn(BaseModel):
    panel_tag: str = "default"
    scopes: list[str] | None = None
    cluster_modes: list[str] | None = None


class PredictIn(BaseModel):
    code: str
    event_kind: str = "interim"
    parent_np: float
    parent_np_yoy: float | None = None
    report_period: date | None = None
    as_of: date | None = None
    model_scope: str = "all"
    use_cluster: bool = False
    model_id: str | None = None
    panel_tag: str = "default"
    with_explain: bool = False


class ModelBriefOut(BaseModel):
    model_id: str
    fitted_at: datetime
    panel_tag: str
    model_scope: str
    cluster_mode: str
    cluster_id: int | None = None
    backend_id: str
    estimator_id: str
    n_samples: int
    metrics: dict[str, Any] = Field(default_factory=dict)
    feature_cols: list[Any] = Field(default_factory=list)


class GenericDictOut(BaseModel):
    """宽松包装，避免为每个管道步骤单独建巨型 schema。"""

    data: dict[str, Any]
