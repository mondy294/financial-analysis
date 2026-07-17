from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class FeatureValue:
    name: str
    value: float | None
    unit: str = "ratio"
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FeatureSimilarity:
    name: str
    similarity: float
    distance: float
    actual: float | None
    ideal: float
    weight: float


@dataclass
class PatternMatchResult:
    pattern_id: str
    code: str
    trade_date: date
    matched: bool
    similarity: float
    stage_similarity: dict[str, float] = field(default_factory=dict)
    feature_similarity: dict[str, float] = field(default_factory=dict)
    chosen_windows: dict[str, int] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    distance: float = 0.0
    hard_failed: list[str] = field(default_factory=list)


@dataclass
class PatternRunResult:
    pattern_id: str
    config_version: str
    trade_date: date
    results: list[PatternMatchResult] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
