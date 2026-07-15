"""A 股交易日历。

首次调用会从 akshare 拉一次全量交易日，缓存到本地磁盘（永久）。
之后所有交易日相关运算都在内存/缓存里完成，不再联网。

只提供只读能力：
- is_trading_day(d)
- previous_trading_day(d, n=1)
- next_trading_day(d, n=1)
- trading_days_between(start, end)
- latest_trading_day(as_of=today)
"""
from __future__ import annotations

import bisect
from datetime import date, datetime, timedelta
from functools import lru_cache

from loguru import logger

from quant_system.infra.cache import CachePolicy, cached_call


def _fetch_all_trading_days() -> list[date]:
    """从 akshare 拉取全部 A 股交易日。永久缓存。"""
    def _raw() -> list[date]:
        import akshare as ak  # 局部 import，避免 infra 层被 provider 反向依赖

        df = ak.tool_trade_date_hist_sina()
        col = "trade_date"
        # akshare 返回列名可能是 trade_date；兼容两种情况
        if col not in df.columns:
            col = df.columns[0]

        days: list[date] = []
        for v in df[col].tolist():
            if isinstance(v, (datetime, date)):
                days.append(v if isinstance(v, date) and not isinstance(v, datetime) else v.date())
            else:
                days.append(datetime.strptime(str(v)[:10], "%Y-%m-%d").date())
        days.sort()
        logger.info("交易日历加载完成：{} 个交易日，范围 {} ~ {}", len(days), days[0], days[-1])
        return days

    return cached_call(
        key_parts=("trading_calendar", "sina", "all"),
        fn=_raw,
        policy=CachePolicy.historical(),
        namespace="calendar",
    )


@lru_cache(maxsize=1)
def _cached_days() -> list[date]:
    return _fetch_all_trading_days()


def refresh() -> int:
    """强制刷新交易日缓存。返回条目数。"""
    from quant_system.infra.cache import clear_namespace

    clear_namespace("calendar")
    _cached_days.cache_clear()
    return len(_cached_days())


def is_trading_day(d: date) -> bool:
    days = _cached_days()
    idx = bisect.bisect_left(days, d)
    return idx < len(days) and days[idx] == d


def previous_trading_day(d: date, n: int = 1) -> date:
    """返回 d 之前第 n 个交易日。d 本身是否交易日不影响。"""
    if n < 1:
        raise ValueError("n 必须 >= 1")
    days = _cached_days()
    idx = bisect.bisect_left(days, d)  # 第一个 >= d 的位置
    target_idx = idx - n
    if target_idx < 0:
        raise ValueError(f"日历范围不足，无法向前 {n} 个交易日")
    return days[target_idx]


def next_trading_day(d: date, n: int = 1) -> date:
    """返回 d 之后第 n 个交易日。d 本身是否交易日不影响。"""
    if n < 1:
        raise ValueError("n 必须 >= 1")
    days = _cached_days()
    idx = bisect.bisect_right(days, d)  # 第一个 > d 的位置
    target_idx = idx + n - 1
    if target_idx >= len(days):
        raise ValueError(f"日历范围不足，无法向后 {n} 个交易日")
    return days[target_idx]


def trading_days_between(start: date, end: date) -> list[date]:
    """返回 [start, end] 区间内所有交易日（含端点）。"""
    if start > end:
        return []
    days = _cached_days()
    lo = bisect.bisect_left(days, start)
    hi = bisect.bisect_right(days, end)
    return days[lo:hi]


def latest_trading_day(as_of: date | None = None) -> date:
    """返回 as_of 及之前最近的一个交易日（含当日）。"""
    as_of = as_of or date.today()
    days = _cached_days()
    idx = bisect.bisect_right(days, as_of) - 1
    if idx < 0:
        raise ValueError("日历范围不足")
    return days[idx]


def count_trading_days(start: date, end: date) -> int:
    return len(trading_days_between(start, end))
