from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select

from quant_system.api.errors import raise_not_found
from quant_system.data.repository import Repositories
from quant_system.database.models import DailyFeature, DailyValuation, StockBasic


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _as_date(v: Any) -> date | None:
    if v is None:
        return None
    # pandas.NaT / 无效时间
    if type(v).__name__ == "NaTType":
        return None
    s = str(v).strip()
    if not s or s in ("NaT", "None", "nan", "NaN", "<NA>"):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


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


def _valuation_fields(
    repos: Repositories, code: str, as_of: date | None = None
) -> dict[str, Any]:
    """日频估值；市值单位亿元。stock_basic.market_cap 作兜底。"""
    val = repos.valuation.get_latest_valuation(code, as_of=as_of)
    stock = repos.stock.get_stock(code)
    mcap = _f(val.market_cap) if val is not None else None
    if mcap is None and stock is not None:
        mcap = _f(stock.market_cap)
    return {
        "pe_ttm": _f(val.pe_ttm) if val is not None else None,
        "pe_static": _f(val.pe_static) if val is not None else None,
        "pb": _f(val.pb) if val is not None else None,
        "ps_ttm": _f(val.ps_ttm) if val is not None else None,
        "market_cap": mcap,
        "float_market_cap": _f(val.float_market_cap) if val is not None else None,
        "valuation_date": val.trade_date if val is not None else None,
    }


def attach_latest_market_caps(
    repos: Repositories, items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """批量为披露条目挂最新总市值（亿元）：daily_valuation 优先，stock_basic 兜底。"""
    from sqlalchemy import func

    if not items:
        return items
    for item in items:
        item.setdefault("market_cap", None)

    codes = sorted({str(x.get("code") or "").upper() for x in items if x.get("code")})
    if not codes:
        return items

    session = repos.stock._session  # type: ignore[attr-defined]
    mcap_by_code: dict[str, float] = {}

    basic_stmt = select(StockBasic.code, StockBasic.market_cap).where(
        StockBasic.code.in_(codes),
        StockBasic.market_cap.is_not(None),
    )
    for code, mcap in session.execute(basic_stmt).all():
        f = _f(mcap)
        if f is not None:
            mcap_by_code[str(code).upper()] = f

    as_of = session.scalar(select(func.max(DailyValuation.trade_date)))
    if as_of is not None:
        vstmt = select(DailyValuation.code, DailyValuation.market_cap).where(
            DailyValuation.trade_date == as_of,
            DailyValuation.code.in_(codes),
            DailyValuation.market_cap.is_not(None),
        )
        for code, mcap in session.execute(vstmt).all():
            f = _f(mcap)
            if f is not None:
                mcap_by_code[str(code).upper()] = f

    for item in items:
        code = str(item.get("code") or "").upper()
        item["market_cap"] = mcap_by_code.get(code)
    return items


def get_stock_detail(repos: Repositories, code: str) -> dict[str, Any]:
    stock = repos.stock.get_stock(code.upper())
    if stock is None:
        raise_not_found(f"股票不存在: {code}")
    val = _valuation_fields(repos, stock.code)
    return {
        "code": stock.code,
        "name": stock.name,
        "exchange": stock.exchange,
        "industry_code": stock.industry_code,
        "industry_name": stock.industry_name,
        "list_date": stock.list_date,
        "is_st": bool(stock.is_st),
        **val,
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
    val = _valuation_fields(repos, code, as_of=trade_date)
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
        **val,
    }


def get_financial_highlights(
    repos: Repositories, code: str, *, years: int = 5
) -> dict[str, Any]:
    """近 N 年年报主要财务指标 + 同期中报/一季报/三季报。"""
    from quant_system.data.provider_factory import get_financial_provider

    code = code.upper()
    stock = repos.stock.get_stock(code)
    if stock is None:
        raise_not_found(f"股票不存在: {code}")
    years = max(1, min(int(years), 20))
    provider = get_financial_provider()
    df = provider.fetch_financial_highlights(code, years=years)
    points: list[dict[str, Any]] = []
    if df is not None and not df.empty:
        for _, row in df.iterrows():
            notice = _as_date(row.get("notice_date"))
            as_of = notice or _as_date(row.get("report_period"))
            val = _valuation_fields(repos, code, as_of=as_of) if as_of else {}
            points.append(
                {
                    "year": int(row["year"]),
                    "report_period": row["report_period"],
                    "report_name": str(row.get("report_name") or ""),
                    "notice_date": notice,
                    "is_annual": bool(row.get("is_annual")),
                    "revenue": _f(row.get("revenue")),
                    "revenue_yoy": _f(row.get("revenue_yoy")),
                    "parent_net_profit": _f(row.get("parent_net_profit")),
                    "parent_net_profit_yoy": _f(row.get("parent_net_profit_yoy")),
                    "ded_net_profit": _f(row.get("ded_net_profit")),
                    "ded_net_profit_yoy": _f(row.get("ded_net_profit_yoy")),
                    "roe": _f(row.get("roe")),
                    "pe_ttm": val.get("pe_ttm"),
                    "pe_static": val.get("pe_static"),
                    "valuation_date": val.get("valuation_date"),
                }
            )
    guidance_raw = provider.fetch_earnings_guidance(code) or []
    guidance: list[dict[str, Any]] = []
    for g in guidance_raw:
        notice = _as_date(g.get("notice_date"))
        as_of = notice or _as_date(g.get("report_period"))
        val = _valuation_fields(repos, code, as_of=as_of) if as_of else {}
        guidance.append(
            {
                "kind": g.get("kind") or "forecast",
                "report_period": g.get("report_period"),
                "report_name": g.get("report_name") or "",
                "notice_date": notice or g.get("notice_date"),
                "metrics": list(g.get("metrics") or []),
                "revenue": _f(g.get("revenue")),
                "revenue_yoy": _f(g.get("revenue_yoy")),
                "parent_net_profit": _f(g.get("parent_net_profit")),
                "parent_net_profit_yoy": _f(g.get("parent_net_profit_yoy")),
                "roe": _f(g.get("roe")),
                "pe_ttm": val.get("pe_ttm"),
                "pe_static": val.get("pe_static"),
                "valuation_date": val.get("valuation_date"),
            }
        )
    has_midyear = any(
        (not p["is_annual"])
        and str(p.get("report_period") or "").endswith("-06-30")
        for p in points
    )
    has_quarter = any(
        (not p["is_annual"])
        and (
            str(p.get("report_period") or "").endswith("-03-31")
            or str(p.get("report_period") or "").endswith("-09-30")
        )
        for p in points
    )
    notes: list[str] = []
    notes.append("正式序列为近五年年报 + 同期中报/一季报/三季报。")
    notes.append("PE 为报告公告日（或之前最近交易日）的 PE(TTM)。")
    if not has_midyear and not has_quarter:
        notes.append("该股窗口内暂无中报/季报数据。")
    elif not has_midyear:
        notes.append("该股窗口内暂无中报数据。")
    elif not has_quarter:
        notes.append("该股窗口内暂无一季报/三季报数据。")
    has_midyear_guidance = any(
        str(g.get("report_period") or "").endswith("06-30")
        or (
            isinstance(g.get("report_period"), date)
            and g["report_period"].month == 6
            and g["report_period"].day == 30
        )
        for g in guidance
    )
    if guidance:
        kinds = "、".join(
            sorted({("快报" if x["kind"] == "express" else "预告") for x in guidance})
        )
        if has_midyear_guidance:
            notes.append(f"另附东财中报业绩{kinds}（含公告日与预测区间）。")
        else:
            notes.append(f"另附东财业绩{kinds}（窗口内暂无中报预告口径）。")
    else:
        notes.append("该股暂无中报业绩预告/快报（并非所有公司都会发）。")
    return {
        "code": code,
        "name": stock.name or "",
        "source": "eastmoney",
        "years": years,
        "note": "".join(notes),
        "points": points,
        "guidance": guidance,
    }


# 兼容旧调用名
get_parent_profit_annual = get_financial_highlights


def get_stock_disclosures(
    repos: Repositories,
    code: str,
    *,
    around_date: date | None = None,
    lookback_days: int = 21,
) -> dict[str, Any]:
    """个股近期财务类公告（与披露列表同源：东财「财务报告」频道）。

    详情页原先只展示结构化业绩预告/快报（YJYG/YJKB），与披露页公告大全不是同一数据源，
    会出现「列表有 18 号公告、详情看不到」的错位；本接口补齐同源列表。
    """
    from datetime import timedelta

    from quant_system.api.errors import raise_bad_request
    from quant_system.data.disclosure_provider import MAX_RANGE_DAYS, DisclosureProvider

    code = code.upper()
    stock = repos.stock.get_stock(code)
    if stock is None:
        raise_not_found(f"股票不存在: {code}")

    lookback_days = max(1, min(int(lookback_days), MAX_RANGE_DAYS - 1))
    end = date.today()
    if around_date is not None:
        start = around_date - timedelta(days=lookback_days)
        end = max(around_date, end)
        if (end - start).days + 1 > MAX_RANGE_DAYS:
            start = end - timedelta(days=MAX_RANGE_DAYS - 1)
    else:
        start = end - timedelta(days=lookback_days)

    provider = DisclosureProvider()
    try:
        items = provider.fetch_financial_notices(start, end)
    except ValueError as e:
        raise_bad_request(str(e))

    items = [x for x in items if str(x.get("code") or "").upper() == code]
    items.sort(
        key=lambda x: (
            -(x["notice_date"].toordinal() if hasattr(x["notice_date"], "toordinal") else 0),
            str(x.get("title") or ""),
        )
    )
    return {
        "code": code,
        "name": stock.name or "",
        "start_date": start,
        "end_date": end,
        "total": len(items),
        "items": items,
    }


def get_disclosures_by_date(
    repos: Repositories | None = None,
    notice_date: date | None = None,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    categories: list[str] | None = None,
    main_only: bool = False,
    enrich_forecast: bool = False,
    enrich_returns: bool = False,
) -> dict[str, Any]:
    """公告日（或区间）的财务类披露列表（预告/快报/定期报告等）。"""
    from quant_system.api.errors import raise_bad_request
    from quant_system.data.disclosure_provider import (
        CATEGORY_LABELS,
        MAX_RANGE_DAYS,
        DisclosureProvider,
        attach_returns_since_notice,
    )
    from quant_system.infra.board import Board

    today = date.today()
    # 兼容旧参数 notice_date；新用法 start_date / end_date
    start = start_date or notice_date or today
    end = end_date or notice_date or start
    if end < start:
        start, end = end, start
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise_bad_request(f"日期区间最多 {MAX_RANGE_DAYS} 天")

    from quant_system.infra.cache import CachePolicy, cached_call

    cat_key = ",".join(sorted(categories)) if categories else ""

    def _build() -> dict[str, Any]:
        provider = DisclosureProvider()
        try:
            rows = provider.fetch_financial_notices(start, end)
        except ValueError as e:
            raise_bad_request(str(e))

        if main_only:
            rows = [x for x in rows if x.get("board") == Board.MAIN.value]
        if categories:
            allow = {c.strip() for c in categories if c and c.strip()}
            if allow:
                rows = [x for x in rows if x.get("category") in allow]
        if enrich_forecast:
            # 预告：YJYG 扣非；正式：YJBB 全市场表（含自带季度环比）
            rows = provider.enrich_forecast_metrics(rows, start=start, end=end)
            rows = provider.enrich_formal_metrics(rows, start=start, end=end)
            rows = provider.enrich_qoq_metrics(rows)
        if enrich_returns and repos is not None:
            rows = attach_returns_since_notice(repos, rows)
        counts: dict[str, int] = {}
        for x in rows:
            cat = str(x.get("category") or "other")
            counts[cat] = counts.get(cat, 0) + 1
        for cat in CATEGORY_LABELS:
            counts.setdefault(cat, 0)
        return {
            "start_date": start,
            "end_date": end,
            "notice_date": end,
            "main_only": main_only,
            "enrich_forecast": enrich_forecast,
            "enrich_returns": enrich_returns,
            "total": len(rows),
            "counts": counts,
            "items": rows,
        }

    # 整表 enrich 结果缓存，避免重复拉预告/业绩报表
    # 含 returns 时不走整表缓存（依赖本地 K 线，且较重）
    if enrich_returns:
        result = _build()
    else:
        result = cached_call(
            key_parts=(
                "disclosures.enriched.v3",
                start.isoformat(),
                end.isoformat(),
                main_only,
                enrich_forecast,
                cat_key,
            ),
            fn=_build,
            policy=CachePolicy.recent(),
        )
    # 市值在缓存外挂载：本地库批量查询，快且保持较新
    if repos is not None:
        result["items"] = attach_latest_market_caps(repos, list(result.get("items") or []))
    return result


def get_disclosure_factor_analysis(
    repos: Repositories,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    notice_date: date | None = None,
    main_only: bool = True,
) -> dict[str, Any]:
    """中报预告 × 估值 × 公告后涨跌的 OLS 因子分析。"""
    from quant_system.analysis.forecast_return_factors import (
        analyze_forecast_return_factors,
    )
    from quant_system.api.errors import raise_bad_request
    from quant_system.data.disclosure_provider import MAX_RANGE_DAYS

    today = date.today()
    start = start_date or notice_date or today
    end = end_date or notice_date or start
    if end < start:
        start, end = end, start
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise_bad_request(f"日期区间最多 {MAX_RANGE_DAYS} 天")
    try:
        return analyze_forecast_return_factors(
            repos, start, end, main_only=main_only
        )
    except ValueError as e:
        raise_bad_request(str(e))
