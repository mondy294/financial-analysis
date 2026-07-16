"""技术指标计算库（纯 numpy/pandas，无第三方指标库依赖）。

约定：
- 输入统一为按 trade_date 升序的 pandas.DataFrame，含列 [open, high, low, close, volume]；
- 输出保持相同 index，指标列 append 到 DataFrame 或返回单列 Series；
- NaN 保留（前 N 期不足会产生 NaN，由调用方决定丢弃或填充）。

**注意：所有指标接受的应该是复权后价格**（策略需要连续的价格序列）。
调用方在传入前用 repository.read_kline(adj="qfq") 拿到前复权数据。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ============================================================================
# 均线 / 动量
# ============================================================================

def ma(close: pd.Series, window: int) -> pd.Series:
    """简单移动平均。"""
    return close.rolling(window=window, min_periods=window).mean()


def ema(close: pd.Series, span: int) -> pd.Series:
    """指数移动平均（等价于中国大陆通行 EMA(n)，alpha=2/(n+1)）。"""
    return close.ewm(span=span, adjust=False, min_periods=span).mean()


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD。返回 (dif, dea, hist)。

    dif  = EMA(fast) - EMA(slow)
    dea  = EMA(dif, signal)
    hist = (dif - dea) * 2   （国内习惯，值域更贴近日常展示）
    """
    ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = (dif - dea) * 2
    return dif, dea, hist


def macd_golden_cross(dif: pd.Series, dea: pd.Series) -> pd.Series:
    """MACD 金叉：dif 上穿 dea。返回 bool Series（当日金叉 = True）。"""
    prev = (dif.shift(1) <= dea.shift(1))
    curr = (dif > dea)
    return (prev & curr).fillna(False)


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """RSI（Wilder 平滑，与主流交易软件一致）。"""
    diff = close.diff()
    gain = diff.clip(lower=0)
    loss = -diff.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    return result


def kdj(
    high: pd.Series, low: pd.Series, close: pd.Series,
    n: int = 9, m1: int = 3, m2: int = 3,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """KDJ（国内通行算法：SMA 平滑）。返回 (K, D, J)。"""
    ll = low.rolling(window=n, min_periods=n).min()
    hh = high.rolling(window=n, min_periods=n).max()
    denom = (hh - ll).replace(0, np.nan)
    rsv = (close - ll) / denom * 100

    # 中国大陆的 KDJ 用的是等价于 EMA(2n-1) 的递推：K[t] = (2*K[t-1] + RSV[t]) / 3
    k = rsv.ewm(alpha=1 / m1, adjust=False, min_periods=n).mean()
    d = k.ewm(alpha=1 / m2, adjust=False, min_periods=n).mean()
    j = 3 * k - 2 * d
    return k, d, j


# ============================================================================
# 波动 / 通道
# ============================================================================

def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """True Range = max(H-L, |H-PC|, |L-PC|)"""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def atr(
    high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14,
) -> pd.Series:
    """ATR = EMA(True Range, window)（Wilder 平滑）。"""
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def bollinger(
    close: pd.Series, window: int = 20, std_mult: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """布林带。返回 (upper, mid, lower, width)。width = (upper-lower)/mid。"""
    mid = close.rolling(window=window, min_periods=window).mean()
    std = close.rolling(window=window, min_periods=window).std(ddof=0)
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    width = (upper - lower) / mid
    return upper, mid, lower, width


# ============================================================================
# 量能 / 突破
# ============================================================================

def volume_ratio(volume: pd.Series, window: int = 20) -> pd.Series:
    """量比：当日成交量 / N 日均量。"""
    vol_ma = volume.rolling(window=window, min_periods=window).mean()
    return volume / vol_ma.replace(0, np.nan)


def rolling_high(high: pd.Series, window: int) -> pd.Series:
    """N 日最高价（含当日）。"""
    return high.rolling(window=window, min_periods=window).max()


def break_new_high(
    close: pd.Series, high: pd.Series, window: int = 20,
) -> tuple[pd.Series, pd.Series]:
    """N 日新高。返回 (high_n, break_flag)。

    break_flag：当日收盘 > 昨日之前 N-1 日的最高（避免用「今日的高」比较「今日的最高」）
    """
    prior_high = high.shift(1).rolling(window=window - 1, min_periods=window - 1).max()
    high_n = high.rolling(window=window, min_periods=window).max()
    break_flag = (close > prior_high).fillna(False)
    return high_n, break_flag


def prior_high(high: pd.Series, window: int) -> pd.Series:
    """不含当日的近 window 日最高价（突破距离用）。"""
    return high.shift(1).rolling(window=window, min_periods=window).max()


def amplitude(high: pd.Series, low: pd.Series, window: int = 20) -> pd.Series:
    """近 N 日振幅（%）：(max_high - min_low) / min_low * 100。"""
    hh = high.rolling(window=window, min_periods=window).max()
    ll = low.rolling(window=window, min_periods=window).min()
    return (hh - ll) / ll.replace(0, np.nan) * 100


def range_position(close: pd.Series, high: pd.Series, low: pd.Series, window: int = 250) -> pd.Series:
    """区间百分位：(close - low_n) / (high_n - low_n)。"""
    hh = high.rolling(window=window, min_periods=window).max()
    ll = low.rolling(window=window, min_periods=window).min()
    span = (hh - ll).replace(0, np.nan)
    return (close - ll) / span


def ma_cross_up(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """快线上穿慢线（当日）。"""
    prev = fast.shift(1) <= slow.shift(1)
    curr = fast > slow
    return (prev & curr).fillna(False)


# ============================================================================
# 收益 / 均线关系
# ============================================================================

def returns(close: pd.Series, window: int) -> pd.Series:
    """N 日累计收益率（百分比）。"""
    return (close / close.shift(window) - 1) * 100


def ma_position(close: pd.Series, ma_series: pd.Series) -> pd.Series:
    """当前价相对某均线的位置：(close - ma) / ma"""
    return (close - ma_series) / ma_series.replace(0, np.nan)


def bull_arrangement(
    ma_short: pd.Series, ma_mid: pd.Series, ma_long: pd.Series,
) -> pd.Series:
    """多头排列：短 > 中 > 长。返回 bool Series。"""
    return ((ma_short > ma_mid) & (ma_mid > ma_long)).fillna(False)


# ============================================================================
# 综合：一次算全套（给 feature_store 用）
# ============================================================================

def compute_all(
    df: pd.DataFrame,
    ma_windows: list[int] | None = None,
    macd_params: dict | None = None,
    rsi_window: int = 14,
    kdj_params: dict | None = None,
    atr_window: int = 14,
    boll_params: dict | None = None,
    breakout_window: int = 20,
    volume_ma_window: int = 20,
) -> pd.DataFrame:
    """在一份 K 线 DataFrame 上算全部指标并 append 新列。

    输入 df 必须按 trade_date 升序，含列 [trade_date, open, high, low, close, volume]。
    """
    ma_windows = ma_windows or [5, 10, 20, 60]
    macd_params = macd_params or {"fast": 12, "slow": 26, "signal": 9}
    kdj_params = kdj_params or {"n": 9, "m1": 3, "m2": 3}
    boll_params = boll_params or {"window": 20, "std": 2.0}

    out = df.copy()
    close = out["close"]
    high = out["high"]
    low = out["low"]
    volume = out["volume"]

    # 均线
    for w in ma_windows:
        out[f"ma{w}"] = ma(close, w)
    # 收益
    for w in [1, 5, 20, 60]:
        out[f"return_{w}d"] = returns(close, w)
    # 均线关系
    if "ma20" in out.columns:
        out["ma_position"] = ma_position(close, out["ma20"])
    if all(f"ma{w}" in out.columns for w in [5, 10, 20]):
        out["ma_bull_arrange"] = bull_arrangement(out["ma5"], out["ma10"], out["ma20"])

    # MACD
    dif, dea, hist = macd(close, **macd_params)
    out["macd"] = dif
    out["macd_signal"] = dea
    out["macd_hist"] = hist
    out["macd_golden_cross"] = macd_golden_cross(dif, dea)

    # RSI
    out[f"rsi_{rsi_window}"] = rsi(close, rsi_window)

    # KDJ
    k, d, j = kdj(high, low, close, **kdj_params)
    out["kdj_k"] = k
    out["kdj_d"] = d
    out["kdj_j"] = j

    # ATR
    out[f"atr_{atr_window}"] = atr(high, low, close, atr_window)

    # 布林带
    upper, mid, lower, width = bollinger(
        close, window=int(boll_params["window"]), std_mult=float(boll_params["std"]),
    )
    out["boll_upper"] = upper
    out["boll_mid"] = mid
    out["boll_lower"] = lower
    out["boll_width"] = width

    # 量能
    out["volume_ratio"] = volume_ratio(volume, volume_ma_window)
    out["amount_ma5"] = out["amount"].rolling(5, min_periods=5).mean() if "amount" in out.columns else None
    out["turnover_change"] = (
        out["turnover_rate"] - out["turnover_rate"].shift(1)
        if "turnover_rate" in out.columns else None
    )

    # 突破（多窗口）+ 振幅 / 年线位置
    for w in sorted({breakout_window, 20, 60, 120, 250}):
        high_n, break_flag = break_new_high(close, high, w)
        out[f"high_{w}d"] = high_n
        out[f"break_high_{w}d"] = break_flag
        ph = prior_high(high, w)
        out[f"prior_high_{w}d"] = ph
        atr_col = out.get(f"atr_{atr_window}")
        if atr_col is not None:
            out[f"break_distance_{w}d"] = (close - ph) / atr_col.replace(0, np.nan)

    out["amplitude_20d"] = amplitude(high, low, 20)
    out["low_250d"] = low.rolling(250, min_periods=250).min()
    out["range_pos_250d"] = range_position(close, high, low, 250)
    out["ma250"] = ma(close, 250)
    out["ma250_bias"] = ma_position(close, out["ma250"])
    if "ma5" in out.columns and "ma10" in out.columns:
        out["ma5_cross_ma10"] = ma_cross_up(out["ma5"], out["ma10"])

    return out
