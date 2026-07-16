"""Pattern Protocol 与通用数据结构。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import pandas as pd


@dataclass
class ScanLevel:
    level: int
    filters: dict[str, Any]


@dataclass
class PatternHit:
    code: str
    pattern_id: str
    scan_level: int
    pattern_score: float
    pattern_rank: int = 0
    reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    score_components: dict[str, Any] = field(default_factory=dict)
    inputs_snapshot: dict[str, Any] = field(default_factory=dict)
    amount: float = 0.0


@runtime_checkable
class Pattern(Protocol):
    pattern_id: str
    display_name: str
    scan_levels: list[ScanLevel]
    top_n: int

    def filter(self, df: pd.DataFrame, level: ScanLevel) -> pd.DataFrame:
        """硬条件过滤，返回通过的行（需含 code）。"""
        ...

    def score_row(self, row: pd.Series) -> tuple[float, dict[str, Any], list[str]]:
        """返回 (pattern_score, score_components, reasons)。"""
        ...
