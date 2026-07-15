"""股票行情 & 基础信息 Provider。

设计原则：
- 所有 akshare 调用统一通过 infra.cache.cached_call，Provider 内不写自己的缓存；
- 使用 tenacity 重试 + 限流；
- 输出列名标准化，业务层不感知 akshare 原生列名。
"""
from __future__ import annotations

import time
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

import pandas as pd
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from quant_system.config.settings import get_settings
from quant_system.infra.cache import CachePolicy, cached_call


# ============================================================================
# 协议
# ============================================================================

@runtime_checkable
class StockProvider(Protocol):
    name: str

    def fetch_stock_basic(self, force_refresh: bool = False) -> pd.DataFrame:
        """columns=[code, name, exchange, industry_name, list_date, is_st,
                    total_share, float_share, market_cap]"""
        ...

    def fetch_daily_kline(
        self,
        code: str,
        start: date,
        end: date,
        adjust: str = "none",
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """columns=[code, trade_date, open, high, low, close, pre_close,
                    volume, amount, turnover_rate, pct_change, adj_factor]"""
        ...

    def fetch_pool_members(
        self, pool_code: str, force_refresh: bool = False
    ) -> pd.DataFrame:
        """columns=[code, weight]"""
        ...


# ============================================================================
# akshare 实现
# ============================================================================

_last_call_at: float = 0.0


def _throttle() -> None:
    """全局节流：两次 akshare 调用之间至少间隔 request_interval_ms。"""
    global _last_call_at
    interval = get_settings().data.akshare_request_interval_ms / 1000.0
    now = time.time()
    wait = interval - (now - _last_call_at)
    if wait > 0:
        time.sleep(wait)
    _last_call_at = time.time()


def _retry():
    cfg = get_settings().data
    return retry(
        stop=stop_after_attempt(cfg.akshare_retry_times),
        wait=wait_exponential(multiplier=cfg.akshare_retry_backoff, min=1, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )


def _normalize_code(raw: str) -> str:
    """把 akshare 返回的 6 位代码转成 `600000.SH` / `000001.SZ` / `430000.BJ`。"""
    raw = str(raw).strip().zfill(6)
    if raw.startswith(("60", "68", "51", "56", "58", "5")):
        return f"{raw}.SH"
    if raw.startswith(("00", "30", "20", "15", "16", "18")):
        return f"{raw}.SZ"
    if raw.startswith(("8", "4", "9")):
        return f"{raw}.BJ"
    return f"{raw}.SH"


def _to_pure_code(code: str) -> str:
    """把 `600000.SH` 转回 6 位纯代码给 akshare 用。"""
    return code.split(".")[0]


class AkshareStockProvider:
    name = "akshare"

    # -------------------- 基础信息 --------------------

    def fetch_stock_basic(self, force_refresh: bool = False) -> pd.DataFrame:
        """全量拉取股票基础信息（每日更新一次）。"""
        return cached_call(
            key_parts=("akshare.stock_basic", "spot_em"),
            fn=self._fetch_stock_basic_raw,
            policy=CachePolicy.recent(),  # 每日更新，1 小时缓存即可
            force_refresh=force_refresh,
        )

    @_retry()
    def _fetch_stock_basic_raw(self) -> pd.DataFrame:
        import akshare as ak

        _throttle()
        # 主表：全 A 股 code + name（稳定接口）
        df_name = ak.stock_info_a_code_name()
        if df_name is None or df_name.empty:
            raise RuntimeError("akshare stock_info_a_code_name 返回空")

        result = pd.DataFrame()
        result["code"] = df_name["code"].astype(str).apply(_normalize_code)
        result["name"] = df_name["name"].astype(str)
        result["exchange"] = result["code"].str.split(".").str[1]
        result["is_st"] = df_name["name"].str.contains("ST", na=False)

        # 副表：市值/换手率快照（可选，失败不影响主表）
        try:
            _throttle()
            df_spot = ak.stock_zh_a_spot_em()
            if df_spot is not None and not df_spot.empty:
                spot_map: dict[str, dict] = {}
                for _, row in df_spot.iterrows():
                    code = _normalize_code(str(row.get("代码", "")))
                    spot_map[code] = {
                        "market_cap": pd.to_numeric(row.get("总市值"), errors="coerce"),
                        "turnover_rate": pd.to_numeric(row.get("换手率"), errors="coerce"),
                    }
                result["market_cap"] = result["code"].map(lambda c: spot_map.get(c, {}).get("market_cap"))
            else:
                result["market_cap"] = None
        except Exception as e:
            logger.warning("stock_zh_a_spot_em 失败，市值字段留空: {}", e)
            result["market_cap"] = None

        # 以下字段暂留空，后续可 individual_info 补
        result["industry_name"] = None
        result["list_date"] = None
        result["total_share"] = None
        result["float_share"] = None

        logger.info("拉取 stock_basic: {} 只", len(result))
        return result

    # -------------------- K 线 --------------------

    def fetch_daily_kline(
        self,
        code: str,
        start: date,
        end: date,
        adjust: str = "none",
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """拉取单只股票的日线（原始价 + adj_factor）。

        akshare 的 adjust 参数：'' 不复权 / 'qfq' 前复权 / 'hfq' 后复权。
        我们统一拉两次：不复权 + 后复权，用 hfq_close / raw_close 反推 adj_factor。
        """
        # kline 按结束日选择缓存策略
        policy = CachePolicy.for_kline_range(end)
        return cached_call(
            key_parts=("akshare.kline", code, start.isoformat(), end.isoformat()),
            fn=lambda: self._fetch_daily_kline_raw(code, start, end),
            policy=policy,
            force_refresh=force_refresh,
        )

    @_retry()
    def _fetch_daily_kline_raw(self, code: str, start: date, end: date) -> pd.DataFrame:
        import akshare as ak

        pure = _to_pure_code(code)
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")

        _throttle()
        df_raw = ak.stock_zh_a_hist(
            symbol=pure, period="daily",
            start_date=start_str, end_date=end_str, adjust="",
        )
        if df_raw is None or df_raw.empty:
            return pd.DataFrame(columns=[
                "code", "trade_date", "open", "high", "low", "close",
                "pre_close", "volume", "amount", "turnover_rate",
                "pct_change", "adj_factor",
            ])

        _throttle()
        df_hfq = ak.stock_zh_a_hist(
            symbol=pure, period="daily",
            start_date=start_str, end_date=end_str, adjust="hfq",
        )

        return self._transform_kline(code, df_raw, df_hfq)

    @staticmethod
    def _transform_kline(code: str, df_raw: pd.DataFrame, df_hfq: pd.DataFrame) -> pd.DataFrame:
        """把 akshare 两份 DataFrame 转成标准列。"""
        col_map = {
            "日期": "trade_date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume",
            "成交额": "amount", "换手率": "turnover_rate", "涨跌幅": "pct_change",
        }
        df_raw = df_raw.rename(columns=col_map)
        df_raw["trade_date"] = pd.to_datetime(df_raw["trade_date"]).dt.date

        # 通过 hfq 收盘 / raw 收盘 得到 adj_factor
        adj_factor = None
        if df_hfq is not None and not df_hfq.empty:
            df_hfq = df_hfq.rename(columns=col_map)
            df_hfq["trade_date"] = pd.to_datetime(df_hfq["trade_date"]).dt.date
            merged = df_raw[["trade_date", "close"]].merge(
                df_hfq[["trade_date", "close"]],
                on="trade_date", suffixes=("_raw", "_hfq"),
            )
            adj_factor = (merged["close_hfq"] / merged["close_raw"]).round(6)
            df_raw = df_raw.merge(
                merged[["trade_date"]].assign(adj_factor=adj_factor),
                on="trade_date", how="left",
            )
        else:
            df_raw["adj_factor"] = 1.0

        df_raw["code"] = code
        # pre_close 用前一日 close 递推
        df_raw = df_raw.sort_values("trade_date").reset_index(drop=True)
        df_raw["pre_close"] = df_raw["close"].shift(1)
        # 第一行 pre_close 用 close / (1 + pct_change/100) 反推
        first_idx = df_raw.index[0]
        if pd.isna(df_raw.at[first_idx, "pre_close"]):
            pct = df_raw.at[first_idx, "pct_change"] or 0.0
            df_raw.at[first_idx, "pre_close"] = float(df_raw.at[first_idx, "close"]) / (1 + pct / 100.0)

        cols = [
            "code", "trade_date", "open", "high", "low", "close", "pre_close",
            "volume", "amount", "turnover_rate", "pct_change", "adj_factor",
        ]
        return df_raw[cols]

    # -------------------- 股票池成分 --------------------

    def fetch_pool_members(self, pool_code: str, force_refresh: bool = False) -> pd.DataFrame:
        """拉取指数成分股。

        pool_code：
        - HS300 → 000300
        - ZZ500 → 000905
        """
        return cached_call(
            key_parts=("akshare.pool_member", pool_code),
            fn=lambda: self._fetch_pool_members_raw(pool_code),
            policy=CachePolicy.recent(),  # 成分变更不频繁，1h 缓存
            force_refresh=force_refresh,
        )

    @_retry()
    def _fetch_pool_members_raw(self, pool_code: str) -> pd.DataFrame:
        import akshare as ak

        symbol_map = {"HS300": "000300", "ZZ500": "000905"}
        if pool_code not in symbol_map:
            raise ValueError(f"不支持的池代码: {pool_code}")

        _throttle()
        df = ak.index_stock_cons_sina(symbol=symbol_map[pool_code])
        if df is None or df.empty:
            raise RuntimeError(f"pool_member 返回空: {pool_code}")

        # sina 返回列: code / name（列名可能是 code 或 品种代码）
        code_col = "code" if "code" in df.columns else df.columns[0]
        result = pd.DataFrame()
        result["code"] = df[code_col].astype(str).apply(_normalize_code)
        result["weight"] = None
        logger.info("拉取 {} 成分股: {} 只", pool_code, len(result))
        return result[["code", "weight"]]
