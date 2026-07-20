"""按公告日（或区间）拉取财务相关披露（业绩预告/快报/定期报告）。"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from quant_system.config.settings import get_settings
from quant_system.data.stock_provider import _normalize_code, _throttle
from quant_system.infra.board import Board, classify
from quant_system.infra.cache import CachePolicy, cached_call

# 前端筛选用的类别
CATEGORY_FORECAST = "forecast"  # 业绩预告
CATEGORY_EXPRESS = "express"  # 业绩快报
CATEGORY_INTERIM = "interim"  # 半年度报告
CATEGORY_ANNUAL = "annual"  # 年度报告
CATEGORY_Q1 = "q1"  # 一季报
CATEGORY_Q3 = "q3"  # 三季报
CATEGORY_OTHER = "other"  # 其他财务报告类

CATEGORY_LABELS = {
    CATEGORY_FORECAST: "业绩预告",
    CATEGORY_EXPRESS: "业绩快报",
    CATEGORY_INTERIM: "半年度报告",
    CATEGORY_ANNUAL: "年度报告",
    CATEGORY_Q1: "一季报",
    CATEGORY_Q3: "三季报",
    CATEGORY_OTHER: "其他财务",
}

BOARD_LABELS = {
    Board.MAIN: "主板",
    Board.STAR: "科创板",
    Board.GEM: "创业板",
    Board.BSE: "北交所",
    Board.B: "B股",
    Board.UNKNOWN: "其他",
}

MAX_RANGE_DAYS = 31


def _retry():
    cfg = get_settings().data
    return retry(
        stop=stop_after_attempt(cfg.akshare_retry_times),
        wait=wait_exponential(multiplier=cfg.akshare_retry_backoff, min=1, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )


def classify_notice(notice_type: str, title: str) -> str | None:
    """返回类别；与财务无关则 None（理论上财务报告频道已过滤）。"""
    t = (notice_type or "").strip()
    title = title or ""
    if t == "业绩预告" or "业绩预告" in title:
        return CATEGORY_FORECAST
    if t == "业绩快报" or "业绩快报" in title:
        return CATEGORY_EXPRESS
    if "半年度报告" in t or "半年度报告" in title or "中期报告" in title:
        return CATEGORY_INTERIM
    if "年度报告" in t or ("年度报告" in title and "半年度" not in title):
        return CATEGORY_ANNUAL
    if "一季度报告" in t or "第一季度报告" in title or "一季报" in title:
        return CATEGORY_Q1
    if "三季度报告" in t or "第三季度报告" in title or "三季报" in title:
        return CATEGORY_Q3
    if any(k in t for k in ("报告", "业绩", "财务")) or any(
        k in title for k in ("报告", "业绩", "财务")
    ):
        return CATEGORY_OTHER
    return CATEGORY_OTHER


class DisclosureProvider:
    """东财公告大全 — 财务报告频道，支持单日或日期区间。"""

    def fetch_financial_notices(
        self,
        start_date: date,
        end_date: date | None = None,
        *,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        end = end_date or start_date
        if end < start_date:
            start_date, end = end, start_date
        if (end - start_date).days + 1 > MAX_RANGE_DAYS:
            raise ValueError(f"日期区间最多 {MAX_RANGE_DAYS} 天")
        return cached_call(
            key_parts=(
                "em.financial_notices_range",
                start_date.isoformat(),
                end.isoformat(),
            ),
            fn=lambda: self._fetch_raw(start_date, end),
            policy=CachePolicy.recent(),
            force_refresh=force_refresh,
        )

    @_retry()
    def _fetch_raw(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        from akshare.stock_fundamental.stock_notice import _stock_notice_report

        _throttle()
        begin = start_date.isoformat()
        end = end_date.isoformat()
        try:
            df = _stock_notice_report(
                symbol="财务报告", begin_date=begin, end_date=end
            )
        except Exception as e:
            logger.debug("财务公告拉取失败 {}~{}: {}", begin, end, e)
            raise

        if df is None or df.empty:
            return []

        rename = {
            "代码": "raw_code",
            "名称": "name",
            "公告标题": "title",
            "公告类型": "notice_type",
            "公告日期": "notice_date",
            "网址": "url",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        if "raw_code" not in df.columns:
            return []

        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for _, row in df.iterrows():
            raw = str(row.get("raw_code") or "").strip().zfill(6)
            if not raw.isdigit() or len(raw) != 6:
                continue
            try:
                code = _normalize_code(raw)
            except Exception:
                continue
            title = str(row.get("title") or "")
            notice_type = str(row.get("notice_type") or "")
            category = classify_notice(notice_type, title)
            if category is None:
                continue
            nd = row.get("notice_date")
            try:
                nd_date = pd.to_datetime(nd, errors="coerce")
                nd_out = None if pd.isna(nd_date) else nd_date.date()
            except Exception:
                nd_out = end_date
            nd_out = nd_out or end_date
            dedupe = (code, category, title, nd_out.isoformat())
            if dedupe in seen:
                continue
            seen.add(dedupe)
            board = classify(code)
            out.append(
                {
                    "code": code,
                    "name": str(row.get("name") or ""),
                    "board": board.value,
                    "board_label": BOARD_LABELS.get(board, board.value),
                    "category": category,
                    "category_label": CATEGORY_LABELS.get(category, category),
                    "notice_type": notice_type,
                    "title": title,
                    "notice_date": nd_out,
                    "url": str(row.get("url") or "") or None,
                }
            )

        order = {
            CATEGORY_FORECAST: 0,
            CATEGORY_EXPRESS: 1,
            CATEGORY_INTERIM: 2,
            CATEGORY_ANNUAL: 3,
            CATEGORY_Q1: 4,
            CATEGORY_Q3: 5,
            CATEGORY_OTHER: 9,
        }
        out.sort(
            key=lambda x: (
                -x["notice_date"].toordinal(),
                order.get(x["category"], 9),
                x["code"],
                x["title"],
            )
        )
        return out

    def fetch_parent_forecast_map(
        self, report_date: date, *, force_refresh: bool = False
    ) -> dict[str, dict[str, Any]]:
        """某报告期全市场「扣非净利润」业绩预告：code -> 同比/预测中枢等。

        数据源：ak.stock_yjyg_em；筛选「扣除非经常性损益后的净利润」。
        字段名仍用 parent_np_*（历史兼容），语义为扣非。
        """
        if report_date > date.today():
            return {}
        key = report_date.strftime("%Y%m%d")
        return cached_call(
            key_parts=("em.yjyg_ded_map.v1", key),
            fn=lambda: self._fetch_parent_forecast_map_raw(report_date),
            policy=CachePolicy.recent(),
            force_refresh=force_refresh,
        )

    @_retry()
    def _fetch_parent_forecast_map_raw(
        self, report_date: date
    ) -> dict[str, dict[str, Any]]:
        import akshare as ak

        _throttle()
        date_str = report_date.strftime("%Y%m%d")
        try:
            df = ak.stock_yjyg_em(date=date_str)
        except TypeError as e:
            # 东财未出该报告期时 akshare 常抛 NoneType，当作空表缓存，避免重试空转
            logger.debug("业绩预告全市场空数据 {}: {}", date_str, e)
            return {}
        except Exception as e:
            logger.debug("业绩预告全市场拉取失败 {}: {}", date_str, e)
            raise
        if df is None or df.empty:
            return {}

        metric_col = "预测指标"
        if metric_col not in df.columns:
            return {}
        mask = df[metric_col].astype(str).str.contains(
            "扣除非经常性损益后的净利润|扣非净利润", regex=True, na=False
        )
        sub = df.loc[mask].copy()
        if sub.empty:
            return {}

        out: dict[str, dict[str, Any]] = {}
        for _, row in sub.iterrows():
            raw = str(row.get("股票代码") or "").strip().zfill(6)
            if not raw.isdigit():
                continue
            try:
                code = _normalize_code(raw)
            except Exception:
                continue
            yoy_pct = pd.to_numeric(row.get("业绩变动幅度"), errors="coerce")
            yoy = None if pd.isna(yoy_pct) else float(yoy_pct) / 100.0
            value = pd.to_numeric(row.get("预测数值"), errors="coerce")
            value_f = None if pd.isna(value) else float(value)
            nd = row.get("公告日期")
            try:
                nd_date = pd.to_datetime(nd, errors="coerce")
                nd_out = None if pd.isna(nd_date) else nd_date.date()
            except Exception:
                nd_out = None
            # 同一股票多条时保留公告日更新的
            prev = out.get(code)
            if prev and prev.get("notice_date") and nd_out and prev["notice_date"] > nd_out:
                continue
            out[code] = {
                "report_period": report_date,
                "parent_np_yoy": yoy,
                "parent_np_value": value_f,
                "predict_type": str(row.get("预告类型") or "") or None,
                "notice_date": nd_out,
                "change_text": str(row.get("业绩变动") or "") or None,
            }
        return out

    def enrich_forecast_metrics(
        self, items: list[dict[str, Any]], *, start: date, end: date
    ) -> list[dict[str, Any]]:
        """为业绩预告条目挂上扣非净利润同比（按报告期中报 6-30）。"""
        if not items:
            return items
        periods = _midyear_periods(start, end)
        maps: dict[date, dict[str, dict[str, Any]]] = {}
        for p in periods:
            try:
                maps[p] = self.fetch_parent_forecast_map(p)
            except Exception as e:
                logger.warning("扣非预告 enrich 跳过 {}: {}", p, e)
                maps[p] = {}

        for item in items:
            item.setdefault("parent_np_yoy", None)
            item.setdefault("parent_np_value", None)
            item.setdefault("predict_type", None)
            item.setdefault("report_period", None)
            if item.get("category") != CATEGORY_FORECAST:
                continue
            period = _infer_midyear_period(
                title=str(item.get("title") or ""),
                notice_date=item.get("notice_date"),
                fallback_periods=periods,
            )
            meta = (maps.get(period) or {}).get(str(item.get("code") or "").upper())
            if not meta:
                # 再试一遍其他中报期
                for p in periods:
                    meta = (maps.get(p) or {}).get(str(item.get("code") or "").upper())
                    if meta:
                        period = p
                        break
            if not meta:
                continue
            item["parent_np_yoy"] = meta.get("parent_np_yoy")
            item["parent_np_value"] = meta.get("parent_np_value")
            item["predict_type"] = meta.get("predict_type")
            item["report_period"] = period
        return items

    def fetch_yjbb_map(
        self, report_date: date, *, force_refresh: bool = False
    ) -> dict[str, dict[str, Any]]:
        """某报告期全市场业绩报表：code -> 净利润/营收/ROE 等（正式披露）。

        数据源：ak.stock_yjbb_em（东财「业绩报表」）。
        """
        if report_date > date.today():
            return {}
        key = report_date.strftime("%Y%m%d")
        return cached_call(
            # v2：含净利润-季度环比增长
            key_parts=("em.yjbb_map.v2", key),
            fn=lambda: self._fetch_yjbb_map_raw(report_date),
            policy=CachePolicy.recent(),
            force_refresh=force_refresh,
        )

    @_retry()
    def _fetch_yjbb_map_raw(self, report_date: date) -> dict[str, dict[str, Any]]:
        import akshare as ak

        _throttle()
        date_str = report_date.strftime("%Y%m%d")
        try:
            df = ak.stock_yjbb_em(date=date_str)
        except TypeError as e:
            # 未披露报告期（如未来年报）akshare 常抛 NoneType，空表缓存避免重试空转
            logger.debug("业绩报表全市场空数据 {}: {}", date_str, e)
            return {}
        except Exception as e:
            logger.debug("业绩报表全市场拉取失败 {}: {}", date_str, e)
            raise
        if df is None or df.empty:
            return {}

        out: dict[str, dict[str, Any]] = {}
        for _, row in df.iterrows():
            raw = str(row.get("股票代码") or "").strip().zfill(6)
            if not raw.isdigit():
                continue
            try:
                code = _normalize_code(raw)
            except Exception:
                continue
            yoy_pct = pd.to_numeric(row.get("净利润-同比增长"), errors="coerce")
            yoy = None if pd.isna(yoy_pct) else float(yoy_pct) / 100.0
            qoq_pct = pd.to_numeric(row.get("净利润-季度环比增长"), errors="coerce")
            qoq = None if pd.isna(qoq_pct) else float(qoq_pct) / 100.0
            np_val = pd.to_numeric(row.get("净利润-净利润"), errors="coerce")
            np_f = None if pd.isna(np_val) else float(np_val)
            rev = pd.to_numeric(row.get("营业总收入-营业总收入"), errors="coerce")
            rev_f = None if pd.isna(rev) else float(rev)
            rev_yoy_pct = pd.to_numeric(row.get("营业总收入-同比增长"), errors="coerce")
            rev_yoy = None if pd.isna(rev_yoy_pct) else float(rev_yoy_pct) / 100.0
            roe_pct = pd.to_numeric(row.get("净资产收益率"), errors="coerce")
            roe = None if pd.isna(roe_pct) else float(roe_pct) / 100.0
            nd = row.get("最新公告日期")
            try:
                nd_date = pd.to_datetime(nd, errors="coerce")
                nd_out = None if pd.isna(nd_date) else nd_date.date()
            except Exception:
                nd_out = None
            prev = out.get(code)
            if prev and prev.get("notice_date") and nd_out and prev["notice_date"] > nd_out:
                continue
            out[code] = {
                "report_period": report_date,
                "parent_np_yoy": yoy,
                "parent_np_value": np_f,
                "parent_np_qoq": qoq,
                "revenue": rev_f,
                "revenue_yoy": rev_yoy,
                "roe": roe,
                "predict_type": "正式报告",
                "notice_date": nd_out,
            }
        return out

    def enrich_formal_metrics(
        self, items: list[dict[str, Any]], *, start: date, end: date
    ) -> list[dict[str, Any]]:
        """为正式定期报告挂上业绩报表指标（全市场一张表，快）。

        东财「业绩报表」无扣非字段，正式披露用净利润同比/季度环比；
        预告仍走 YJYG 扣非。环比优先用表内「净利润-季度环比增长」。
        """
        if not items:
            return items
        formal_cats = {
            CATEGORY_INTERIM,
            CATEGORY_ANNUAL,
            CATEGORY_Q1,
            CATEGORY_Q3,
        }
        need = [x for x in items if x.get("category") in formal_cats]
        if not need:
            return items

        periods = _formal_periods_for_items(need, start=start, end=end)
        maps: dict[date, dict[str, dict[str, Any]]] = {}
        for p in periods:
            try:
                maps[p] = self.fetch_yjbb_map(p)
            except Exception as e:
                logger.warning("业绩报表 enrich 跳过 {}: {}", p, e)
                maps[p] = {}

        for item in items:
            item.setdefault("parent_np_yoy", None)
            item.setdefault("parent_np_value", None)
            item.setdefault("parent_np_qoq", None)
            item.setdefault("predict_type", None)
            item.setdefault("report_period", None)
            cat = item.get("category")
            if cat not in formal_cats:
                continue
            period = _infer_formal_period(
                category=str(cat),
                title=str(item.get("title") or ""),
                notice_date=item.get("notice_date"),
                fallback_periods=periods,
            )
            code = str(item.get("code") or "").upper()
            meta = (maps.get(period) or {}).get(code)
            if not meta:
                for p in periods:
                    if _period_matches_category(p, str(cat)):
                        meta = (maps.get(p) or {}).get(code)
                        if meta:
                            period = p
                            break
            if not meta:
                continue
            item["parent_np_yoy"] = meta.get("parent_np_yoy")
            item["parent_np_value"] = meta.get("parent_np_value")
            if meta.get("parent_np_qoq") is not None:
                item["parent_np_qoq"] = meta.get("parent_np_qoq")
            item["predict_type"] = meta.get("predict_type") or "正式报告"
            item["report_period"] = period
        return items

    def enrich_qoq_metrics(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """补全单季环比：正式报告优先用 YJBB 自带季度环比；其余用累计差分。

        差分数据源为全市场业绩报表（快），预告金额可覆盖对应报告期。
        """
        if not items:
            return items

        for item in items:
            item.setdefault("parent_np_qoq", None)
            item.setdefault("parent_np_qoq_prev", None)
            item.setdefault("parent_np_qoq_delta", None)
            item.setdefault("parent_np_sq", None)

        overrides: dict[tuple[str, date], float] = {}
        periods_needed: set[date] = set()
        need_compute: list[dict[str, Any]] = []
        for item in items:
            rp = item.get("report_period")
            if not isinstance(rp, date):
                continue
            code = str(item.get("code") or "").upper()
            if not code:
                continue
            val = item.get("parent_np_value")
            if isinstance(val, (int, float)) and val == val:
                overrides[(code, rp)] = float(val)
            # 已有东财季度环比则只补上季环比/Δ
            p1 = _prev_report_period(rp)
            p2 = _prev_report_period(p1)
            periods_needed.update({rp, p1, p2})
            need_compute.append(item)

        if not periods_needed or not need_compute:
            return items

        maps: dict[date, dict[str, dict[str, Any]]] = {}
        for p in sorted(periods_needed):
            try:
                maps[p] = self.fetch_yjbb_map(p)
            except Exception as e:
                logger.warning("环比 enrich 跳过业绩报表 {}: {}", p, e)
                maps[p] = {}

        for item in need_compute:
            rp = item.get("report_period")
            if not isinstance(rp, date):
                continue
            code = str(item.get("code") or "").upper()
            p1 = _prev_report_period(rp)
            p2 = _prev_report_period(p1)
            sq = _single_quarter_np(maps, overrides, code, rp)
            sq_prev = _single_quarter_np(maps, overrides, code, p1)
            sq_prev2 = _single_quarter_np(maps, overrides, code, p2)
            item["parent_np_sq"] = sq
            # 本季环比：已有正式表字段则保留，否则用差分
            qoq = item.get("parent_np_qoq")
            if qoq is None:
                qoq = _growth_ratio(sq, sq_prev)
                item["parent_np_qoq"] = qoq
            # 上季环比：优先取上期 YJBB 自带字段
            prev_meta = (maps.get(p1) or {}).get(code) or {}
            prev_qoq = prev_meta.get("parent_np_qoq")
            if prev_qoq is None:
                prev_qoq = _growth_ratio(sq_prev, sq_prev2)
            item["parent_np_qoq_prev"] = prev_qoq
            if qoq is not None and prev_qoq is not None:
                item["parent_np_qoq_delta"] = float(qoq) - float(prev_qoq)
        return items


def _prev_report_period(period: date) -> date:
    if period.month == 3 and period.day == 31:
        return date(period.year - 1, 12, 31)
    if period.month == 6 and period.day == 30:
        return date(period.year, 3, 31)
    if period.month == 9 and period.day == 30:
        return date(period.year, 6, 30)
    if period.month == 12 and period.day == 31:
        return date(period.year, 9, 30)
    # 兜底：回退约一季
    if period.month <= 3:
        return date(period.year - 1, 12, 31)
    if period.month <= 6:
        return date(period.year, 3, 31)
    if period.month <= 9:
        return date(period.year, 6, 30)
    return date(period.year, 9, 30)


def _cumul_np(
    maps: dict[date, dict[str, dict[str, Any]]],
    overrides: dict[tuple[str, date], float],
    code: str,
    period: date,
) -> float | None:
    ov = overrides.get((code, period))
    if ov is not None:
        return ov
    meta = (maps.get(period) or {}).get(code)
    if not meta:
        return None
    v = meta.get("parent_np_value")
    if isinstance(v, (int, float)) and v == v:
        return float(v)
    return None


def _single_quarter_np(
    maps: dict[date, dict[str, dict[str, Any]]],
    overrides: dict[tuple[str, date], float],
    code: str,
    period: date,
) -> float | None:
    cumul = _cumul_np(maps, overrides, code, period)
    if cumul is None:
        return None
    if period.month == 3 and period.day == 31:
        return cumul
    prev = _prev_report_period(period)
    prev_cumul = _cumul_np(maps, overrides, code, prev)
    if prev_cumul is None:
        return None
    return cumul - prev_cumul


def _growth_ratio(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev is None:
        return None
    if prev == 0:
        return None
    return (cur - prev) / abs(prev)


def _midyear_periods(start: date, end: date) -> list[date]:
    years = set(range(start.year, end.year + 1))
    # 年初看上年中报预告修正也常见
    years.add(start.year - 1)
    years.add(end.year)
    return sorted({date(y, 6, 30) for y in years})


def _period_matches_category(period: date, category: str) -> bool:
    if category == CATEGORY_INTERIM:
        return period.month == 6 and period.day == 30
    if category == CATEGORY_ANNUAL:
        return period.month == 12 and period.day == 31
    if category == CATEGORY_Q1:
        return period.month == 3 and period.day == 31
    if category == CATEGORY_Q3:
        return period.month == 9 and period.day == 30
    return False


def _formal_periods_for_items(
    items: list[dict[str, Any]], *, start: date, end: date
) -> list[date]:
    """根据条目类别推断需要拉取的业绩报表报告期。"""
    years = set(range(start.year - 1, end.year + 1))
    cats = {str(x.get("category") or "") for x in items}
    periods: set[date] = set()
    for y in years:
        if CATEGORY_INTERIM in cats:
            periods.add(date(y, 6, 30))
        if CATEGORY_ANNUAL in cats:
            periods.add(date(y, 12, 31))
        if CATEGORY_Q1 in cats:
            periods.add(date(y, 3, 31))
        if CATEGORY_Q3 in cats:
            periods.add(date(y, 9, 30))
    # 至少覆盖公告窗口附近的中报（最常见）
    if not periods:
        periods.update(_midyear_periods(start, end))
    # 不拉未到期报告期，避免东财空数据 + 重试拖死冷启动
    today = date.today()
    return sorted(p for p in periods if p <= today)


def _infer_formal_period(
    *,
    category: str,
    title: str,
    notice_date: date | None,
    fallback_periods: list[date],
) -> date:
    import re

    if category == CATEGORY_INTERIM:
        return _infer_midyear_period(
            title=title, notice_date=notice_date, fallback_periods=fallback_periods
        )
    if category == CATEGORY_ANNUAL:
        m = re.search(r"(20\d{2})\s*年?\s*(年度|年报)", title)
        if m:
            return date(int(m.group(1)), 12, 31)
        m2 = re.search(r"(20\d{2})", title)
        if m2:
            return date(int(m2.group(1)), 12, 31)
        if notice_date is not None:
            y = notice_date.year - 1 if notice_date.month <= 6 else notice_date.year
            return date(y, 12, 31)
    if category == CATEGORY_Q1:
        m = re.search(r"(20\d{2})", title)
        y = int(m.group(1)) if m else (notice_date.year if notice_date else date.today().year)
        return date(y, 3, 31)
    if category == CATEGORY_Q3:
        m = re.search(r"(20\d{2})", title)
        y = int(m.group(1)) if m else (notice_date.year if notice_date else date.today().year)
        return date(y, 9, 30)

    matched = [p for p in fallback_periods if _period_matches_category(p, category)]
    if matched:
        return matched[-1]
    return fallback_periods[-1] if fallback_periods else date.today()


NOTICE_RETURN_HORIZONS = (1, 5, 10)


def attach_returns_since_notice(
    repos: Any,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """公告日后收益（前复权）。

    - return_{1,5,10}d：锚点收盘 → 其后第 h 个交易日收盘
    - return_since_notice：锚点收盘 → 最新收盘

    公告日非交易日则用其后首个有 K 线的交易日作锚点。
    """
    from sqlalchemy import select

    from quant_system.database.models import DailyKline

    if not items:
        return items
    for item in items:
        item.setdefault("return_since_notice", None)
        for h in NOTICE_RETURN_HORIZONS:
            item.setdefault(f"return_{h}d", None)

    by_notice: dict[date, list[dict[str, Any]]] = {}
    for item in items:
        raw = item.get("notice_date")
        if isinstance(raw, date):
            nd = raw
        else:
            try:
                nd = date.fromisoformat(str(raw)[:10])
            except Exception:
                continue
        by_notice.setdefault(nd, []).append(item)

    session = repos.kline._session  # noqa: SLF001
    as_of = date.today()

    for notice_date, group in by_notice.items():
        codes = sorted({str(h["code"]).upper() for h in group})
        if not codes:
            continue
        stmt = (
            select(
                DailyKline.code,
                DailyKline.trade_date,
                DailyKline.close,
                DailyKline.adj_factor,
            )
            .where(DailyKline.code.in_(codes))
            .where(DailyKline.trade_date >= notice_date)
            .where(DailyKline.trade_date <= as_of)
            .order_by(DailyKline.code, DailyKline.trade_date)
        )
        rows = session.execute(stmt).all()
        if not rows:
            continue
        df = pd.DataFrame(
            [
                {
                    "code": str(c).upper(),
                    "trade_date": d,
                    "close": float(cl),
                    "adj_factor": float(af) if af is not None else 1.0,
                }
                for c, d, cl, af in rows
            ]
        )
        rets = _returns_from_anchor(df, horizons=NOTICE_RETURN_HORIZONS)
        for item in group:
            code = str(item["code"]).upper()
            row = rets.get(code) or {}
            item["return_since_notice"] = row.get("return_since_notice")
            for h in NOTICE_RETURN_HORIZONS:
                item[f"return_{h}d"] = row.get(f"return_{h}d")

    return items


def _returns_from_anchor(
    df: pd.DataFrame, *, horizons: tuple[int, ...] = NOTICE_RETURN_HORIZONS
) -> dict[str, dict[str, float | None]]:
    import numpy as np

    out: dict[str, dict[str, float | None]] = {}
    if df.empty:
        return out
    for code, g in df.groupby("code", sort=False):
        empty = {
            "return_since_notice": None,
            **{f"return_{h}d": None for h in horizons},
        }
        g = g.sort_values("trade_date").reset_index(drop=True)
        latest_adj = float(g["adj_factor"].iloc[-1]) or 1.0
        closes = (g["close"] * (g["adj_factor"] / latest_adj)).to_numpy(dtype=float)
        if len(closes) < 1:
            out[str(code)] = empty
            continue
        anchor = float(closes[0])
        last = float(closes[-1])
        if not np.isfinite(anchor) or anchor <= 0 or not np.isfinite(last):
            out[str(code)] = empty
            continue
        row = dict(empty)
        since = float(last / anchor - 1.0)
        row["return_since_notice"] = since
        # 锚点后第 h 根 K（不含锚点当日）；不足 h 日则用至今涨幅
        forward = closes[1:]
        for h in horizons:
            if len(forward) >= h:
                v = float(forward[h - 1] / anchor - 1.0)
                row[f"return_{h}d"] = v if np.isfinite(v) else None
            else:
                row[f"return_{h}d"] = since
        out[str(code)] = row
    return out


def _infer_midyear_period(
    *,
    title: str,
    notice_date: date | None,
    fallback_periods: list[date],
) -> date:
    import re

    m = re.search(r"(20\d{2})\s*年?\s*(半年度|中报|中期)", title)
    if m:
        return date(int(m.group(1)), 6, 30)
    m2 = re.search(r"(20\d{2})", title)
    if m2:
        return date(int(m2.group(1)), 6, 30)
    if notice_date is not None:
        # 7 月及以后发的预告多半是当年中报
        y = notice_date.year if notice_date.month >= 4 else notice_date.year - 1
        return date(y, 6, 30)
    return fallback_periods[-1] if fallback_periods else date.today().replace(month=6, day=30)
