"""市场情绪 Provider：涨跌家数 / 涨跌停 / 北向资金。

约定：
- fetch_today_snapshot()  当日快照，不缓存
- fetch_by_date(d)        指定日回填（用于 --backfill）
"""
from __future__ import annotations

from datetime import date
from typing import Optional, Protocol, runtime_checkable

import pandas as pd
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from quant_system.config.settings import get_settings
from quant_system.data.stock_provider import _throttle
from quant_system.infra.cache import CachePolicy, cached_call


@runtime_checkable
class SentimentProvider(Protocol):
    name: str
    def fetch_today_snapshot(self, force_refresh: bool = False) -> Optional[dict]: ...
    def fetch_by_date(self, d: date, force_refresh: bool = False) -> Optional[dict]: ...


def _retry():
    cfg = get_settings().data
    return retry(
        stop=stop_after_attempt(cfg.akshare_retry_times),
        wait=wait_exponential(multiplier=cfg.akshare_retry_backoff, min=1, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )


class AkshareSentimentProvider:
    name = "akshare"

    def fetch_today_snapshot(self, force_refresh: bool = False) -> Optional[dict]:
        """今日市场活跃度快照（不缓存）。返回 dict 或 None。"""
        return cached_call(
            key_parts=("akshare.market_activity", "today"),
            fn=self._fetch_today_raw,
            policy=CachePolicy.realtime(),
            force_refresh=force_refresh,
        )

    @_retry()
    def _fetch_today_raw(self) -> Optional[dict]:
        import akshare as ak

        _throttle()
        try:
            df = ak.stock_market_activity_legu()
        except Exception as e:
            logger.warning("market_activity_legu 失败: {}", e)
            return None
        if df is None or df.empty:
            return None

        # 该接口返回一个「item / value」的键值对表
        mapping = dict(zip(df.iloc[:, 0].astype(str), df.iloc[:, 1]))
        try:
            up = int(str(mapping.get("上涨", 0)).replace(",", "").split(".")[0])
            down = int(str(mapping.get("下跌", 0)).replace(",", "").split(".")[0])
            flat = int(str(mapping.get("平盘", 0)).replace(",", "").split(".")[0])
            limit_up = int(str(mapping.get("涨停", 0)).replace(",", "").split(".")[0])
            limit_down = int(str(mapping.get("跌停", 0)).replace(",", "").split(".")[0])
            broken = int(str(mapping.get("真实涨停", limit_up)).replace(",", "").split(".")[0])
        except Exception:
            up = down = flat = limit_up = limit_down = 0
            broken = None

        return {
            "up_count": up, "down_count": down, "flat_count": flat,
            "limit_up_count": limit_up, "limit_down_count": limit_down,
            "broken_limit_up_count": broken,
            "total_amount": None,
            "north_money_net": None,
        }

    def fetch_by_date(self, d: date, force_refresh: bool = False) -> Optional[dict]:
        """指定日回填市场情绪。当前实现从涨停池 + 全市场行情推导。

        注意：历史情绪回填开销大，仅在 --backfill 时用。
        """
        return cached_call(
            key_parts=("akshare.market_backfill", d.isoformat()),
            fn=lambda: self._fetch_by_date_raw(d),
            policy=CachePolicy.for_date(d),
            force_refresh=force_refresh,
        )

    @_retry()
    def _fetch_by_date_raw(self, d: date) -> Optional[dict]:
        import akshare as ak

        date_str = d.strftime("%Y%m%d")
        _throttle()
        try:
            df_zt = ak.stock_zt_pool_em(date=date_str)
            limit_up = 0 if df_zt is None else int(len(df_zt))
        except Exception:
            limit_up = 0

        try:
            _throttle()
            df_dt = ak.stock_zt_pool_dtgc_em(date=date_str)
            limit_down = 0 if df_dt is None else int(len(df_dt))
        except Exception:
            limit_down = 0

        # 涨跌家数历史精确统计需要逐股遍历，成本太大；这里回填只写涨跌停数，其他留空。
        return {
            "up_count": 0, "down_count": 0, "flat_count": 0,
            "limit_up_count": limit_up, "limit_down_count": limit_down,
            "broken_limit_up_count": None,
            "total_amount": None,
            "north_money_net": None,
        }
