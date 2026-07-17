from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

import numpy as np
import pandas as pd

from quant_system.patterns.result import FeatureValue

FeatureCategory = Literal[
    "price", "volume", "volatility", "trend", "candle", "relation", "atom",
]

StageAtoms = dict[str, float | None]
StageFrames = dict[str, pd.DataFrame]


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    category: FeatureCategory
    description: str
    kind: Literal["stage", "relation", "context", "atom"] = "stage"
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


FEATURE_CATALOG: dict[str, FeatureSpec] = {
    # 长/通用
    "amplitude": FeatureSpec("amplitude", "volatility", "切片 (high_max-low_min)/low_min", kind="stage", extract_stage=extract_amplitude),
    "close_vs_window_high": FeatureSpec(
        "close_vs_window_high", "price",
        "close_last/段内high_max - 1（相对窗口高点回撤）",
        kind="stage", extract_stage=extract_close_vs_window_high,
    ),
    "peak_day": FeatureSpec(
        "peak_day", "trend",
        "段内最高价位置 [0,1]，0=段首 1=段尾",
        kind="stage", extract_stage=extract_peak_day,
    ),
    "total_return": FeatureSpec(
        "total_return", "price",
        "多日: close_last/close_first-1；单日: close/前收-1",
        kind="stage", extract_stage=extract_total_return,
    ),
    "slope": FeatureSpec(
        "slope", "trend",
        "close~t 最小二乘拟合斜率/均价（非首尾相连）",
        kind="stage", extract_stage=extract_slope,
    ),
    "linearity": FeatureSpec(
        "linearity", "trend",
        "close~t 直线拟合 R²，越接近1越像直线",
        kind="stage", extract_stage=extract_linearity,
    ),
    "volatility": FeatureSpec("volatility", "volatility", "日收益标准差", kind="stage", extract_stage=extract_volatility),
    "volume_shrink_ratio": FeatureSpec("volume_shrink_ratio", "volume", "后半段均量/前半段均量", kind="stage", extract_stage=extract_volume_shrink_ratio),
    "bull_ratio": FeatureSpec("bull_ratio", "candle", "阳线占比", kind="stage", extract_stage=extract_bull_ratio),
    "body_ratio": FeatureSpec("body_ratio", "candle", "实体/振幅均值", kind="stage", extract_stage=extract_body_ratio),
    "avg_volume": FeatureSpec("avg_volume", "volume", "均量", kind="stage", extract_stage=extract_avg_volume),
    # 短阶段价格路径
    "gap_open": FeatureSpec(
        "gap_open", "price",
        "段首 open/前收-1（跳高开为正）",
        kind="stage", extract_stage=extract_gap_open,
    ),
    "return_first": FeatureSpec("return_first", "price", "首日 (close/open-1)", kind="stage", extract_stage=extract_return_first),
    "return_last": FeatureSpec("return_last", "price", "尾日 (close/open-1)", kind="stage", extract_stage=extract_return_last),
    "return_acceleration": FeatureSpec("return_acceleration", "price", "尾日涨幅-首日涨幅", kind="stage", extract_stage=extract_return_acceleration),
    "up_day_ratio": FeatureSpec("up_day_ratio", "price", "上涨日占比", kind="stage", extract_stage=extract_up_day_ratio),
    "consecutive_up_ratio": FeatureSpec("consecutive_up_ratio", "price", "从段首连续上涨占比", kind="stage", extract_stage=extract_consecutive_up_ratio),
    "stall_score": FeatureSpec("stall_score", "price", "滞涨分（首强尾弱）", kind="stage", extract_stage=extract_stall_score),
    "close_strength": FeatureSpec("close_strength", "candle", "收盘在振幅中的位置", kind="stage", extract_stage=extract_close_strength),
    # 短阶段量能路径
    "volume_up_ratio": FeatureSpec("volume_up_ratio", "volume", "放量日占比", kind="stage", extract_stage=extract_volume_up_ratio),
    "consecutive_volume_up_ratio": FeatureSpec("consecutive_volume_up_ratio", "volume", "从段首连续放量占比", kind="stage", extract_stage=extract_consecutive_volume_up_ratio),
    "volume_acceleration": FeatureSpec("volume_acceleration", "volume", "尾日量/首日量", kind="stage", extract_stage=extract_volume_acceleration),
    "volume_last_vs_avg": FeatureSpec("volume_last_vs_avg", "volume", "尾日量/段内均量", kind="stage", extract_stage=extract_volume_last_vs_avg),
    "volume_climax_day": FeatureSpec("volume_climax_day", "volume", "最大量位置 0~1", kind="stage", extract_stage=extract_volume_climax_day),
    # K 线质量
    "upper_shadow_ratio": FeatureSpec("upper_shadow_ratio", "candle", "上影占比", kind="stage", extract_stage=extract_upper_shadow_ratio),
    "lower_shadow_ratio": FeatureSpec("lower_shadow_ratio", "candle", "下影占比", kind="stage", extract_stage=extract_lower_shadow_ratio),
    # Relation
    "breakout_distance": FeatureSpec(
        "breakout_distance", "relation",
        "(breakout.close_last - platform.high_max) / platform.high_max",
        kind="relation", extract_relation=relation_breakout_distance,
    ),
    "volume_vs_platform": FeatureSpec(
        "volume_vs_platform", "relation",
        "breakout.avg_volume / platform.avg_volume",
        kind="relation", extract_relation=relation_volume_vs_platform,
    ),
    "close_vs_platform_mid": FeatureSpec(
        "close_vs_platform_mid", "relation",
        "(breakout.close_last - platform_mid) / platform_mid",
        kind="relation", extract_relation=relation_close_vs_platform_mid,
    ),
    "break_hold_ratio": FeatureSpec(
        "break_hold_ratio", "relation",
        "突破段收盘站上平台高点的天数占比",
        kind="relation", extract_relation=relation_break_hold_ratio,
    ),
    # Context（股票级价位，由 ContextSpec.lookback_bars 决定历史范围）
    "price_position": FeatureSpec(
        "price_position", "price",
        "close 在 lookback 高低区间位置 [0,1]",
        kind="context", extract_context=extract_price_position,
    ),
    "price_percentile": FeatureSpec(
        "price_percentile", "price",
        "close 在 lookback 收盘分位 [0,1]",
        kind="context", extract_context=extract_price_percentile,
    ),
    "close_vs_high": FeatureSpec(
        "close_vs_high", "price",
        "close/lookback_high - 1（相对高点回撤）",
        kind="context", extract_context=extract_close_vs_high,
    ),
}


def get_feature(name: str) -> FeatureSpec:
    if name not in FEATURE_CATALOG:
        raise KeyError(f"unknown feature: {name}")
    return FEATURE_CATALOG[name]


def list_features() -> list[str]:
    return sorted(FEATURE_CATALOG)
