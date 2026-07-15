"""全局配置。

设计要点：
1. 用 pydantic-settings 从 .env / 环境变量加载，带类型校验；
2. 所有可调参数集中在这里，业务代码零 magic number；
3. 分组用嵌套 BaseModel，便于 IDE 补全和阅读；
4. 单例 get_settings() 缓存，避免重复解析。

本文件只定义结构和默认值，实现细节由后续阶段填充。
"""
from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ============ 枚举定义（业务语义集中在这里，避免字符串散落）============

class Env(str, Enum):
    DEV = "dev"
    PROD = "prod"


class StockPoolCode(str, Enum):
    ALL = "ALL"
    HS300 = "HS300"
    ZZ500 = "ZZ500"
    CUSTOM = "CUSTOM"


class SignalRecordLevel(str, Enum):
    """策略信号写库级别。数值越大记录越全，表膨胀风险越大。"""
    HIT_ONLY = "HIT_ONLY"              # 只写 HIT
    HIT_FILTERED = "HIT_FILTERED"      # 写 HIT + FILTERED（默认，推荐）
    WITH_WATCH = "WITH_WATCH"          # HIT + FILTERED + WATCH
    ALL = "ALL"                        # 全写（含 NEAR_MISS，表会膨胀 5-10 倍）


class DQFilterLevel(str, Enum):
    """数据质量前置过滤级别。"""
    OFF = "OFF"                        # 不过滤（不推荐生产）
    ERROR = "ERROR"                    # 只剔除 ERROR（默认）
    WARN_AND_ABOVE = "WARN_AND_ABOVE"  # 剔除 WARN + ERROR（严格模式）


# ============ 分组配置 ============

class DatabaseConfig(BaseModel):
    url: str = "sqlite:///./data_cache/quant.db"
    echo_sql: bool = False
    pool_size: int = 5
    # SQLite PRAGMA（仅 dialect=sqlite 时生效）
    sqlite_journal_mode: str = "WAL"
    sqlite_synchronous: str = "NORMAL"
    sqlite_cache_size_kb: int = 262144           # 256MB
    sqlite_mmap_size_bytes: int = 268435456      # 256MB


class DataConfig(BaseModel):
    cache_dir: Path = Path("./data_cache/akshare")
    cache_ttl_seconds: int = 86400               # 磁盘缓存 TTL
    akshare_retry_times: int = 3
    akshare_retry_backoff: float = 2.0
    akshare_request_interval_ms: int = 200       # 限流：两次请求最小间隔
    kline_start_date: str = "2015-01-01"         # 首次拉数的起始日（覆盖 2015 牛/2018 熊/2020 疫情/2021 抱团/2022 下跌/2023-2025 震荡）
    financial_lookback_quarters: int = 12        # 财报拉多少个季度


class StockPoolConfig(BaseModel):
    """股票池配置。

    - pool = ALL / HS300 / ZZ500 时忽略 custom_codes
    - pool = CUSTOM 时使用 custom_codes 列表
    """
    pool: StockPoolCode = StockPoolCode.HS300
    custom_codes: list[str] = Field(default_factory=list)
    exclude_st: bool = True
    exclude_new_listed_days: int = 60            # 剔除上市不足 N 天的新股
    exclude_suspended: bool = True               # 剔除停牌股


class FeatureConfig(BaseModel):
    version: str = "v1.0"
    # 技术指标参数
    ma_windows: list[int] = Field(default_factory=lambda: [5, 10, 20, 60])
    macd_params: dict[str, int] = Field(default_factory=lambda: {"fast": 12, "slow": 26, "signal": 9})
    rsi_window: int = 14
    kdj_params: dict[str, int] = Field(default_factory=lambda: {"n": 9, "m1": 3, "m2": 3})
    atr_window: int = 14
    boll_params: dict[str, int | float] = Field(default_factory=lambda: {"window": 20, "std": 2.0})
    breakout_window: int = 20
    volume_ma_window: int = 20


class StrategyConfig(BaseModel):
    """策略参数快照（每次修改这里，写入 backtest_task.params_snapshot）"""
    breakout: dict = Field(default_factory=lambda: {
        "high_window": 20,
        "volume_ratio_min": 1.5,
        "require_above_ma20": True,
    })
    momentum: dict = Field(default_factory=lambda: {
        "return_window": 20,
        "min_return": 0.05,
        "require_ma_bull_arrange": True,
        "require_macd_golden": True,
    })
    value_growth: dict = Field(default_factory=lambda: {
        "pe_max": 30.0,
        "pe_min": 0.0,
        "roe_min": 12.0,
        "net_profit_yoy_min": 0.0,
        "revenue_yoy_min": 0.0,
    })


class ScoringConfig(BaseModel):
    """综合评分权重（可配置，避免硬编码）"""
    weight_technical: float = 40.0
    weight_capital: float = 30.0
    weight_fundamental: float = 30.0
    # 触发多个策略的加成
    multi_hit_bonus: float = 5.0                 # 每多命中一个策略 +5
    max_bonus: float = 15.0


class SignalConfig(BaseModel):
    record_level: SignalRecordLevel = SignalRecordLevel.HIT_FILTERED
    # NEAR_MISS 的判定阈值（差多少算差一点）
    near_miss_tolerance: float = 0.02            # 2%


class DataQualityConfig(BaseModel):
    filter_level: DQFilterLevel = DQFilterLevel.ERROR
    # 触发 ABNORMAL_PRICE 的阈值（涨跌停 20%，主板 10%，创业板 20%；这里用最宽的）
    abnormal_pct_threshold: float = 22.0
    # 特征空值率告警阈值
    feature_null_rate_warn: float = 0.05
    # 数据同步落后天数
    sync_stale_days: int = 3


class ReportConfig(BaseModel):
    output_dir: Path = Path("./reports")
    top_n: int = 20
    formats: list[Literal["md", "html"]] = Field(default_factory=lambda: ["md", "html"])
    embed_charts: bool = True
    include_dq_summary: bool = True              # 附数据质量摘要


class SchedulerConfig(BaseModel):
    timezone: str = "Asia/Shanghai"
    # 每日任务时间
    daily_hour: int = 15
    daily_minute: int = 30
    # 是否跳过非交易日
    skip_non_trading_day: bool = True


class BacktestConfig(BaseModel):
    default_initial_capital: float = 1_000_000.0
    default_commission_rate: float = 0.0003
    default_slippage_bps: int = 5
    default_max_positions: int = 10
    equity_curve_dir: Path = Path("./reports/backtest")


class LoggingConfig(BaseModel):
    log_dir: Path = Path("./logs")
    level: str = "INFO"
    rotation: str = "50 MB"
    retention: str = "30 days"


# ============ 顶层 Settings ============

class Settings(BaseSettings):
    """全局配置入口。

    加载优先级：
    1. 环境变量（QS_ 前缀）
    2. .env 文件
    3. 类默认值
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="QS_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    env: Env = Env.DEV
    timezone: str = "Asia/Shanghai"

    # 板块过滤（数据层不用，selector/backtest 读特征时用）
    # 支持：MAIN / MAIN,GEM / MAIN,STAR / MAIN,GEM,STAR / ALL
    board_filter: str = "MAIN"

    # 分组配置
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    stock_pool: StockPoolConfig = Field(default_factory=StockPoolConfig)
    feature: FeatureConfig = Field(default_factory=FeatureConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    signal: SignalConfig = Field(default_factory=SignalConfig)
    data_quality: DataQualityConfig = Field(default_factory=DataQualityConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """全局单例入口。任何模块用 `from quant_system.config.settings import get_settings`。"""
    return Settings()
