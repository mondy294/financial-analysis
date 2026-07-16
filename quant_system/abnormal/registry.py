"""Pattern 注册表。"""
from __future__ import annotations

from quant_system.abnormal.patterns.ath_250 import Ath250Pattern
from quant_system.abnormal.patterns.bottom_launch import BottomLaunchPattern
from quant_system.abnormal.patterns.range_breakout import RangeBreakoutPattern
from quant_system.abnormal.patterns.trend_accel import TrendAccelPattern

DEFAULT_PATTERNS = [
    RangeBreakoutPattern(),
    BottomLaunchPattern(),
    TrendAccelPattern(),
    Ath250Pattern(),
]

PATTERN_REGISTRY: dict[str, object] = {p.pattern_id: p for p in DEFAULT_PATTERNS}


def get_patterns(ids: list[str] | None = None) -> list:
    if not ids:
        return list(DEFAULT_PATTERNS)
    out = []
    for i in ids:
        key = i.strip().upper()
        if key not in PATTERN_REGISTRY:
            raise KeyError(f"未知 Pattern: {i}，可选: {list(PATTERN_REGISTRY)}")
        out.append(PATTERN_REGISTRY[key])
    return out
