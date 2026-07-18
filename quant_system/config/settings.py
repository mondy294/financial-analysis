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
    # 抢不到写锁时的最大等待（毫秒）。0 = 立刻报 "database is locked"。
    # 调长可让短时锁冲突排队等待而非直接崩（如 pattern.scan 撞上 similarity.refresh）。
    sqlite_busy_timeout_ms: int = 60000


class DataConfig(BaseModel):
    cache_dir: Path = Path("./data_cache/akshare")
    cache_ttl_seconds: int = 86400               # 磁盘缓存 TTL
    akshare_retry_times: int = 3
    akshare_retry_backoff: float = 2.0
    akshare_request_interval_ms: int = 200       # 单次调用间隔下限（毫秒）
    # 节流模式：
    #   True  = 全局节流（跨线程共享计时，QPS 上限 = 1000/interval_ms，并发无收益）
    #   False = 每线程节流（每 worker 独立计时，QPS 上限 = concurrency × 1000/interval_ms）
    # 默认 False（腾讯数据源较稳定，追求真并发）；数据源不稳时改回 True 保守
    throttle_global: bool = False
    concurrency: int = 4                          # kline/financial 拉取的并发线程数（1 = 关闭并发）
    kline_start_date: str = "2015-01-01"         # 首次拉数的起始日（覆盖 2015 牛/2018 熊/2020 疫情/2021 抱团/2022 下跌/2023-2025 震荡）
    financial_lookback_quarters: int = 12        # 财报拉多少个季度
    # 拉数据阶段的板块过滤（数据层唯一使用板块过滤的地方，独立于 QS_BOARD_FILTER）
    # 支持：MAIN / MAIN,GEM / MAIN,STAR / MAIN,GEM,STAR / ALL
    # 默认只拉主板（腾讯 hist_tx 对北交所支持差、量小不划算）
    # 想拉全部：QS_DATA__FETCH_BOARDS=ALL
    fetch_boards: str = "MAIN"


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
    """综合评分权重（可配置，避免硬编码）。

    注：v2 加权公式已改用 REGIME_WEIGHTS（下方常量）+ 维度自适应归一。
    这里的 weight_* 保留是为了兼容老代码路径，默认作为 UNKNOWN regime 的兜底权重。
    共振加分改用 ResonanceConfig.bonus_per_cat。
    """
    weight_technical: float = 40.0
    weight_capital: float = 30.0
    weight_fundamental: float = 30.0
    # 老参数（v1 遗留，v2 不再使用；保留是为了平滑升级不破坏旧配置）
    multi_hit_bonus: float = 5.0
    max_bonus: float = 15.0


# ============ 策略 v2 新增配置 ============

# 类别顺序常量（用于 resonance_categories 输出、日志一致性）
CATEGORY_ORDER: tuple[str, ...] = ("trend", "reversal", "volume_price", "fundamental")

# 现有 3 条策略的 category 映射（阶段 A 不动策略源码，在 scoring 里做映射）
# key = StrategyResult.category（策略源码里声明的），value = v2 归属的大类
STRATEGY_CATEGORY_MAP: dict[str, str] = {
    "technical": "trend",         # BREAKOUT_20D → trend
    "momentum":  "trend",         # MOMENTUM_MA  → trend
    "breakout":  "trend",         # 兼容别名
    "value":     "fundamental",   # VALUE_GROWTH → fundamental
    # 阶段 B 起，新策略应直接在源码里声明为 trend/reversal/volume_price/fundamental
    "reversal":     "reversal",
    "volume_price": "volume_price",
    "fundamental":  "fundamental",
    "trend":        "trend",
}

# 按 regime 的动态权重（v2）
# 每项：tech / capital / fund 之和 = 100；bonus_per_cat = 每多共振 1 个大类的加分
REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "BULL_STRONG": {"tech": 45, "capital": 30, "fund": 25, "bonus_per_cat": 5},
    "BULL_WEAK":   {"tech": 40, "capital": 25, "fund": 35, "bonus_per_cat": 5},
    "BEAR_WEAK":   {"tech": 30, "capital": 20, "fund": 50, "bonus_per_cat": 8},
    "BEAR_STRONG": {"tech": 20, "capital": 10, "fund": 70, "bonus_per_cat": 10},
    # 阶段 A regime 恒为 UNKNOWN，用中性权重（三档平均 + 中等 bonus）
    "UNKNOWN":     {"tech": 40, "capital": 25, "fund": 35, "bonus_per_cat": 5},
}


class HardFilterConfig(BaseModel):
    """L2 硬否决规则阈值（v1.2）。

    命中任一 → 直接淘汰，不参与后续评分。
    被淘汰的股票只放 SelectionReport.hard_filtered（内存 + 日报），不落库。
    """
    # RSI 极端超买 → 淘汰
    rsi_max: float = 85.0
    # 短期暴涨（板块自适应）→ 淘汰
    return_5d_main: float = 20.0        # 主板
    return_5d_gem:  float = 30.0        # 创业板
    return_5d_star: float = 30.0        # 科创板
    return_5d_bse:  float = 30.0        # 北交所
    # 量价背离（突破新高但缩量）→ 淘汰
    divergence_vol_min: float = 0.8
    # 一字板：O==H==L==C 且 |pct_change| ≥ 涨跌停幅 × 该系数
    one_word_limit_ratio: float = 0.98
    # 涨跌停幅（按板块）— 用于一字板判定
    price_limit_main: float = 10.0
    price_limit_gem:  float = 20.0
    price_limit_star: float = 20.0
    price_limit_bse:  float = 30.0
    # 关键指标缺失（任一 NULL）→ 淘汰
    require_ma20: bool = True
    require_macd: bool = True
    require_rsi14: bool = True


class ResonanceConfig(BaseModel):
    """L4 共振门控（v1.2）。

    共振度 = 命中的不同大类（category）数。
    不满足 regime 对应的最小共振度 → 淘汰（不进 Top 排序）。
    """
    bull_strong_min: int = 1
    bull_weak_min:   int = 2
    bear_weak_min:   int = 2
    bear_strong_min: int = 3
    # UNKNOWN regime（阶段 A 用）— 保持较宽松，避免"改动过激"
    unknown_min: int = 1
    # BEAR_WEAK 特别要求：共振里必须包含 Fundamental
    bear_weak_require_fundamental: bool = True
    bear_strong_require_fundamental: bool = True
    # 启用的大类（可关闭某类，如 "trend,fundamental"）
    # v1.2 语义：关闭后共振门槛不自动下调，selector 会给出 WARN 日志
    enabled_categories: str = "trend,reversal,volume_price,fundamental"


class SoftPenaltyConfig(BaseModel):
    """L5 软风险扣分（v1.2）。

    没到硬淘汰线但值得警惕：final_score 扣分 + risk_flags 标记。
    假突破（fake_break_5d）阶段 A 不启用，等 B1 落地。
    """
    # RSI 接近超买（75-85）
    rsi_75_85: float = 5.0
    rsi_warn_lower: float = 75.0
    # 短期涨过多（板块自适应，主板 15-20% / 创业板 20-30%）
    return_5d_upper: float = 3.0
    return_5d_warn_main: float = 15.0
    return_5d_warn_gem:  float = 20.0
    return_5d_warn_star: float = 20.0
    return_5d_warn_bse:  float = 20.0
    # 数据质量 WARN
    dq_warn: float = 2.0
    # 布林带宽异常
    boll_width_high: float = 3.0
    boll_width_threshold: float = 15.0
    # ATR/close 偏高（v1.1 迁自 L2 硬过滤）
    atr_high: float = 5.0
    atr_ratio_threshold: float = 0.08          # ATR/close ≥ 8%
    # 假突破（v1.2 挪到 B1；阶段 A 不启用）
    # fake_break: float = 5.0


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


class AIConfig(BaseModel):
    """AI 分析配置（DeepSeek / OpenAI 兼容接口）。

    默认关闭，配置 QS_AI__ENABLED=true 且填了 QS_AI__API_KEY 后启用。
    在报告生成阶段被调用，为每只 Top 股票产生一段建议。
    """
    enabled: bool = False
    provider: str = "deepseek"                     # 目前只支持 deepseek（openai 兼容）
    base_url: str = "https://api.deepseek.com"
    api_key: str = ""
    model: str = "deepseek-v4-pro"
    concurrency: int = 5                           # 并发调用数（Top N 股票同时分析）
    timeout_sec: int = 60
    max_tokens: int = 800
    reasoning_effort: str = "high"                 # deepseek-v4-pro 特有：low/medium/high
    thinking_enabled: bool = True                  # 是否启用 thinking 模式


class PatternConfig(BaseModel):
    """形态扫描配置。"""
    # 按股票并行匹配的线程数；1 = 关闭并发
    # 环境变量：QS_PATTERN__CONCURRENCY
    concurrency: int = 4


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
    ai: AIConfig = Field(default_factory=AIConfig)
    pattern: PatternConfig = Field(default_factory=PatternConfig)
    # v2 策略新增
    hard_filter: HardFilterConfig = Field(default_factory=HardFilterConfig)
    resonance: ResonanceConfig = Field(default_factory=ResonanceConfig)
    soft_penalty: SoftPenaltyConfig = Field(default_factory=SoftPenaltyConfig)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """全局单例入口。任何模块用 `from quant_system.config.settings import get_settings`。"""
    return Settings()
