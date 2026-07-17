from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import select

from quant_system.config.settings import get_settings
from quant_system.data.repository import Repositories
from quant_system.data_quality.checker import get_blacklist_for_selector
from quant_system.database.models import DailyKline, StockBasic
from quant_system.infra.board import filter_codes


def build_pattern_context(
    repos: Repositories,
    trade_date: date,
    *,
    codes: list[str] | None = None,
    lookback_calendar_days: int | None = None,
    max_bars: int = 80,
) -> dict[str, Any]:
    """构建扫描上下文：按 code 提供 OHLCV 序列 + 元数据。

    max_bars: 每只股票保留的最近交易日根数（由 Definition.required_history_bars 驱动）。
    lookback_calendar_days: 查询起始自然日；None 时按 max_bars 估算（含节假日冗余）。
    """
    session = repos.kline._session  # type: ignore[attr-defined]
    if lookback_calendar_days is None:
        # 交易日 → 自然日：约 *1.7，再留 buffer
        lookback_calendar_days = max(120, int(max_bars * 1.7) + 40)

    # 宇宙：当日有 K 线的股票
    stmt_codes = select(DailyKline.code).where(DailyKline.trade_date == trade_date).distinct()
    available = [str(c) for c in session.scalars(stmt_codes).all()]
    allowed = filter_codes(available)
    if codes is not None:
        wanted = set(codes)
        allowed = [c for c in allowed if c in wanted]

    blacklist = get_blacklist_for_selector(trade_date, repos)
    if blacklist:
        allowed = [c for c in allowed if c not in blacklist]
    if not allowed:
        return {
            "trade_date": trade_date,
            "kline_by_code": {},
            "stock_meta": {},
            "amount_by_code": {},
            "universe_size": 0,
            "feature_version": get_settings().feature.version,
            "market_median_return": 0.0,
            "max_bars": max_bars,
            "lookback_calendar_days": lookback_calendar_days,
        }

    start = trade_date - timedelta(days=lookback_calendar_days)
    stmt = (
        select(
            DailyKline.code,
            DailyKline.trade_date,
            DailyKline.open,
            DailyKline.high,
            DailyKline.low,
            DailyKline.close,
            DailyKline.volume,
            DailyKline.amount,
            DailyKline.pct_change,
        )
        .where(DailyKline.code.in_(allowed))
        .where(DailyKline.trade_date >= start)
        .where(DailyKline.trade_date <= trade_date)
        .order_by(DailyKline.code, DailyKline.trade_date)
    )
    rows = session.execute(stmt).all()
    hist = pd.DataFrame(
        rows,
        columns=["code", "trade_date", "open", "high", "low", "close", "volume", "amount", "pct_change"],
    )
    kline_by_code: dict[str, pd.DataFrame] = {}
    amount_by_code: dict[str, float] = {}
    returns: list[float] = []

    if not hist.empty:
        for col in ("open", "high", "low", "close", "volume", "amount", "pct_change"):
            hist[col] = pd.to_numeric(hist[col], errors="coerce")
        # 腾讯 amount ≈ 手*均价，换算人民币
        hist["amount"] = hist["amount"] * 100.0

        for code, sub in hist.groupby("code", sort=False):
            sub = sub.sort_values("trade_date").tail(max_bars).reset_index(drop=True)
            kline_by_code[str(code)] = sub[["trade_date", "open", "high", "low", "close", "volume", "amount"]]
            last = sub.iloc[-1]
            amount_by_code[str(code)] = float(last["amount"] or 0.0)
            # pct_change 库内多为百分数，这里仅用于市场中位数展示，转成小数
            pc = last.get("pct_change")
            if pc is not None and not pd.isna(pc):
                returns.append(float(pc) / 100.0)

    meta = _load_stock_meta(session, list(kline_by_code.keys()))
    # 剔除 ST（约束层还会再查，这里先收窄宇宙）
    for code, m in list(meta.items()):
        if m.get("is_st") and code in kline_by_code:
            # 仍保留序列，由 Matcher hard constraint 决定；不在此处删除
            pass

    median_ret = float(pd.Series(returns).median()) if returns else 0.0
    return {
        "trade_date": trade_date,
        "kline_by_code": kline_by_code,
        "stock_meta": meta,
        "amount_by_code": amount_by_code,
        "universe_size": len(kline_by_code),
        "feature_version": get_settings().feature.version,
        "market_median_return": round(median_ret, 6),
        "max_bars": max_bars,
        "lookback_calendar_days": lookback_calendar_days,
    }


def _load_stock_meta(session: Any, codes: list[str]) -> dict[str, dict[str, Any]]:
    if not codes:
        return {}
    stmt = select(StockBasic.code, StockBasic.name, StockBasic.is_st, StockBasic.list_date).where(
        StockBasic.code.in_(codes)
    )
    out: dict[str, dict[str, Any]] = {}
    for code, name, is_st, list_date in session.execute(stmt).all():
        out[str(code)] = {"name": name, "is_st": bool(is_st), "list_date": list_date}
    return out


def _to_python_scalar(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value
