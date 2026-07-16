"""财务数据 Provider。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Protocol, runtime_checkable

import pandas as pd
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from quant_system.config.settings import get_settings
from quant_system.data.stock_provider import _throttle, _to_pure_code
from quant_system.infra.cache import CachePolicy, cached_call


@runtime_checkable
class FinancialProvider(Protocol):
    name: str

    def fetch_financial_snapshot(
        self, code: str, quarters: int = 12, force_refresh: bool = False,
    ) -> pd.DataFrame: ...

    def fetch_daily_valuation(
        self, code: str, force_refresh: bool = False,
    ) -> pd.DataFrame: ...


def _retry():
    cfg = get_settings().data
    return retry(
        stop=stop_after_attempt(cfg.akshare_retry_times),
        wait=wait_exponential(multiplier=cfg.akshare_retry_backoff, min=1, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )


class AkshareFinancialProvider:
    name = "akshare"

    # -------------------- 季度财报 --------------------

    def fetch_financial_snapshot(
        self, code: str, quarters: int = 12, force_refresh: bool = False,
    ) -> pd.DataFrame:
        """拉取最近 N 个季度的财务数据。

        columns=[code, report_period, ann_date, pe_ttm, pb, ps_ttm, roe, roa,
                 net_profit, revenue, net_profit_yoy, revenue_yoy,
                 gross_margin, debt_to_asset]

        注：ann_date 若数据源没提供，暂用 report_period + 45 天（大致公告窗口）。
        """
        return cached_call(
            key_parts=("akshare.financial", code, quarters),
            fn=lambda: self._fetch_financial_raw(code, quarters),
            policy=CachePolicy.recent(),  # 财务季度更新，短 TTL
            force_refresh=force_refresh,
        )

    @_retry()
    def _fetch_financial_raw(self, code: str, quarters: int) -> pd.DataFrame:
        import akshare as ak

        pure = _to_pure_code(code)
        _throttle()

        try:
            # 按报告期的关键指标
            df = ak.stock_financial_abstract_ths(symbol=pure, indicator="按报告期")
        except Exception as e:
            # 同花顺限流时页面解析失败（如 'NoneType' object has no attribute 'string'）。
            # 抛出让 @_retry 退避重试（退避后 THS 冷却下来往往能成功）；
            # 重试用尽仍失败才由上层 data_update 记为 error。空结果也不会被缓存。
            logger.debug("财务数据拉取失败（将重试） {}: {}", code, e)
            raise

        if df is None or df.empty:
            return pd.DataFrame()

        # 同花顺返回的常见列（宽表，中文列名）
        rename = {
            "报告期": "report_period",
            "净资产收益率": "roe",
            "总资产收益率": "roa",
            "净利润": "net_profit",
            "营业总收入": "revenue",
            "净利润同比增长率": "net_profit_yoy",
            "营业总收入同比增长率": "revenue_yoy",
            "销售毛利率": "gross_margin",
            "资产负债率": "debt_to_asset",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

        # 只取近 N 个季度
        if "report_period" not in df.columns:
            return pd.DataFrame()

        df["report_period"] = pd.to_datetime(df["report_period"], errors="coerce").dt.date
        df = df.dropna(subset=["report_period"]).sort_values("report_period", ascending=False)
        df = df.head(quarters).copy()

        # 补充固定列
        df["code"] = code
        df["ann_date"] = df["report_period"].apply(
            lambda d: (pd.Timestamp(d) + pd.Timedelta(days=45)).date() if d else None
        )
        # PE/PB/PS 通过日频估值走 fetch_daily_valuation，这里先留空
        for col in ["pe_ttm", "pb", "ps_ttm"]:
            df[col] = None

        # 数值列强制转数值
        num_cols = ["roe", "roa", "net_profit", "revenue",
                    "net_profit_yoy", "revenue_yoy", "gross_margin", "debt_to_asset"]
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c].astype(str).str.replace("%", "", regex=False), errors="coerce")
            else:
                df[c] = None

        cols = [
            "code", "report_period", "ann_date", "pe_ttm", "pb", "ps_ttm",
            "roe", "roa", "net_profit", "revenue",
            "net_profit_yoy", "revenue_yoy", "gross_margin", "debt_to_asset",
        ]
        return df[cols].reset_index(drop=True)

    # -------------------- 日频估值 --------------------

    # 日频估值输出列（表 daily_valuation 对齐；市值单位统一为「亿元」）
    _VAL_COLS = [
        "code", "trade_date", "pe_ttm", "pe_static", "pb",
        "ps_ttm", "market_cap", "float_market_cap",
    ]

    def fetch_daily_valuation(
        self, code: str, force_refresh: bool = False,
    ) -> pd.DataFrame:
        """按日 PE/PB/PS/市值。columns=_VAL_COLS，市值单位=亿元。

        数据源：东财 stock_value_em 为主（一次拿全历史），失败降级到百度
        stock_zh_valuation_baidu（逐指标各拉一次，只取近一年）。
        """
        return cached_call(
            key_parts=("akshare.daily_val", code),
            fn=lambda: self._fetch_daily_val_raw(code),
            policy=CachePolicy.recent(),
            force_refresh=force_refresh,
        )

    @_retry()
    def _fetch_daily_val_raw(self, code: str) -> pd.DataFrame:
        pure = _to_pure_code(code)
        df = self._daily_val_from_em(code, pure)
        if df is not None and not df.empty:
            return df
        # 东财失败/被封 → 百度兜底
        return self._daily_val_from_baidu(code, pure)

    def _daily_val_from_em(self, code: str, pure: str) -> pd.DataFrame:
        """东财 stock_value_em：一次返回全历史（总市值单位=元，需 /1e8）。"""
        import akshare as ak

        _throttle()
        df = ak.stock_value_em(symbol=pure)
        if df is None or df.empty or "数据日期" not in df.columns:
            return pd.DataFrame()

        out = pd.DataFrame()
        out["trade_date"] = pd.to_datetime(df["数据日期"], errors="coerce").dt.date
        out["code"] = code
        out["pe_ttm"] = pd.to_numeric(df.get("PE(TTM)"), errors="coerce")
        out["pe_static"] = pd.to_numeric(df.get("PE(静)"), errors="coerce")
        out["pb"] = pd.to_numeric(df.get("市净率"), errors="coerce")
        out["ps_ttm"] = pd.to_numeric(df.get("市销率"), errors="coerce")
        # 元 → 亿元
        out["market_cap"] = pd.to_numeric(df.get("总市值"), errors="coerce") / 1e8
        out["float_market_cap"] = pd.to_numeric(df.get("流通市值"), errors="coerce") / 1e8
        out = out.dropna(subset=["trade_date"]).reset_index(drop=True)
        return out[self._VAL_COLS]

    def _daily_val_from_baidu(self, code: str, pure: str) -> pd.DataFrame:
        """百度 stock_zh_valuation_baidu：逐指标各一次调用，市值单位本就是亿元。"""
        import akshare as ak

        ind_map = {"总市值": "market_cap", "市盈率(TTM)": "pe_ttm", "市净率": "pb"}
        merged: pd.DataFrame | None = None
        for ind, col in ind_map.items():
            try:
                _throttle()
                d = ak.stock_zh_valuation_baidu(symbol=pure, indicator=ind, period="近一年")
            except Exception as e:
                logger.debug("baidu 估值 {} {} 失败: {}", code, ind, e)
                continue
            if d is None or d.empty or "date" not in d.columns:
                continue
            part = pd.DataFrame({
                "trade_date": pd.to_datetime(d["date"], errors="coerce").dt.date,
                col: pd.to_numeric(d["value"], errors="coerce"),
            })
            merged = part if merged is None else merged.merge(part, on="trade_date", how="outer")

        if merged is None or merged.empty:
            return pd.DataFrame()

        merged["code"] = code
        for col in ["pe_ttm", "pe_static", "pb", "ps_ttm", "market_cap", "float_market_cap"]:
            if col not in merged.columns:
                merged[col] = None
        merged = merged.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
        return merged[self._VAL_COLS]
