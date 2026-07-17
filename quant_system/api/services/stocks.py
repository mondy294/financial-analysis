from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import or_, select

from quant_system.api.errors import raise_not_found
from quant_system.data.repository import Repositories
from quant_system.database.models import DailyFeature, StockBasic


def _f(v: Any) -> float | None:
    if v is None:
        return None
    return float(v)


def search_stocks(repos: Repositories, q: str, *, limit: int = 20) -> list[dict[str, Any]]:
    q = (q or "").strip()
    if not q:
        return []
    session = repos.stock._session  # type: ignore[attr-defined]
    like = f"%{q}%"
    stmt = (
        select(StockBasic)
        .where(or_(StockBasic.code.ilike(like), StockBasic.name.ilike(like)))
        .order_by(StockBasic.code)
        .limit(limit)
    )
    # SQLite: ilike may fall back; use like for broader compatibility
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        stmt = (
            select(StockBasic)
            .where(or_(StockBasic.code.like(like), StockBasic.name.like(like)))
            .order_by(StockBasic.code)
            .limit(limit)
        )
    rows = session.scalars(stmt).all()
    return [
        {
            "code": r.code,
            "name": r.name,
            "industry_name": r.industry_name,
            "is_st": bool(r.is_st),
        }
        for r in rows
    ]


def get_stock_detail(repos: Repositories, code: str) -> dict[str, Any]:
    stock = repos.stock.get_stock(code.upper())
    if stock is None:
        raise_not_found(f"股票不存在: {code}")
    return {
        "code": stock.code,
        "name": stock.name,
        "exchange": stock.exchange,
        "industry_code": stock.industry_code,
        "industry_name": stock.industry_name,
        "list_date": stock.list_date,
        "is_st": bool(stock.is_st),
        "market_cap": _f(stock.market_cap),
    }


def get_kline(
    repos: Repositories,
    code: str,
    *,
    start: date | None = None,
    end: date | None = None,
    limit: int = 250,
    adj: str = "qfq",
) -> list[dict[str, Any]]:
    code = code.upper()
    end = end or repos.kline.get_latest_trade_date(code) or date.today()
    start = start or (end - timedelta(days=int(limit * 1.8)))
    df = repos.kline.read_kline(code, start, end, adj=adj)
    if df.empty:
        return []
    df = df.tail(limit)
    out: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        out.append(
            {
                "trade_date": row["trade_date"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "amount": float(row["amount"]) if row.get("amount") is not None else None,
                "pct_change": float(row["pct_change"]) if row.get("pct_change") is not None else None,
            }
        )
    return out


def get_features(
    repos: Repositories,
    code: str,
    *,
    start: date | None = None,
    end: date | None = None,
    limit: int = 250,
) -> list[dict[str, Any]]:
    code = code.upper()
    session = repos.feature._session  # type: ignore[attr-defined]
    end = end or repos.kline.get_latest_trade_date(code) or date.today()
    start = start or (end - timedelta(days=int(limit * 1.8)))
    stmt = (
        select(DailyFeature)
        .where(DailyFeature.code == code)
        .where(DailyFeature.trade_date >= start)
        .where(DailyFeature.trade_date <= end)
        .order_by(DailyFeature.trade_date)
    )
    rows = session.scalars(stmt).all()
    rows = rows[-limit:]
    return [
        {
            "trade_date": r.trade_date,
            "ma5": _f(r.ma5),
            "ma10": _f(r.ma10),
            "ma20": _f(r.ma20),
            "ma60": _f(r.ma60),
            "macd": _f(r.macd),
            "macd_signal": _f(r.macd_signal),
            "macd_hist": _f(r.macd_hist),
            "rsi_14": _f(r.rsi_14),
            "atr_14": _f(r.atr_14),
            "boll_upper": _f(r.boll_upper),
            "boll_mid": _f(r.boll_mid),
            "boll_lower": _f(r.boll_lower),
            "return_1d": _f(r.return_1d),
            "return_5d": _f(r.return_5d),
            "return_20d": _f(r.return_20d),
            "ma_position": _f(r.ma_position),
            "ma_bull_arrange": r.ma_bull_arrange,
        }
        for r in rows
    ]


def get_snapshot(repos: Repositories, code: str, trade_date: date | None = None) -> dict[str, Any]:
    code = code.upper()
    trade_date = trade_date or repos.kline.get_latest_trade_date(code)
    if trade_date is None:
        raise_not_found(f"无交易日数据: {code}")
    bars = get_kline(repos, code, end=trade_date, limit=1, adj="none")
    feats = get_features(repos, code, end=trade_date, limit=1)
    bar = bars[-1] if bars else {}
    feat = feats[-1] if feats else {}
    feature_map = {k: v for k, v in feat.items() if k != "trade_date"}
    return {
        "code": code,
        "trade_date": trade_date,
        "open": bar.get("open"),
        "high": bar.get("high"),
        "low": bar.get("low"),
        "close": bar.get("close"),
        "volume": bar.get("volume"),
        "amount": bar.get("amount"),
        "pct_change": bar.get("pct_change"),
        "features": feature_map,
    }
