"""Repository 层：DB 读写唯一入口（R4）。

本轮补齐：
- SQLAlchemy 各 repo 的 upsert 实体方法（用 dialect-aware upsert）
- read_kline(adj) 复权计算（在读取层动态算）
- data_sync_state 游标读写
- job_run_log 生命周期方法
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Optional, Protocol, runtime_checkable

import pandas as pd
from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from quant_system.database.models import (
    DailyFeature,
    DailyKline,
    DataQualityCheck,
    DataSyncState,
    FinancialSnapshot,
    IndexDaily,
    JobRunLog,
    MarketDaily,
    StockBasic,
    StockPool,
    StockPoolMember,
    Strategy,
    StrategySignal,
)


# ============================================================================
# 抽象协议
# ============================================================================

@runtime_checkable
class StockRepository(Protocol):
    def get_stock(self, code: str) -> Optional[StockBasic]: ...
    def upsert_stocks(self, records: Iterable[dict]) -> int: ...
    def list_pool_members(self, pool_code: str, as_of: Optional[date] = None) -> list[str]: ...
    def replace_pool_members(self, pool_code: str, codes: list[str], as_of: date) -> int: ...


@runtime_checkable
class KlineRepository(Protocol):
    def upsert_klines(self, records: Iterable[dict]) -> int: ...
    def get_latest_trade_date(self, code: Optional[str] = None) -> Optional[date]: ...
    def read_kline(
        self, code: str, start: date, end: date, adj: str = "none",
    ) -> pd.DataFrame: ...


@runtime_checkable
class FinancialRepository(Protocol):
    def upsert_snapshots(self, records: Iterable[dict]) -> int: ...
    def get_latest_snapshot(
        self, code: str, as_of: Optional[date] = None,
    ) -> Optional[FinancialSnapshot]: ...


@runtime_checkable
class FeatureRepository(Protocol):
    def upsert_features(self, records: Iterable[dict]) -> int: ...
    def read_features_on(
        self, trade_date: date, codes: Optional[list[str]] = None,
    ) -> list[DailyFeature]: ...
    def count_features_on(self, trade_date: date) -> int: ...


@runtime_checkable
class MarketRepository(Protocol):
    def upsert_index_daily(self, records: Iterable[dict]) -> int: ...
    def upsert_market_daily(self, records: Iterable[dict]) -> int: ...


@runtime_checkable
class SyncStateRepository(Protocol):
    def get_cursor(self, source: str, entity_key: str) -> Optional[date]: ...
    def set_cursor(self, source: str, entity_key: str, sync_date: date) -> None: ...


@runtime_checkable
class JobLogRepository(Protocol):
    def start_job(self, job_name: str, trade_date: Optional[date]) -> int: ...
    def finish_job(
        self, job_id: int, status: str,
        error: Optional[str] = None, stats: Optional[dict] = None,
    ) -> None: ...


@runtime_checkable
class QualityRepository(Protocol):
    def add_check(self, record: dict) -> None: ...
    def list_unresolved(
        self, check_date: date, severity: Optional[str] = None,
    ) -> list[DataQualityCheck]: ...


# ============================================================================
# SQLAlchemy 实现
# ============================================================================

class _BaseSQLARepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _upsert_batch(self, table, records: list[dict], index_cols: list[str]) -> int:
        """SQLite 方言 upsert。records 已经是纯 dict 列表。

        SQLite 单条 SQL 的绑定变量上限：旧版 999，新版 32766。
        为兼容全量场景（如全 A 股 5500+ 行 × 10 列 = 55000 参数），按块切分。
        """
        if not records:
            return 0
        dialect = self._session.bind.dialect.name if self._session.bind else "sqlite"
        if dialect == "sqlite":
            # 单条 SQL 变量数 ≈ chunk_size × 列数；保守取上限 900，避免撞旧 SQLite 的 999 限制
            n_cols = len(table.__table__.columns)
            chunk_size = max(1, 900 // max(1, n_cols))
            update_cols_names = [
                c.name for c in table.__table__.columns if c.name not in index_cols
            ]
            for i in range(0, len(records), chunk_size):
                chunk = records[i : i + chunk_size]
                stmt = sqlite_insert(table).values(chunk)
                update_cols = {name: stmt.excluded[name] for name in update_cols_names}
                stmt = stmt.on_conflict_do_update(
                    index_elements=index_cols,
                    set_=update_cols,
                )
                self._session.execute(stmt)
        else:
            # 通用 fallback（PG 走 on_conflict 需另实现，这里先简单 merge）
            for r in records:
                self._session.merge(table(**r))
        return len(records)


# -------------------- Stock --------------------

class SQLAStockRepository(_BaseSQLARepo, StockRepository):
    def get_stock(self, code: str) -> Optional[StockBasic]:
        return self._session.get(StockBasic, code)

    def upsert_stocks(self, records: Iterable[dict]) -> int:
        rows = list(records)
        for r in rows:
            r.setdefault("updated_at", datetime.utcnow())
        return self._upsert_batch(StockBasic, rows, ["code"])

    def list_pool_members(self, pool_code: str, as_of: Optional[date] = None) -> list[str]:
        stmt = select(StockPoolMember.code).where(StockPoolMember.pool_code == pool_code)
        if as_of is None:
            stmt = stmt.where(StockPoolMember.out_date.is_(None))
        else:
            stmt = stmt.where(StockPoolMember.in_date <= as_of)
            stmt = stmt.where(
                (StockPoolMember.out_date.is_(None)) | (StockPoolMember.out_date > as_of)
            )
        return list(self._session.scalars(stmt).all())

    def replace_pool_members(self, pool_code: str, codes: list[str], as_of: date) -> int:
        """替换某池的当前成分：
        1. 现有 out_date IS NULL 的记录若不在新列表 → 打上 out_date = as_of
        2. 新列表里未存在于池的股票 → 插入新记录 (in_date=as_of, out_date=NULL)
        3. 已存在且仍在的股票不变

        FK 约束：只保留 stock_basic 里存在的 code；数据源脏数据（含已退市）会被跳过并记录。
        """
        # 过滤掉 stock_basic 里不存在的 code（外键保护）
        existing_stmt = select(StockBasic.code).where(StockBasic.code.in_(list(codes)))
        existing_codes = set(self._session.scalars(existing_stmt).all())
        missing = set(codes) - existing_codes
        if missing:
            logger.warning(
                "pool {} 有 {} 只股票不在 stock_basic 中，已跳过：{}",
                pool_code, len(missing), sorted(missing)[:5],
            )
        codes = [c for c in codes if c in existing_codes]

        current = set(self.list_pool_members(pool_code))
        target = set(codes)

        removed = current - target
        added = target - current

        if removed:
            for code in removed:
                stmt = (
                    select(StockPoolMember)
                    .where(StockPoolMember.pool_code == pool_code)
                    .where(StockPoolMember.code == code)
                    .where(StockPoolMember.out_date.is_(None))
                )
                obj = self._session.scalars(stmt).first()
                if obj is not None:
                    obj.out_date = as_of

        for code in added:
            self._session.add(StockPoolMember(
                pool_code=pool_code, code=code, in_date=as_of,
                out_date=None, weight=None,
            ))

        logger.info(
            "pool {} 更新：新增 {} 只 / 剔除 {} 只 / 保留 {} 只",
            pool_code, len(added), len(removed), len(current & target),
        )
        return len(added) + len(removed)


# -------------------- Kline --------------------

class SQLAKlineRepository(_BaseSQLARepo, KlineRepository):
    def upsert_klines(self, records: Iterable[dict]) -> int:
        rows = list(records)
        for r in rows:
            r.setdefault("created_at", datetime.utcnow())
        return self._upsert_batch(DailyKline, rows, ["code", "trade_date"])

    def get_latest_trade_date(self, code: Optional[str] = None) -> Optional[date]:
        stmt = select(DailyKline.trade_date).order_by(DailyKline.trade_date.desc()).limit(1)
        if code is not None:
            stmt = stmt.where(DailyKline.code == code)
        return self._session.scalars(stmt).first()

    def read_kline(
        self, code: str, start: date, end: date, adj: str = "none",
    ) -> pd.DataFrame:
        """读取日线并按需复权。

        adj:
        - "none": 原始价
        - "qfq": 前复权（以最新价为基准，adj_factor 归一到当前）
        - "hfq": 后复权（乘以 adj_factor）
        """
        stmt = (
            select(DailyKline)
            .where(DailyKline.code == code)
            .where(DailyKline.trade_date >= start)
            .where(DailyKline.trade_date <= end)
            .order_by(DailyKline.trade_date)
        )
        rows = self._session.scalars(stmt).all()
        if not rows:
            return pd.DataFrame(columns=[
                "trade_date", "open", "high", "low", "close",
                "pre_close", "volume", "amount", "turnover_rate",
                "pct_change", "adj_factor",
            ])

        df = pd.DataFrame([{
            "trade_date": r.trade_date,
            "open": float(r.open),
            "high": float(r.high),
            "low": float(r.low),
            "close": float(r.close),
            "pre_close": float(r.pre_close),
            "volume": int(r.volume),
            "amount": float(r.amount),
            "turnover_rate": float(r.turnover_rate) if r.turnover_rate is not None else None,
            "pct_change": float(r.pct_change) if r.pct_change is not None else None,
            "adj_factor": float(r.adj_factor),
        } for r in rows])

        if adj == "none":
            return df

        if adj == "hfq":
            for c in ("open", "high", "low", "close", "pre_close"):
                df[c] = df[c] * df["adj_factor"]
            return df

        if adj == "qfq":
            latest_factor = df["adj_factor"].iloc[-1]
            ratio = df["adj_factor"] / latest_factor
            for c in ("open", "high", "low", "close", "pre_close"):
                df[c] = df[c] * ratio
            return df

        raise ValueError(f"未知复权类型: {adj}")


# -------------------- Financial --------------------

class SQLAFinancialRepository(_BaseSQLARepo, FinancialRepository):
    def upsert_snapshots(self, records: Iterable[dict]) -> int:
        rows = list(records)
        for r in rows:
            r.setdefault("updated_at", datetime.utcnow())
        return self._upsert_batch(FinancialSnapshot, rows, ["code", "report_period"])

    def get_latest_snapshot(
        self, code: str, as_of: Optional[date] = None,
    ) -> Optional[FinancialSnapshot]:
        stmt = (
            select(FinancialSnapshot)
            .where(FinancialSnapshot.code == code)
            .order_by(FinancialSnapshot.report_period.desc())
            .limit(1)
        )
        if as_of is not None:
            stmt = stmt.where(FinancialSnapshot.ann_date <= as_of)
        return self._session.scalars(stmt).first()


# -------------------- Feature --------------------

class SQLAFeatureRepository(_BaseSQLARepo, FeatureRepository):
    def upsert_features(self, records: Iterable[dict]) -> int:
        return self._upsert_batch(DailyFeature, list(records), ["code", "trade_date"])

    def read_features_on(
        self, trade_date: date, codes: Optional[list[str]] = None,
    ) -> list[DailyFeature]:
        stmt = select(DailyFeature).where(DailyFeature.trade_date == trade_date)
        if codes:
            stmt = stmt.where(DailyFeature.code.in_(codes))
        return list(self._session.scalars(stmt).all())

    def count_features_on(self, trade_date: date) -> int:
        from sqlalchemy import func
        stmt = select(func.count()).select_from(DailyFeature).where(
            DailyFeature.trade_date == trade_date,
        )
        return int(self._session.scalar(stmt) or 0)


# -------------------- Market --------------------

class SQLAMarketRepository(_BaseSQLARepo, MarketRepository):
    def upsert_index_daily(self, records: Iterable[dict]) -> int:
        return self._upsert_batch(IndexDaily, list(records), ["index_code", "trade_date"])

    def upsert_market_daily(self, records: Iterable[dict]) -> int:
        rows = list(records)
        for r in rows:
            r.setdefault("updated_at", datetime.utcnow())
        return self._upsert_batch(MarketDaily, rows, ["trade_date"])


# -------------------- SyncState --------------------

class SQLASyncStateRepository(_BaseSQLARepo, SyncStateRepository):
    def get_cursor(self, source: str, entity_key: str) -> Optional[date]:
        obj = self._session.get(DataSyncState, (source, entity_key))
        return obj.last_sync_date if obj is not None else None

    def set_cursor(self, source: str, entity_key: str, sync_date: date) -> None:
        obj = self._session.get(DataSyncState, (source, entity_key))
        now = datetime.utcnow()
        if obj is None:
            obj = DataSyncState(
                source=source, entity_key=entity_key,
                last_sync_date=sync_date, updated_at=now,
            )
            self._session.add(obj)
        else:
            if obj.last_sync_date is None or sync_date > obj.last_sync_date:
                obj.last_sync_date = sync_date
            obj.updated_at = now


# -------------------- JobLog --------------------

class SQLAJobLogRepository(_BaseSQLARepo, JobLogRepository):
    def start_job(self, job_name: str, trade_date: Optional[date]) -> int:
        obj = JobRunLog(
            job_name=job_name, status="RUNNING",
            trade_date=trade_date, start_at=datetime.utcnow(),
        )
        self._session.add(obj)
        self._session.flush()
        return int(obj.id)

    def finish_job(
        self, job_id: int, status: str,
        error: Optional[str] = None, stats: Optional[dict] = None,
    ) -> None:
        obj = self._session.get(JobRunLog, job_id)
        if obj is None:
            logger.warning("job_run_log id={} 不存在", job_id)
            return
        obj.status = status
        obj.end_at = datetime.utcnow()
        obj.duration_ms = int((obj.end_at - obj.start_at).total_seconds() * 1000)
        obj.error_msg = error
        obj.stats = stats


# -------------------- Quality --------------------

class SQLAQualityRepository(_BaseSQLARepo, QualityRepository):
    def add_check(self, record: dict) -> None:
        record.setdefault("created_at", datetime.utcnow())
        record.setdefault("resolved", False)
        self._session.add(DataQualityCheck(**record))

    def list_unresolved(
        self, check_date: date, severity: Optional[str] = None,
    ) -> list[DataQualityCheck]:
        stmt = (
            select(DataQualityCheck)
            .where(DataQualityCheck.check_date == check_date)
            .where(DataQualityCheck.resolved.is_(False))
        )
        if severity is not None:
            stmt = stmt.where(DataQualityCheck.severity == severity)
        return list(self._session.scalars(stmt).all())


# ============================================================================
# 依赖注入：Repositories bundle
# ============================================================================

@dataclass(frozen=True)
class Repositories:
    stock: StockRepository
    kline: KlineRepository
    financial: FinancialRepository
    feature: FeatureRepository
    market: MarketRepository
    sync_state: SyncStateRepository
    job_log: JobLogRepository
    quality: QualityRepository


def build_repositories(session: Session) -> Repositories:
    return Repositories(
        stock=SQLAStockRepository(session),
        kline=SQLAKlineRepository(session),
        financial=SQLAFinancialRepository(session),
        feature=SQLAFeatureRepository(session),
        market=SQLAMarketRepository(session),
        sync_state=SQLASyncStateRepository(session),
        job_log=SQLAJobLogRepository(session),
        quality=SQLAQualityRepository(session),
    )


# ============================================================================
# 便利函数
# ============================================================================

def list_active_stock_pools(session: Session) -> list[StockPool]:
    stmt = select(StockPool).where(StockPool.is_active.is_(True)).order_by(StockPool.code)
    return list(session.scalars(stmt).all())


def list_active_strategies(session: Session) -> list[Strategy]:
    stmt = select(Strategy).where(Strategy.is_active.is_(True)).order_by(Strategy.code)
    return list(session.scalars(stmt).all())


def get_last_job_log(session: Session, job_name: str) -> Optional[JobRunLog]:
    stmt = (
        select(JobRunLog)
        .where(JobRunLog.job_name == job_name)
        .order_by(JobRunLog.start_at.desc())
        .limit(1)
    )
    return session.scalars(stmt).first()
