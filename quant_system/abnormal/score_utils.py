"""Pattern 内评分工具（锚点插值等，无业务 IO）。"""
from __future__ import annotations

import math
from typing import Sequence


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def anchor_score(
    x: float,
    anchors: Sequence[tuple[float, float]],
    *,
    log_x: bool = False,
) -> float:
    """按锚点表映射到分数。anchors 须按 x 升序：[(x0,s0), (x1,s1), ...]。"""
    if not anchors:
        return 0.0
    if x <= anchors[0][0]:
        return float(anchors[0][1])
    if x >= anchors[-1][0]:
        return float(anchors[-1][1])
    for i in range(len(anchors) - 1):
        x0, s0 = anchors[i]
        x1, s1 = anchors[i + 1]
        if x0 <= x <= x1:
            if log_x:
                if x0 <= 0 or x1 <= 0 or x <= 0:
                    t = (x - x0) / (x1 - x0) if x1 != x0 else 0.0
                else:
                    t = (math.log(x) - math.log(x0)) / (math.log(x1) - math.log(x0))
            else:
                t = (x - x0) / (x1 - x0) if x1 != x0 else 0.0
            return float(lerp(s0, s1, t))
    return float(anchors[-1][1])


def volume_ratio_score(v: float) -> float:
    return anchor_score(v, [(2.0, 60.0), (3.0, 80.0), (5.0, 100.0)], log_x=True)


def amount_score(amount: float) -> float:
    """amount 单位：元。"""
    return anchor_score(
        amount,
        [(2e8, 40.0), (5e8, 60.0), (1e9, 80.0), (2e9, 100.0)],
        log_x=True,
    )


def break_distance_score(d: float) -> float:
    return anchor_score(d, [(0.0, 0.0), (0.1, 60.0), (0.5, 80.0), (1.0, 100.0)])


def relative_return_score(rr: float) -> float:
    """rr：相对市场中位数的超额（百分点）。"""
    return anchor_score(rr, [(0.0, 20.0), (1.0, 50.0), (2.5, 75.0), (5.0, 100.0)])


def weighted_score(parts: dict[str, tuple[float, float]]) -> tuple[float, dict[str, float]]:
    """parts: name -> (score, weight)。返回 (总分, 贡献字典)。"""
    total_w = sum(w for s, w in parts.values() if s == s and w > 0)  # noqa: PLR0124
    if total_w <= 0:
        return 0.0, {}
    contrib: dict[str, float] = {}
    acc = 0.0
    for name, (s, w) in parts.items():
        if s != s or w <= 0:  # NaN
            continue
        c = s * w
        contrib[name] = round(c, 2)
        acc += c
    return clamp(acc / total_w), contrib
