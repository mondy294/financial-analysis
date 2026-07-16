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
from typing import Any, ClassVar, Iterable, Optional, Protocol, runtime_checkable

import pandas as pd
from loguru import logger
from sqlalchemy import Integer, delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, aliased

from quant_system.database.models import (
    AbnormalRun,
    AbnormalSignal,
    DailyFeature,
    DailyKline,
    DailyValuation,
    DataQualityCheck,
    DataSyncState,
    FinancialSnapshot,
    IndexDaily,
    JobRunLog,
    MarketDaily,
    StockBasic,
    StockPool,
    StockPoolMember,
    StockRelationship,
    StockRelationshipRun,
    Strategy,
    StrategySignal,
)


# ============================================================================
# 抽象协议
# ============================================================================

@runtime_checkable
class StockRepository(Protocol):
    def get_stock(self, code: str) -> Optional[StockBasic]: ...
    def update_market_cap(self, code: str, market_cap: Optional[Decimal]) -> None: ...
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
class ValuationRepository(Protocol):
    def upsert_valuations(self, records: Iterable[dict]) -> int: ...
    def get_latest_valuation(
        self, code: str, as_of: Optional[date] = None,
    ) -> Optional[DailyValuation]: ...


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


@runtime_checkable
class RelationRepository(Protocol):
    # 写
    def replace_snapshot(self, relation_type: str, window: str) -> int: ...
    def bulk_insert(self, records: Iterable[dict]) -> int: ...
    def start_run(self, record: dict) -> int: ...
    def finish_run(
        self, run_id: int, status: str,
        stats: Optional[dict] = None, error: Optional[str] = None,
    ) -> None: ...
    def has_success_run(self, calc_date: date, relation_type: str) -> bool: ...

    # 辅助读
    def industry_map(self, codes: list[str]) -> dict[str, Optional[str]]: ...
    def read_prices(self, codes: list[str], start: date, end: date) -> pd.DataFrame: ...
    def latest_calc_date(
        self, relation_type: str = "PEARSON", window: str = "W250",
    ) -> Optional[date]: ...

    # 查询场景（min_sample 为额外过滤；build 时已按窗口做质量门槛，默认不再叠加）
    def neighbors(
        self, code: str, *, relation_type: str = "PEARSON", window: str = "W250",
        sign: Optional[int] = None, min_sample: int = 1, limit: int = 20,
        as_of: Optional[date] = None,
    ) -> list[dict]: ...
    def get_pair(
        self, code_x: str, code_y: str, *,
        relation_type: str = "PEARSON", window: str = "W250",
        as_of: Optional[date] = None,
    ) -> Optional[dict]: ...
    def list_strong(
        self, *, relation_type: str = "PEARSON", window: str = "W250", sign: int = 1,
        min_abs: float = 0.8, min_sample: int = 1, limit: int = 50,
        as_of: Optional[date] = None,
    ) -> list[dict]: ...
    def list_strengthening(
        self, *, relation_type: str = "PEARSON",
        short_window: str = "W60", long_window: str = "W250",
        min_delta: float = 0.3, min_sample: int = 1, limit: int = 50,
        as_of: Optional[date] = None,
    ) -> list[dict]: ...
    def list_pairs(
        self, *, relation_type: str = "PEARSON", window: str = "W60",
        min_abs: float = 0.0, as_of: Optional[date] = None,
    ) -> list[tuple[str, str]]: ...
    def lead_lag_of(
        self, code: str, *, relation_type: str = "LEAD_LAG", window: str = "W60",
        role: str = "all", limit: int = 20, as_of: Optional[date] = None,
    ) -> list[dict]: ...
    def snapshot_stats(
        self, *, relation_type: str = "PEARSON", window: Optional[str] = None,
    ) -> dict: ...


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

        **字段集对齐**：为了让 SQLAlchemy 能编译出统一的 INSERT，
        所有 record 必须有相同的键集。这里做防御性对齐：以第一条 record
        的键集为准，缺失的键补 None。避免上游忘记补 None 时批量 insert 挂掉。
        """
        if not records:
            return 0

        # 字段集对齐：以第一条 record 的键集为主，缺失字段填 None
        canonical_keys = list(records[0].keys())
        canonical_set = set(canonical_keys)
        aligned: list[dict] = []
        for r in records:
            if set(r.keys()) == canonical_set:
                aligned.append(r)
            else:
                # 保持第一条的键顺序，缺的补 None，多的忽略（防止把非表列传进去）
                aligned.append({k: r.get(k) for k in canonical_keys})
        records = aligned

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

    def update_market_cap(self, code: str, market_cap: Optional[Decimal]) -> None:
        """只更新 stock_basic.market_cap 单列（避免 upsert 把 name/exchange 冲空）。"""
        obj = self._session.get(StockBasic, code)
        if obj is not None:
            obj.market_cap = market_cap
            obj.updated_at = datetime.utcnow()

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


# -------------------- Valuation --------------------

class SQLAValuationRepository(_BaseSQLARepo, ValuationRepository):
    def upsert_valuations(self, records: Iterable[dict]) -> int:
        rows = list(records)
        for r in rows:
            r.setdefault("updated_at", datetime.utcnow())
        return self._upsert_batch(DailyValuation, rows, ["code", "trade_date"])

    def get_latest_valuation(
        self, code: str, as_of: Optional[date] = None,
    ) -> Optional[DailyValuation]:
        stmt = (
            select(DailyValuation)
            .where(DailyValuation.code == code)
            .order_by(DailyValuation.trade_date.desc())
            .limit(1)
        )
        if as_of is not None:
            stmt = stmt.where(DailyValuation.trade_date <= as_of)
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


# -------------------- Relation --------------------

class SQLARelationRepository(_BaseSQLARepo, RelationRepository):
    """股票关系层 DB 读写。对称存储 (code_a < code_b)，只留最新快照。"""

    _PK: ClassVar[list[str]] = ["relation_type", "window", "stock_code_a", "stock_code_b", "calc_date"]

    # ---- 写 ----
    def replace_snapshot(self, relation_type: str, window: str) -> int:
        """删除该 (relation_type, window) 的所有旧行，保证只留最新快照。"""
        stmt = (
            delete(StockRelationship)
            .where(StockRelationship.relation_type == relation_type)
            .where(StockRelationship.window == window)
        )
        result = self._session.execute(stmt)
        return int(result.rowcount or 0)

    def bulk_insert(self, records: Iterable[dict]) -> int:
        rows = list(records)
        for r in rows:
            r.setdefault("created_at", datetime.utcnow())
            r.setdefault("direction", 0)
            r.setdefault("is_same_industry", False)
        return self._upsert_batch(StockRelationship, rows, self._PK)

    def start_run(self, record: dict) -> int:
        record.setdefault("created_at", datetime.utcnow())
        record.setdefault("status", "RUNNING")
        obj = StockRelationshipRun(**record)
        self._session.add(obj)
        self._session.flush()
        return int(obj.id)

    def finish_run(
        self, run_id: int, status: str,
        stats: Optional[dict] = None, error: Optional[str] = None,
    ) -> None:
        obj = self._session.get(StockRelationshipRun, run_id)
        if obj is None:
            logger.warning("stock_relationship_run id={} 不存在", run_id)
            return
        obj.status = status
        obj.error_msg = error
        if stats:
            obj.universe_size = stats.get("universe_size")
            obj.pair_evaluated = stats.get("pair_evaluated")
            obj.pair_written = stats.get("pair_written")
            obj.code_hash = stats.get("code_hash")
            obj.duration_ms = stats.get("duration_ms")
        self._session.flush()

    def has_success_run(self, calc_date: date, relation_type: str) -> bool:
        stmt = (
            select(StockRelationshipRun.id)
            .where(StockRelationshipRun.calc_date == calc_date)
            .where(StockRelationshipRun.relation_type == relation_type)
            .where(StockRelationshipRun.status == "SUCCESS")
            .limit(1)
        )
        return self._session.scalars(stmt).first() is not None

    # ---- 辅助读 ----
    def industry_map(self, codes: list[str]) -> dict[str, Optional[str]]:
        if not codes:
            return {}
        stmt = select(StockBasic.code, StockBasic.industry_code).where(
            StockBasic.code.in_(codes)
        )
        return {c: ind for c, ind in self._session.execute(stmt).all()}

    def read_prices(self, codes: list[str], start: date, end: date) -> pd.DataFrame:
        """批量读取后复权收益率所需字段（single query），返回长表 DataFrame。

        列：code / trade_date / close / adj_factor / volume。
        """
        if not codes:
            return pd.DataFrame(columns=["code", "trade_date", "close", "adj_factor", "volume"])
        stmt = (
            select(
                DailyKline.code, DailyKline.trade_date,
                DailyKline.close, DailyKline.adj_factor, DailyKline.volume,
            )
            .where(DailyKline.code.in_(codes))
            .where(DailyKline.trade_date >= start)
            .where(DailyKline.trade_date <= end)
        )
        rows = self._session.execute(stmt).all()
        if not rows:
            return pd.DataFrame(columns=["code", "trade_date", "close", "adj_factor", "volume"])
        return pd.DataFrame(
            [
                {
                    "code": c, "trade_date": d,
                    "close": float(cl), "adj_factor": float(af), "volume": int(v),
                }
                for c, d, cl, af, v in rows
            ]
        )

    def latest_calc_date(
        self, relation_type: str = "PEARSON", window: str = "W250",
    ) -> Optional[date]:
        stmt = (
            select(StockRelationship.calc_date)
            .where(StockRelationship.relation_type == relation_type)
            .where(StockRelationship.window == window)
            .order_by(StockRelationship.calc_date.desc())
            .limit(1)
        )
        return self._session.scalars(stmt).first()

    # ---- 查询场景 ----
    def _base_where(self, stmt, relation_type: str, window: str, as_of: Optional[date]):
        stmt = stmt.where(StockRelationship.relation_type == relation_type)
        stmt = stmt.where(StockRelationship.window == window)
        if as_of is not None:
            stmt = stmt.where(StockRelationship.calc_date == as_of)
        return stmt

    def neighbors(
        self, code: str, *, relation_type: str = "PEARSON", window: str = "W250",
        sign: Optional[int] = None, min_sample: int = 1, limit: int = 20,
        as_of: Optional[date] = None,
    ) -> list[dict]:
        """查某只股票的邻居：合并 a 侧 + b 侧，按 |value| 降序取 limit。"""
        if as_of is None:
            as_of = self.latest_calc_date(relation_type, window)
            if as_of is None:
                return []
        out: list[dict] = []
        for is_a in (True, False):
            col_self = StockRelationship.stock_code_a if is_a else StockRelationship.stock_code_b
            col_peer = StockRelationship.stock_code_b if is_a else StockRelationship.stock_code_a
            stmt = select(
                col_peer.label("peer"),
                StockRelationship.relation_value,
                StockRelationship.sample_size,
                StockRelationship.is_same_industry,
                StockRelationship.direction,
            )
            stmt = self._base_where(stmt, relation_type, window, as_of)
            stmt = stmt.where(col_self == code)
            stmt = stmt.where(StockRelationship.sample_size >= min_sample)
            if sign is not None:
                if sign > 0:
                    stmt = stmt.where(StockRelationship.relation_value > 0)
                else:
                    stmt = stmt.where(StockRelationship.relation_value < 0)
            for peer, val, ss, same_ind, direction in self._session.execute(stmt).all():
                out.append({
                    "peer": peer, "relation_value": float(val),
                    "sample_size": int(ss), "is_same_industry": bool(same_ind),
                    "direction": int(direction),
                })
        out.sort(key=lambda r: abs(r["relation_value"]), reverse=True)
        return out[:limit]

    def get_pair(
        self, code_x: str, code_y: str, *,
        relation_type: str = "PEARSON", window: str = "W250",
        as_of: Optional[date] = None,
    ) -> Optional[dict]:
        a, b = (code_x, code_y) if code_x < code_y else (code_y, code_x)
        if as_of is None:
            as_of = self.latest_calc_date(relation_type, window)
            if as_of is None:
                return None
        stmt = select(StockRelationship)
        stmt = self._base_where(stmt, relation_type, window, as_of)
        stmt = stmt.where(StockRelationship.stock_code_a == a)
        stmt = stmt.where(StockRelationship.stock_code_b == b)
        obj = self._session.scalars(stmt).first()
        if obj is None:
            return None
        return {
            "stock_code_a": obj.stock_code_a, "stock_code_b": obj.stock_code_b,
            "relation_value": float(obj.relation_value), "sample_size": obj.sample_size,
            "is_same_industry": obj.is_same_industry, "direction": obj.direction,
            "calc_date": obj.calc_date,
        }

    def list_strong(
        self, *, relation_type: str = "PEARSON", window: str = "W250", sign: int = 1,
        min_abs: float = 0.8, min_sample: int = 1, limit: int = 50,
        as_of: Optional[date] = None,
    ) -> list[dict]:
        if as_of is None:
            as_of = self.latest_calc_date(relation_type, window)
            if as_of is None:
                return []
        stmt = select(StockRelationship)
        stmt = self._base_where(stmt, relation_type, window, as_of)
        stmt = stmt.where(StockRelationship.sample_size >= min_sample)
        if sign > 0:
            stmt = stmt.where(StockRelationship.relation_value >= min_abs)
            stmt = stmt.order_by(StockRelationship.relation_value.desc())
        else:
            stmt = stmt.where(StockRelationship.relation_value <= -min_abs)
            stmt = stmt.order_by(StockRelationship.relation_value.asc())
        stmt = stmt.limit(limit)
        return [
            {
                "stock_code_a": o.stock_code_a, "stock_code_b": o.stock_code_b,
                "relation_value": float(o.relation_value), "sample_size": o.sample_size,
                "is_same_industry": o.is_same_industry,
            }
            for o in self._session.scalars(stmt).all()
        ]

    def list_strengthening(
        self, *, relation_type: str = "PEARSON",
        short_window: str = "W60", long_window: str = "W250",
        min_delta: float = 0.3, min_sample: int = 1, limit: int = 50,
        as_of: Optional[date] = None,
    ) -> list[dict]:
        """联动增强：short_window 与 long_window 的自连接，delta = 短 - 长。"""
        if as_of is None:
            as_of = self.latest_calc_date(relation_type, short_window)
            if as_of is None:
                return []
        short = aliased(StockRelationship)
        long_ = aliased(StockRelationship)
        stmt = (
            select(
                short.stock_code_a, short.stock_code_b,
                short.relation_value.label("v_short"),
                long_.relation_value.label("v_long"),
                short.sample_size.label("s_short"),
                long_.sample_size.label("s_long"),
                short.is_same_industry,
            )
            .join(
                long_,
                (short.stock_code_a == long_.stock_code_a)
                & (short.stock_code_b == long_.stock_code_b)
                & (long_.relation_type == relation_type)
                & (long_.window == long_window)
                & (long_.calc_date == as_of),
            )
            .where(short.relation_type == relation_type)
            .where(short.window == short_window)
            .where(short.calc_date == as_of)
            .where(short.sample_size >= min_sample)
            .where(long_.sample_size >= min_sample)
        )
        rows = self._session.execute(stmt).all()
        out = []
        for a, b, vs, vl, ss, sl, same_ind in rows:
            delta = float(vs) - float(vl)
            if abs(delta) < min_delta:
                continue
            out.append({
                "stock_code_a": a, "stock_code_b": b,
                "v_short": float(vs), "v_long": float(vl), "delta": delta,
                "sample_short": int(ss), "sample_long": int(sl),
                "is_same_industry": bool(same_ind),
            })
        out.sort(key=lambda r: r["delta"], reverse=True)
        return out[:limit]

    def list_pairs(
        self, *, relation_type: str = "PEARSON", window: str = "W60",
        min_abs: float = 0.0, as_of: Optional[date] = None,
    ) -> list[tuple[str, str]]:
        """取某快照的 (code_a, code_b) 候选对列表（供 Lead-Lag 等二次计算复用）。"""
        if as_of is None:
            as_of = self.latest_calc_date(relation_type, window)
            if as_of is None:
                return []
        stmt = select(StockRelationship.stock_code_a, StockRelationship.stock_code_b)
        stmt = self._base_where(stmt, relation_type, window, as_of)
        if min_abs > 0:
            stmt = stmt.where(func.abs(StockRelationship.relation_value) >= min_abs)
        return [(a, b) for a, b in self._session.execute(stmt).all()]

    def lead_lag_of(
        self, code: str, *, relation_type: str = "LEAD_LAG", window: str = "W60",
        role: str = "all", limit: int = 20, as_of: Optional[date] = None,
    ) -> list[dict]:
        """某只股票的领先-滞后关系。lag_days>0 = code 领先 peer；<0 = code 跟随 peer。

        role: 'leads'（只看 code 领先的）/ 'follows'（只看 code 跟随的）/ 'all'。
        """
        if as_of is None:
            as_of = self.latest_calc_date(relation_type, window)
            if as_of is None:
                return []
        out: list[dict] = []
        for is_a in (True, False):
            col_self = StockRelationship.stock_code_a if is_a else StockRelationship.stock_code_b
            col_peer = StockRelationship.stock_code_b if is_a else StockRelationship.stock_code_a
            stmt = select(
                col_peer.label("peer"),
                StockRelationship.relation_value,
                StockRelationship.sample_size,
                StockRelationship.direction,
                StockRelationship.is_same_industry,
            )
            stmt = self._base_where(stmt, relation_type, window, as_of)
            stmt = stmt.where(col_self == code)
            for peer, val, ss, direction, same_ind in self._session.execute(stmt).all():
                # direction 以 (a→b) 为准；b 侧要取反成「code 视角」
                lag = int(direction) if is_a else -int(direction)
                out.append({
                    "peer": peer, "corr": float(val), "sample_size": int(ss),
                    "lag_days": lag, "is_same_industry": bool(same_ind),
                })
        if role == "leads":
            out = [r for r in out if r["lag_days"] > 0]
        elif role == "follows":
            out = [r for r in out if r["lag_days"] < 0]
        out.sort(key=lambda r: abs(r["corr"]), reverse=True)
        return out[:limit]

    def snapshot_stats(
        self, *, relation_type: str = "PEARSON", window: Optional[str] = None,
    ) -> dict:
        stmt = select(
            StockRelationship.window,
            func.count().label("n"),
            func.min(StockRelationship.calc_date),
            func.avg(StockRelationship.sample_size),
            func.sum(
                (StockRelationship.relation_value > 0).cast(Integer)
            ).label("pos"),
        ).where(StockRelationship.relation_type == relation_type)
        if window is not None:
            stmt = stmt.where(StockRelationship.window == window)
        stmt = stmt.group_by(StockRelationship.window)
        rows = self._session.execute(stmt).all()
        return {
            "relation_type": relation_type,
            "windows": [
                {
                    "window": w, "rows": int(n),
                    "calc_date": str(cd) if cd else None,
                    "avg_sample": round(float(avg), 1) if avg is not None else None,
                    "positive": int(pos or 0), "negative": int(n) - int(pos or 0),
                }
                for w, n, cd, avg, pos in rows
            ],
        }


# ============================================================================
# 依赖注入：Repositories bundle
# ============================================================================

@dataclass(frozen=True)
@runtime_checkable
class AbnormalRepository(Protocol):
    def replace_day(self, trade_date: date, pattern_ids: Optional[list[str]] = None) -> int: ...
    def bulk_insert(self, records: list[dict]) -> int: ...
    def start_run(self, record: dict) -> int: ...
    def finish_run(
        self, run_id: int, status: str,
        stats: Optional[dict] = None, error: Optional[str] = None,
    ) -> None: ...
    def has_success_run(self, trade_date: date, params_version: str) -> bool: ...
    def top_by_pattern(
        self, trade_date: date, pattern_id: str, limit: int = 10,
    ) -> list[dict]: ...
    def hits_of(self, code: str, trade_date: Optional[date] = None) -> list[dict]: ...
    def stats(self, trade_date: date) -> dict: ...
    def latest_trade_date(self) -> Optional[date]: ...


class SQLAAbnormalRepository(_BaseSQLARepo, AbnormalRepository):
    def replace_day(self, trade_date: date, pattern_ids: Optional[list[str]] = None) -> int:
        stmt = delete(AbnormalSignal).where(AbnormalSignal.trade_date == trade_date)
        if pattern_ids:
            stmt = stmt.where(AbnormalSignal.pattern_id.in_(pattern_ids))
        res = self._session.execute(stmt)
        return int(res.rowcount or 0)

    def bulk_insert(self, records: list[dict]) -> int:
        if not records:
            return 0
        now = datetime.utcnow()
        for r in records:
            r.setdefault("created_at", now)
            r.setdefault("risk_flags", [])
            r.setdefault("reasons", [])
        return self._upsert_batch(
            AbnormalSignal, records, ["trade_date", "code", "pattern_id"],
        )

    def start_run(self, record: dict) -> int:
        record.setdefault("created_at", datetime.utcnow())
        record.setdefault("status", "RUNNING")
        obj = AbnormalRun(**record)
        self._session.add(obj)
        self._session.flush()
        return int(obj.id)

    def finish_run(
        self, run_id: int, status: str,
        stats: Optional[dict] = None, error: Optional[str] = None,
    ) -> None:
        obj = self._session.get(AbnormalRun, run_id)
        if obj is None:
            return
        obj.status = status
        if stats:
            obj.universe_size = stats.get("universe_size", obj.universe_size)
            obj.written_count = stats.get("written_count", obj.written_count)
            obj.per_pattern_stats = stats.get("per_pattern_stats", obj.per_pattern_stats)
            obj.duration_ms = stats.get("duration_ms", obj.duration_ms)
        if error:
            obj.error_msg = error
        self._session.flush()

    def has_success_run(self, trade_date: date, params_version: str) -> bool:
        stmt = (
            select(AbnormalRun.id)
            .where(
                AbnormalRun.trade_date == trade_date,
                AbnormalRun.status == "SUCCESS",
                AbnormalRun.params_version == params_version,
            )
            .limit(1)
        )
        return self._session.scalars(stmt).first() is not None

    def top_by_pattern(
        self, trade_date: date, pattern_id: str, limit: int = 10,
    ) -> list[dict]:
        stmt = (
            select(AbnormalSignal)
            .where(
                AbnormalSignal.trade_date == trade_date,
                AbnormalSignal.pattern_id == pattern_id,
            )
            .order_by(AbnormalSignal.pattern_rank.asc())
            .limit(limit)
        )
        return [self._hit_dict(o) for o in self._session.scalars(stmt).all()]

    def hits_of(self, code: str, trade_date: Optional[date] = None) -> list[dict]:
        stmt = select(AbnormalSignal).where(AbnormalSignal.code == code)
        if trade_date is not None:
            stmt = stmt.where(AbnormalSignal.trade_date == trade_date)
        else:
            latest = self.latest_trade_date()
            if latest is None:
                return []
            stmt = stmt.where(AbnormalSignal.trade_date == latest)
        stmt = stmt.order_by(AbnormalSignal.pattern_id)
        return [self._hit_dict(o) for o in self._session.scalars(stmt).all()]

    def stats(self, trade_date: date) -> dict:
        stmt = (
            select(
                AbnormalSignal.pattern_id,
                AbnormalSignal.scan_level,
                func.count(),
            )
            .where(AbnormalSignal.trade_date == trade_date)
            .group_by(AbnormalSignal.pattern_id, AbnormalSignal.scan_level)
        )
        out: dict[str, dict[str, int]] = {}
        for pid, level, cnt in self._session.execute(stmt).all():
            out.setdefault(pid, {})
            out[pid][f"L{level}"] = int(cnt)
        return out

    def latest_trade_date(self) -> Optional[date]:
        stmt = select(func.max(AbnormalSignal.trade_date))
        return self._session.scalar(stmt)

    @staticmethod
    def _hit_dict(o: AbnormalSignal) -> dict:
        return {
            "trade_date": o.trade_date,
            "code": o.code,
            "pattern_id": o.pattern_id,
            "scan_level": o.scan_level,
            "pattern_score": float(o.pattern_score),
            "pattern_rank": o.pattern_rank,
            "reasons": o.reasons or [],
            "risk_flags": o.risk_flags or [],
            "score_components": o.score_components,
            "inputs_snapshot": o.inputs_snapshot,
        }


@dataclass
class Repositories:
    stock: StockRepository
    kline: KlineRepository
    financial: FinancialRepository
    valuation: ValuationRepository
    feature: FeatureRepository
    market: MarketRepository
    sync_state: SyncStateRepository
    job_log: JobLogRepository
    quality: QualityRepository
    relation: RelationRepository
    abnormal: AbnormalRepository


def build_repositories(session: Session) -> Repositories:
    return Repositories(
        stock=SQLAStockRepository(session),
        kline=SQLAKlineRepository(session),
        financial=SQLAFinancialRepository(session),
        valuation=SQLAValuationRepository(session),
        feature=SQLAFeatureRepository(session),
        market=SQLAMarketRepository(session),
        sync_state=SQLASyncStateRepository(session),
        job_log=SQLAJobLogRepository(session),
        quality=SQLAQualityRepository(session),
        relation=SQLARelationRepository(session),
        abnormal=SQLAAbnormalRepository(session),
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
