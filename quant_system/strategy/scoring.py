"""综合评分器。

约定：
- 输入：某只股票在多条策略上的 StrategyResult 列表 + 该股当日特征行
- 输出：final_score（0-100）+ 分维度得分 + 汇总理由

维度：
- 技术面 40 分：technical / momentum / breakout 类策略的最高子分
- 资金面 30 分：量比 + 换手率 + 换手率变化（近似「资金活跃度」）
- 基本面 30 分：value 类策略的子分（若没触发，用 ROE + 增长率的简单打分）
- 多策略加成：每额外命中一个策略 +5，最多 +15
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from quant_system.config.settings import get_settings
from quant_system.strategy.base_strategy import SIGNAL_HIT, StrategyResult


@dataclass
class ScoredStock:
    code: str
    final_score: float
    tech_score: float
    capital_score: float
    fundamental_score: float
    hit_strategies: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    # 保留原始 StrategyResult，写入 signal 表时用
    raw_results: list[StrategyResult] = field(default_factory=list)


def _to_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        f = float(x)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _score_capital(row: pd.Series) -> tuple[float, list[str]]:
    """资金面 30 分：量比 + 换手率 + 换手率变化。"""
    reasons: list[str] = []
    vr = _to_float(row.get("volume_ratio"))
    tr = _to_float(row.get("turnover_rate"))
    tc = _to_float(row.get("turnover_change"))

    # 量比：1.0→10 分基础；每 +0.5 → +2 分，封顶 15
    if vr is not None and vr >= 1.0:
        vr_score = min(15.0, 10.0 + (vr - 1.0) * 4)
        if vr >= 1.5:
            reasons.append(f"量比 {vr:.2f}x")
    else:
        vr_score = max(0.0, 10.0 - abs(1.0 - (vr or 0.0)) * 5)

    # 换手率：1%→5，3%→10，>5%→10（换手过高扣分留给以后做）
    if tr is not None:
        tr_score = min(10.0, tr * 3)
        if tr >= 3:
            reasons.append(f"换手率 {tr:.2f}%")
    else:
        tr_score = 0.0

    # 换手率变化：正向变化奖励
    if tc is not None and tc > 0:
        tc_score = min(5.0, tc * 2)
    else:
        tc_score = 0.0

    return round(vr_score + tr_score + tc_score, 2), reasons


def _score_fundamental_from_features(row: pd.Series) -> tuple[float, list[str]]:
    """基本面 30 分兜底（当 value 策略没触发时用）。"""
    reasons: list[str] = []
    roe = _to_float(row.get("roe_latest"))
    np_yoy = _to_float(row.get("net_profit_yoy_latest"))
    rev_yoy = _to_float(row.get("revenue_yoy_latest"))
    pe = _to_float(row.get("pe_ttm"))

    if roe is None and np_yoy is None and rev_yoy is None and pe is None:
        return 0.0, reasons  # 完全无基本面数据

    score = 0.0
    # ROE 10-30 → 0-15
    if roe is not None:
        score += min(15.0, max(0.0, (roe - 5.0) / 25.0 * 15))
        if roe >= 12:
            reasons.append(f"ROE {roe:.1f}%")
    # 净利润增速 0-50 → 0-10
    if np_yoy is not None:
        score += min(10.0, max(0.0, np_yoy / 50.0 * 10))
        if np_yoy > 20:
            reasons.append(f"净利润同比 {np_yoy:.1f}%")
    # PE 合理性 15-40 → 5-0，越低越好（简化处理）
    if pe is not None and pe > 0:
        if pe <= 30:
            score += 5.0
    return round(min(30.0, score), 2), reasons


def score_stock(
    code: str,
    results: list[StrategyResult],
    feature_row: pd.Series,
) -> ScoredStock:
    """给一只股票综合打分。"""
    settings = get_settings()
    scoring_cfg = settings.scoring

    # ---- 技术面：technical + momentum + breakout 类，取最高子分归一到 40 ----
    tech_results = [r for r in results if r.hit and r.category in {"technical", "momentum"}]
    if tech_results:
        max_sub = max(r.sub_score for r in tech_results)
        tech_score = round(max_sub / 100.0 * scoring_cfg.weight_technical, 2)
    else:
        tech_score = 0.0

    # ---- 资金面：从特征直接算 ----
    cap_raw, cap_reasons = _score_capital(feature_row)
    # 归一到 30
    capital_score = round(cap_raw / 30.0 * scoring_cfg.weight_capital, 2)

    # ---- 基本面：优先用 value 策略结果 ----
    value_hits = [r for r in results if r.hit and r.category == "value"]
    fund_reasons: list[str] = []
    if value_hits:
        max_sub = max(r.sub_score for r in value_hits)
        fundamental_score = round(max_sub / 100.0 * scoring_cfg.weight_fundamental, 2)
    else:
        fund_raw, fund_reasons = _score_fundamental_from_features(feature_row)
        fundamental_score = round(fund_raw / 30.0 * scoring_cfg.weight_fundamental, 2)

    # ---- 多策略命中加成 ----
    hit_results = [r for r in results if r.hit]
    hit_count = len(hit_results)
    if hit_count >= 2:
        bonus = min(scoring_cfg.max_bonus, (hit_count - 1) * scoring_cfg.multi_hit_bonus)
    else:
        bonus = 0.0

    final_score = round(min(100.0, tech_score + capital_score + fundamental_score + bonus), 2)

    # ---- 汇总理由 ----
    reasons: list[str] = []
    for r in hit_results:
        reasons.extend(r.reasons)
    reasons.extend(cap_reasons)
    reasons.extend(fund_reasons)
    if bonus > 0:
        reasons.append(f"多策略共振（命中 {hit_count} 条策略，+{bonus:.0f}）")

    # 去重保序
    seen: set[str] = set()
    deduped = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            deduped.append(r)

    return ScoredStock(
        code=code,
        final_score=final_score,
        tech_score=tech_score,
        capital_score=capital_score,
        fundamental_score=fundamental_score,
        hit_strategies=[r.strategy_code for r in hit_results],
        reasons=deduped,
        raw_results=results,
    )
