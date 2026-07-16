"""指数日线 Provider。"""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

import pandas as pd
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from quant_system.config.settings import get_settings
from quant_system.data.stock_provider import _throttle
from quant_system.infra.cache import CachePolicy, cached_call


# 关键指数集合（默认）
DEFAULT_INDICES: dict[str, str] = {
    # code -> akshare symbol
    # —— 宽基/板块指数（覆盖 上证/深证/创业板/科创板/北交所）——
    "000001.SH": "sh000001",  # 上证指数
    "399001.SZ": "sz399001",  # 深证成指
    "399006.SZ": "sz399006",  # 创业板指
    "000688.SH": "sh000688",  # 科创 50
    "899050.BJ": "bj899050",  # 北证 50
    # —— 规模指数（大/中/小盘基准）——
    "000016.SH": "sh000016",  # 上证 50
    "000300.SH": "sh000300",  # 沪深 300
    "000905.SH": "sh000905",  # 中证 500
    "000852.SH": "sh000852",  # 中证 1000
}


@runtime_checkable
class IndexProvider(Protocol):
    name: str
    def fetch_index_daily(
        self, index_code: str, start: date, end: date, force_refresh: bool = False,
    ) -> pd.DataFrame: ...


def _retry():
    cfg = get_settings().data
    return retry(
        stop=stop_after_attempt(cfg.akshare_retry_times),
        wait=wait_exponential(multiplier=cfg.akshare_retry_backoff, min=1, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )


class AkshareIndexProvider:
    name = "akshare"

    def fetch_index_daily(
        self, index_code: str, start: date, end: date, force_refresh: bool = False,
    ) -> pd.DataFrame:
        return cached_call(
            key_parts=("akshare.index_daily", index_code, start.isoformat(), end.isoformat()),
            fn=lambda: self._raw(index_code, start, end),
            policy=CachePolicy.for_kline_range(end),
            force_refresh=force_refresh,
        )

    @_retry()
    def _raw(self, index_code: str, start: date, end: date) -> pd.DataFrame:
        import akshare as ak

        symbol = DEFAULT_INDICES.get(index_code)
        if symbol is None:
            raise ValueError(f"未注册的指数代码: {index_code}")

        _throttle()
        # akshare stock_zh_index_daily 返回列: date/open/close/high/low/volume
        df = ak.stock_zh_index_daily(symbol=symbol)
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.copy()
        df["trade_date"] = pd.to_datetime(df["date"]).dt.date
        df = df[(df["trade_date"] >= start) & (df["trade_date"] <= end)].copy()
        df["index_code"] = index_code
        df["amount"] = None  # 该接口不提供成交额
        df["pct_change"] = (df["close"].pct_change() * 100).round(4)

        cols = ["index_code", "trade_date", "open", "high", "low", "close", "volume", "amount", "pct_change"]
        result = df[cols].reset_index(drop=True)
        logger.debug("index {} 日线: {} 条", index_code, len(result))
        return result
