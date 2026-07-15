"""选股编排（v2）。

流程（阶段 A）：
1. 读某日 daily_feature → DataFrame
2. 板块过滤（QS_BOARD_FILTER）
3. 数据质量前置过滤（DQ 黑名单）
4. **[v2 新增]** L2 硬风险否决 → 淘汰的入 SelectionReport.hard_filtered
5. **[v2 新增]** 一次性 batch 查 kline OHLC（用于一字板判定）
6. 遍历策略跑 evaluate()
7. 按 code 聚合 → **[v2]** 共振门控 + 维度自适应打分
8. **[v2]** 淘汰的（<2 维度 或 共振度不足）也入 hard_filtered
9. final_score 降序取 top_n
10. 写 strategy_signal 表

阶段 A：regime 恒为 UNKNOWN（等阶段 C 加 detect_regime()）。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
from loguru import logger
from sqlalchemy import select

from quant_system.config.settings import Settings, get_settings
from quant_system.data.repository import Repositories
from quant_system.data_quality.checker import get_blacklist_for_selector
from quant_system.database.models import DailyFeature, DailyKline, DataQualityCheck
from quant_system.infra.board import filter_codes
from quant_system.strategy.base_strategy import (
    SIGNAL_HIT,
    BaseStrategy,
    StrategyResult,
)
from quant_system.strategy.breakout_strategy import BreakoutStrategy
from quant_system.strategy.momentum_strategy import MomentumStrategy
from quant_system.strategy.risk_filter import apply_hard_filters
from quant_system.strategy.scoring import (
    REASON_INSUFFICIENT_DIMENSIONS,
    REASON_RESONANCE_TOO_LOW,
    ScoredStock,
    _parse_enabled_categories,
    score_stock,
)
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
    after_hard_filter: int = 0                # v2 新增
    hit_count: int = 0
    top_stocks: list[ScoredStock] = field(default_factory=list)
    strategy_hit_stats: dict[str, int] = field(default_factory=dict)
    # v2 新增：被硬过滤 & scoring 淘汰的股票
    # 每项 {"code": "000001.SZ", "reason": "RSI_TOO_HIGH", "stage": "hard_filter" | "scoring"}
    hard_filtered: list[dict] = field(default_factory=list)
    regime: str = "UNKNOWN"                   # 阶段 A 恒为 UNKNOWN，阶段 C 才填

    def summary(self) -> dict:
        # 按 reason 聚合硬过滤明细
        by_reason: dict[str, int] = {}
        for f in self.hard_filtered:
            by_reason[f["reason"]] = by_reason.get(f["reason"], 0) + 1
        return {
            "trade_date": self.trade_date.isoformat(),
            "regime": self.regime,
            "total_features": self.total_features,
            "after_board_filter": self.after_board_filter,
            "after_dq_filter": self.after_dq_filter,
            "after_hard_filter": self.after_hard_filter,
            "hit_count": self.hit_count,
            "top_n": len(self.top_stocks),
            "hard_filtered_total": len(self.hard_filtered),
            "hard_filtered_by_reason": by_reason,
            "strategy_hits": self.strategy_hit_stats,
        }


# ============================================================================
# 工厂
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
# 辅助：特征 ORM → DataFrame
# ============================================================================

def _features_to_dataframe(rows: list[DailyFeature]) -> pd.DataFrame:
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


def _load_kline_snapshot(
    trade_date: date, codes: list[str], repos: Repositories,
) -> dict[str, dict[str, float | None]]:
    """一次性 batch 查当日 OHLC，避免 N+1。用于一字板判定。"""
    if not codes:
        return {}
    session = repos.feature._session  # type: ignore[attr-defined]
    result: dict[str, dict[str, float | None]] = {}
    # SQLite 变量数上限：分批
    BATCH = 500
    for i in range(0, len(codes), BATCH):
        chunk = codes[i:i + BATCH]
        stmt = select(
            DailyKline.code, DailyKline.open, DailyKline.high,
            DailyKline.low, DailyKline.close, DailyKline.pct_change,
        ).where(
            DailyKline.trade_date == trade_date,
            DailyKline.code.in_(chunk),
        )
        for code, o, h, l, c, pct in session.execute(stmt).all():
            result[code] = {
                "open": float(o) if o is not None else None,
                "high": float(h) if h is not None else None,
                "low":  float(l) if l is not None else None,
                "close": float(c) if c is not None else None,
                "pct_change": float(pct) if pct is not None else None,
            }
    return result


def _load_dq_warn_codes(trade_date: date, repos: Repositories) -> set[str]:
    """查当日有 WARN 级别质量问题的股票（用于 soft_penalty）。"""
    session = repos.feature._session  # type: ignore[attr-defined]
    stmt = select(DataQualityCheck.entity_key).where(
        DataQualityCheck.check_date == trade_date,
        DataQualityCheck.severity == "WARN",
        DataQualityCheck.entity_type == "STOCK",
    )
    return {row[0] for row in session.execute(stmt).all() if row[0]}


# ============================================================================
# 主入口
# ============================================================================

def run_selector(
    trade_date: date,
    repos: Repositories,
    settings: Settings | None = None,
    top_n: int | None = None,
) -> SelectionReport:
    """执行完整选股链路（v2）。"""
    settings = settings or get_settings()
    top_n = top_n or settings.report.top_n

    report = SelectionReport(trade_date=trade_date)

    # ---- 1. 读特征 ----
    features = repos.feature.read_features_on(trade_date)
    df = _features_to_dataframe(features)
    report.total_features = len(df)
    if df.empty:
        logger.warning("selector: {} 无特征，跳过", trade_date)
        return report

    # ---- 2. 板块过滤 ----
    allowed = set(filter_codes(df["code"].tolist(), settings.board_filter))
    df = df[df["code"].isin(allowed)].reset_index(drop=True)
    report.after_board_filter = len(df)
    logger.info("selector: 板块过滤 {} → {}", report.total_features, report.after_board_filter)

    # ---- 3. DQ 黑名单 ----
    blacklist = get_blacklist_for_selector(
        trade_date, repos, settings.data_quality.filter_level.value,
    )
    if blacklist:
        df = df[~df["code"].isin(blacklist)].reset_index(drop=True)
    report.after_dq_filter = len(df)
    logger.info("selector: DQ 过滤 → {}（剔除 {}）", report.after_dq_filter, len(blacklist))

    if df.empty:
        return report

    # ---- 4. [v2] batch 查当日 kline OHLC ----
    codes_all = df["code"].tolist()
    kline_map = _load_kline_snapshot(trade_date, codes_all, repos)

    # ---- 5. [v2] L2 硬风险否决 ----
    df, hard_filtered = apply_hard_filters(df, kline_map, settings.hard_filter)
    for f in hard_filtered:
        f["stage"] = "hard_filter"
    report.hard_filtered.extend(hard_filtered)
    report.after_hard_filter = len(df)

    if df.empty:
        logger.warning("selector: 硬过滤后无股票，返回空 Top")
        return report

    # ---- 6. [v2] DQ WARN 集合 ----
    dq_warn_codes = _load_dq_warn_codes(trade_date, repos)

    # ---- 7. 跑策略 ----
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

    # ---- 8. 按 code 聚合评分 + 共振门控 ----
    by_code: dict[str, list[StrategyResult]] = defaultdict(list)
    for r in all_results:
        by_code[r.code].append(r)

    # 解析启用的大类（v1.2：关闭类别后共振门槛不下调；给 WARN）
    enabled_cats = _parse_enabled_categories(settings.resonance.enabled_categories)
    if not enabled_cats:
        logger.warning(
            "resonance: enabled_categories='{}' 解析为空，退化为全部启用",
            settings.resonance.enabled_categories,
        )
        enabled_cats = {"trend", "reversal", "volume_price", "fundamental"}

    scored: list[ScoredStock] = []
    dropped_at_scoring: list[dict] = []

    for code, results in by_code.items():
        if not any(r.hit for r in results):
            # 无 HIT 的股票（只有 WATCH）不进 Top，也不进 hard_filtered
            continue
        row = df[df["code"] == code]
        if row.empty:
            # 可能被硬过滤剔除了（罕见：策略拿到的是过滤前的 df？其实这里已经是过滤后了，防御性判断）
            continue
        feature_row = row.iloc[0]

        result = score_stock(
            code=code,
            results=results,
            feature_row=feature_row,
            regime=report.regime,
            enabled_cats=enabled_cats,
            dq_warn=(code in dq_warn_codes),
        )

        if isinstance(result, ScoredStock):
            scored.append(result)
        else:
            # 淘汰：result = (None, reason)
            _, reason = result
            dropped_at_scoring.append({"code": code, "reason": reason, "stage": "scoring"})

    report.hard_filtered.extend(dropped_at_scoring)

    # 统计淘汰明细日志
    if dropped_at_scoring:
        by_reason: dict[str, int] = {}
        for d in dropped_at_scoring:
            by_reason[d["reason"]] = by_reason.get(d["reason"], 0) + 1
        summary = ", ".join(f"{k}={v}" for k, v in sorted(by_reason.items()))
        logger.info(
            "scoring 阶段淘汰 {} 只（明细: {}）",
            len(dropped_at_scoring), summary,
        )

    report.hit_count = len(scored)

    # ---- 9. 排序取 TopN ----
    scored.sort(key=lambda s: s.final_score, reverse=True)
    report.top_stocks = scored[:top_n]

    # 若 Top 为空 & enabled_cats 非默认，给出提示
    if not scored:
        logger.warning(
            "selector: 命中 & 过共振门控的股票为 0。"
            "若 enabled_categories 已收窄，可能过严；当前配置='{}'",
            settings.resonance.enabled_categories,
        )

    # ---- 10. 写 strategy_signal ----
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

    final_score_map = {s.code: s.final_score for s in scored}

    from sqlalchemy import delete

    from quant_system.database.models import StrategySignal
    session = repos.feature._session  # type: ignore[attr-defined]

    session.execute(
        delete(StrategySignal).where(StrategySignal.trade_date == trade_date)
    )

    inserted = 0
    for r in all_results:
        if level == "HIT_ONLY" and r.signal_type != SIGNAL_HIT:
            continue
        if level == "HIT_FILTERED" and r.signal_type not in {"HIT", "FILTERED"}:
            continue
        if level == "WITH_WATCH" and r.signal_type not in {"HIT", "WATCH", "FILTERED"}:
            continue

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
