"""选股编排。

流程（严格保序）：
1. 读某日 daily_feature → DataFrame
2. **板块过滤**（QS_BOARD_FILTER）
3. **数据质量前置过滤**（DQ 黑名单）
4. 遍历 3 条策略跑 evaluate() → 各自 StrategyResult 列表
5. 按 code 聚合 → 综合评分 scoring.score_stock()
6. final_score 降序排列，取 top_n
7. 写 strategy_signal 表（配合 signal_record_level 控制 WATCH 是否写）

对外接口：run_selector(trade_date, repos, settings) → SelectionReport
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pandas as pd
from loguru import logger

from quant_system.config.settings import Settings, get_settings
from quant_system.data.repository import Repositories
from quant_system.data_quality.checker import get_blacklist_for_selector
from quant_system.database.models import DailyFeature
from quant_system.infra.board import filter_codes
from quant_system.strategy.base_strategy import (
    SIGNAL_HIT,
    SIGNAL_WATCH,
    BaseStrategy,
    StrategyResult,
)
from quant_system.strategy.breakout_strategy import BreakoutStrategy
from quant_system.strategy.momentum_strategy import MomentumStrategy
from quant_system.strategy.scoring import ScoredStock, score_stock
from quant_system.strategy.value_growth_strategy import ValueGrowthStrategy


# ============================================================================
# 报告结构
# ============================================================================

@dataclass
class SelectionReport:
    trade_date: date
    total_features: int = 0
    after_board_filter: int = 0
    after_dq_filter: int = 0
    hit_count: int = 0
    top_stocks: list[ScoredStock] = field(default_factory=list)
    strategy_hit_stats: dict[str, int] = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "trade_date": self.trade_date.isoformat(),
            "total_features": self.total_features,
            "after_board_filter": self.after_board_filter,
            "after_dq_filter": self.after_dq_filter,
            "hit_count": self.hit_count,
            "top_n": len(self.top_stocks),
            "strategy_hits": self.strategy_hit_stats,
        }


# ============================================================================
# 工厂：按 config 构造策略实例
# ============================================================================

def build_strategies(settings: Settings) -> list[BaseStrategy]:
    """未来加新策略只需要往这里 append。"""
    cfg = settings.strategy
    return [
        BreakoutStrategy(cfg.breakout),
        MomentumStrategy(cfg.momentum),
        ValueGrowthStrategy(cfg.value_growth),
    ]


# ============================================================================
# 主入口
# ============================================================================

def _features_to_dataframe(rows: list[DailyFeature]) -> pd.DataFrame:
    """把 ORM 对象转成 DataFrame，供策略消费。"""
    records: list[dict] = []
    for r in rows:
        records.append({
            "code": r.code,
            "trade_date": r.trade_date,
            "return_1d": r.return_1d, "return_5d": r.return_5d,
            "return_20d": r.return_20d, "return_60d": r.return_60d,
            "ma5": r.ma5, "ma10": r.ma10, "ma20": r.ma20, "ma60": r.ma60,
            "ma_position": r.ma_position, "ma_bull_arrange": r.ma_bull_arrange,
            "macd": r.macd, "macd_signal": r.macd_signal,
            "macd_hist": r.macd_hist, "macd_golden_cross": r.macd_golden_cross,
            "rsi_14": r.rsi_14, "kdj_k": r.kdj_k, "kdj_d": r.kdj_d, "kdj_j": r.kdj_j,
            "atr_14": r.atr_14, "boll_upper": r.boll_upper, "boll_mid": r.boll_mid,
            "boll_lower": r.boll_lower, "boll_width": r.boll_width,
            "volume_ratio": r.volume_ratio, "turnover_rate": r.turnover_rate,
            "turnover_change": r.turnover_change,
            "high_20d": r.high_20d, "break_high_20d": r.break_high_20d,
            "pe_ttm": r.pe_ttm, "pb": r.pb,
            "roe_latest": r.roe_latest,
            "net_profit_yoy_latest": r.net_profit_yoy_latest,
            "revenue_yoy_latest": r.revenue_yoy_latest,
            "market_cap": r.market_cap,
            "financial_ann_date": r.financial_ann_date,
        })
    return pd.DataFrame(records)


def run_selector(
    trade_date: date,
    repos: Repositories,
    settings: Settings | None = None,
    top_n: int | None = None,
) -> SelectionReport:
    """执行完整选股链路。"""
    settings = settings or get_settings()
    top_n = top_n or settings.report.top_n

    report = SelectionReport(trade_date=trade_date)

    # 1. 读特征
    features = repos.feature.read_features_on(trade_date)
    df = _features_to_dataframe(features)
    report.total_features = len(df)
    if df.empty:
        logger.warning("selector: {} 无特征，跳过", trade_date)
        return report

    # 2. 板块过滤
    allowed = set(filter_codes(df["code"].tolist(), settings.board_filter))
    df = df[df["code"].isin(allowed)].reset_index(drop=True)
    report.after_board_filter = len(df)
    logger.info("selector: 板块过滤 {} → {}", report.total_features, report.after_board_filter)

    # 3. 数据质量黑名单
    blacklist = get_blacklist_for_selector(
        trade_date, repos, settings.data_quality.filter_level.value,
    )
    if blacklist:
        df = df[~df["code"].isin(blacklist)].reset_index(drop=True)
    report.after_dq_filter = len(df)
    logger.info("selector: DQ 过滤 → {}（剔除 {}）", report.after_dq_filter, len(blacklist))

    if df.empty:
        return report

    # 4. 跑策略
    strategies = build_strategies(settings)
    all_results: list[StrategyResult] = []
    for strat in strategies:
        try:
            res = strat.evaluate(df)
            all_results.extend(res)
            hit_cnt = sum(1 for r in res if r.hit)
            report.strategy_hit_stats[strat.code] = hit_cnt
            logger.info("strategy {}: {} 命中", strat.code, hit_cnt)
        except Exception as e:
            logger.exception("策略 {} 执行失败: {}", strat.code, e)

    # 5. 按 code 聚合评分
    by_code: dict[str, list[StrategyResult]] = defaultdict(list)
    for r in all_results:
        by_code[r.code].append(r)

    scored: list[ScoredStock] = []
    for code, results in by_code.items():
        if not any(r.hit for r in results):
            # 只有 WATCH 的股票，暂不进入综合评分（未来可开）
            continue
        row = df[df["code"] == code].iloc[0]
        scored.append(score_stock(code, results, row))

    report.hit_count = len(scored)

    # 6. 排序取 TopN
    scored.sort(key=lambda s: s.final_score, reverse=True)
    report.top_stocks = scored[:top_n]

    # 7. 写 strategy_signal
    _write_signals(trade_date, all_results, scored, repos, settings)

    return report


def _write_signals(
    trade_date: date,
    all_results: list[StrategyResult],
    scored: list[ScoredStock],
    repos: Repositories,
    settings: Settings,
) -> None:
    """把策略触发写入 strategy_signal 表。按 signal_record_level 控制记录范围。"""
    level = settings.signal.record_level.value
    now = datetime.utcnow()

    # 快速查找每只股票的 final_score
    final_score_map = {s.code: s.final_score for s in scored}

    # 用 upsert（unique 约束: date + code + strategy_code）
    from sqlalchemy import delete

    from quant_system.database.models import StrategySignal
    session = repos.feature._session  # type: ignore[attr-defined]

    # 先删今日已有信号（重跑幂等）
    session.execute(
        delete(StrategySignal).where(StrategySignal.trade_date == trade_date)
    )

    inserted = 0
    for r in all_results:
        # 按 record_level 过滤
        if level == "HIT_ONLY" and r.signal_type != SIGNAL_HIT:
            continue
        if level == "HIT_FILTERED" and r.signal_type not in {"HIT", "FILTERED"}:
            continue
        if level == "WITH_WATCH" and r.signal_type not in {"HIT", "WATCH", "FILTERED"}:
            continue
        # ALL：全写

        session.add(StrategySignal(
            trade_date=trade_date,
            code=r.code,
            strategy_code=r.strategy_code,
            signal_type=r.signal_type,
            hit=r.hit,
            filter_reason=r.filter_reason,
            near_miss_gap=Decimal(str(r.near_miss_gap)) if r.near_miss_gap else None,
            sub_score=Decimal(str(round(r.sub_score, 2))),
            final_score=Decimal(str(final_score_map.get(r.code, 0.0))),
            reasons=r.reasons,
            feature_snapshot_id=None,
            market_trend=None,
            created_at=now,
        ))
        inserted += 1

    logger.info("strategy_signal 写入: {} 条 (level={})", inserted, level)
