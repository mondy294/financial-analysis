from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

import numpy as np
import pandas as pd

from quant_system.patterns.result import FeatureValue

FeatureCategory = Literal[
    "price", "volume", "volatility", "trend", "candle", "relation", "atom",
]
FeatureTier = Literal["universal", "role_specific", "relation", "context"]
StageRoleName = Literal["range", "up", "down"]

StageAtoms = dict[str, float | None]
StageFrames = dict[str, pd.DataFrame]

ALL_STAGE_ROLES: frozenset[str] = frozenset({"range", "up", "down"})


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    category: FeatureCategory
    description: str
    kind: Literal["stage", "relation", "context", "atom"] = "stage"
    # 引导编辑分层：universal=三角色可用；role_specific=仅 roles 内角色
    tier: FeatureTier = "universal"
    # None / 含 "all" → 全角色；否则为允许的 StageRole 集合
    roles: frozenset[str] | None = None
    ui_group: str = "price"
    default_target: dict[str, Any] | None = None
    extract_stage: Callable[[pd.DataFrame], FeatureValue] | None = None
    extract_relation: Callable[
        [dict[str, StageAtoms], dict[str, str], StageFrames | None], FeatureValue
    ] | None = None
    # 股票级特征：输入为已按 lookback 切好的历史序列（含 asof 当日）
    extract_context: Callable[[pd.DataFrame], FeatureValue] | None = None


def _safe_div(a: float, b: float) -> float | None:
    if b == 0 or np.isnan(b) or np.isnan(a):
        return None
    return float(a / b)


def _returns(close: np.ndarray) -> np.ndarray:
    if len(close) < 2:
        return np.array([], dtype=float)
    prev = close[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        ret = np.where(prev == 0, np.nan, close[1:] / prev - 1.0)
    return ret.astype(float)


def _day_returns(df: pd.DataFrame) -> np.ndarray:
    """单日涨跌：优先用 (close/open - 1)，避免短 Stage 缺少前收。"""
    if df.empty:
        return np.array([], dtype=float)
    open_ = df["open"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        ret = np.where(open_ == 0, np.nan, close / open_ - 1.0)
    return ret.astype(float)


def _feat(name: str, value: float | None, **meta: Any) -> FeatureValue:
    if value is not None and isinstance(value, float) and np.isnan(value):
        value = None
    return FeatureValue(name=name, value=None if value is None else float(value), meta=meta)


# ---------------------------------------------------------------------------
# 既有 Stage Feature
# ---------------------------------------------------------------------------

def extract_amplitude(df: pd.DataFrame) -> FeatureValue:
    if df.empty:
        return _feat("amplitude", None)
    high = float(df["high"].max())
    low = float(df["low"].min())
    return _feat("amplitude", _safe_div(high - low, low), high=high, low=low)


def extract_close_vs_window_high(df: pd.DataFrame) -> FeatureValue:
    """段末收盘相对段内最高价：close_last/high_max - 1；越接近 0 越未深砸。"""
    if df.empty:
        return _feat("close_vs_window_high", None)
    high = float(df["high"].max())
    close = float(df["close"].iloc[-1])
    if high == 0:
        return _feat("close_vs_window_high", None)
    return _feat(
        "close_vs_window_high",
        close / high - 1.0,
        high=high, close=close, n=len(df),
    )


def extract_peak_day(df: pd.DataFrame) -> FeatureValue:
    """段内最高价出现位置，归一化到 [0,1]；0=段首，1=段尾。"""
    n = len(df)
    if n < 2:
        return _feat("peak_day", None)
    highs = df["high"].to_numpy(dtype=float)
    if np.any(~np.isfinite(highs)):
        return _feat("peak_day", None)
    idx = int(np.nanargmax(highs))
    return _feat("peak_day", idx / (n - 1), peak_index=idx, n=n)


def extract_trough_day(df: pd.DataFrame) -> FeatureValue:
    """段内最低价出现位置，归一化到 [0,1]；0=段首，1=段尾。弧形下跌段理想靠近段尾。"""
    n = len(df)
    if n < 2:
        return _feat("trough_day", None)
    lows = df["low"].to_numpy(dtype=float)
    if np.any(~np.isfinite(lows)):
        return _feat("trough_day", None)
    idx = int(np.nanargmin(lows))
    return _feat("trough_day", idx / (n - 1), trough_index=idx, n=n)


def extract_total_return(df: pd.DataFrame) -> FeatureValue:
    """段收益：多日用 close_last/close_first-1；单日用 close/prior_close-1。

    prior_close 由 Matcher 写入 df.attrs['prior_close']（段前一根收盘）。
    """
    if df.empty:
        return _feat("total_return", None)
    last = float(df["close"].iloc[-1])
    if len(df) >= 2:
        first = float(df["close"].iloc[0])
        return _feat("total_return", _safe_div(last, first) - 1.0)
    prior = df.attrs.get("prior_close")
    if prior is None:
        return _feat("total_return", None, note="missing_prior_close")
    prior_f = float(prior)
    if prior_f == 0:
        return _feat("total_return", None)
    return _feat(
        "total_return",
        last / prior_f - 1.0,
        prior_close=prior_f,
        close_last=last,
    )


def _linear_fit_close(df: pd.DataFrame) -> tuple[float | None, float | None, float | None]:
    """对 close ~ t 做最小二乘直线拟合。

    返回:
      slope_norm: 拟合斜率 / 均价，单位≈每日涨跌比例（不是首尾相连）
      r2: 决定系数，越接近 1 越像直线
      residual_ratio: 残差标准差 / 均价
    """
    n = len(df)
    if n < 2:
        return None, None, None
    y = df["close"].to_numpy(dtype=float)
    if np.any(~np.isfinite(y)):
        return None, None, None
    mean_y = float(np.mean(y))
    if mean_y == 0:
        return None, None, None
    if float(np.std(y)) < 1e-12:
        return 0.0, 1.0, 0.0

    t = np.arange(n, dtype=float)
    # close = a + b*t
    b, a = np.polyfit(t, y, 1)
    fitted = a + b * t
    ss_res = float(np.sum((y - fitted) ** 2))
    ss_tot = float(np.sum((y - mean_y) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    r2 = float(max(0.0, min(1.0, r2)))
    residual_ratio = float(np.sqrt(ss_res / n) / abs(mean_y))
    slope_norm = float(b / mean_y)
    return slope_norm, r2, residual_ratio


def extract_slope(df: pd.DataFrame) -> FeatureValue:
    """拟合直线斜率（归一化），不是首尾相连。"""
    slope_norm, r2, residual_ratio = _linear_fit_close(df)
    if slope_norm is None:
        return _feat("slope", None)
    return _feat("slope", slope_norm, r2=r2, residual_ratio=residual_ratio)


def extract_linearity(df: pd.DataFrame) -> FeatureValue:
    """价格路径对直线的拟合优度 R²；越接近 1 越像直线。"""
    slope_norm, r2, residual_ratio = _linear_fit_close(df)
    if r2 is None:
        return _feat("linearity", None)
    return _feat("linearity", r2, slope=slope_norm, residual_ratio=residual_ratio)


def extract_volatility(df: pd.DataFrame) -> FeatureValue:
    close = df["close"].to_numpy(dtype=float)
    ret = _returns(close)
    if len(ret) == 0:
        # 单日退化：用实体涨跌绝对值近似
        day = _day_returns(df)
        if len(day) == 0:
            return _feat("volatility", None)
        return _feat("volatility", float(abs(day[0])))
    return _feat("volatility", float(np.nanstd(ret, ddof=1)) if len(ret) > 1 else float(np.nanstd(ret)))


def extract_volume_shrink_ratio(df: pd.DataFrame) -> FeatureValue:
    vol = df["volume"].to_numpy(dtype=float)
    n = len(vol)
    if n < 4:
        return _feat("volume_shrink_ratio", None)
    mid = n // 2
    left = float(np.nanmean(vol[:mid]))
    right = float(np.nanmean(vol[mid:]))
    return _feat("volume_shrink_ratio", _safe_div(right, left), left_avg=left, right_avg=right)


def extract_bull_ratio(df: pd.DataFrame) -> FeatureValue:
    n = len(df)
    if n == 0:
        return _feat("bull_ratio", None)
    bull = int((df["close"].to_numpy(dtype=float) > df["open"].to_numpy(dtype=float)).sum())
    return _feat("bull_ratio", bull / n, bull_days=bull, n=n)


def extract_body_ratio(df: pd.DataFrame) -> FeatureValue:
    if df.empty:
        return _feat("body_ratio", None)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    open_ = df["open"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    span = np.maximum(high - low, 1e-12)
    body = np.abs(close - open_) / span
    return _feat("body_ratio", float(np.nanmean(body)))


def extract_avg_volume(df: pd.DataFrame) -> FeatureValue:
    if df.empty:
        return _feat("avg_volume", None)
    return _feat("avg_volume", float(np.nanmean(df["volume"].to_numpy(dtype=float))))


# ---------------------------------------------------------------------------
# 短阶段价格路径
# ---------------------------------------------------------------------------

def extract_gap_open(df: pd.DataFrame) -> FeatureValue:
    """段首跳空：open_first / prior_close - 1；>0 跳高开，<0 跳低开。

    prior_close 由 Matcher 写入 df.attrs['prior_close']。
    """
    if df.empty:
        return _feat("gap_open", None)
    prior = df.attrs.get("prior_close")
    if prior is None:
        return _feat("gap_open", None, note="missing_prior_close")
    prior_f = float(prior)
    if prior_f == 0:
        return _feat("gap_open", None)
    open_first = float(df["open"].iloc[0])
    return _feat(
        "gap_open",
        open_first / prior_f - 1.0,
        prior_close=prior_f,
        open_first=open_first,
    )


def extract_return_first(df: pd.DataFrame) -> FeatureValue:
    day = _day_returns(df)
    if len(day) == 0:
        return _feat("return_first", None)
    return _feat("return_first", float(day[0]))


def extract_return_last(df: pd.DataFrame) -> FeatureValue:
    day = _day_returns(df)
    if len(day) == 0:
        return _feat("return_last", None)
    return _feat("return_last", float(day[-1]))


def extract_return_acceleration(df: pd.DataFrame) -> FeatureValue:
    """尾日涨幅 - 首日涨幅；>0 加速，<0 滞涨。"""
    day = _day_returns(df)
    if len(day) == 0:
        return _feat("return_acceleration", None)
    if len(day) == 1:
        return _feat("return_acceleration", 0.0)
    return _feat("return_acceleration", float(day[-1] - day[0]))


def extract_up_day_ratio(df: pd.DataFrame) -> FeatureValue:
    """上涨日占比：多日用 close>prev_close；单日用 close>open。"""
    n = len(df)
    if n == 0:
        return _feat("up_day_ratio", None)
    close = df["close"].to_numpy(dtype=float)
    if n == 1:
        open_ = float(df["open"].iloc[0])
        return _feat("up_day_ratio", 1.0 if close[0] > open_ else 0.0)
    ups = int(np.sum(close[1:] > close[:-1]))
    return _feat("up_day_ratio", ups / (n - 1), up_days=ups, transitions=n - 1)


def extract_consecutive_up_ratio(df: pd.DataFrame) -> FeatureValue:
    """从段首开始的连续上涨长度 / 可比较天数。全程连涨 = 1。"""
    n = len(df)
    if n == 0:
        return _feat("consecutive_up_ratio", None)
    close = df["close"].to_numpy(dtype=float)
    open_ = df["open"].to_numpy(dtype=float)
    if n == 1:
        return _feat("consecutive_up_ratio", 1.0 if close[0] > open_[0] else 0.0)
    run = 0
    for i in range(1, n):
        if close[i] > close[i - 1]:
            run += 1
        else:
            break
    return _feat("consecutive_up_ratio", run / (n - 1), consecutive_up_days=run)


def extract_stall_score(df: pd.DataFrame) -> FeatureValue:
    """滞涨分：首日强、尾日弱时变大。ideal=0，one_sided_low。"""
    day = _day_returns(df)
    if len(day) == 0:
        return _feat("stall_score", None)
    if len(day) == 1:
        return _feat("stall_score", 0.0)
    first = float(day[0])
    last = float(day[-1])
    if first <= 0:
        # 首日不强，不算“冲高后滞涨”
        return _feat("stall_score", 0.0, return_first=first, return_last=last)
    score = max(0.0, first - last) / max(abs(first), 1e-6)
    return _feat("stall_score", float(score), return_first=first, return_last=last)


def extract_close_strength(df: pd.DataFrame) -> FeatureValue:
    """收盘在当日振幅中的位置，1=收在最高附近。"""
    if df.empty:
        return _feat("close_strength", None)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    span = np.maximum(high - low, 1e-12)
    strength = (close - low) / span
    return _feat("close_strength", float(np.nanmean(strength)))


# ---------------------------------------------------------------------------
# 短阶段量能路径
# ---------------------------------------------------------------------------

def extract_volume_up_ratio(df: pd.DataFrame) -> FeatureValue:
    """放量日占比：vol[i] > vol[i-1]。"""
    vol = df["volume"].to_numpy(dtype=float)
    n = len(vol)
    if n == 0:
        return _feat("volume_up_ratio", None)
    if n == 1:
        return _feat("volume_up_ratio", 1.0)
    ups = int(np.sum(vol[1:] > vol[:-1]))
    return _feat("volume_up_ratio", ups / (n - 1), volume_up_days=ups)


def extract_consecutive_volume_up_ratio(df: pd.DataFrame) -> FeatureValue:
    """从段首开始的连续放量长度占比。"""
    vol = df["volume"].to_numpy(dtype=float)
    n = len(vol)
    if n == 0:
        return _feat("consecutive_volume_up_ratio", None)
    if n == 1:
        return _feat("consecutive_volume_up_ratio", 1.0)
    run = 0
    for i in range(1, n):
        if vol[i] > vol[i - 1]:
            run += 1
        else:
            break
    return _feat("consecutive_volume_up_ratio", run / (n - 1), consecutive_volume_up_days=run)


def extract_volume_acceleration(df: pd.DataFrame) -> FeatureValue:
    """尾日量 / 首日量。"""
    vol = df["volume"].to_numpy(dtype=float)
    if len(vol) == 0:
        return _feat("volume_acceleration", None)
    if len(vol) == 1:
        return _feat("volume_acceleration", 1.0)
    return _feat("volume_acceleration", _safe_div(float(vol[-1]), float(vol[0])))


def extract_volume_last_vs_avg(df: pd.DataFrame) -> FeatureValue:
    """尾日量 / 段内均量。"""
    vol = df["volume"].to_numpy(dtype=float)
    if len(vol) == 0:
        return _feat("volume_last_vs_avg", None)
    avg = float(np.nanmean(vol))
    return _feat("volume_last_vs_avg", _safe_div(float(vol[-1]), avg), avg_volume=avg)


def extract_volume_climax_day(df: pd.DataFrame) -> FeatureValue:
    """最大量出现位置，0=首日，1=尾日。"""
    vol = df["volume"].to_numpy(dtype=float)
    n = len(vol)
    if n == 0:
        return _feat("volume_climax_day", None)
    if n == 1:
        return _feat("volume_climax_day", 1.0)
    idx = int(np.nanargmax(vol))
    return _feat("volume_climax_day", idx / (n - 1), climax_index=idx)


# ---------------------------------------------------------------------------
# K 线质量
# ---------------------------------------------------------------------------

def extract_upper_shadow_ratio(df: pd.DataFrame) -> FeatureValue:
    if df.empty:
        return _feat("upper_shadow_ratio", None)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    open_ = df["open"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    span = np.maximum(high - low, 1e-12)
    upper = (high - np.maximum(open_, close)) / span
    return _feat("upper_shadow_ratio", float(np.nanmean(upper)))


def extract_lower_shadow_ratio(df: pd.DataFrame) -> FeatureValue:
    if df.empty:
        return _feat("lower_shadow_ratio", None)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    open_ = df["open"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    span = np.maximum(high - low, 1e-12)
    lower = (np.minimum(open_, close) - low) / span
    return _feat("lower_shadow_ratio", float(np.nanmean(lower)))


# ---------------------------------------------------------------------------
# P0 角色 / 通用新增
# ---------------------------------------------------------------------------

def extract_consecutive_up_days(df: pd.DataFrame) -> FeatureValue:
    """从段首起连续上涨天数（整数）。单日：收>开计 1。"""
    n = len(df)
    if n == 0:
        return _feat("consecutive_up_days", None)
    close = df["close"].to_numpy(dtype=float)
    open_ = df["open"].to_numpy(dtype=float)
    if n == 1:
        days = 1.0 if close[0] > open_[0] else 0.0
        return _feat("consecutive_up_days", days)
    run = 0
    for i in range(1, n):
        if close[i] > close[i - 1]:
            run += 1
        else:
            break
    return _feat("consecutive_up_days", float(run))


def extract_consecutive_down_days(df: pd.DataFrame) -> FeatureValue:
    """从段首起连续下跌天数（整数）。单日：收<开计 1。"""
    n = len(df)
    if n == 0:
        return _feat("consecutive_down_days", None)
    close = df["close"].to_numpy(dtype=float)
    open_ = df["open"].to_numpy(dtype=float)
    if n == 1:
        days = 1.0 if close[0] < open_[0] else 0.0
        return _feat("consecutive_down_days", days)
    run = 0
    for i in range(1, n):
        if close[i] < close[i - 1]:
            run += 1
        else:
            break
    return _feat("consecutive_down_days", float(run))


def extract_consecutive_down_ratio(df: pd.DataFrame) -> FeatureValue:
    """从段首连续下跌长度 / 可比较天数。"""
    n = len(df)
    if n == 0:
        return _feat("consecutive_down_ratio", None)
    close = df["close"].to_numpy(dtype=float)
    open_ = df["open"].to_numpy(dtype=float)
    if n == 1:
        return _feat("consecutive_down_ratio", 1.0 if close[0] < open_[0] else 0.0)
    run = 0
    for i in range(1, n):
        if close[i] < close[i - 1]:
            run += 1
        else:
            break
    return _feat("consecutive_down_ratio", run / (n - 1), consecutive_down_days=run)


def extract_down_day_ratio(df: pd.DataFrame) -> FeatureValue:
    """下跌日占比：多日用 close<prev_close；单日用 close<open。"""
    n = len(df)
    if n == 0:
        return _feat("down_day_ratio", None)
    close = df["close"].to_numpy(dtype=float)
    if n == 1:
        open_ = float(df["open"].iloc[0])
        return _feat("down_day_ratio", 1.0 if close[0] < open_ else 0.0)
    downs = int(np.sum(close[1:] < close[:-1]))
    return _feat("down_day_ratio", downs / (n - 1), down_days=downs, transitions=n - 1)


def extract_return_slope_accel(df: pd.DataFrame) -> FeatureValue:
    """后半段 slope − 前半段 slope；>0 越涨越快 / 跌势放缓。"""
    n = len(df)
    if n < 4:
        return _feat("return_slope_accel", None)
    mid = n // 2
    left = df.iloc[:mid]
    right = df.iloc[mid:]
    s_left, _, _ = _linear_fit_close(left)
    s_right, _, _ = _linear_fit_close(right)
    if s_left is None or s_right is None:
        return _feat("return_slope_accel", None)
    return _feat(
        "return_slope_accel",
        float(s_right - s_left),
        slope_first_half=s_left,
        slope_second_half=s_right,
    )


def extract_close_accel_ratio(df: pd.DataFrame) -> FeatureValue:
    """后半段 total_return / 前半段 total_return；>1 加速（符号同向时）。"""
    n = len(df)
    if n < 4:
        return _feat("close_accel_ratio", None)
    mid = n // 2
    left = df.iloc[:mid]
    right = df.iloc[mid:]
    r_left = extract_total_return(left).value
    r_right = extract_total_return(right).value
    if r_left is None or r_right is None:
        return _feat("close_accel_ratio", None)
    if abs(r_left) < 1e-12:
        return _feat("close_accel_ratio", None, note="first_half_return_near_zero")
    return _feat(
        "close_accel_ratio",
        float(r_right / r_left),
        return_first_half=r_left,
        return_second_half=r_right,
    )


def extract_max_drawdown_in_window(df: pd.DataFrame) -> FeatureValue:
    """段内最大回撤（正数）：从运行高点到后续低点的最大跌幅。"""
    if df.empty:
        return _feat("max_drawdown_in_window", None)
    close = df["close"].to_numpy(dtype=float)
    if not np.any(np.isfinite(close)):
        return _feat("max_drawdown_in_window", None)
    peak = close[0]
    max_dd = 0.0
    for c in close:
        if not np.isfinite(c):
            continue
        if c > peak:
            peak = c
        if peak > 0:
            dd = 1.0 - c / peak
            if dd > max_dd:
                max_dd = dd
    return _feat("max_drawdown_in_window", float(max_dd))


# ---------------------------------------------------------------------------
# Atoms / Relations
# ---------------------------------------------------------------------------

def compute_stage_atoms(df: pd.DataFrame) -> StageAtoms:
    if df.empty:
        return {
            "high_max": None,
            "low_min": None,
            "close_last": None,
            "close_first": None,
            "avg_volume": None,
            "n": 0.0,
        }
    return {
        "high_max": float(df["high"].max()),
        "low_min": float(df["low"].min()),
        "close_last": float(df["close"].iloc[-1]),
        "close_first": float(df["close"].iloc[0]),
        "avg_volume": float(np.nanmean(df["volume"].to_numpy(dtype=float))),
        "n": float(len(df)),
    }


def relation_breakout_distance(
    atoms: dict[str, StageAtoms],
    stage_map: dict[str, str],
    frames: StageFrames | None = None,
) -> FeatureValue:
    plat = atoms.get(stage_map.get("platform", "platform"), {})
    brk = atoms.get(stage_map.get("breakout", "breakout"), {})
    high = plat.get("high_max")
    close = brk.get("close_last")
    if high is None or close is None or high == 0:
        return _feat("breakout_distance", None)
    return _feat("breakout_distance", float(close) / float(high) - 1.0, platform_high=high, close_last=close)


def relation_volume_vs_platform(
    atoms: dict[str, StageAtoms],
    stage_map: dict[str, str],
    frames: StageFrames | None = None,
) -> FeatureValue:
    plat = atoms.get(stage_map.get("platform", "platform"), {})
    brk = atoms.get(stage_map.get("breakout", "breakout"), {})
    base = plat.get("avg_volume")
    active = brk.get("avg_volume")
    if base is None or active is None or base == 0:
        return _feat("volume_vs_platform", None)
    return _feat("volume_vs_platform", float(active) / float(base), platform_avg_vol=base, breakout_avg_vol=active)


def relation_close_vs_platform_mid(
    atoms: dict[str, StageAtoms],
    stage_map: dict[str, str],
    frames: StageFrames | None = None,
) -> FeatureValue:
    plat = atoms.get(stage_map.get("platform", "platform"), {})
    brk = atoms.get(stage_map.get("breakout", "breakout"), {})
    high = plat.get("high_max")
    low = plat.get("low_min")
    close = brk.get("close_last")
    if high is None or low is None or close is None:
        return _feat("close_vs_platform_mid", None)
    mid = (float(high) + float(low)) / 2.0
    return _feat("close_vs_platform_mid", _safe_div(float(close) - mid, mid), platform_mid=mid)


def relation_break_hold_ratio(
    atoms: dict[str, StageAtoms],
    stage_map: dict[str, str],
    frames: StageFrames | None = None,
) -> FeatureValue:
    """突破段内收盘仍站上平台高点的天数占比。"""
    plat = atoms.get(stage_map.get("platform", "platform"), {})
    high = plat.get("high_max")
    if high is None or frames is None:
        return _feat("break_hold_ratio", None)
    brk_name = stage_map.get("breakout", "breakout")
    brk_df = frames.get(brk_name)
    if brk_df is None or brk_df.empty:
        return _feat("break_hold_ratio", None)
    closes = brk_df["close"].to_numpy(dtype=float)
    held = int(np.sum(closes >= float(high)))
    return _feat("break_hold_ratio", held / len(closes), held_days=held, n=len(closes), platform_high=high)


def relation_low_vs_prior_high(
    atoms: dict[str, StageAtoms],
    stage_map: dict[str, str],
    frames: StageFrames | None = None,
) -> FeatureValue:
    """回踩段最低价相对前高：low / prior.high_max - 1；>=0 表示未跌破前高。"""
    plat = atoms.get(stage_map.get("platform", "platform"), {})
    brk = atoms.get(stage_map.get("breakout", "breakout"), {})
    high = plat.get("high_max")
    low = brk.get("low_min")
    if frames is not None:
        brk_name = stage_map.get("breakout", "breakout")
        brk_df = frames.get(brk_name)
        if brk_df is not None and not brk_df.empty:
            low = float(brk_df["low"].min())
    if high is None or low is None or high == 0:
        return _feat("low_vs_prior_high", None)
    return _feat(
        "low_vs_prior_high",
        float(low) / float(high) - 1.0,
        platform_high=high,
        low_min=low,
    )


def relation_breakout_on_last_day(
    atoms: dict[str, StageAtoms],
    stage_map: dict[str, str],
    frames: StageFrames | None = None,
) -> FeatureValue:
    """拉升段是否在末日才首次收盘站上前高：1=末日首破，0=更早已破或末日未破。"""
    plat = atoms.get(stage_map.get("platform", "platform"), {})
    high = plat.get("high_max")
    if high is None or frames is None:
        return _feat("breakout_on_last_day", None)
    brk_name = stage_map.get("breakout", "breakout")
    brk_df = frames.get(brk_name)
    if brk_df is None or brk_df.empty:
        return _feat("breakout_on_last_day", None)
    closes = brk_df["close"].to_numpy(dtype=float)
    h = float(high)
    last_above = bool(np.isfinite(closes[-1]) and closes[-1] >= h)
    if not last_above:
        return _feat("breakout_on_last_day", 0.0, platform_high=h, last_close=float(closes[-1]))
    if len(closes) == 1:
        return _feat("breakout_on_last_day", 1.0, platform_high=h, last_close=float(closes[-1]))
    earlier = closes[:-1]
    earlier_above = bool(np.any(np.isfinite(earlier) & (earlier >= h)))
    return _feat(
        "breakout_on_last_day",
        0.0 if earlier_above else 1.0,
        platform_high=h,
        last_close=float(closes[-1]),
        earlier_broke=earlier_above,
    )


# ---------------------------------------------------------------------------
# Context Feature（股票级：对 lookback 历史算一次）
# ---------------------------------------------------------------------------

def extract_price_position(df: pd.DataFrame) -> FeatureValue:
    """当前收盘在 lookback 高低区间中的位置：[0,1]，0=最低附近，1=最高附近。"""
    if df.empty or len(df) < 2:
        return _feat("price_position", None)
    high = float(df["high"].max())
    low = float(df["low"].min())
    close = float(df["close"].iloc[-1])
    span = high - low
    if span <= 0:
        return _feat("price_position", 0.5, high=high, low=low, close=close, n=len(df))
    pos = (close - low) / span
    return _feat(
        "price_position",
        float(max(0.0, min(1.0, pos))),
        high=high, low=low, close=close, n=len(df),
    )


def extract_price_percentile(df: pd.DataFrame) -> FeatureValue:
    """当前收盘在 lookback 收盘序列中的分位：[0,1]。"""
    if df.empty or len(df) < 2:
        return _feat("price_percentile", None)
    closes = df["close"].to_numpy(dtype=float)
    last = float(closes[-1])
    if not np.isfinite(last):
        return _feat("price_percentile", None)
    valid = closes[np.isfinite(closes)]
    if len(valid) < 2:
        return _feat("price_percentile", None)
    rank = float(np.sum(valid <= last))
    pct = (rank - 1.0) / (len(valid) - 1.0)
    return _feat("price_percentile", float(max(0.0, min(1.0, pct))), close=last, n=len(valid))


def extract_close_vs_high(df: pd.DataFrame) -> FeatureValue:
    """相对 lookback 最高价：close/high_max - 1；越接近 0 越靠近高点，越负越低位。"""
    if df.empty:
        return _feat("close_vs_high", None)
    high = float(df["high"].max())
    close = float(df["close"].iloc[-1])
    if high == 0:
        return _feat("close_vs_high", None)
    return _feat("close_vs_high", close / high - 1.0, high=high, close=close, n=len(df))


def _stage(
    name: str,
    category: FeatureCategory,
    description: str,
    extract: Callable[[pd.DataFrame], FeatureValue],
    *,
    tier: FeatureTier = "universal",
    roles: frozenset[str] | None = None,
    ui_group: str = "price",
    default_target: dict[str, Any] | None = None,
) -> FeatureSpec:
    if roles is None and tier == "universal":
        roles = ALL_STAGE_ROLES
    return FeatureSpec(
        name=name,
        category=category,
        description=description,
        kind="stage",
        tier=tier,
        roles=roles,
        ui_group=ui_group,
        default_target=default_target,
        extract_stage=extract,
    )


# 编辑器展示用中文短名（稳定英文 name 不变）
FEATURE_LABELS_ZH: dict[str, str] = {
    "amplitude": "振幅",
    "close_vs_window_high": "相对窗口高点",
    "peak_day": "最高价位置",
    "trough_day": "最低价位置",
    "total_return": "区间涨跌幅",
    "slope": "价格斜率",
    "linearity": "走势直线度",
    "volatility": "波动率",
    "volume_shrink_ratio": "后半段缩量比",
    "bull_ratio": "阳线占比",
    "body_ratio": "实体占比",
    "avg_volume": "平均成交量",
    "gap_open": "跳空开盘",
    "close_strength": "收盘强度",
    "volume_up_ratio": "放量日占比",
    "volume_acceleration": "量能首尾比",
    "volume_last_vs_avg": "尾日量/均量",
    "volume_climax_day": "天量位置",
    "upper_shadow_ratio": "上影占比",
    "lower_shadow_ratio": "下影占比",
    "max_drawdown_in_window": "段内最大回撤",
    "return_first": "首日涨跌幅",
    "return_last": "尾日涨跌幅",
    "return_acceleration": "涨幅加速度",
    "up_day_ratio": "上涨日占比",
    "consecutive_up_ratio": "连涨占比",
    "consecutive_up_days": "连涨天数",
    "stall_score": "滞涨分",
    "consecutive_volume_up_ratio": "连续放量占比",
    "return_slope_accel": "斜率加速度",
    "close_accel_ratio": "涨幅加速比",
    "down_day_ratio": "下跌日占比",
    "consecutive_down_days": "连跌天数",
    "consecutive_down_ratio": "连跌占比",
    "breakout_distance": "突破前高距离",
    "volume_vs_platform": "相对前段放量",
    "close_vs_platform_mid": "相对前段中轴",
    "break_hold_ratio": "站上前高占比",
    "low_vs_prior_high": "最低价相对前高",
    "breakout_on_last_day": "末日首破前高",
    "price_position": "一年价位",
    "price_percentile": "收盘分位",
    "close_vs_high": "相对历史高点",
}


FEATURE_CATALOG: dict[str, FeatureSpec] = {
    # ---- L0 通用段内 ----
    "amplitude": _stage(
        "amplitude", "volatility", "切片 (high_max-low_min)/low_min",
        extract_amplitude, ui_group="price",
        default_target={"ideal": 0.08, "tolerance": 0.06, "mode": "one_sided_low"},
    ),
    "close_vs_window_high": _stage(
        "close_vs_window_high", "price",
        "close_last/段内high_max - 1（相对窗口高点回撤）",
        extract_close_vs_window_high, ui_group="price",
    ),
    "peak_day": _stage(
        "peak_day", "trend",
        "段内最高价位置 [0,1]，0=段首 1=段尾",
        extract_peak_day, ui_group="path",
    ),
    "trough_day": _stage(
        "trough_day", "trend",
        "段内最低价位置 [0,1]，0=段首 1=段尾（弧形下跌理想靠近段尾）",
        extract_trough_day, ui_group="path",
    ),
    "total_return": _stage(
        "total_return", "price",
        "多日: close_last/close_first-1；单日: close/前收-1",
        extract_total_return, ui_group="price",
        default_target={"ideal": 0.05, "tolerance": 0.05, "mode": "one_sided_high"},
    ),
    "slope": _stage(
        "slope", "trend",
        "close~t 最小二乘拟合斜率/均价（非首尾相连）",
        extract_slope, ui_group="path",
        default_target={"ideal": 0.0, "tolerance": 0.01, "mode": "two_sided"},
    ),
    "linearity": _stage(
        "linearity", "trend",
        "close~t 直线拟合 R²，越接近1越像直线",
        extract_linearity, ui_group="path",
    ),
    "volatility": _stage(
        "volatility", "volatility", "日收益标准差",
        extract_volatility, ui_group="price",
    ),
    "volume_shrink_ratio": _stage(
        "volume_shrink_ratio", "volume", "后半段均量/前半段均量",
        extract_volume_shrink_ratio, ui_group="volume",
    ),
    "bull_ratio": _stage(
        "bull_ratio", "candle", "阳线占比",
        extract_bull_ratio, ui_group="quality",
    ),
    "body_ratio": _stage(
        "body_ratio", "candle", "实体/振幅均值",
        extract_body_ratio, ui_group="quality",
    ),
    "avg_volume": _stage(
        "avg_volume", "volume", "均量",
        extract_avg_volume, ui_group="volume",
    ),
    "gap_open": _stage(
        "gap_open", "price",
        "段首 open/前收-1（跳高开为正）",
        extract_gap_open, ui_group="price",
    ),
    "close_strength": _stage(
        "close_strength", "candle", "收盘在振幅中的位置",
        extract_close_strength, ui_group="quality",
    ),
    "volume_up_ratio": _stage(
        "volume_up_ratio", "volume", "放量日占比",
        extract_volume_up_ratio, ui_group="volume",
    ),
    "volume_acceleration": _stage(
        "volume_acceleration", "volume", "尾日量/首日量",
        extract_volume_acceleration, ui_group="volume",
    ),
    "volume_last_vs_avg": _stage(
        "volume_last_vs_avg", "volume", "尾日量/段内均量",
        extract_volume_last_vs_avg, ui_group="volume",
    ),
    "volume_climax_day": _stage(
        "volume_climax_day", "volume", "最大量位置 0~1",
        extract_volume_climax_day, ui_group="volume",
    ),
    "upper_shadow_ratio": _stage(
        "upper_shadow_ratio", "candle", "上影占比",
        extract_upper_shadow_ratio, ui_group="quality",
    ),
    "lower_shadow_ratio": _stage(
        "lower_shadow_ratio", "candle", "下影占比",
        extract_lower_shadow_ratio, ui_group="quality",
    ),
    "max_drawdown_in_window": _stage(
        "max_drawdown_in_window", "price",
        "段内最大回撤（正数，从运行高点算）",
        extract_max_drawdown_in_window, ui_group="price",
        default_target={"ideal": 0.05, "tolerance": 0.05, "mode": "one_sided_low"},
    ),
    # ---- L1 上涨专用 ----
    "return_first": _stage(
        "return_first", "price", "首日 (close/open-1)",
        extract_return_first, tier="role_specific", roles=frozenset({"up"}),
        ui_group="price",
    ),
    "return_last": _stage(
        "return_last", "price", "尾日 (close/open-1)",
        extract_return_last, tier="role_specific", roles=frozenset({"up", "down"}),
        ui_group="price",
    ),
    "return_acceleration": _stage(
        "return_acceleration", "price", "尾日涨幅-首日涨幅",
        extract_return_acceleration, tier="role_specific", roles=frozenset({"up"}),
        ui_group="path",
    ),
    "up_day_ratio": _stage(
        "up_day_ratio", "price", "上涨日占比",
        extract_up_day_ratio, tier="role_specific", roles=frozenset({"up"}),
        ui_group="path",
    ),
    "consecutive_up_ratio": _stage(
        "consecutive_up_ratio", "price", "从段首连续上涨占比",
        extract_consecutive_up_ratio, tier="role_specific", roles=frozenset({"up"}),
        ui_group="path",
    ),
    "consecutive_up_days": _stage(
        "consecutive_up_days", "price", "从段首连续上涨天数",
        extract_consecutive_up_days, tier="role_specific", roles=frozenset({"up"}),
        ui_group="path",
        default_target={
            "ideal": 2.0, "tolerance": 1.0, "mode": "one_sided_high", "hard_min": 1.0,
        },
    ),
    "stall_score": _stage(
        "stall_score", "price", "滞涨分（首强尾弱）",
        extract_stall_score, tier="role_specific", roles=frozenset({"up"}),
        ui_group="path",
        default_target={"ideal": 0.0, "tolerance": 0.5, "mode": "one_sided_low"},
    ),
    "consecutive_volume_up_ratio": _stage(
        "consecutive_volume_up_ratio", "volume", "从段首连续放量占比",
        extract_consecutive_volume_up_ratio, tier="role_specific", roles=frozenset({"up"}),
        ui_group="volume",
    ),
    "return_slope_accel": _stage(
        "return_slope_accel", "trend",
        "后半段slope−前半段slope（加速/减速）",
        extract_return_slope_accel, tier="role_specific", roles=frozenset({"up", "down"}),
        ui_group="path",
    ),
    "close_accel_ratio": _stage(
        "close_accel_ratio", "price",
        "后半段total_return/前半段（>1加速）",
        extract_close_accel_ratio, tier="role_specific", roles=frozenset({"up", "down"}),
        ui_group="path",
    ),
    # ---- L1 下跌专用 ----
    "down_day_ratio": _stage(
        "down_day_ratio", "price", "下跌日占比",
        extract_down_day_ratio, tier="role_specific", roles=frozenset({"down"}),
        ui_group="path",
    ),
    "consecutive_down_days": _stage(
        "consecutive_down_days", "price", "从段首连续下跌天数",
        extract_consecutive_down_days, tier="role_specific", roles=frozenset({"down"}),
        ui_group="path",
        default_target={
            "ideal": 2.0, "tolerance": 1.0, "mode": "one_sided_high", "hard_min": 1.0,
        },
    ),
    "consecutive_down_ratio": _stage(
        "consecutive_down_ratio", "price", "从段首连续下跌占比",
        extract_consecutive_down_ratio, tier="role_specific", roles=frozenset({"down"}),
        ui_group="path",
    ),
    # ---- L2 Relation ----
    "breakout_distance": FeatureSpec(
        "breakout_distance", "relation",
        "(breakout.close_last - platform.high_max) / platform.high_max",
        kind="relation", tier="relation", ui_group="relation",
        extract_relation=relation_breakout_distance,
    ),
    "volume_vs_platform": FeatureSpec(
        "volume_vs_platform", "relation",
        "breakout.avg_volume / platform.avg_volume",
        kind="relation", tier="relation", ui_group="relation",
        extract_relation=relation_volume_vs_platform,
    ),
    "close_vs_platform_mid": FeatureSpec(
        "close_vs_platform_mid", "relation",
        "(breakout.close_last - platform_mid) / platform_mid",
        kind="relation", tier="relation", ui_group="relation",
        extract_relation=relation_close_vs_platform_mid,
    ),
    "break_hold_ratio": FeatureSpec(
        "break_hold_ratio", "relation",
        "突破段收盘站上平台高点的天数占比",
        kind="relation", tier="relation", ui_group="relation",
        extract_relation=relation_break_hold_ratio,
    ),
    "low_vs_prior_high": FeatureSpec(
        "low_vs_prior_high", "relation",
        "回踩段 low_min / 前高 - 1（未跌破前高应 >= 0 附近）",
        kind="relation", tier="relation", ui_group="relation",
        extract_relation=relation_low_vs_prior_high,
    ),
    "breakout_on_last_day": FeatureSpec(
        "breakout_on_last_day", "relation",
        "拉升段是否末日才首次收盘站上前高（1=是，0=否）",
        kind="relation", tier="relation", ui_group="relation",
        extract_relation=relation_breakout_on_last_day,
    ),
    # ---- L2 Context ----
    "price_position": FeatureSpec(
        "price_position", "price",
        "close 在 lookback 高低区间位置 [0,1]",
        kind="context", tier="context", ui_group="context",
        extract_context=extract_price_position,
    ),
    "price_percentile": FeatureSpec(
        "price_percentile", "price",
        "close 在 lookback 收盘分位 [0,1]",
        kind="context", tier="context", ui_group="context",
        extract_context=extract_price_percentile,
    ),
    "close_vs_high": FeatureSpec(
        "close_vs_high", "price",
        "close/lookback_high - 1（相对高点回撤）",
        kind="context", tier="context", ui_group="context",
        extract_context=extract_close_vs_high,
    ),
}


def get_feature(name: str) -> FeatureSpec:
    if name not in FEATURE_CATALOG:
        raise KeyError(f"unknown feature: {name}")
    return FEATURE_CATALOG[name]


def list_features() -> list[str]:
    return sorted(FEATURE_CATALOG)


def feature_allows_role(name: str, role: str) -> bool:
    """stage 特征是否允许挂在给定角色上。"""
    spec = FEATURE_CATALOG.get(name)
    if spec is None or spec.kind != "stage":
        return False
    if spec.tier == "universal":
        return True
    roles = spec.roles
    if roles is None or "all" in roles:
        return True
    return role in roles


def features_for_role(role: str | None, *, include_all_when_no_role: bool = True) -> list[str]:
    """引导模式可见的 stage 特征名列表。"""
    out: list[str] = []
    for name, spec in FEATURE_CATALOG.items():
        if spec.kind != "stage":
            continue
        if role is None:
            if include_all_when_no_role:
                out.append(name)
            continue
        if feature_allows_role(name, role):
            out.append(name)
    return sorted(out)


def feature_label_zh(name: str, description: str = "") -> str:
    return FEATURE_LABELS_ZH.get(name) or description or name


def feature_public_dict(spec: FeatureSpec) -> dict[str, Any]:
    roles_out: list[str] | None
    if spec.roles is None:
        roles_out = None
    else:
        roles_out = sorted(spec.roles)
    return {
        "name": spec.name,
        "label": feature_label_zh(spec.name, spec.description),
        "category": spec.category,
        "kind": spec.kind,
        "description": spec.description,
        "tier": spec.tier,
        "roles": roles_out,
        "ui_group": spec.ui_group,
        "default_target": spec.default_target,
    }
