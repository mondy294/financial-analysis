"""L2 · 硬风险否决（Hard Filter）。

在策略池执行之前，把当日"结构性有风险"或"数据缺失"的股票直接淘汰，
不参与后续评分与共振门控。被淘汰的股票只放 SelectionReport.hard_filtered
（内存 + 日报"过滤汇总"块），不写入 data_quality_check 表。

判定规则（v1.2）：

1. RSI(14) ≥ 85              → RSI_TOO_HIGH
2. return_5d 按板块超标        → RETURN_5D_EXTREME
3. break_high_20d=True 且缩量  → VOLUME_PRICE_DIVERGENCE
4. 一字板（O==H==L==C 且触板） → ONE_WORD_LIMIT
5. 关键指标 NULL (ma20/macd/rsi_14 任一) → MISSING_KEY_FEATURE

**注意**："维度不足"（<2 维度有数据）在 scoring 层判定，不放在 L2。
因为需要看完策略池命中情况后才知道 tech/capital/fund 各维度有没有分。

对外接口：apply_hard_filters(df, kline_map, cfg) -> (df_pass, hard_filtered)
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from loguru import logger

from quant_system.config.settings import HardFilterConfig
from quant_system.infra.board import Board, classify


# ============================================================================
# 板块自适应阈值
# ============================================================================

def _return_5d_threshold(code: str, cfg: HardFilterConfig) -> float:
    """按板块返回 return_5d 硬过滤阈值（百分比）。"""
    board = classify(code)
    if board == Board.MAIN:
        return cfg.return_5d_main
    if board == Board.GEM:
        return cfg.return_5d_gem
    if board == Board.STAR:
        return cfg.return_5d_star
    if board == Board.BSE:
        return cfg.return_5d_bse
    # UNKNOWN / B 股：保守用主板阈值
    return cfg.return_5d_main


def _price_limit_pct(code: str, cfg: HardFilterConfig) -> float:
    """按板块返回涨跌停幅（百分比）。用于一字板判定。"""
    board = classify(code)
    if board == Board.GEM:
        return cfg.price_limit_gem
    if board == Board.STAR:
        return cfg.price_limit_star
    if board == Board.BSE:
        return cfg.price_limit_bse
    return cfg.price_limit_main


# ============================================================================
# 单条判定函数
# ============================================================================

def _to_float(x: Any) -> float | None:
    """安全 float 转换。None / NaN / 非法值 → None。"""
    if x is None:
        return None
    try:
        f = float(x)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _to_bool(x: Any) -> bool:
    """安全 bool 转换。None → False。"""
    if x is None:
        return False
    try:
        return bool(x) and str(x).lower() != "nan"
    except Exception:
        return False


def _is_one_word_limit(
    open_p: float | None,
    high: float | None,
    low: float | None,
    close: float | None,
    pct_change: float | None,
    code: str,
    cfg: HardFilterConfig,
) -> bool:
    """一字板判定：O==H==L==C 且 |pct_change| ≥ 涨跌停幅 × ratio。"""
    if None in (open_p, high, low, close, pct_change):
        return False
    # 浮点比较：用 abs 差值容忍
    if not (
        abs(open_p - high) < 1e-6
        and abs(high - low) < 1e-6
        and abs(low - close) < 1e-6
    ):
        return False
    limit = _price_limit_pct(code, cfg)
    return abs(pct_change) >= limit * cfg.one_word_limit_ratio


# ============================================================================
# 主入口
# ============================================================================

# 硬淘汰原因枚举（字符串常量，便于统计和展示）
REASON_RSI_TOO_HIGH = "RSI_TOO_HIGH"
REASON_RETURN_5D_EXTREME = "RETURN_5D_EXTREME"
REASON_VOLUME_PRICE_DIVERGENCE = "VOLUME_PRICE_DIVERGENCE"
REASON_ONE_WORD_LIMIT = "ONE_WORD_LIMIT"
REASON_MISSING_KEY_FEATURE = "MISSING_KEY_FEATURE"

# 面向 UI 的中文描述（日报展示用）
REASON_DESCRIPTIONS: dict[str, str] = {
    REASON_RSI_TOO_HIGH: "RSI 极端超买",
    REASON_RETURN_5D_EXTREME: "5 日暴涨（板块阈值）",
    REASON_VOLUME_PRICE_DIVERGENCE: "突破无量（量价背离）",
    REASON_ONE_WORD_LIMIT: "一字涨跌停",
    REASON_MISSING_KEY_FEATURE: "关键指标缺失",
}


def apply_hard_filters(
    df: pd.DataFrame,
    kline_map: dict[str, dict[str, float | None]],
    cfg: HardFilterConfig,
) -> tuple[pd.DataFrame, list[dict]]:
    """对特征 DataFrame 应用 L2 硬过滤。

    Args:
        df: 已经过板块 & DQ 黑名单过滤的特征 DataFrame，含 code + 特征列
        kline_map: {code: {"open": ..., "high": ..., "low": ..., "close": ..., "pct_change": ...}}
            selector 从 daily_kline 一次性 batch 查出来传进来（避免 N+1）
        cfg: HardFilterConfig

    Returns:
        (df_pass, hard_filtered)
        - df_pass: 通过硬过滤的 DataFrame
        - hard_filtered: [{"code": "000001.SZ", "reason": "RSI_TOO_HIGH"}, ...]
    """
    if df.empty:
        return df, []

    filtered: list[dict] = []
    pass_mask: list[bool] = []

    for _, row in df.iterrows():
        code = row["code"]
        reason = _evaluate_one(row, kline_map.get(code, {}), cfg)
        if reason is None:
            pass_mask.append(True)
        else:
            pass_mask.append(False)
            filtered.append({"code": code, "reason": reason})

    df_pass = df[pass_mask].reset_index(drop=True)

    # 汇总日志（按 reason 分组）
    if filtered:
        by_reason: dict[str, int] = {}
        for f in filtered:
            by_reason[f["reason"]] = by_reason.get(f["reason"], 0) + 1
        summary = ", ".join(f"{k}={v}" for k, v in sorted(by_reason.items()))
        logger.info(
            "hard_filter: {} → {} (剔除 {}，明细: {})",
            len(df), len(df_pass), len(filtered), summary,
        )
    else:
        logger.info("hard_filter: {} → {} (无剔除)", len(df), len(df_pass))

    return df_pass, filtered


def _evaluate_one(
    row: pd.Series,
    kline: dict[str, float | None],
    cfg: HardFilterConfig,
) -> str | None:
    """对单只股票判定是否命中硬过滤。返回命中的第一个 reason，或 None（通过）。

    判定顺序按"最容易命中优先"，一旦命中立即返回，节省计算。
    """
    code = row["code"]

    # ---- 1. 关键指标缺失 ----
    if cfg.require_ma20 and _to_float(row.get("ma20")) is None:
        return REASON_MISSING_KEY_FEATURE
    if cfg.require_macd and _to_float(row.get("macd")) is None:
        return REASON_MISSING_KEY_FEATURE
    if cfg.require_rsi14 and _to_float(row.get("rsi_14")) is None:
        return REASON_MISSING_KEY_FEATURE

    # ---- 2. RSI 极端超买 ----
    rsi = _to_float(row.get("rsi_14"))
    if rsi is not None and rsi >= cfg.rsi_max:
        return REASON_RSI_TOO_HIGH

    # ---- 3. 5 日暴涨（板块自适应）----
    r5 = _to_float(row.get("return_5d"))
    if r5 is not None and r5 >= _return_5d_threshold(code, cfg):
        return REASON_RETURN_5D_EXTREME

    # ---- 4. 量价背离：突破新高但缩量 ----
    break_flag = _to_bool(row.get("break_high_20d"))
    vr = _to_float(row.get("volume_ratio"))
    if break_flag and vr is not None and vr < cfg.divergence_vol_min:
        return REASON_VOLUME_PRICE_DIVERGENCE

    # ---- 5. 一字板 ----
    if _is_one_word_limit(
        kline.get("open"), kline.get("high"),
        kline.get("low"), kline.get("close"),
        kline.get("pct_change"),
        code, cfg,
    ):
        return REASON_ONE_WORD_LIMIT

    return None
