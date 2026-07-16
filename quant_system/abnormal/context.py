"""构建 Pattern 扫描用的当日宽表（feature + kline + 派生字段）。"""
from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import select

from quant_system.config.settings import get_settings
from quant_system.database.models import DailyKline, StockBasic
from quant_system.infra.board import filter_codes
from quant_system.indicators.technical import (
    amplitude,
    break_new_high,
    ma,
    ma_cross_up,
    ma_position,
    prior_high,
    range_position,
)
from quant_system.strategy.risk_filter import _is_one_word_limit

if TYPE_CHECKING:
    from quant_system.data.repository import Repositories


def _to_float(x) -> float | None:
    if x is None:
        return None
    try:
        f = float(x)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _features_to_df(rows) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    recs = []
    for r in rows:
        recs.append({
            "code": r.code,
            "return_1d": _to_float(r.return_1d),
            "return_5d": _to_float(r.return_5d),
            "ma5": _to_float(r.ma5), "ma10": _to_float(r.ma10),
            "ma20": _to_float(r.ma20), "ma60": _to_float(r.ma60),
            "ma_bull_arrange": bool(r.ma_bull_arrange) if r.ma_bull_arrange is not None else False,
            "macd_hist": _to_float(r.macd_hist),
            "macd_golden_cross": bool(r.macd_golden_cross) if r.macd_golden_cross is not None else False,
            "atr_14": _to_float(r.atr_14),
            "volume_ratio": _to_float(r.volume_ratio),
            "break_high_20d": bool(r.break_high_20d) if r.break_high_20d is not None else False,
            "break_high_60d": bool(getattr(r, "break_high_60d", None) or False),
            "break_high_250d": bool(getattr(r, "break_high_250d", None) or False),
            "amplitude_20d": _to_float(getattr(r, "amplitude_20d", None)),
            "range_pos_250d": _to_float(getattr(r, "range_pos_250d", None)),
            "ma250_bias": _to_float(getattr(r, "ma250_bias", None)),
            "ma5_cross_ma10": bool(getattr(r, "ma5_cross_ma10", None) or False),
            "break_distance_20d": _to_float(getattr(r, "break_distance_20d", None)),
            "break_distance_60d": _to_float(getattr(r, "break_distance_60d", None)),
            "break_distance_250d": _to_float(getattr(r, "break_distance_250d", None)),
            "feature_version": r.feature_version,
        })
    return pd.DataFrame(recs)


def _load_kline_today(session, trade_date: date, codes: list[str]) -> pd.DataFrame:
    if not codes:
        return pd.DataFrame()
    rows = []
    for i in range(0, len(codes), 500):
        chunk = codes[i:i + 500]
        stmt = select(
            DailyKline.code, DailyKline.open, DailyKline.high,
            DailyKline.low, DailyKline.close, DailyKline.amount,
            DailyKline.pct_change, DailyKline.volume,
        ).where(DailyKline.trade_date == trade_date, DailyKline.code.in_(chunk))
        rows.extend(session.execute(stmt).all())
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows, columns=[
        "code", "open", "high", "low", "close", "amount", "pct_change", "volume",
    ])


def _load_hist(session, codes: list[str], start: date, end: date) -> pd.DataFrame:
    if not codes:
        return pd.DataFrame()
    rows = []
    for i in range(0, len(codes), 300):
        chunk = codes[i:i + 300]
        stmt = select(
            DailyKline.code, DailyKline.trade_date,
            DailyKline.high, DailyKline.low, DailyKline.close, DailyKline.volume,
        ).where(
            DailyKline.code.in_(chunk),
            DailyKline.trade_date >= start,
            DailyKline.trade_date <= end,
        )
        rows.extend(session.execute(stmt).all())
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows, columns=["code", "trade_date", "high", "low", "close", "volume"])


def _derive_from_hist(hist: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """从历史 K 线派生 Pattern 所需字段（补齐 feature 缺失）。"""
    if hist.empty:
        return pd.DataFrame()
    hist = hist[hist["trade_date"] <= as_of].sort_values(["code", "trade_date"])
    out_rows = []
    for code, g in hist.groupby("code", sort=False):
        if g.empty or g.iloc[-1]["trade_date"] != as_of:
            continue
        high = g["high"].astype(float)
        low = g["low"].astype(float)
        close = g["close"].astype(float)
        vol = g["volume"].astype(float)
        # 量比序列用于连续放量
        vol_ma = vol.rolling(20, min_periods=20).mean()
        vr = vol / vol_ma.replace(0, np.nan)
        streak = 0
        for x in reversed(vr.fillna(0).tolist()):
            if x >= 2.0:
                streak += 1
            else:
                break

        def _last(series):
            v = series.iloc[-1] if len(series) else np.nan
            return None if v != v else float(v)

        _, br20 = break_new_high(close, high, 20)
        _, br60 = break_new_high(close, high, 60)
        _, br250 = break_new_high(close, high, 250)
        ph20 = prior_high(high, 20)
        ph60 = prior_high(high, 60)
        ph250 = prior_high(high, 250)
        # ATR14 近似
        prev_c = close.shift(1)
        tr = pd.concat([
            high - low, (high - prev_c).abs(), (low - prev_c).abs(),
        ], axis=1).max(axis=1)
        atr14 = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        atr_last = _last(atr14) or 1e-6

        ma5 = ma(close, 5)
        ma10 = ma(close, 10)
        ma250_s = ma(close, 250)

        out_rows.append({
            "code": code,
            "amplitude_20d": _last(amplitude(high, low, 20)),
            "break_high_20d": bool(br20.iloc[-1]),
            "break_high_60d": bool(br60.iloc[-1]),
            "break_high_250d": bool(br250.iloc[-1]),
            "break_distance_20d": (float(close.iloc[-1]) - (_last(ph20) or float(close.iloc[-1]))) / atr_last,
            "break_distance_60d": (float(close.iloc[-1]) - (_last(ph60) or float(close.iloc[-1]))) / atr_last,
            "break_distance_250d": (float(close.iloc[-1]) - (_last(ph250) or float(close.iloc[-1]))) / atr_last,
            "range_pos_250d": _last(range_position(close, high, low, 250)),
            "ma250_bias": _last(ma_position(close, ma250_s)),
            "ma5_cross_ma10": bool(ma_cross_up(ma5, ma10).iloc[-1]),
            "vol_streak": streak,
            "volume_ratio_hist": _last(vr),
        })
    return pd.DataFrame(out_rows)


def build_scan_frame(
    repos: "Repositories",
    trade_date: date,
    *,
    use_hist_enrich: bool = True,
) -> pd.DataFrame:
    """返回可供 Pattern 过滤的 DataFrame。"""
    settings = get_settings()
    session = repos.feature._session  # type: ignore[attr-defined]

    features = repos.feature.read_features_on(trade_date)
    df = _features_to_df(features)
    if df.empty:
        logger.warning("abnormal: {} 无 daily_feature", trade_date)
        return df

    # 板块过滤
    allowed = set(filter_codes(df["code"].tolist(), settings.board_filter))
    df = df[df["code"].isin(allowed)].reset_index(drop=True)

    codes = df["code"].tolist()
    today = _load_kline_today(session, trade_date, codes)
    if not today.empty:
        df = df.merge(today, on="code", how="left")
        # 腾讯源 volume 实为「手」，amount≈手×均价，比真实成交额（元）小约 100 倍
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce") * 100.0
    else:
        for c in ("open", "high", "low", "close", "amount", "pct_change", "volume"):
            df[c] = np.nan

    # ST
    st_map = {}
    for i in range(0, len(codes), 500):
        chunk = codes[i:i + 500]
        for code, is_st in session.execute(
            select(StockBasic.code, StockBasic.is_st).where(StockBasic.code.in_(chunk))
        ).all():
            st_map[code] = bool(is_st)
    df["is_st"] = df["code"].map(st_map).fillna(False)

    # 阳线 / 一字板
    cfg = settings.hard_filter
    yang, one_word = [], []
    for _, row in df.iterrows():
        o, h, l, c = row.get("open"), row.get("high"), row.get("low"), row.get("close")
        yang.append(
            o is not None and c is not None
            and float(c) > float(o)
        )
        one_word.append(_is_one_word_limit(
            _to_float(o), _to_float(h), _to_float(l), _to_float(c),
            _to_float(row.get("pct_change")),
            str(row["code"]), cfg,
        ))
    df["is_yang"] = yang
    df["is_one_word"] = one_word

    # 相对强度
    med = float(pd.to_numeric(df["return_1d"], errors="coerce").median())
    if med != med:
        med = 0.0
    df["market_median_return"] = med
    df["relative_return"] = pd.to_numeric(df["return_1d"], errors="coerce") - med

    # 用历史 K 线派生振幅/多级突破/连续放量（不依赖 feature 是否已重建）
    if use_hist_enrich:
        start = trade_date - timedelta(days=420)
        logger.info("abnormal: 历史 K 线派生字段 {} 只，{} ~ {}", len(codes), start, trade_date)
        hist = _load_hist(session, codes, start, trade_date)
        derived = _derive_from_hist(hist, trade_date)
        if not derived.empty:
            dmap = derived.set_index("code")
            # Pattern 关键字段以 hist 派生为准（与突破/振幅口径一致）
            for col in (
                "amplitude_20d", "break_high_20d", "break_high_60d", "break_high_250d",
                "break_distance_20d", "break_distance_60d", "break_distance_250d",
                "range_pos_250d", "ma250_bias", "ma5_cross_ma10", "vol_streak",
            ):
                if col in dmap.columns:
                    df[col] = df["code"].map(dmap[col])
            if "volume_ratio_hist" in dmap.columns:
                miss_vr = df["volume_ratio"].isna()
                df.loc[miss_vr, "volume_ratio"] = df.loc[miss_vr, "code"].map(dmap["volume_ratio_hist"])
        else:
            df["vol_streak"] = 1
    else:
        df["vol_streak"] = 1

    logger.info(
        "abnormal scan frame: {} 只, median_ret={:.2f}%, yang={}, break20={}",
        len(df), med, int(df["is_yang"].sum()), int(df["break_high_20d"].fillna(False).sum()),
    )
    return df
