"""综合评分器（v2）。

对比 v1 的核心变化：
1. 共振度（category 去重后计数）替代 multi_hit_bonus，同类多命中不叠加
2. 加权公式改用 REGIME_WEIGHTS（regime 感知），阶段 A regime=UNKNOWN 用中性权重
3. **维度自适应归一 + 至少 2 维度硬约束**：<2 维度有数据 → 返回 None 触发淘汰
4. **基本面 NULL 时 final_score 上限 75**：防次新股无财报冲顶
5. 软风险扣分（soft penalty）+ risk_flags 输出
6. ScoredStock 新增 regime / resonance_count / resonance_categories / positive_reasons / risk_flags

保持不变：
- 技术分 T = max(命中的 trend/reversal/volume_price 类 sub_score)
- 资金分 C = _score_capital（量比 + 换手率 + 换手率变化）
- 基本面分 F = max(命中的 fundamental 类 sub_score)，无命中且有基本面数据时用 _score_fundamental_from_features 兜底
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from quant_system.config.settings import (
    CATEGORY_ORDER,
    REGIME_WEIGHTS,
    STRATEGY_CATEGORY_MAP,
    HardFilterConfig,
    ResonanceConfig,
    SoftPenaltyConfig,
    get_settings,
)
from quant_system.infra.board import Board, classify
from quant_system.strategy.base_strategy import StrategyResult


# ============================================================================
# 淘汰原因（scoring 阶段追加，与 risk_filter 的原因分开）
# ============================================================================

REASON_INSUFFICIENT_DIMENSIONS = "INSUFFICIENT_DIMENSIONS"
REASON_RESONANCE_TOO_LOW = "RESONANCE_TOO_LOW"

SCORING_REASON_DESCRIPTIONS: dict[str, str] = {
    REASON_INSUFFICIENT_DIMENSIONS: "维度数据不足（<2 维度有数据）",
    REASON_RESONANCE_TOO_LOW: "共振度不达 regime 门槛",
}


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class ScoredStock:
    """v2：新增 regime / resonance_count / resonance_categories / positive_reasons / risk_flags"""
    code: str
    final_score: float
    tech_score: float
    capital_score: float
    fundamental_score: float
    hit_strategies: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    raw_results: list[StrategyResult] = field(default_factory=list)

    # v2 新增（保持向后兼容：老代码不读这些字段也能跑）
    regime: str = "UNKNOWN"
    resonance_count: int = 0
    resonance_categories: list[str] = field(default_factory=list)
    positive_reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)


# ============================================================================
# 辅助函数
# ============================================================================

def _to_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        f = float(x)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _map_category(raw_category: str) -> str:
    """把策略源码里声明的 category 映射到 v2 的 4 大类。未知 → trend（保守）。"""
    return STRATEGY_CATEGORY_MAP.get(raw_category, "trend")


def _parse_enabled_categories(raw: str) -> set[str]:
    """解析 enabled_categories 配置字符串。"""
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    return {p for p in parts if p in CATEGORY_ORDER}


# ============================================================================
# 分维度打分
# ============================================================================

def _score_capital(row: pd.Series) -> tuple[float, list[str]]:
    """资金面得分（0-100，未归一）。返回 (score, reasons)。

    结构与 v1 一致：量比（0-50）+ 换手率（0-33）+ 换手率变化（0-17）。
    这里返回的是"资金分 raw"（0-100 尺度），selector 再乘 adjusted_w_cap/100 得到最终贡献。
    """
    reasons: list[str] = []
    vr = _to_float(row.get("volume_ratio"))
    tr = _to_float(row.get("turnover_rate"))
    tc = _to_float(row.get("turnover_change"))

    # 量比：0-50 分
    if vr is not None and vr >= 1.0:
        vr_score = min(50.0, 33.0 + (vr - 1.0) * 13.5)
        if vr >= 1.5:
            reasons.append(f"量比 {vr:.2f}x")
    elif vr is not None:
        vr_score = max(0.0, 33.0 - abs(1.0 - vr) * 16.5)
    else:
        vr_score = 0.0

    # 换手率：0-33 分
    if tr is not None:
        tr_score = min(33.0, tr * 10.0)
        if tr >= 3:
            reasons.append(f"换手率 {tr:.2f}%")
    else:
        tr_score = 0.0

    # 换手率变化：0-17 分
    if tc is not None and tc > 0:
        tc_score = min(17.0, tc * 6.8)
    else:
        tc_score = 0.0

    total = min(100.0, vr_score + tr_score + tc_score)
    return round(total, 2), reasons


def _score_fundamental_from_features(row: pd.Series) -> tuple[float, list[str]]:
    """基本面兜底得分（0-100，未归一），当 fundamental 策略未命中但有数据时用。"""
    reasons: list[str] = []
    roe = _to_float(row.get("roe_latest"))
    np_yoy = _to_float(row.get("net_profit_yoy_latest"))
    rev_yoy = _to_float(row.get("revenue_yoy_latest"))
    pe = _to_float(row.get("pe_ttm"))

    if roe is None and np_yoy is None and rev_yoy is None and pe is None:
        return 0.0, reasons  # 完全无基本面数据

    score = 0.0
    if roe is not None:
        score += min(50.0, max(0.0, (roe - 5.0) / 25.0 * 50))
        if roe >= 12:
            reasons.append(f"ROE {roe:.1f}%")
    if np_yoy is not None:
        score += min(33.0, max(0.0, np_yoy / 50.0 * 33))
        if np_yoy > 20:
            reasons.append(f"净利润同比 {np_yoy:.1f}%")
    if pe is not None and pe > 0 and pe <= 30:
        score += 17.0
    return round(min(100.0, score), 2), reasons


# ============================================================================
# 数据可用性判定
# ============================================================================

def _dims_available(row: pd.Series) -> tuple[bool, bool, bool]:
    """判定 tech / capital / fund 三个维度是否有数据。

    - tech: ma20 or macd or rsi_14 任一非 NULL（技术几乎必有）
    - capital: volume_ratio or turnover_rate 任一非 NULL
    - fund: pe_ttm or roe_latest 任一非 NULL
    """
    has_tech = any(
        _to_float(row.get(k)) is not None for k in ("ma20", "macd", "rsi_14")
    )
    has_cap = any(
        _to_float(row.get(k)) is not None for k in ("volume_ratio", "turnover_rate")
    )
    has_fund = any(
        _to_float(row.get(k)) is not None for k in ("pe_ttm", "roe_latest")
    )
    return has_tech, has_cap, has_fund


def _adjusted_weights(
    regime_w: dict[str, float],
    has_tech: bool,
    has_cap: bool,
    has_fund: bool,
) -> dict[str, float] | None:
    """维度自适应归一。<2 维度 → None（触发硬淘汰）。"""
    active: dict[str, float] = {}
    if has_tech:
        active["tech"] = regime_w["tech"]
    if has_cap:
        active["capital"] = regime_w["capital"]
    if has_fund:
        active["fund"] = regime_w["fund"]

    if len(active) < 2:
        return None

    total = sum(active.values())
    return {k: v / total * 100 for k, v in active.items()}


# ============================================================================
# 共振度计算 & 门控
# ============================================================================

def _resonance_categories(
    hit_results: list[StrategyResult],
    enabled: set[str],
) -> list[str]:
    """从命中结果里提取"启用的大类"集合，按 CATEGORY_ORDER 固定顺序输出。"""
    hit_cats: set[str] = set()
    for r in hit_results:
        cat = _map_category(r.category)
        if cat in enabled:
            hit_cats.add(cat)
    return [c for c in CATEGORY_ORDER if c in hit_cats]


def _resonance_min_by_regime(regime: str, cfg: ResonanceConfig) -> int:
    """按 regime 查最小共振度门槛。"""
    return {
        "BULL_STRONG": cfg.bull_strong_min,
        "BULL_WEAK":   cfg.bull_weak_min,
        "BEAR_WEAK":   cfg.bear_weak_min,
        "BEAR_STRONG": cfg.bear_strong_min,
        "UNKNOWN":     cfg.unknown_min,
    }.get(regime, cfg.unknown_min)


def _passes_resonance_gate(
    regime: str,
    resonance_cats: list[str],
    cfg: ResonanceConfig,
) -> bool:
    """共振门控。返回 True=通过，False=淘汰。"""
    min_count = _resonance_min_by_regime(regime, cfg)
    if len(resonance_cats) < min_count:
        return False
    # BEAR_WEAK / BEAR_STRONG：必须含 fundamental
    if regime == "BEAR_WEAK" and cfg.bear_weak_require_fundamental:
        if "fundamental" not in resonance_cats:
            return False
    if regime == "BEAR_STRONG" and cfg.bear_strong_require_fundamental:
        if "fundamental" not in resonance_cats:
            return False
    return True


# ============================================================================
# 软风险扣分
# ============================================================================

def _return_5d_warn_threshold(code: str, cfg: SoftPenaltyConfig) -> float:
    """按板块返回 return_5d 软警告阈值（不达硬淘汰线，但接近）。"""
    board = classify(code)
    if board == Board.GEM:
        return cfg.return_5d_warn_gem
    if board == Board.STAR:
        return cfg.return_5d_warn_star
    if board == Board.BSE:
        return cfg.return_5d_warn_bse
    return cfg.return_5d_warn_main


def _soft_penalty(
    row: pd.Series,
    cfg: SoftPenaltyConfig,
    hard_cfg: HardFilterConfig,
    dq_warn_for_code: bool = False,
) -> tuple[float, list[str]]:
    """L5 软扣分。返回 (总扣分, risk_flags 列表)。"""
    total = 0.0
    flags: list[str] = []
    code = row["code"]

    # 1. RSI 75-85（未到硬淘汰的 85，但接近）
    rsi = _to_float(row.get("rsi_14"))
    if rsi is not None and cfg.rsi_warn_lower <= rsi < hard_cfg.rsi_max:
        total += cfg.rsi_75_85
        flags.append(f"RSI 偏高({rsi:.1f})")

    # 2. return_5d 短期涨幅偏高（未到硬淘汰的板块阈值）
    r5 = _to_float(row.get("return_5d"))
    warn_thr = _return_5d_warn_threshold(code, cfg)
    if r5 is not None and warn_thr <= r5:
        # 硬过滤线是各板块的 return_5d_main/gem/star（return_5d_extreme）
        # 已经过 L2 硬过滤剩下的，都保证 r5 < 硬线
        total += cfg.return_5d_upper
        flags.append(f"5 日涨幅偏高({r5:.1f}%)")

    # 3. 数据质量 WARN
    if dq_warn_for_code:
        total += cfg.dq_warn
        flags.append("数据质量 WARN")

    # 4. 布林带宽异常
    bw = _to_float(row.get("boll_width"))
    if bw is not None and bw >= cfg.boll_width_threshold:
        total += cfg.boll_width_high
        flags.append(f"布林带宽 {bw:.1f}%")

    # 5. ATR/close 偏高（v1.1 迁自 L2）
    atr = _to_float(row.get("atr_14"))
    # ATR 在 daily_feature 里是绝对值，需要 close 计算比率
    # scoring 阶段拿不到 close（在 kline 里）；退化用 ATR 绝对值 + ma20 作代理
    # 这里用 ATR / ma20 近似 ATR / close（阶段 A 妥协；阶段 B 可传 close 进来）
    ma20 = _to_float(row.get("ma20"))
    if atr is not None and ma20 is not None and ma20 > 0:
        atr_ratio = atr / ma20
        if atr_ratio >= cfg.atr_ratio_threshold:
            total += cfg.atr_high
            flags.append(f"波动率偏高(ATR/MA20={atr_ratio*100:.1f}%)")

    return round(total, 2), flags


# ============================================================================
# 主入口
# ============================================================================

def score_stock(
    code: str,
    results: list[StrategyResult],
    feature_row: pd.Series,
    regime: str = "UNKNOWN",
    enabled_cats: set[str] | None = None,
    dq_warn: bool = False,
) -> ScoredStock | tuple[None, str]:
    """给一只股票综合打分（v2）。

    Returns:
        - ScoredStock（正常打分）
        - (None, reason)：被淘汰（<2 维度 或 共振度不足）
    """
    settings = get_settings()
    resonance_cfg = settings.resonance
    soft_cfg = settings.soft_penalty
    hard_cfg = settings.hard_filter

    if enabled_cats is None:
        enabled_cats = _parse_enabled_categories(resonance_cfg.enabled_categories)

    hit_results = [r for r in results if r.hit]

    # ---- 共振度（按启用类别去重）----
    resonance_cats = _resonance_categories(hit_results, enabled_cats)
    resonance_count = len(resonance_cats)

    # ---- 共振门控 ----
    if not _passes_resonance_gate(regime, resonance_cats, resonance_cfg):
        return None, REASON_RESONANCE_TOO_LOW

    # ---- 维度可用性 ----
    has_tech, has_cap, has_fund = _dims_available(feature_row)

    regime_w = REGIME_WEIGHTS.get(regime, REGIME_WEIGHTS["UNKNOWN"])
    adjusted = _adjusted_weights(regime_w, has_tech, has_cap, has_fund)
    if adjusted is None:
        return None, REASON_INSUFFICIENT_DIMENSIONS

    # ---- 技术分 T：命中的 trend/reversal/volume_price 类中取最高 sub_score ----
    tech_hits = [
        r for r in hit_results
        if _map_category(r.category) in ("trend", "reversal", "volume_price")
    ]
    if tech_hits:
        t_raw = max(r.sub_score for r in tech_hits)
    else:
        t_raw = 0.0
    tech_score = round(adjusted.get("tech", 0.0) * t_raw / 100.0, 2)

    # ---- 资金分 C：直接从特征算 ----
    cap_raw, cap_reasons = _score_capital(feature_row)
    capital_score = round(adjusted.get("capital", 0.0) * cap_raw / 100.0, 2)

    # ---- 基本面分 F ----
    fund_hits = [r for r in hit_results if _map_category(r.category) == "fundamental"]
    fund_reasons: list[str] = []
    if fund_hits:
        f_raw = max(r.sub_score for r in fund_hits)
    else:
        f_raw, fund_reasons = _score_fundamental_from_features(feature_row)
    fundamental_score = round(adjusted.get("fund", 0.0) * f_raw / 100.0, 2)

    # ---- 共振加分（跨类别）----
    resonance_bonus = 0.0
    if resonance_count >= 2:
        resonance_bonus = (resonance_count - 1) * regime_w["bonus_per_cat"]

    # ---- 软风险扣分 ----
    penalty, risk_flags = _soft_penalty(feature_row, soft_cfg, hard_cfg, dq_warn)

    # ---- 汇总 ----
    final_score = tech_score + capital_score + fundamental_score + resonance_bonus - penalty

    # 基本面 NULL 时 final_score ≤ 75（防次新股冲顶）
    if not has_fund:
        final_score = min(final_score, 75.0)

    final_score = round(max(0.0, min(100.0, final_score)), 2)

    # ---- 收集正向理由（分开）----
    positive: list[str] = []
    for r in hit_results:
        positive.extend(r.reasons)
    positive.extend(cap_reasons)
    positive.extend(fund_reasons)
    if resonance_bonus > 0:
        positive.append(
            f"跨类共振 {resonance_count} 类"
            f"（{'+' if resonance_bonus >= 0 else ''}{resonance_bonus:.0f} 分）"
        )

    # 兼容老 reasons 字段 = positive + risk_flags（去重保序）
    all_reasons = positive + [f"⚠️ {rf}" for rf in risk_flags]
    seen: set[str] = set()
    deduped: list[str] = []
    for r in all_reasons:
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
        regime=regime,
        resonance_count=resonance_count,
        resonance_categories=resonance_cats,
        positive_reasons=positive,
        risk_flags=risk_flags,
    )
