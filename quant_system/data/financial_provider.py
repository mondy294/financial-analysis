"""财务数据 Provider。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable

import pandas as pd
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from quant_system.config.settings import get_settings
from quant_system.data.stock_provider import _normalize_code, _throttle, _to_pure_code
from quant_system.infra.cache import CachePolicy, cached_call


def _parse_cn_amount(value: Any) -> float | None:
    """同花顺摘要里的金额：`1.13亿` / `4302.00万` / 纯数字 → 元。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = str(value).strip().replace(",", "").replace("%", "")
    if not s or s.lower() in {"false", "none", "nan", "-", "--"}:
        return None
    mult = 1.0
    if s.endswith("亿"):
        mult = 1e8
        s = s[:-1]
    elif s.endswith("万"):
        mult = 1e4
        s = s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None


def _parse_pct(value: Any) -> float | None:
    """`64.75%` / `False` / 数字 → 百分点（64.75 表示 64.75%）。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(",", "").replace("%", "")
    if not s or s.lower() in {"false", "none", "nan", "-", "--"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


@runtime_checkable
class FinancialProvider(Protocol):
    name: str

    def fetch_financial_snapshot(
        self, code: str, quarters: int = 12, force_refresh: bool = False,
    ) -> pd.DataFrame: ...

    def fetch_daily_valuation(
        self, code: str, force_refresh: bool = False,
    ) -> pd.DataFrame: ...

    def fetch_financial_highlights(
        self, code: str, years: int = 5, force_refresh: bool = False,
    ) -> pd.DataFrame: ...

    def fetch_earnings_guidance(
        self, code: str, force_refresh: bool = False,
    ) -> list[dict[str, Any]]: ...


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

        # 金额列含「万/亿」；同比与比率多为百分号字符串
        for c in ("net_profit", "revenue"):
            if c in df.columns:
                df[c] = df[c].map(_parse_cn_amount)
            else:
                df[c] = None
        for c in ("roe", "roa", "net_profit_yoy", "revenue_yoy", "gross_margin", "debt_to_asset"):
            if c in df.columns:
                df[c] = df[c].map(_parse_pct)
            else:
                df[c] = None

        cols = [
            "code", "report_period", "ann_date", "pe_ttm", "pb", "ps_ttm",
            "roe", "roa", "net_profit", "revenue",
            "net_profit_yoy", "revenue_yoy", "gross_margin", "debt_to_asset",
        ]
        return df[cols].reset_index(drop=True)

    # -------------------- 主要财务指标（年报 + 最新报告期） --------------------

    _HIGHLIGHT_COLS = [
        "code",
        "year",
        "report_period",
        "report_name",
        "notice_date",
        "is_annual",
        "revenue",
        "revenue_yoy",
        "parent_net_profit",
        "parent_net_profit_yoy",
        "ded_net_profit",
        "ded_net_profit_yoy",
        "roe",
    ]

    def fetch_financial_highlights(
        self, code: str, years: int = 5, force_refresh: bool = False,
    ) -> pd.DataFrame:
        """近 N 年年报 + 同期中报/一季报/三季报。

        数据源：东财 `stock_financial_analysis_indicator_em`
        - 营业总收入 TOTALOPERATEREVE
        - 归母净利润 PARENTNETPROFIT
        - 扣非净利润 KCFJCXSYJLR
        - ROE(加权) ROEJQ
        - 公告日 NOTICE_DATE
        同比字段单位为百分点，输出转为比率（0.03=+3%）；金额单位：元。
        """
        years = max(1, min(int(years), 20))
        return cached_call(
            # v4：近 N 年含年报/中报/一季报/三季报
            key_parts=("akshare.fin_highlights.v4", code, years),
            fn=lambda: self._fetch_financial_highlights_raw(code, years),
            policy=CachePolicy.recent(),
            force_refresh=force_refresh,
        )

    @_retry()
    def _fetch_financial_highlights_raw(self, code: str, years: int) -> pd.DataFrame:
        import akshare as ak

        _throttle()
        symbol = code.upper() if "." in code else _normalize_code(code)
        try:
            df = ak.stock_financial_analysis_indicator_em(
                symbol=symbol, indicator="按报告期"
            )
        except Exception as e:
            logger.debug("财务亮点拉取失败（将重试） {}: {}", code, e)
            raise

        if df is None or df.empty or "REPORT_DATE" not in df.columns:
            return pd.DataFrame(columns=self._HIGHLIGHT_COLS)

        out = pd.DataFrame()
        out["report_period"] = pd.to_datetime(df["REPORT_DATE"], errors="coerce").dt.date
        if "REPORT_DATE_NAME" in df.columns:
            out["report_name"] = df["REPORT_DATE_NAME"].astype(str)
        else:
            out["report_name"] = ""
        # 公告日：优先 NOTICE_DATE，其次 UPDATE_DATE
        notice_src = df["NOTICE_DATE"] if "NOTICE_DATE" in df.columns else None
        if notice_src is None and "UPDATE_DATE" in df.columns:
            notice_src = df["UPDATE_DATE"]
        if notice_src is not None:
            out["notice_date"] = pd.to_datetime(notice_src, errors="coerce").dt.date
        else:
            out["notice_date"] = pd.NaT
        out["revenue"] = pd.to_numeric(df.get("TOTALOPERATEREVE"), errors="coerce")
        out["revenue_yoy"] = pd.to_numeric(df.get("TOTALOPERATEREVETZ"), errors="coerce") / 100.0
        out["parent_net_profit"] = pd.to_numeric(df.get("PARENTNETPROFIT"), errors="coerce")
        out["parent_net_profit_yoy"] = (
            pd.to_numeric(df.get("PARENTNETPROFITTZ"), errors="coerce") / 100.0
        )
        out["ded_net_profit"] = pd.to_numeric(df.get("KCFJCXSYJLR"), errors="coerce")
        out["ded_net_profit_yoy"] = (
            pd.to_numeric(df.get("KCFJCXSYJLRTZ"), errors="coerce") / 100.0
        )
        # ROE 本身是百分点
        roe_pct = pd.to_numeric(df.get("ROEJQ"), errors="coerce")
        out["roe"] = roe_pct / 100.0
        out = out.dropna(subset=["report_period"]).copy()
        out["is_annual"] = out["report_period"].map(
            lambda d: bool(d and d.month == 12 and d.day == 31)
        )
        out["year"] = out["report_period"].map(lambda d: d.year)
        out["code"] = code.upper()

        annuals = (
            out[out["is_annual"]]
            .sort_values("report_period", ascending=False)
            .head(years)
        )
        year_lo = int(annuals["year"].min()) if not annuals.empty else None

        def _md(d: Any, month: int, day: int) -> bool:
            return bool(d and d.month == month and d.day == day)

        is_midyear = out["report_period"].map(lambda d: _md(d, 6, 30))
        is_q1 = out["report_period"].map(lambda d: _md(d, 3, 31))
        is_q3 = out["report_period"].map(lambda d: _md(d, 9, 30))
        is_quarterly = is_q1 | is_q3

        # 中报 / 一季报 / 三季报：与近 N 年年报同一时间窗
        if year_lo is not None:
            midyears = out[is_midyear & (out["year"] >= year_lo)]
            quarters = out[is_quarterly & (out["year"] >= year_lo)]
        else:
            midyears = (
                out[is_midyear]
                .sort_values("report_period", ascending=False)
                .head(years)
            )
            quarters = (
                out[is_quarterly]
                .sort_values("report_period", ascending=False)
                .head(years * 2)
            )

        picked = (
            pd.concat([annuals, midyears, quarters], ignore_index=True)
            .drop_duplicates(subset=["report_period"])
            .sort_values("report_period", ascending=True)
            .reset_index(drop=True)
        )
        # 缺省报告期名称
        empty_name = picked["report_name"].isna() | (picked["report_name"].str.strip() == "")
        if empty_name.any():
            def _default_name(r: pd.Series) -> str:
                if r["is_annual"]:
                    return f"{r['year']}年报"
                d = r["report_period"]
                if getattr(d, "month", None) == 3:
                    return f"{r['year']}一季报"
                if getattr(d, "month", None) == 6:
                    return f"{r['year']}中报"
                if getattr(d, "month", None) == 9:
                    return f"{r['year']}三季报"
                return str(r["report_period"])

            picked.loc[empty_name, "report_name"] = picked.loc[empty_name].apply(
                _default_name, axis=1
            )
        return picked[self._HIGHLIGHT_COLS]

    # -------------------- 业绩预告 / 快报 --------------------

    def fetch_earnings_guidance(
        self, code: str, force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """个股业绩预告 + 业绩快报（东财 datacenter）。

        优先返回近若干年「中报」预告/快报（与正式中报并列展示）；
        若窗口内无中报口径，再回退到最新一季报/三季报/年报。
        全市场拉表太重，这里按 SECURITY_CODE 过滤单票查询。
        """
        return cached_call(
            # v3：近五年中报预告/快报（与财务亮点 years=5 对齐）
            key_parts=("em.earnings_guidance.v3", code.upper()),
            fn=lambda: self._fetch_earnings_guidance_raw(code),
            policy=CachePolicy.recent(),
            force_refresh=force_refresh,
        )

    def _midyear_guidance_dates(self, today: date | None = None, years: int = 5) -> list[str]:
        """近 N 年中报报告期（含当年），新→旧；默认 5 年与财务亮点一致。"""
        today = today or date.today()
        years = max(1, min(int(years), 8))
        return [f"{y}-06-30" for y in range(today.year, today.year - years, -1)]

    def _fallback_guidance_dates(self, today: date | None = None) -> list[str]:
        """无中报预告时的回退报告期：一季报/三季报/年报。"""
        today = today or date.today()
        y = today.year
        return [f"{y}-03-31", f"{y}-09-30", f"{y - 1}-12-31"]

    @_retry()
    def _fetch_earnings_guidance_raw(self, code: str) -> list[dict[str, Any]]:
        pure = _to_pure_code(code)
        items: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def _push(item: dict[str, Any] | None) -> None:
            if not item:
                return
            period = item.get("report_period")
            period_s = period.isoformat() if isinstance(period, date) else str(period or "")
            key = (str(item.get("kind") or ""), period_s)
            if not period_s or key in seen:
                return
            seen.add(key)
            items.append(item)

        # 1) 中报预告 + 中报快报（可同报告期并存；预告在前）
        for report_date in self._midyear_guidance_dates():
            _push(self._em_yjyg_for_code(pure, report_date))
            _push(self._em_yjkb_for_code(pure, report_date))

        # 2) 若完全没有中报口径，回退一条最新非中报预告/快报
        if not items:
            for report_date in self._fallback_guidance_dates():
                express = self._em_yjkb_for_code(pure, report_date)
                if express:
                    _push(express)
                    break
                forecast = self._em_yjyg_for_code(pure, report_date)
                if forecast:
                    _push(forecast)
                    break

        # 展示顺序：报告期新→旧；同报告期预告先于快报（稳定排序）
        kind_rank = {"forecast": 0, "express": 1}
        items.sort(key=lambda g: kind_rank.get(str(g.get("kind") or ""), 9))
        items.sort(
            key=lambda g: g["report_period"]
            if isinstance(g.get("report_period"), date)
            else date.min,
            reverse=True,
        )
        return items

    def _em_datacenter_get(
        self, *, report_name: str, filt: str, page_size: int = 50
    ) -> list[dict[str, Any]]:
        import requests

        _throttle()
        url = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
        params = {
            "sortColumns": "NOTICE_DATE,SECURITY_CODE",
            "sortTypes": "-1,-1",
            "pageSize": str(page_size),
            "pageNumber": "1",
            "reportName": report_name,
            "columns": "ALL",
            "filter": filt,
        }
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        payload = r.json()
        result = payload.get("result") or {}
        rows = result.get("data") or []
        return list(rows) if isinstance(rows, list) else []

    def _em_yjyg_for_code(self, pure: str, report_date: str) -> dict[str, Any] | None:
        """业绩预告（区间估计）。"""
        rows = self._em_datacenter_get(
            report_name="RPT_PUBLIC_OP_NEWPREDICT",
            filt=f"(REPORT_DATE='{report_date}')(SECURITY_CODE=\"{pure}\")",
        )
        if not rows:
            return None
        metrics: list[dict[str, Any]] = []
        notice_date = None
        for row in rows:
            notice_date = notice_date or _em_date(row.get("NOTICE_DATE"))
            yoy_lo = _to_ratio_pct(row.get("ADD_AMP_LOWER"))
            yoy_hi = _to_ratio_pct(row.get("ADD_AMP_UPPER"))
            metrics.append(
                {
                    "metric": str(row.get("PREDICT_FINANCE") or ""),
                    "predict_type": str(row.get("PREDICT_TYPE") or "") or None,
                    "value_lower": _to_float(row.get("PREDICT_AMT_LOWER")),
                    "value_upper": _to_float(row.get("PREDICT_AMT_UPPER")),
                    "value_mid": _mid(
                        _to_float(row.get("PREDICT_AMT_LOWER")),
                        _to_float(row.get("PREDICT_AMT_UPPER")),
                    ),
                    "yoy_lower": yoy_lo,
                    "yoy_upper": yoy_hi,
                    "yoy_mid": _mid(yoy_lo, yoy_hi),
                    "content": str(row.get("PREDICT_CONTENT") or "") or None,
                    "reason": str(row.get("CHANGE_REASON_EXPLAIN") or "") or None,
                    "preyear_value": _to_float(row.get("PREYEAR_SAME_PERIOD")),
                }
            )
        return {
            "kind": "forecast",
            "report_period": date.fromisoformat(report_date),
            "report_name": _report_label(report_date, "预告"),
            "notice_date": notice_date,
            "metrics": metrics,
            "revenue": None,
            "revenue_yoy": None,
            "parent_net_profit": None,
            "parent_net_profit_yoy": None,
            "roe": None,
        }

    def _em_yjkb_for_code(self, pure: str, report_date: str) -> dict[str, Any] | None:
        """业绩快报（近似正式数）。"""
        filt = (
            '(SECURITY_TYPE_CODE in ("058001001","058001008"))'
            '(TRADE_MARKET_CODE!="069001017")'
            f"(REPORT_DATE='{report_date}')(SECURITY_CODE=\"{pure}\")"
        )
        rows = self._em_datacenter_get(
            report_name="RPT_FCI_PERFORMANCEE",
            filt=filt,
            page_size=20,
        )
        if not rows:
            return None
        row = rows[0]
        return {
            "kind": "express",
            "report_period": date.fromisoformat(report_date),
            "report_name": _report_label(report_date, "快报"),
            "notice_date": _em_date(row.get("UPDATE_DATE") or row.get("NOTICE_DATE")),
            "metrics": [],
            "revenue": _to_float(row.get("TOTAL_OPERATE_INCOME")),
            "revenue_yoy": _to_ratio_pct(row.get("YSTZ")),
            "parent_net_profit": _to_float(row.get("PARENT_NETPROFIT")),
            "parent_net_profit_yoy": _to_ratio_pct(row.get("JLRTBZCL")),
            "roe": _to_ratio_pct(row.get("WEIGHTAVG_ROE")),
        }

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


def _to_float(v: Any) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return f


def _to_ratio_pct(v: Any) -> float | None:
    """东财百分点 → 比率。"""
    f = _to_float(v)
    if f is None:
        return None
    return f / 100.0


def _mid(a: float | None, b: float | None) -> float | None:
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return (a + b) / 2.0


def _em_date(v: Any) -> date | None:
    if v is None:
        return None
    try:
        ts = pd.to_datetime(v, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.date()
    except Exception:
        return None


def _report_label(report_date: str, suffix: str) -> str:
    y, m, _ = report_date.split("-")
    if m == "03":
        base = f"{y}一季报"
    elif m == "06":
        base = f"{y}中报"
    elif m == "09":
        base = f"{y}三季报"
    elif m == "12":
        base = f"{y}年报"
    else:
        base = report_date
    return f"{base}{suffix}"
