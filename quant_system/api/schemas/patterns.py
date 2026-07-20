from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel


class WindowRangeOut(BaseModel):
    length: int
    start: str
    end: str


class PatternHitOut(BaseModel):
    trade_date: date
    code: str
    name: str = ""
    pattern_id: str
    pattern_score: float
    pattern_rank: int
    reasons: list[str] = []
    chosen_windows: dict[str, int] = {}
    chosen_window_ranges: dict[str, WindowRangeOut] | None = None
    stage_similarity: dict[str, float] = {}
    feature_similarity: dict[str, float] = {}
    distance: float = 0.0
    hard_failed: list[str] = []
    metrics_values: dict[str, Any] = {}
    # 命中后短期收益（信号日收盘 → T+h 收盘，前复权；不足为 null）
    return_1: float | None = None
    return_3: float | None = None
    return_5: float | None = None


class PatternEvalOut(BaseModel):
    code: str
    name: str = ""
    trade_date: date
    pattern_id: str
    matched: bool
    similarity: float
    threshold: float
    distance: float = 0.0
    version: str
    chosen_windows: dict[str, int] = {}
    chosen_window_ranges: dict[str, WindowRangeOut] = {}
    stage_similarity: dict[str, float] = {}
    feature_similarity: dict[str, float] = {}
    hard_failed: list[str] = []
    reasons: list[str] = []
    metrics_values: dict[str, Any] = {}


class PatternStatsOut(BaseModel):
    trade_date: date
    stats: dict[str, dict[str, int]]
