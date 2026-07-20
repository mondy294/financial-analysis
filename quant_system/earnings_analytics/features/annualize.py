"""利润机械年化规则。"""
from __future__ import annotations

from datetime import date


def annualize_parent_np(
    parent_np: float,
    event_kind: str,
    report_period: date | None = None,
) -> float | None:
    """按报告进度年化；无法判断时返回 None。"""
    kind = (event_kind or "").lower()
    month = report_period.month if report_period is not None else None

    if kind == "annual":
        return float(parent_np)
    if kind == "interim":
        return float(parent_np) * 2.0
    if kind == "q1":
        return float(parent_np) * 4.0
    if kind == "q3":
        return float(parent_np) * (4.0 / 3.0)

    if kind in ("forecast", "express"):
        if month == 12:
            return float(parent_np)
        if month == 6:
            return float(parent_np) * 2.0
        if month == 3:
            return float(parent_np) * 4.0
        if month == 9:
            return float(parent_np) * (4.0 / 3.0)
        # 缺报告期时：中报语义标题外层应已标 interim；此处保守按中报×2
        return float(parent_np) * 2.0

    return None
