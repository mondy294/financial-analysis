from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

import numpy as np
import pandas as pd

from quant_system.eventstats.constants import DEFAULT_RETURN_HORIZONS


@dataclass(frozen=True)
class ObserveContext:
    horizon_bars: int
    return_horizons: tuple[int, ...]
    code: str
    signal_date: date


class MetricProvider(Protocol):
    name: str
    version: str

    def compute(
        self,
        *,
        forward_bars: pd.DataFrame,
        anchor_close: float,
        ctx: ObserveContext,
    ) -> dict[str, Any]:
        """写入 extra_metrics_json 的扩展事实；不得改写标准宽列语义。"""
        ...


def _f(v: float | None) -> float | None:
    if v is None:
        return None
    if isinstance(v, (float, np.floating)) and (np.isnan(v) or np.isinf(v)):
        return None
    return float(v)


def compute_observation(
    forward_bars: pd.DataFrame,
    *,
    anchor_close: float,
    horizon_bars: int,
    return_horizons: tuple[int, ...] | list[int] = DEFAULT_RETURN_HORIZONS,
) -> dict[str, Any]:
    """对信号日之后的 qfq 序列计算标准 Observation 宽列。

    forward_bars: 严格 > signal_date 的交易日行，按日期升序；第 0 行 = T+1。
    收益 / MFE / MAE 相对 anchor_close（信号日收盘）。
    """
    horizons = tuple(int(h) for h in return_horizons)
    out: dict[str, Any] = {
        "return_1": None,
        "return_3": None,
        "return_5": None,
        "return_10": None,
        "return_20": None,
        "return_60": None,
        "return_horizon": None,
        "mfe": None,
        "mae": None,
        "max_drawdown": None,
        "volatility": None,
        "bull_ratio": None,
        "up_days": None,
        "continuous_up_days": None,
        "highest_day": None,
        "lowest_day": None,
        "time_to_mfe": None,
        "time_to_mae": None,
        "forward_bars_available": 0,
        "forward_status": "insufficient",
    }

    if anchor_close is None or not np.isfinite(anchor_close) or anchor_close <= 0:
        return out
    if forward_bars is None or forward_bars.empty:
        return out

    n = len(forward_bars)
    out["forward_bars_available"] = n
    if n <= 0:
        return out

    H = max(1, int(horizon_bars))
    window = forward_bars.iloc[: min(n, H)].copy()
    wlen = len(window)
    if wlen < H:
        out["forward_status"] = "truncated"
    else:
        out["forward_status"] = "ok"

    close = window["close"].to_numpy(dtype=float)
    high = window["high"].to_numpy(dtype=float)
    low = window["low"].to_numpy(dtype=float)
    open_ = window["open"].to_numpy(dtype=float)

    # 各 horizon 收益（第 h 根 = T+h，iloc h-1）
    for h in horizons:
        col = f"return_{h}"
        if col not in out:
            continue
        if n >= h:
            out[col] = _f(float(forward_bars["close"].iloc[h - 1]) / anchor_close - 1.0)

    if n >= H:
        out["return_horizon"] = _f(float(forward_bars["close"].iloc[H - 1]) / anchor_close - 1.0)
    elif wlen > 0:
        # truncated：仍给出窗末收益作为 return_horizon
        out["return_horizon"] = _f(float(close[-1]) / anchor_close - 1.0)

    if wlen == 0:
        return out

    # MFE / MAE（相对信号收盘）
    max_high = float(np.nanmax(high))
    min_low = float(np.nanmin(low))
    out["mfe"] = _f(max_high / anchor_close - 1.0)
    out["mae"] = _f(1.0 - min_low / anchor_close)

    hi_idx = int(np.nanargmax(high)) + 1  # 1-based day
    lo_idx = int(np.nanargmin(low)) + 1
    out["highest_day"] = hi_idx
    out["lowest_day"] = lo_idx

    # time_to_mfe / mae：favorable = high 极值日；adverse = low 极值日
    out["time_to_mfe"] = hi_idx
    out["time_to_mae"] = lo_idx

    # max_drawdown：窗内 close 的 running peak → trough
    peak = close[0]
    max_dd = 0.0
    for c in close:
        if c > peak:
            peak = c
        if peak > 0:
            dd = 1.0 - c / peak
            if dd > max_dd:
                max_dd = dd
    out["max_drawdown"] = _f(max_dd)

    # 日收益波动（close-to-close within window；首日用 open→close）
    day_rets: list[float] = []
    for i in range(wlen):
        if i == 0:
            if open_[i] > 0:
                day_rets.append(float(close[i] / open_[i] - 1.0))
        else:
            prev = close[i - 1]
            if prev > 0:
                day_rets.append(float(close[i] / prev - 1.0))
    if len(day_rets) >= 2:
        out["volatility"] = _f(float(np.std(day_rets, ddof=1)))
    elif len(day_rets) == 1:
        out["volatility"] = 0.0

    bulls = sum(1 for i in range(wlen) if close[i] > open_[i])
    out["bull_ratio"] = _f(bulls / wlen)

    up = 0
    streak = 0
    max_streak = 0
    for i in range(wlen):
        if i == 0:
            is_up = close[i] > open_[i]
        else:
            is_up = close[i] > close[i - 1]
        if is_up:
            up += 1
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    out["up_days"] = up
    out["continuous_up_days"] = max_streak

    return out
