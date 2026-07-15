"""数据库迁移 / 建表。

当前策略：
- 第一版用 Base.metadata.create_all()，快速搭起来；
- 后续如果需要 schema 变更，切到 Alembic（已在依赖里）。

同时负责初始种子数据：
- 内置股票池：ALL / HS300 / ZZ500 / CUSTOM_DEFAULT
- 内置策略：BREAKOUT_20D / MOMENTUM_MA / VALUE_GROWTH
- feature_meta 初始条目
"""
from __future__ import annotations

from datetime import datetime

from loguru import logger
from sqlalchemy import Engine, inspect
from sqlalchemy.orm import Session

from quant_system.database.models import (
    ALL_MODELS,
    Base,
    FeatureMeta,
    Strategy,
    StockPool,
)


# ============ 种子数据 ============

SEED_STOCK_POOLS = [
    ("ALL", "全 A 股", "ALL", "全市场（约 5300 只，含 ST/新股，需应用层过滤）"),
    ("HS300", "沪深 300", "INDEX", "沪深 300 成分股，覆盖大盘蓝筹"),
    ("ZZ500", "中证 500", "INDEX", "中证 500 成分股，覆盖中盘"),
    ("CUSTOM_DEFAULT", "自定义默认池", "CUSTOM", "从 config.stock_pool.custom_codes 加载"),
]

SEED_STRATEGIES = [
    (
        "BREAKOUT_20D", "20 日突破策略", "technical",
        "20 日新高 + 量能放大 + 站上 MA20", "v1.0",
    ),
    (
        "MOMENTUM_MA", "均线多头趋势策略", "momentum",
        "MA5>MA10>MA20 + MACD 金叉 + 20 日上涨", "v1.0",
    ),
    (
        "VALUE_GROWTH", "低估成长策略", "value",
        "PE 低 + ROE 高 + 净利润和营收正增长", "v1.0",
    ),
]

SEED_FEATURE_META = [
    # (name, category, description)
    ("return_5d", "return", "5 日收益率"),
    ("return_20d", "return", "20 日收益率"),
    ("ma5", "trend", "5 日移动均线"),
    ("ma20", "trend", "20 日移动均线"),
    ("ma_bull_arrange", "trend", "均线多头排列：MA5>MA10>MA20"),
    ("macd", "momentum", "MACD 主线"),
    ("macd_golden_cross", "momentum", "MACD 当日金叉"),
    ("rsi_14", "momentum", "14 日 RSI"),
    ("atr_14", "volatility", "14 日 ATR"),
    ("boll_width", "volatility", "布林带宽度"),
    ("volume_ratio", "volume", "量比：当日量 / MA20 量"),
    ("turnover_rate", "volume", "换手率"),
    ("break_high_20d", "breakout", "是否突破 20 日新高"),
    ("pe_ttm", "fundamental", "TTM 市盈率"),
    ("roe_latest", "fundamental", "最近报告期 ROE"),
    ("net_profit_yoy_latest", "fundamental", "最近报告期净利润同比"),
]


def create_all_tables(engine: Engine, drop_first: bool = False) -> None:
    """建立所有表。drop_first=True 会先 drop（危险，仅测试用）。"""
    if drop_first:
        logger.warning("drop_first=True，正在删除所有现有表")
        Base.metadata.drop_all(engine)

    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    created = inspector.get_table_names()
    logger.info("建表完成，共 {} 张表", len(created))
    for name in sorted(created):
        logger.debug("  - {}", name)


def seed_initial_data(session: Session) -> None:
    """种子数据。幂等：已存在则跳过。"""
    now = datetime.utcnow()

    # 股票池
    for code, name, pool_type, desc in SEED_STOCK_POOLS:
        if session.get(StockPool, code) is None:
            session.add(StockPool(
                code=code, name=name, pool_type=pool_type,
                description=desc, is_active=True, updated_at=now,
            ))
            logger.debug("seed stock_pool: {}", code)

    # 策略
    for code, name, category, desc, version in SEED_STRATEGIES:
        if session.get(Strategy, code) is None:
            session.add(Strategy(
                code=code, name=name, category=category,
                description=desc, params=None, version=version,
                is_active=True, created_at=now,
            ))
            logger.debug("seed strategy: {}", code)

    # 特征元数据
    for name, category, description in SEED_FEATURE_META:
        if session.get(FeatureMeta, name) is None:
            session.add(FeatureMeta(
                name=name, category=category, description=description,
                version="v1.0", is_active=True,
            ))

    session.flush()
    logger.info("种子数据写入完成")


def init_db(drop_first: bool = False) -> None:
    """建表 + 写种子数据。CLI init-db 的主体。"""
    from quant_system.infra.db import get_engine, session_scope

    engine = get_engine()
    create_all_tables(engine, drop_first=drop_first)
    with session_scope() as session:
        seed_initial_data(session)
    logger.info("数据库初始化完成: {}", engine.url)


def check_schema_integrity() -> tuple[bool, list[str]]:
    """检查 22 张表是否齐全。返回 (ok, missing_tables)。"""
    from quant_system.infra.db import get_engine

    engine = get_engine()
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    expected = {m.__tablename__ for m in ALL_MODELS}
    missing = expected - existing
    return len(missing) == 0, sorted(missing)
