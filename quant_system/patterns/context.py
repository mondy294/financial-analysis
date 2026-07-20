from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from math import isfinite
from typing import Any

import pandas as pd
from sqlalchemy import func, select

from quant_system.config.settings import get_settings
from quant_system.data.repository import Repositories
from quant_system.data_quality.checker import get_blacklist_for_selector
from quant_system.database.models import DailyKline, DailyValuation, StockBasic
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
            DailyKline.adj_factor,
        )
        .where(DailyKline.code.in_(allowed))
        .where(DailyKline.trade_date >= start)
        .where(DailyKline.trade_date <= trade_date)
        .order_by(DailyKline.code, DailyKline.trade_date)
    )
    rows = session.execute(stmt).all()
    hist = pd.DataFrame(
        rows,
        columns=[
            "code", "trade_date", "open", "high", "low", "close",
            "volume", "amount", "pct_change", "adj_factor",
        ],
    )
    kline_by_code: dict[str, pd.DataFrame] = {}
    amount_by_code: dict[str, float] = {}
    returns: list[float] = []

    if not hist.empty:
        for col in ("open", "high", "low", "close", "volume", "amount", "pct_change", "adj_factor"):
            hist[col] = pd.to_numeric(hist[col], errors="coerce")
        # 腾讯 amount ≈ 手*均价，换算人民币
        hist["amount"] = hist["amount"] * 100.0

        for code, sub in hist.groupby("code", sort=False):
            sub = sub.sort_values("trade_date").tail(max_bars).reset_index(drop=True)
            # Pattern 几何特征必须用复权价：未复权在除权日会造出假斜率/假振幅。
            # 前复权（对齐 Web K 线默认 qfq）：以窗口内最新 adj_factor 归一。
            latest_af = float(sub["adj_factor"].iloc[-1]) if len(sub) else 1.0
            if latest_af and isfinite(latest_af) and latest_af != 0:
                ratio = sub["adj_factor"] / latest_af
                for c in ("open", "high", "low", "close"):
                    sub[c] = sub[c] * ratio
            kline_by_code[str(code)] = sub[["trade_date", "open", "high", "low", "close", "volume", "amount"]]
            last = sub.iloc[-1]
            amount_by_code[str(code)] = float(last["amount"] or 0.0)
            # pct_change 库内多为百分数，这里仅用于市场中位数展示，转成小数
            pc = last.get("pct_change")
            if pc is not None and not pd.isna(pc):
                returns.append(float(pc) / 100.0)

    codes = list(kline_by_code.keys())
    meta = _load_stock_meta(session, codes, as_of=trade_date)
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


def _load_stock_meta(
    session: Any,
    codes: list[str],
    *,
    as_of: date | None = None,
) -> dict[str, dict[str, Any]]:
    if not codes:
        return {}
    stmt = select(
        StockBasic.code,
        StockBasic.name,
        StockBasic.is_st,
        StockBasic.list_date,
        StockBasic.market_cap,
        StockBasic.industry_name,
    ).where(StockBasic.code.in_(codes))
    out: dict[str, dict[str, Any]] = {}
    for code, name, is_st, list_date, market_cap, industry_name in session.execute(stmt).all():
        out[str(code)] = {
            "name": name,
            "is_st": bool(is_st),
            "list_date": list_date,
            # 单位：亿元；优先用 daily_valuation 覆盖（见下）
            "market_cap": float(market_cap) if market_cap is not None else None,
            "industry_name": industry_name,
        }

    # stock_basic.market_cap 经常为空；日频估值表才是可靠来源（亿元）
    val_date = as_of
    if val_date is None:
        val_date = session.scalar(select(func.max(DailyValuation.trade_date)))
    if val_date is not None:
        # 若 as_of 当天没有估值，回退到 <= as_of 的最近一日
        day = session.scalar(
            select(func.max(DailyValuation.trade_date)).where(
                DailyValuation.trade_date <= val_date
            )
        )
        if day is not None:
            vstmt = select(DailyValuation.code, DailyValuation.market_cap).where(
                DailyValuation.trade_date == day,
                DailyValuation.code.in_(codes),
                DailyValuation.market_cap.is_not(None),
            )
            for code, market_cap in session.execute(vstmt).all():
                key = str(code)
                if key in out:
                    out[key]["market_cap"] = float(market_cap)
    return out


def _to_python_scalar(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value
