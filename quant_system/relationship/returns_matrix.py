"""收益率宽表构建 + 上市时间/停牌对齐 + 缓存。

核心口径（对齐设计 §3）：
- 后复权价（close × adj_factor）算日收益率 pct_change；
- 停牌日（volume==0）收益率置 NaN；
- 不补 0 / 不 fill / 不插值；不同上市时间天然为 NaN；
- 两只股票配对时只用共同交易日交集（由下游 corr 的 pairwise 语义保证）。

产物：DataFrame，index=trade_date（升序），columns=sorted(codes)，值=日收益率。
列按代码升序排列，使下游取上三角 (i<j) 时天然满足 code_a < code_b 规范。
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import TYPE_CHECKING

import pandas as pd
from loguru import logger

from quant_system.infra import trading_calendar as tc
from quant_system.infra.cache import get_backend

if TYPE_CHECKING:
    from quant_system.data.repository import RelationRepository

# 窗口标签 → 交易日数量；FULL 表示全部可用区间
WINDOW_DAYS: dict[str, int | None] = {
    "W20": 20,
    "W60": 60,
    "W120": 120,
    "W250": 250,
    "FULL": None,
}

_CACHE_NAMESPACE = "relationship_returns"

# A 股单日理论最大涨幅（新股首日 ~+44%），|r| 超此阈值必为脏数据
# （复权因子跳变 / 停复牌错位 / 数据源错误），置 NaN 避免污染相关度。
MAX_ABS_RETURN = 1.1


def parse_windows(windows: list[str]) -> list[tuple[str, int | None]]:
    """把窗口标签列表解析成 [(label, days)]，校验合法性。"""
    out: list[tuple[str, int | None]] = []
    for w in windows:
        key = w.upper()
        if key not in WINDOW_DAYS:
            raise ValueError(f"未知窗口: {w}（可选 {list(WINDOW_DAYS)}）")
        out.append((key, WINDOW_DAYS[key]))
    return out


def max_window_days(windows: list[str], full_lookback: int) -> int:
    """本次计算需要的最大回看交易日数。FULL 用 full_lookback 上限。"""
    days: list[int] = []
    for _, d in parse_windows(windows):
        days.append(full_lookback if d is None else d)
    return max(days) if days else 250


def _cache_key(codes: list[str], calc_date: date, lookback: int) -> str:
    codes_digest = hashlib.sha256("|".join(codes).encode("utf-8")).hexdigest()[:16]
    return hashlib.sha256(
        f"{calc_date.isoformat()}|{lookback}|{len(codes)}|{codes_digest}".encode("utf-8")
    ).hexdigest()


def _start_date(calc_date: date, lookback: int) -> date:
    """回看 lookback 个交易日的起始日（多留 5 日 buffer 给 pct_change 首行）。"""
    try:
        return tc.previous_trading_day(calc_date, lookback + 5)
    except ValueError:
        # 日历范围不足：退化到自然日估算（宁可多取）
        return calc_date - timedelta(days=int((lookback + 5) * 1.6))


def build_returns_matrix(
    repos: "RelationRepository",
    codes: list[str],
    calc_date: date,
    lookback: int,
    *,
    use_cache: bool = True,
) -> pd.DataFrame:
    """构建收益率宽表。codes 会被排序去重。

    Args:
        repos: RelationRepository（提供 read_prices 批量读取）。
        codes: 计算宇宙。
        calc_date: 快照基准日（含）。
        lookback: 最大回看交易日数。
        use_cache: 是否用磁盘缓存（同一 calc_date + 宇宙 + lookback 复用）。
    """
    codes = sorted(set(codes))
    if not codes:
        return pd.DataFrame()

    key = _cache_key(codes, calc_date, lookback)
    backend = get_backend(_CACHE_NAMESPACE)
    if use_cache:
        hit = backend.get(key)
        if hit is not None:
            logger.debug("returns_matrix cache HIT key={}", key[:8])
            return hit

    start = _start_date(calc_date, lookback)
    logger.info(
        "构建收益率宽表：{} 只股票，区间 {} ~ {}（lookback={}）",
        len(codes), start, calc_date, lookback,
    )
    long_df = repos.read_prices(codes, start, calc_date)
    if long_df.empty:
        logger.warning("read_prices 返回空，无法构建收益率宽表")
        return pd.DataFrame()

    # 后复权收盘价；停牌日（volume==0）价格置 NaN，pct_change 前后天然剔除
    long_df["hfq_close"] = long_df["close"] * long_df["adj_factor"]
    long_df.loc[long_df["volume"] == 0, "hfq_close"] = pd.NA

    wide = long_df.pivot(index="trade_date", columns="code", values="hfq_close")
    wide = wide.sort_index()
    # 列补齐到完整宇宙并按代码升序（未上市/无数据列为全 NaN）
    wide = wide.reindex(columns=codes)
    wide = wide.astype("float64")

    returns = wide.pct_change()
    # 首行必为 NaN（无前收），交给 corr 的 min_periods 处理

    # 异常收益率剔除：复权因子跳变/停复牌错位会造出上千倍的假收益，
    # Pearson 对极值极敏感（单个离群点即可把无关股票拉到 corr≈1），必须前置清洗。
    extreme = returns.abs() > MAX_ABS_RETURN
    n_extreme = int(extreme.to_numpy().sum())
    if n_extreme:
        returns = returns.mask(extreme)
        logger.warning(
            "剔除 {} 个异常收益率(|r|>{})，多为复权因子/停复牌数据问题",
            n_extreme, MAX_ABS_RETURN,
        )

    if use_cache:
        backend.set(key, returns, ttl=None)
    return returns
