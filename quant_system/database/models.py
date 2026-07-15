"""ORM 模型（SQLAlchemy 2.0 Mapped 风格）。

对应 v2 数据库设计，共 22 张表。

数据库中立原则（R8）：
- 只用 SQLAlchemy 类型抽象，不用 SQLite 独有语法；
- sqlite_with_rowid=False 通过 __table_args__ 传递，其他方言会忽略；
- JSON 查询在 repository 层完成，不在 SQL 里做。
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 ORM 模型基类。"""


# ============================================================================
# 基础域（4 张）
# ============================================================================

class Industry(Base):
    __tablename__ = "industry"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    parent_code: Mapped[Optional[str]] = mapped_column(String(16))


class StockBasic(Base):
    __tablename__ = "stock_basic"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False)
    industry_code: Mapped[Optional[str]] = mapped_column(String(16), ForeignKey("industry.code"))
    industry_name: Mapped[Optional[str]] = mapped_column(String(64))
    list_date: Mapped[Optional[date]] = mapped_column(Date)
    delist_date: Mapped[Optional[date]] = mapped_column(Date)
    is_st: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    total_share: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    float_share: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    market_cap: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_stock_basic_industry", "industry_code"),
        Index("ix_stock_basic_status", "is_st", "delist_date"),
    )


class StockPool(Base):
    __tablename__ = "stock_pool"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    pool_type: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class StockPoolMember(Base):
    __tablename__ = "stock_pool_member"
    pool_code: Mapped[str] = mapped_column(String(32), ForeignKey("stock_pool.code"), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), ForeignKey("stock_basic.code"), primary_key=True)
    in_date: Mapped[date] = mapped_column(Date, primary_key=True)
    out_date: Mapped[Optional[date]] = mapped_column(Date)
    weight: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))

    __table_args__ = (Index("ix_pool_member_active", "pool_code", "out_date"),)


# ============================================================================
# 行情域（1 张）
# ============================================================================

class DailyKline(Base):
    __tablename__ = "daily_kline"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    pre_close: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    turnover_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    pct_change: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    adj_factor: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("1.0"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_kline_date_code", "trade_date", "code"),
        Index("ix_kline_date_pct", "trade_date", "pct_change"),
        {"sqlite_with_rowid": False},
    )


# ============================================================================
# 财务域（1 张）
# ============================================================================

class FinancialSnapshot(Base):
    __tablename__ = "financial_snapshot"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    report_period: Mapped[date] = mapped_column(Date, primary_key=True)
    ann_date: Mapped[date] = mapped_column(Date, nullable=False)
    pe_ttm: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    pb: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    ps_ttm: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    roe: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    roa: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    net_profit: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    revenue: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    net_profit_yoy: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    revenue_yoy: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    gross_margin: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    debt_to_asset: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_fin_ann", "ann_date"),
        Index("ix_fin_period_roe", "report_period", "roe"),
        Index("ix_fin_period_pe", "report_period", "pe_ttm"),
    )


# ============================================================================
# 市场域（3 张）
# ============================================================================

class IndexDaily(Base):
    __tablename__ = "index_daily"
    index_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    pct_change: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))

    __table_args__ = (Index("ix_index_daily_date", "trade_date"),)


class MarketDaily(Base):
    __tablename__ = "market_daily"
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    up_count: Mapped[int] = mapped_column(Integer, nullable=False)
    down_count: Mapped[int] = mapped_column(Integer, nullable=False)
    flat_count: Mapped[int] = mapped_column(Integer, nullable=False)
    limit_up_count: Mapped[int] = mapped_column(Integer, nullable=False)
    limit_down_count: Mapped[int] = mapped_column(Integer, nullable=False)
    broken_limit_up_count: Mapped[Optional[int]] = mapped_column(Integer)
    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    north_money_net: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class MarketFeatureDaily(Base):
    __tablename__ = "market_feature_daily"
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    market_trend: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sentiment_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    limit_up_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    up_down_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    turnover_ma5: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    hs300_ma20_position: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


# ============================================================================
# 特征域（2 张）
# ============================================================================

class DailyFeature(Base):
    __tablename__ = "daily_feature"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)

    # 收益
    return_1d: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    return_5d: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    return_20d: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    return_60d: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))

    # 趋势
    ma5: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    ma10: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    ma20: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    ma60: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    ma_position: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    ma_bull_arrange: Mapped[Optional[bool]] = mapped_column(Boolean)

    # 动量
    macd: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    macd_signal: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    macd_hist: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    macd_golden_cross: Mapped[Optional[bool]] = mapped_column(Boolean)
    rsi_14: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    kdj_k: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    kdj_d: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    kdj_j: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))

    # 波动
    atr_14: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    boll_upper: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    boll_mid: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    boll_lower: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    boll_width: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))

    # 量能
    volume_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    turnover_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    turnover_change: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    amount_ma5: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))

    # 突破
    high_20d: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    break_high_20d: Mapped[Optional[bool]] = mapped_column(Boolean)

    # 基本面快照 + 血缘
    pe_ttm: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    pb: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    roe_latest: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    net_profit_yoy_latest: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    revenue_yoy_latest: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    market_cap: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    financial_snapshot_date: Mapped[Optional[date]] = mapped_column(Date)
    financial_ann_date: Mapped[Optional[date]] = mapped_column(Date)

    # 向量预留
    vector_version: Mapped[Optional[str]] = mapped_column(String(16))
    embedding_id: Mapped[Optional[str]] = mapped_column(String(64))

    # 扩展 + 元
    ext: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    feature_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_feat_date_code", "trade_date", "code"),
        Index("ix_feat_date_mcap", "trade_date", "market_cap"),
        Index("ix_feat_date_pe", "trade_date", "pe_ttm"),
        Index("ix_feat_date_break", "trade_date", "break_high_20d"),
        Index("ix_feat_date_gcross", "trade_date", "macd_golden_cross"),
        Index("ix_feat_ann_date", "financial_ann_date"),
        Index("ix_feat_vec_version", "vector_version"),
        Index("ix_feat_embed", "embedding_id"),
        {"sqlite_with_rowid": False},
    )


class FeatureMeta(Base):
    __tablename__ = "feature_meta"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# ============================================================================
# 策略域（4 张）
# ============================================================================

class Strategy(Base):
    __tablename__ = "strategy"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    params: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class StrategySignal(Base):
    __tablename__ = "strategy_signal"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    code: Mapped[str] = mapped_column(String(16), ForeignKey("stock_basic.code"), nullable=False)
    strategy_code: Mapped[str] = mapped_column(String(32), ForeignKey("strategy.code"), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(16), nullable=False)  # HIT/WATCH/NEAR_MISS/FILTERED
    hit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    filter_reason: Mapped[Optional[str]] = mapped_column(String(64))
    near_miss_gap: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4))
    sub_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    final_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    reasons: Mapped[Optional[list[str]]] = mapped_column(JSON)
    feature_snapshot_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    market_trend: Mapped[Optional[int]] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("trade_date", "code", "strategy_code", name="uk_signal_date_code_strategy"),
        Index("ix_signal_strategy_date", "strategy_code", "trade_date"),
        Index("ix_signal_code_date", "code", "trade_date"),
        Index("ix_signal_date_hit_score", "trade_date", "hit", "final_score"),
        Index("ix_signal_date_type", "trade_date", "signal_type"),
        Index("ix_signal_strategy_type_date", "strategy_code", "signal_type", "trade_date"),
        Index("ix_signal_strategy_market", "strategy_code", "market_trend"),
    )


class StrategySignalFeature(Base):
    __tablename__ = "strategy_signal_feature"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    signal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("strategy_signal.id"), unique=True, nullable=False
    )
    feature_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    feature_version: Mapped[str] = mapped_column(String(16), nullable=False)


class StrategyPerformance(Base):
    __tablename__ = "strategy_performance"
    strategy_code: Mapped[str] = mapped_column(String(32), ForeignKey("strategy.code"), primary_key=True)
    eval_date: Mapped[date] = mapped_column(Date, primary_key=True)
    lookback_days: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_count: Mapped[int] = mapped_column(Integer, nullable=False)
    win_count: Mapped[int] = mapped_column(Integer, nullable=False)
    win_rate_5d: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4))
    win_rate_10d: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4))
    win_rate_20d: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4))
    avg_return_5d: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    avg_return_10d: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    avg_return_20d: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    max_drawdown: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    sharpe: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


# ============================================================================
# 回测域（2 张）
# ============================================================================

class BacktestTask(Base):
    __tablename__ = "backtest_task"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    task_name: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_code: Mapped[str] = mapped_column(String(32), ForeignKey("strategy.code"), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(16), nullable=False)
    strategy_code_hash: Mapped[Optional[str]] = mapped_column(String(40))
    params_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    pool_code: Mapped[str] = mapped_column(String(32), ForeignKey("stock_pool.code"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    benchmark_code: Mapped[Optional[str]] = mapped_column(String(16))
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    rebalance_freq: Mapped[Optional[str]] = mapped_column(String(16))
    position_sizing: Mapped[Optional[str]] = mapped_column(String(32))
    max_positions: Mapped[Optional[int]] = mapped_column(Integer)
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0.0003"), nullable=False)
    slippage_bps: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    feature_version: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # PENDING/RUNNING/SUCCESS/FAILED
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    __table_args__ = (
        Index("ix_bt_strategy_time", "strategy_code", "created_at"),
        Index("ix_bt_status", "status"),
    )


class BacktestResult(Base):
    __tablename__ = "backtest_result"
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("backtest_task.id"), primary_key=True
    )
    # 收益
    total_return: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    annual_return: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    benchmark_return: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    alpha: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    beta: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    # 风险
    max_drawdown: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    max_drawdown_start: Mapped[Optional[date]] = mapped_column(Date)
    max_drawdown_end: Mapped[Optional[date]] = mapped_column(Date)
    max_drawdown_days: Mapped[Optional[int]] = mapped_column(Integer)
    volatility: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    # 风险调整
    sharpe: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    sortino: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    calmar: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    # 交易
    trade_count: Mapped[Optional[int]] = mapped_column(Integer)
    win_count: Mapped[Optional[int]] = mapped_column(Integer)
    win_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4))
    avg_win: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    avg_loss: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    profit_factor: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    avg_holding_days: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    # 产物
    equity_curve_path: Mapped[Optional[str]] = mapped_column(String(255))
    trade_log_path: Mapped[Optional[str]] = mapped_column(String(255))
    report_html_path: Mapped[Optional[str]] = mapped_column(String(255))
    extra_metrics: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_br_sharpe", "sharpe"),
        Index("ix_br_annual", "annual_return"),
    )


# ============================================================================
# 报告域（2 张）
# ============================================================================

class DailyReport(Base):
    __tablename__ = "daily_report"
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    market_trend: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sentiment_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    top_n: Mapped[int] = mapped_column(Integer, nullable=False)
    md_path: Mapped[Optional[str]] = mapped_column(String(255))
    html_path: Mapped[Optional[str]] = mapped_column(String(255))
    summary: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class DailyReportItem(Base):
    __tablename__ = "daily_report_item"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, ForeignKey("daily_report.trade_date"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    final_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    tech_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    capital_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    fundamental_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    hit_strategies: Mapped[Optional[list[str]]] = mapped_column(JSON)
    reasons: Mapped[Optional[list[str]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (Index("ix_report_item_date_rank", "trade_date", "rank"),)


# ============================================================================
# 系统域（3 张）
# ============================================================================

class JobRunLog(Base):
    __tablename__ = "job_run_log"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # RUNNING/SUCCESS/FAILED
    trade_date: Mapped[Optional[date]] = mapped_column(Date)
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    error_msg: Mapped[Optional[str]] = mapped_column(Text)
    stats: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)

    __table_args__ = (Index("ix_job_name_time", "job_name", "start_at"),)


class DataSyncState(Base):
    __tablename__ = "data_sync_state"
    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    entity_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_sync_date: Mapped[Optional[date]] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class DataQualityCheck(Base):
    __tablename__ = "data_quality_check"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    check_date: Mapped[date] = mapped_column(Date, nullable=False)
    check_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)  # INFO/WARN/ERROR
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_key: Mapped[Optional[str]] = mapped_column(String(32))
    trade_date: Mapped[Optional[date]] = mapped_column(Date)
    issue: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    resolution_note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_dqc_date_sev", "check_date", "severity"),
        Index("ix_dqc_type_resolved", "check_type", "resolved"),
        Index("ix_dqc_entity", "entity_type", "entity_key", "check_date"),
    )


# ============================================================================
# 导出清单（便于 migrations 使用）
# ============================================================================

ALL_MODELS = [
    # 基础
    Industry, StockBasic, StockPool, StockPoolMember,
    # 行情
    DailyKline,
    # 财务
    FinancialSnapshot,
    # 市场
    IndexDaily, MarketDaily, MarketFeatureDaily,
    # 特征
    DailyFeature, FeatureMeta,
    # 策略
    Strategy, StrategySignal, StrategySignalFeature, StrategyPerformance,
    # 回测
    BacktestTask, BacktestResult,
    # 报告
    DailyReport, DailyReportItem,
    # 系统
    JobRunLog, DataSyncState, DataQualityCheck,
]

assert len(ALL_MODELS) == 22, "表数量应为 22"
