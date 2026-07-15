"""数据更新编排层。

包含 6 个 Updater：
- StockBasicUpdater
- StockPoolUpdater
- KlineUpdater
- FinancialUpdater
- MarketUpdater
- run_update_all（编排）

每个 Updater 都：
1. 通过依赖注入拿 provider + repos + settings；
2. 走 data_sync_state 表做增量游标；
3. 用 job_run_log 记录执行；
4. 幂等：同一天重跑不重复写。
"""
from __future__ import annotations

import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

import pandas as pd
from loguru import logger

from quant_system.config.settings import Settings, StockPoolCode, get_settings
from quant_system.data.financial_provider import FinancialProvider
from quant_system.data.repository import Repositories
from quant_system.data.stock_provider import StockProvider
from quant_system.infra import trading_calendar as tc
from quant_system.market.index_provider import DEFAULT_INDICES, IndexProvider
from quant_system.market.sentiment import SentimentProvider


# ============================================================================
# 统计结构
# ============================================================================

@dataclass
class UpdateStats:
    job_name: str
    target_date: date
    processed: int = 0
    inserted: int = 0
    skipped: int = 0
    errors: int = 0
    error_samples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "job_name": self.job_name,
            "target_date": self.target_date.isoformat(),
            "processed": self.processed,
            "inserted": self.inserted,
            "skipped": self.skipped,
            "errors": self.errors,
            "error_samples": self.error_samples[:5],
        }


# ============================================================================
# 基类
# ============================================================================

class BaseUpdater(ABC):
    source_name: str = ""

    def __init__(
        self,
        repos: Repositories,
        settings: Settings | None = None,
    ) -> None:
        self.repos = repos
        self.settings = settings or get_settings()

    # 子类实现
    @abstractmethod
    def run(self, target_date: date, full: bool = False, **kwargs) -> UpdateStats: ...

    # 通用工具
    def _wrap_job(
        self, target_date: date, fn, **kwargs,
    ) -> UpdateStats:
        job_id = self.repos.job_log.start_job(self.source_name, target_date)
        stats = UpdateStats(job_name=self.source_name, target_date=target_date)
        try:
            fn(stats, target_date, **kwargs)
            self.repos.job_log.finish_job(job_id, "SUCCESS", stats=stats.to_dict())
        except Exception as e:
            stats.errors += 1
            stats.error_samples.append(str(e))
            self.repos.job_log.finish_job(
                job_id, "FAILED", error=str(e), stats=stats.to_dict(),
            )
            logger.exception("{} 执行失败", self.source_name)
            raise
        return stats


# ============================================================================
# 1. StockBasicUpdater
# ============================================================================

class StockBasicUpdater(BaseUpdater):
    source_name = "akshare.stock_basic"

    def __init__(self, provider: StockProvider, repos: Repositories, settings: Settings | None = None) -> None:
        super().__init__(repos, settings)
        self.provider = provider

    def run(self, target_date: date, full: bool = False, **kwargs) -> UpdateStats:
        return self._wrap_job(target_date, self._do, full=full)

    def _do(self, stats: UpdateStats, target_date: date, full: bool = False) -> None:
        df = self.provider.fetch_stock_basic(force_refresh=full)
        records = df.to_dict(orient="records")
        stats.processed = len(records)
        stats.inserted = self.repos.stock.upsert_stocks(records)
        self.repos.sync_state.set_cursor(self.source_name, "_GLOBAL_", target_date)
        logger.info("stock_basic: 共 {} 只", stats.inserted)


# ============================================================================
# 2. StockPoolUpdater
# ============================================================================

class StockPoolUpdater(BaseUpdater):
    source_name = "akshare.stock_pool"

    def __init__(self, provider: StockProvider, repos: Repositories, settings: Settings | None = None) -> None:
        super().__init__(repos, settings)
        self.provider = provider

    def run(
        self, target_date: date, full: bool = False,
        pool: Optional[str] = None, **kwargs,
    ) -> UpdateStats:
        pool = pool or self.settings.stock_pool.pool.value
        return self._wrap_job(target_date, self._do, full=full, pool=pool)

    def _do(self, stats: UpdateStats, target_date: date, full: bool, pool: str) -> None:
        cfg = self.settings.stock_pool

        if pool == StockPoolCode.CUSTOM.value:
            codes = list(cfg.custom_codes)
            if not codes:
                logger.warning("CUSTOM 池 custom_codes 为空，跳过")
                return
            pool_code_db = "CUSTOM_DEFAULT"
        elif pool == StockPoolCode.ALL.value:
            # ALL 池的成分 = 所有非退市股票（从 stock_basic 反向拿）
            all_stocks = self.repos.stock.list_pool_members("ALL", as_of=None)
            # 若首次为空，则从 stock_basic 全表取
            if not all_stocks:
                from sqlalchemy import select

                from quant_system.database.models import StockBasic
                session = self.repos.stock._session  # type: ignore[attr-defined]
                codes = list(session.scalars(
                    select(StockBasic.code).where(StockBasic.delist_date.is_(None))
                ).all())
            else:
                codes = all_stocks
            pool_code_db = "ALL"
        else:
            df = self.provider.fetch_pool_members(pool, force_refresh=full)
            codes = df["code"].tolist()
            pool_code_db = pool

        stats.processed = len(codes)
        stats.inserted = self.repos.stock.replace_pool_members(pool_code_db, codes, target_date)
        self.repos.sync_state.set_cursor(
            f"{self.source_name}.{pool_code_db}", "_GLOBAL_", target_date,
        )


# ============================================================================
# 3. KlineUpdater（重头戏，增量）
# ============================================================================

class KlineUpdater(BaseUpdater):
    source_name = "akshare.kline"

    def __init__(self, provider: StockProvider, repos: Repositories, settings: Settings | None = None) -> None:
        super().__init__(repos, settings)
        self.provider = provider

    def run(
        self, target_date: date, full: bool = False,
        pool: Optional[str] = None,
        codes: Optional[list[str]] = None,
        dry_run: bool = False,
        **kwargs,
    ) -> UpdateStats:
        return self._wrap_job(
            target_date, self._do,
            full=full, pool=pool, codes=codes, dry_run=dry_run,
        )

    def _do(
        self, stats: UpdateStats, target_date: date, full: bool,
        pool: Optional[str], codes: Optional[list[str]], dry_run: bool,
    ) -> None:
        # 1. 决定股票范围
        if codes:
            target_codes = codes
        else:
            pool_code = pool or self.settings.stock_pool.pool.value
            pool_code_db = "CUSTOM_DEFAULT" if pool_code == "CUSTOM" else pool_code
            target_codes = self.repos.stock.list_pool_members(pool_code_db)
            if not target_codes:
                logger.warning("池 {} 无成员，请先跑 update stock-pool", pool_code_db)
                return

        stats.processed = len(target_codes)

        # 2. 决定起始日
        start_default = pd.to_datetime(self.settings.data.kline_start_date).date()

        logger.info(
            "kline 更新: {} 只股票 → {} ({})",
            len(target_codes), target_date, "全量" if full else "增量",
        )

        # 3. 逐股拉取
        for i, code in enumerate(target_codes, 1):
            try:
                cursor = self.repos.sync_state.get_cursor(self.source_name, code)
                if full or cursor is None:
                    start = start_default
                else:
                    if cursor >= target_date:
                        stats.skipped += 1
                        continue
                    try:
                        start = tc.next_trading_day(cursor, 1)
                    except ValueError:
                        start = start_default
                    if start > target_date:
                        stats.skipped += 1
                        continue

                if dry_run:
                    logger.info("[dry-run] {} {} → {}", code, start, target_date)
                    continue

                df = self.provider.fetch_daily_kline(
                    code, start=start, end=target_date, force_refresh=full,
                )
                if df.empty:
                    # 记录停牌可能
                    self.repos.quality.add_check({
                        "check_date": target_date,
                        "check_type": "MISSING_KLINE",
                        "severity": "WARN",
                        "entity_type": "STOCK",
                        "entity_key": code,
                        "trade_date": target_date,
                        "issue": f"{code} {start}~{target_date} 无 K 线数据",
                        "detail": {"start": start.isoformat(), "end": target_date.isoformat()},
                    })
                    stats.skipped += 1
                    self.repos.sync_state.set_cursor(self.source_name, code, target_date)
                    continue

                records = df.to_dict(orient="records")
                stats.inserted += self.repos.kline.upsert_klines(records)
                self.repos.sync_state.set_cursor(self.source_name, code, target_date)

                if i % 50 == 0:
                    logger.info("kline 进度 {}/{}", i, len(target_codes))

            except Exception as e:
                stats.errors += 1
                if len(stats.error_samples) < 5:
                    stats.error_samples.append(f"{code}: {e}")
                logger.warning("kline {} 失败: {}", code, e)
                continue

        logger.info(
            "kline 完成: processed={} inserted={} skipped={} errors={}",
            stats.processed, stats.inserted, stats.skipped, stats.errors,
        )


# ============================================================================
# 4. FinancialUpdater
# ============================================================================

class FinancialUpdater(BaseUpdater):
    source_name = "akshare.financial"

    def __init__(
        self, provider: FinancialProvider, repos: Repositories, settings: Settings | None = None,
    ) -> None:
        super().__init__(repos, settings)
        self.provider = provider

    def run(
        self, target_date: date, full: bool = False,
        pool: Optional[str] = None,
        codes: Optional[list[str]] = None,
        **kwargs,
    ) -> UpdateStats:
        return self._wrap_job(target_date, self._do, full=full, pool=pool, codes=codes)

    def _do(
        self, stats: UpdateStats, target_date: date, full: bool,
        pool: Optional[str], codes: Optional[list[str]],
    ) -> None:
        if codes:
            target_codes = codes
        else:
            pool_code = pool or self.settings.stock_pool.pool.value
            pool_code_db = "CUSTOM_DEFAULT" if pool_code == "CUSTOM" else pool_code
            target_codes = self.repos.stock.list_pool_members(pool_code_db)

        stats.processed = len(target_codes)
        quarters = self.settings.data.financial_lookback_quarters

        for i, code in enumerate(target_codes, 1):
            try:
                df = self.provider.fetch_financial_snapshot(
                    code, quarters=quarters, force_refresh=full,
                )
                if df.empty:
                    stats.skipped += 1
                    continue
                stats.inserted += self.repos.financial.upsert_snapshots(df.to_dict(orient="records"))
                self.repos.sync_state.set_cursor(self.source_name, code, target_date)

                if i % 50 == 0:
                    logger.info("financial 进度 {}/{}", i, len(target_codes))
            except Exception as e:
                stats.errors += 1
                if len(stats.error_samples) < 5:
                    stats.error_samples.append(f"{code}: {e}")
                continue


# ============================================================================
# 5. MarketUpdater（指数 + 情绪）
# ============================================================================

class MarketUpdater(BaseUpdater):
    source_name = "akshare.market"

    def __init__(
        self,
        index_provider: IndexProvider,
        sentiment_provider: SentimentProvider,
        repos: Repositories,
        settings: Settings | None = None,
    ) -> None:
        super().__init__(repos, settings)
        self.index_provider = index_provider
        self.sentiment_provider = sentiment_provider

    def run(
        self, target_date: date, full: bool = False,
        backfill: bool = False,
        **kwargs,
    ) -> UpdateStats:
        return self._wrap_job(target_date, self._do, full=full, backfill=backfill)

    def _do(self, stats: UpdateStats, target_date: date, full: bool, backfill: bool) -> None:
        # 1. 指数日线（增量）
        start_default = pd.to_datetime(self.settings.data.kline_start_date).date()
        for idx_code in DEFAULT_INDICES:
            try:
                cursor = self.repos.sync_state.get_cursor(f"akshare.index_daily", idx_code)
                if full or cursor is None:
                    start = start_default
                else:
                    if cursor >= target_date:
                        continue
                    start = tc.next_trading_day(cursor, 1)

                df = self.index_provider.fetch_index_daily(
                    idx_code, start=start, end=target_date, force_refresh=full,
                )
                if not df.empty:
                    records = df.to_dict(orient="records")
                    stats.inserted += self.repos.market.upsert_index_daily(records)
                self.repos.sync_state.set_cursor(f"akshare.index_daily", idx_code, target_date)
                stats.processed += 1
            except Exception as e:
                stats.errors += 1
                if len(stats.error_samples) < 5:
                    stats.error_samples.append(f"{idx_code}: {e}")

        # 2. 市场情绪
        if backfill:
            # 历史回填：从 kline 起点到 target_date，按交易日逐日拉
            cursor = self.repos.sync_state.get_cursor("akshare.market_daily", "_GLOBAL_")
            start = cursor and tc.next_trading_day(cursor, 1) or start_default
            days = tc.trading_days_between(start, target_date)
            logger.info("市场情绪回填: {} 个交易日", len(days))
            for d in days:
                try:
                    snapshot = self.sentiment_provider.fetch_by_date(d)
                    if snapshot is None:
                        continue
                    snapshot["trade_date"] = d
                    self.repos.market.upsert_market_daily([snapshot])
                    self.repos.sync_state.set_cursor("akshare.market_daily", "_GLOBAL_", d)
                except Exception as e:
                    stats.errors += 1
                    if len(stats.error_samples) < 5:
                        stats.error_samples.append(f"{d}: {e}")
        else:
            # 仅当日快照
            try:
                snapshot = self.sentiment_provider.fetch_today_snapshot()
                if snapshot is not None:
                    snapshot["trade_date"] = target_date
                    self.repos.market.upsert_market_daily([snapshot])
                    self.repos.sync_state.set_cursor("akshare.market_daily", "_GLOBAL_", target_date)
                    stats.inserted += 1
            except Exception as e:
                stats.errors += 1
                stats.error_samples.append(f"sentiment: {e}")


# ============================================================================
# 编排：update all
# ============================================================================

@dataclass
class UpdateAllReport:
    stock_basic: UpdateStats
    stock_pool: UpdateStats
    kline: UpdateStats
    financial: UpdateStats
    market: UpdateStats

    def summary_rows(self) -> list[tuple[str, int, int, int, int]]:
        rows = []
        for name, s in [
            ("stock_basic", self.stock_basic),
            ("stock_pool", self.stock_pool),
            ("kline", self.kline),
            ("financial", self.financial),
            ("market", self.market),
        ]:
            rows.append((name, s.processed, s.inserted, s.skipped, s.errors))
        return rows


def run_update_all(
    stock_provider: StockProvider,
    financial_provider: FinancialProvider,
    index_provider: IndexProvider,
    sentiment_provider: SentimentProvider,
    repos: Repositories,
    settings: Settings,
    target_date: date,
    full: bool = False,
) -> UpdateAllReport:
    """按依赖顺序全跑。"""
    logger.info("========== update all: target_date={} full={} ==========", target_date, full)

    basic = StockBasicUpdater(stock_provider, repos, settings).run(target_date, full=full)
    pool = StockPoolUpdater(stock_provider, repos, settings).run(target_date, full=full)
    kline = KlineUpdater(stock_provider, repos, settings).run(target_date, full=full)
    fin = FinancialUpdater(financial_provider, repos, settings).run(target_date, full=full)
    market = MarketUpdater(index_provider, sentiment_provider, repos, settings).run(
        target_date, full=full, backfill=False,
    )

    return UpdateAllReport(
        stock_basic=basic, stock_pool=pool, kline=kline,
        financial=fin, market=market,
    )
