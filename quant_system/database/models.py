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
# 估值域（1 张）
# ============================================================================

class DailyValuation(Base):
    """日频估值快照：PE/PB/PS/市值。市值单位=亿元。

    与 financial_snapshot（季频报告期）分离：估值随行情每日变化，
    走独立数据源（东财 stock_value_em / 百度兜底），按 (code, trade_date) 存储。
    """
    __tablename__ = "daily_valuation"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    pe_ttm: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    pe_static: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    pb: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    ps_ttm: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    market_cap: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    float_market_cap: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_dval_date_code", "trade_date", "code"),
        Index("ix_dval_date_pe", "trade_date", "pe_ttm"),
        {"sqlite_with_rowid": False},
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

    # 突破 / 位置（异动 Pattern Engine 用）
    high_20d: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    break_high_20d: Mapped[Optional[bool]] = mapped_column(Boolean)
    high_60d: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    break_high_60d: Mapped[Optional[bool]] = mapped_column(Boolean)
    high_120d: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    break_high_120d: Mapped[Optional[bool]] = mapped_column(Boolean)
    high_250d: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    low_250d: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    break_high_250d: Mapped[Optional[bool]] = mapped_column(Boolean)
    prior_high_20d: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    prior_high_60d: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    prior_high_250d: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    break_distance_20d: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    break_distance_60d: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    break_distance_250d: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    amplitude_20d: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    range_pos_250d: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    ma250: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    ma250_bias: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    ma5_cross_ma10: Mapped[Optional[bool]] = mapped_column(Boolean)

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
# 关系域（2 张）
# ============================================================================

class StockRelationship(Base):
    """股票关系长表：一行 = 一个 relation_type × window × 股票对 的关系。

    - 对称方法（PEARSON 等）按 code_a < code_b 规范化，只存一行；
    - 有向方法（LEAD_LAG）用 direction 字段承载方向，不破坏规范；
    - 只保留最新快照（service 每次 replace）。
    大表：自然复合主键 + WITHOUT ROWID（对齐 daily_kline/daily_feature 约定）。
    """
    __tablename__ = "stock_relationship"
    relation_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    window: Mapped[str] = mapped_column(String(8), primary_key=True)
    stock_code_a: Mapped[str] = mapped_column(String(16), primary_key=True)
    stock_code_b: Mapped[str] = mapped_column(String(16), primary_key=True)
    calc_date: Mapped[date] = mapped_column(Date, primary_key=True)
    relation_value: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    is_same_industry: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Similarity Framework：score=relation_value；以下为协议补齐字段
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    breakdown_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    meta_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        # a 侧查询走复合主键前缀 (relation_type, window, stock_code_a)，无需额外索引
        Index("ix_rel_b", "relation_type", "window", "stock_code_b"),      # 反向查「谁把我当邻居」
        Index("ix_rel_value", "relation_type", "window", "relation_value"),  # 全局强/负相关扫描
        {"sqlite_with_rowid": False},
    )


class StockRelationshipRun(Base):
    """关系计算批次 / 血缘表。对齐 backtest_task，用于幂等、复现、监控。"""
    __tablename__ = "stock_relationship_run"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    calc_date: Mapped[date] = mapped_column(Date, nullable=False)
    relation_type: Mapped[str] = mapped_column(String(16), nullable=False)
    windows: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    pool_code: Mapped[Optional[str]] = mapped_column(String(32))
    board_filter: Mapped[Optional[str]] = mapped_column(String(32))
    min_sample: Mapped[int] = mapped_column(Integer, nullable=False)
    value_threshold: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    max_neighbors: Mapped[int] = mapped_column(Integer, nullable=False)
    universe_size: Mapped[Optional[int]] = mapped_column(Integer)
    pair_evaluated: Mapped[Optional[int]] = mapped_column(Integer)
    pair_written: Mapped[Optional[int]] = mapped_column(Integer)
    code_hash: Mapped[Optional[str]] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # RUNNING/SUCCESS/FAILED
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    error_msg: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_rel_run_asof", "calc_date", "relation_type"),
        Index("ix_rel_run_status", "status"),
    )


# ============================================================================
# Stock Cluster Framework（3 张）
# ============================================================================

class StockClusterRun(Base):
    """一次聚类作业 / 血缘。graph_spec_json 为 SimilarityGraphRequest 完整序列化。"""
    __tablename__ = "stock_cluster_run"
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    calc_date: Mapped[date] = mapped_column(Date, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), nullable=False, default="pearson_w60")
    graph_spec_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    algo: Mapped[str] = mapped_column(String(16), nullable=False, default="LOUVAIN")
    resolution: Mapped[Optional[float]] = mapped_column(Numeric(8, 4))
    seed: Mapped[int] = mapped_column(Integer, nullable=False, default=42)
    universe_size: Mapped[Optional[int]] = mapped_column(Integer)
    edge_used: Mapped[Optional[int]] = mapped_column(Integer)
    n_clusters: Mapped[Optional[int]] = mapped_column(Integer)
    modularity: Mapped[Optional[float]] = mapped_column(Numeric(8, 4))
    max_cluster_size: Mapped[Optional[int]] = mapped_column(Integer)
    singleton_count: Mapped[Optional[int]] = mapped_column(Integer)
    params_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    error_msg: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_cluster_run_profile", "profile_id", "calc_date"),
        Index("ix_cluster_run_status", "status"),
    )


class StockCluster(Base):
    __tablename__ = "stock_cluster"
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cluster_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_internal_similarity: Mapped[Optional[float]] = mapped_column(Numeric(8, 4))
    density: Mapped[Optional[float]] = mapped_column(Numeric(8, 4))
    representative_code: Mapped[Optional[str]] = mapped_column(String(16))
    top_members_json: Mapped[Optional[list[Any]]] = mapped_column(JSON)


class StockClusterMember(Base):
    __tablename__ = "stock_cluster_member"
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    cluster_id: Mapped[int] = mapped_column(Integer, nullable=False)
    centrality: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    rank_in_cluster: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_cluster_member_cid", "run_id", "cluster_id", "rank_in_cluster"),
    )


# ============================================================================
# 异动 Pattern Engine（2 张）
# ============================================================================

class AbnormalSignal(Base):
    """异动模式命中：一行 = 某日某股某个 Pattern。"""
    __tablename__ = "abnormal_signal"
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    pattern_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    scan_level: Mapped[int] = mapped_column(Integer, nullable=False)
    pattern_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    pattern_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    global_rank: Mapped[Optional[int]] = mapped_column(Integer)
    reasons: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    risk_flags: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    score_components: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    inputs_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    params_version: Mapped[str] = mapped_column(String(32), nullable=False)
    feature_version: Mapped[Optional[str]] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_abn_pat_rank", "trade_date", "pattern_id", "pattern_rank"),
        Index("ix_abn_pat_level", "trade_date", "pattern_id", "scan_level"),
        {"sqlite_with_rowid": False},
    )


class AbnormalRun(Base):
    """异动扫描批次 / 血缘。"""
    __tablename__ = "abnormal_run"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    patterns_enabled: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    params_version: Mapped[str] = mapped_column(String(32), nullable=False)
    universe_size: Mapped[Optional[int]] = mapped_column(Integer)
    per_pattern_stats: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    written_count: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    error_msg: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_abn_run_date", "trade_date"),
        Index("ix_abn_run_status", "status"),
    )


# ============================================================================
# Pattern Definition 域（2 张）
# ============================================================================

class PatternDefinitionRow(Base):
    """可编辑 Pattern 模板元数据（当前 published 指针 + 状态）。"""

    __tablename__ = "pattern_definition"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name_en: Mapped[Optional[str]] = mapped_column(String(128))
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    published_version: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class PatternDefinitionRevision(Base):
    """Definition 版本快照；version=__draft__ 表示当前草稿。"""

    __tablename__ = "pattern_definition_revision"
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True
    )
    pattern_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("pattern_definition.id"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    body_json: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint("pattern_id", "version", name="uq_pattern_def_rev"),
        Index("ix_pattern_def_rev_pid", "pattern_id", "created_at"),
    )


# ============================================================================
# Event Statistics 域（2 张）— 见 design/13-event-statistics-engine.md
# ============================================================================

class PatternEventRun(Base):
    """事件统计 Run：锁定 Entry + Observation 配置 + 聚合缓存。"""

    __tablename__ = "pattern_event_run"
    run_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    entry_pattern_id: Mapped[str] = mapped_column(String(32), nullable=False)
    entry_version: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="observation")
    outcome_version: Mapped[Optional[str]] = mapped_column(String(32))
    universe_spec: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    horizon_bars: Mapped[int] = mapped_column(Integer, nullable=False)
    return_horizons_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    calendar: Mapped[str] = mapped_column(String(64), nullable=False, default="ChinaTradingCalendar")
    anchor_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="t1_close")
    price_adj: Mapped[str] = mapped_column(String(16), nullable=False, default="qfq")
    dedup_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="cooldown_h")
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregation_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    error_msg: Mapped[Optional[str]] = mapped_column(Text)
    event_count: Mapped[Optional[int]] = mapped_column(Integer)
    summary_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    job_id: Mapped[Optional[str]] = mapped_column(String(32))
    progress: Mapped[Optional[float]] = mapped_column(Numeric(8, 6))
    progress_msg: Mapped[Optional[str]] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)

    __table_args__ = (
        Index("ix_pev_run_pattern", "entry_pattern_id", "created_at"),
        Index("ix_pev_run_status", "status"),
        Index("ix_pev_run_job", "job_id"),
    )


class PatternEvent(Base):
    """单条 Pattern 事件 + Observation 宽列事实指标。"""

    __tablename__ = "pattern_event"
    event_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True
    )
    run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("pattern_event_run.run_id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_similarity: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    match_explain_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    entry_snapshot_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    tags_json: Mapped[Optional[list[Any]]] = mapped_column(JSON)

    return_1: Mapped[Optional[float]] = mapped_column(Numeric(12, 6))
    return_3: Mapped[Optional[float]] = mapped_column(Numeric(12, 6))
    return_5: Mapped[Optional[float]] = mapped_column(Numeric(12, 6))
    return_10: Mapped[Optional[float]] = mapped_column(Numeric(12, 6))
    return_20: Mapped[Optional[float]] = mapped_column(Numeric(12, 6))
    return_60: Mapped[Optional[float]] = mapped_column(Numeric(12, 6))
    return_horizon: Mapped[Optional[float]] = mapped_column(Numeric(12, 6))
    mfe: Mapped[Optional[float]] = mapped_column(Numeric(12, 6))
    mae: Mapped[Optional[float]] = mapped_column(Numeric(12, 6))
    max_drawdown: Mapped[Optional[float]] = mapped_column(Numeric(12, 6))
    volatility: Mapped[Optional[float]] = mapped_column(Numeric(12, 6))
    bull_ratio: Mapped[Optional[float]] = mapped_column(Numeric(12, 6))
    up_days: Mapped[Optional[int]] = mapped_column(Integer)
    continuous_up_days: Mapped[Optional[int]] = mapped_column(Integer)
    highest_day: Mapped[Optional[int]] = mapped_column(Integer)
    lowest_day: Mapped[Optional[int]] = mapped_column(Integer)
    time_to_mfe: Mapped[Optional[int]] = mapped_column(Integer)
    time_to_mae: Mapped[Optional[int]] = mapped_column(Integer)
    forward_bars_available: Mapped[Optional[int]] = mapped_column(Integer)
    forward_status: Mapped[str] = mapped_column(String(16), nullable=False, default="insufficient")

    extra_metrics_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    outcome_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)

    __table_args__ = (
        UniqueConstraint("run_id", "code", "signal_date", name="uq_pattern_event_run_code_date"),
        Index("ix_pev_run_date", "run_id", "signal_date"),
        Index("ix_pev_run_sim", "run_id", "entry_similarity"),
        Index("ix_pev_run_ret5", "run_id", "return_5"),
        Index("ix_pev_run_ret10", "run_id", "return_10"),
        Index("ix_pev_run_mfe", "run_id", "mfe"),
        Index("ix_pev_run_mae", "run_id", "mae"),
        Index("ix_pev_run_fwd", "run_id", "forward_status"),
    )


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
# Earnings Event Analytics（3 张）
# ============================================================================

class EarningsDisclosureEvent(Base):
    """业绩披露原始事件（Event Builder 产出）。"""

    __tablename__ = "earnings_disclosure_event"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    report_period: Mapped[Optional[date]] = mapped_column(Date)
    event_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(512))
    parent_np: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    parent_np_yoy: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    predict_type: Mapped[Optional[str]] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="em_notice")
    raw_extra_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "code", "event_date", "event_kind", "report_period",
            name="uq_eea_event_identity",
        ),
        Index("ix_eea_event_date", "event_date"),
        Index("ix_eea_event_kind_date", "event_kind", "event_date"),
        Index("ix_eea_event_code_date", "code", "event_date"),
    )


class EarningsEventPanel(Base):
    """Event Panel：Raw + Derived + Targets 宽表。"""

    __tablename__ = "earnings_event_panel"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    report_period: Mapped[Optional[date]] = mapped_column(Date)
    event_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    # Raw
    parent_np: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    parent_np_yoy: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    predict_type: Mapped[Optional[str]] = mapped_column(String(32))
    title: Mapped[Optional[str]] = mapped_column(String(512))
    raw_extra_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    # Derived
    annualized_parent_np: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    pe_ttm: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    mcap: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    ln_mcap: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 6))
    ey_event: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 8))
    ey_event_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 6))
    pe_event: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    pe_rel: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 6))
    yoy_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 6))
    range_pos_250d: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    range_pos_750d: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    dist_to_high_250d: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    cluster_run_id: Mapped[Optional[str]] = mapped_column(String(64))
    cluster_id: Mapped[Optional[int]] = mapped_column(Integer)
    valuation_date: Mapped[Optional[date]] = mapped_column(Date)
    feature_asof_date: Mapped[Optional[date]] = mapped_column(Date)
    derived_extra_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    # Targets
    ret_5d: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    ret_10d: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    ret_20d: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    target_extra_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    # Meta
    panel_tag: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    built_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_eea_panel_tag_date", "panel_tag", "event_date"),
        Index("ix_eea_panel_kind", "panel_tag", "event_kind"),
        Index("ix_eea_panel_cluster", "panel_tag", "cluster_run_id", "cluster_id"),
        Index("ix_eea_panel_event", "event_id"),
    )


class EarningsAnalyticsModel(Base):
    """EEA 拟合结果（Regression + Fair Value 元数据）。"""

    __tablename__ = "earnings_analytics_model"
    model_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    panel_tag: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    model_scope: Mapped[str] = mapped_column(String(16), nullable=False)  # all|interim|annual
    cluster_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    cluster_id: Mapped[Optional[int]] = mapped_column(Integer)
    cluster_run_id: Mapped[Optional[str]] = mapped_column(String(64))
    backend_id: Mapped[str] = mapped_column(String(32), nullable=False, default="ols")
    estimator_id: Mapped[str] = mapped_column(String(32), nullable=False, default="median_ey")
    feature_cols_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    filter_spec_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    n_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    regression_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    fair_value_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ready")

    __table_args__ = (
        Index("ix_eea_model_scope", "panel_tag", "model_scope", "cluster_mode"),
        Index("ix_eea_model_fitted", "fitted_at"),
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
    # 估值
    DailyValuation,
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
    # 关系 / Similarity 边
    StockRelationship, StockRelationshipRun,
    # 聚类
    StockClusterRun, StockCluster, StockClusterMember,
    # 异动
    AbnormalSignal, AbnormalRun,
    # Pattern Definition
    PatternDefinitionRow, PatternDefinitionRevision,
    # Event Statistics
    PatternEventRun, PatternEvent,
    # Earnings Event Analytics
    EarningsDisclosureEvent, EarningsEventPanel, EarningsAnalyticsModel,
    # 系统
    JobRunLog, DataSyncState, DataQualityCheck,
]

assert len(ALL_MODELS) == 37, "表数量应为 37"
