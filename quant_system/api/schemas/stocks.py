from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class StockBriefOut(BaseModel):
    code: str
    name: str
    industry_name: str | None = None
    is_st: bool = False


class StockDetailOut(BaseModel):
    code: str
    name: str
    exchange: str
    industry_code: str | None = None
    industry_name: str | None = None
    list_date: date | None = None
    is_st: bool = False
    market_cap: float | None = None


class KlineBarOut(BaseModel):
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None = None
    pct_change: float | None = None


class FeaturePointOut(BaseModel):
    trade_date: date
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None
    ma60: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    rsi_14: float | None = None
    atr_14: float | None = None
    boll_upper: float | None = None
    boll_mid: float | None = None
    boll_lower: float | None = None
    return_1d: float | None = None
    return_5d: float | None = None
    return_20d: float | None = None
    ma_position: float | None = None
    ma_bull_arrange: bool | None = None


class SnapshotOut(BaseModel):
    code: str
    trade_date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    amount: float | None = None
    pct_change: float | None = None
    features: dict[str, float | bool | None] = {}
