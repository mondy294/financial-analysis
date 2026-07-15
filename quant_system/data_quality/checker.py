"""数据质量巡检（简版）。

只检查跑通链路必需的几项：
- MISSING_KLINE：池成员某天没有 K 线（除非之前已经停牌）
- SUSPENDED：成交量 = 0 但非停牌日
- ABNORMAL_PRICE：单日涨跌幅 |pct| > 阈值（默认 22%）
- FEATURE_NULL_RATE_HIGH：daily_feature 空值率过高（说明上游行情不足）
- SYNC_STALE：data_sync_state 落后 > N 天

用法：run_checks(trade_date, repos) 返回统计。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from loguru import logger
from sqlalchemy import func, select

from quant_system.config.settings import get_settings
from quant_system.data.repository import Repositories
from quant_system.database.models import DailyFeature, DailyKline, DataSyncState


@dataclass
class QualitySummary:
    trade_date: date
    checks_added: int = 0
    error_count: int = 0
    warn_count: int = 0
    info_count: int = 0

    def add(self, severity: str) -> None:
        self.checks_added += 1
        if severity == "ERROR":
            self.error_count += 1
        elif severity == "WARN":
            self.warn_count += 1
        else:
            self.info_count += 1


def run_checks(trade_date: date, repos: Repositories) -> QualitySummary:
    """对某个交易日跑一遍数据质量检查。"""
    settings = get_settings()
    summary = QualitySummary(trade_date=trade_date)

    _check_missing_kline(trade_date, repos, summary)
    _check_abnormal_price(trade_date, repos, summary, threshold=settings.data_quality.abnormal_pct_threshold)
    _check_feature_null_rate(trade_date, repos, summary, warn_threshold=settings.data_quality.feature_null_rate_warn)
    _check_sync_stale(trade_date, repos, summary, stale_days=settings.data_quality.sync_stale_days)

    logger.info(
        "quality checks 完成: date={} added={} ERROR={} WARN={} INFO={}",
        trade_date, summary.checks_added,
        summary.error_count, summary.warn_count, summary.info_count,
    )
    return summary


# ============================================================================
# 单项检查
# ============================================================================

def _check_missing_kline(
    trade_date: date, repos: Repositories, summary: QualitySummary,
) -> None:
    """当日 HS300 池成员是否都有 K 线。缺失记 WARN。"""
    pool_code = get_settings().stock_pool.pool.value
    pool_code_db = "CUSTOM_DEFAULT" if pool_code == "CUSTOM" else pool_code
    members = repos.stock.list_pool_members(pool_code_db)
    if not members:
        return

    session = repos.kline._session  # type: ignore[attr-defined]
    stmt = (
        select(DailyKline.code)
        .where(DailyKline.trade_date == trade_date)
        .where(DailyKline.code.in_(members))
    )
    existing = set(session.scalars(stmt).all())
    missing = [c for c in members if c not in existing]

    for code in missing:
        repos.quality.add_check({
            "check_date": trade_date,
            "check_type": "MISSING_KLINE",
            "severity": "WARN",
            "entity_type": "STOCK",
            "entity_key": code,
            "trade_date": trade_date,
            "issue": f"{code} 在 {trade_date} 无 K 线",
            "detail": {"pool": pool_code_db},
        })
        summary.add("WARN")


def _check_abnormal_price(
    trade_date: date, repos: Repositories, summary: QualitySummary,
    threshold: float = 22.0,
) -> None:
    """涨跌幅绝对值超过阈值（22% 涵盖科创板/创业板 20% 涨跌停）。"""
    session = repos.kline._session  # type: ignore[attr-defined]
    stmt = (
        select(DailyKline.code, DailyKline.pct_change, DailyKline.volume)
        .where(DailyKline.trade_date == trade_date)
    )
    for code, pct, vol in session.execute(stmt):
        if pct is None:
            continue
        pct_f = float(pct)
        if abs(pct_f) > threshold:
            repos.quality.add_check({
                "check_date": trade_date,
                "check_type": "ABNORMAL_PRICE",
                "severity": "ERROR",
                "entity_type": "STOCK",
                "entity_key": code,
                "trade_date": trade_date,
                "issue": f"{code} 涨跌幅 {pct_f:.2f}% 超阈值 {threshold}%",
                "detail": {"pct_change": pct_f, "threshold": threshold},
            })
            summary.add("ERROR")

        # 顺便检查 SUSPENDED
        if vol is not None and int(vol) == 0:
            repos.quality.add_check({
                "check_date": trade_date,
                "check_type": "SUSPENDED",
                "severity": "WARN",
                "entity_type": "STOCK",
                "entity_key": code,
                "trade_date": trade_date,
                "issue": f"{code} {trade_date} 成交量为 0（疑似停牌）",
                "detail": None,
            })
            summary.add("WARN")


def _check_feature_null_rate(
    trade_date: date, repos: Repositories, summary: QualitySummary,
    warn_threshold: float = 0.05,
) -> None:
    """daily_feature 关键指标空值率过高。"""
    features = repos.feature.read_features_on(trade_date)
    if not features:
        return
    total = len(features)
    null_count = sum(
        1 for f in features
        if f.ma20 is None or f.macd is None or f.rsi_14 is None
    )
    rate = null_count / total
    if rate > warn_threshold:
        repos.quality.add_check({
            "check_date": trade_date,
            "check_type": "FEATURE_NULL_RATE_HIGH",
            "severity": "WARN",
            "entity_type": "SYSTEM",
            "entity_key": None,
            "trade_date": trade_date,
            "issue": f"特征空值率 {rate:.2%} 超阈值 {warn_threshold:.2%}",
            "detail": {"total": total, "null_count": null_count},
        })
        summary.add("WARN")


def _check_sync_stale(
    trade_date: date, repos: Repositories, summary: QualitySummary,
    stale_days: int = 3,
) -> None:
    """data_sync_state 落后过久。"""
    session = repos.kline._session  # type: ignore[attr-defined]
    threshold_date = trade_date - timedelta(days=stale_days)
    stmt = select(DataSyncState).where(
        DataSyncState.last_sync_date < threshold_date,
    )
    for row in session.scalars(stmt):
        repos.quality.add_check({
            "check_date": trade_date,
            "check_type": "SYNC_STALE",
            "severity": "INFO",
            "entity_type": "SYSTEM",
            "entity_key": f"{row.source}:{row.entity_key}",
            "trade_date": trade_date,
            "issue": f"{row.source}/{row.entity_key} 最后同步 {row.last_sync_date}",
            "detail": {"last_sync": str(row.last_sync_date)},
        })
        summary.add("INFO")


def get_blacklist_for_selector(
    trade_date: date, repos: Repositories, filter_level: str | None = None,
) -> set[str]:
    """selector 前置过滤用。返回当日应该剔除的股票 code 集合。

    filter_level:
    - OFF：返回空集
    - ERROR：只剔除 ERROR 级 STOCK
    - WARN_AND_ABOVE：剔除 ERROR + WARN 级 STOCK（严格）
    """
    settings = get_settings()
    level = filter_level or settings.data_quality.filter_level.value

    if level == "OFF":
        return set()

    session = repos.kline._session  # type: ignore[attr-defined]
    from quant_system.database.models import DataQualityCheck

    if level == "ERROR":
        severities = ["ERROR"]
    else:
        severities = ["ERROR", "WARN"]

    stmt = (
        select(DataQualityCheck.entity_key)
        .where(DataQualityCheck.check_date == trade_date)
        .where(DataQualityCheck.entity_type == "STOCK")
        .where(DataQualityCheck.severity.in_(severities))
        .where(DataQualityCheck.resolved.is_(False))
    )
    return {r for r in session.scalars(stmt) if r}
