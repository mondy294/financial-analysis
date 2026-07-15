"""特征聚合：把 kline + financial 组装成 daily_feature 一行。

流程：
1. 读某只股票的 K 线（含足够 lookback，默认 90 天），前复权；
2. 算全套技术指标；
3. 取目标日的一行；
4. 拼上最近一期财务快照的基本面字段（含 ann_date / report_period 血缘）；
5. 返回一个 dict，可以直接 upsert 到 daily_feature 表。

批量入口：build_features_for_date(codes, trade_date, ...) 返回 list[dict]。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from quant_system.config.settings import get_settings
from quant_system.data.repository import Repositories
from quant_system.indicators.technical import compute_all


# 计算指标需要的最少 lookback 天数（60 日均线 + 缓冲）
DEFAULT_LOOKBACK_DAYS = 120


def _to_decimal(x: Any) -> Decimal | None:
    if x is None:
        return None
    try:
        if isinstance(x, float) and (np.isnan(x) or np.isinf(x)):
            return None
        return Decimal(str(round(float(x), 6)))
    except (ValueError, TypeError):
        return None


def _to_bool(x: Any) -> bool | None:
    if x is None:
        return None
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        pass
    return bool(x)


def build_feature_row(
    code: str,
    trade_date: date,
    repos: Repositories,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    feature_version: str | None = None,
) -> dict | None:
    """构造某只股票某天的特征行。数据不足返回 None。"""
    settings = get_settings()
    feature_version = feature_version or settings.feature.version

    # 1. 读 K 线（前复权，保证价格序列连续）
    start = trade_date - timedelta(days=lookback_days * 2)  # 自然日冗余，扣掉周末假日
    df = repos.kline.read_kline(code, start, trade_date, adj="qfq")
    if df.empty or trade_date not in df["trade_date"].values:
        return None

    # 2. 算全套指标
    fcfg = settings.feature
    df = compute_all(
        df,
        ma_windows=fcfg.ma_windows,
        macd_params=fcfg.macd_params,
        rsi_window=fcfg.rsi_window,
        kdj_params={"n": fcfg.kdj_params["n"],
                    "m1": fcfg.kdj_params["m1"],
                    "m2": fcfg.kdj_params["m2"]},
        atr_window=fcfg.atr_window,
        boll_params=fcfg.boll_params,
        breakout_window=fcfg.breakout_window,
        volume_ma_window=fcfg.volume_ma_window,
    )

    # 3. 取目标日行
    row = df[df["trade_date"] == trade_date].iloc[0]

    # 4. 拼基本面（含血缘）
    snapshot = repos.financial.get_latest_snapshot(code, as_of=trade_date)
    fin: dict = {}
    if snapshot is not None:
        fin = {
            "pe_ttm": _to_decimal(snapshot.pe_ttm),
            "pb": _to_decimal(snapshot.pb),
            "roe_latest": _to_decimal(snapshot.roe),
            "net_profit_yoy_latest": _to_decimal(snapshot.net_profit_yoy),
            "revenue_yoy_latest": _to_decimal(snapshot.revenue_yoy),
            "financial_snapshot_date": snapshot.report_period,
            "financial_ann_date": snapshot.ann_date,
        }
    # 市值：优先用 stock_basic 冗余的 market_cap
    stock = repos.stock.get_stock(code)
    market_cap = _to_decimal(stock.market_cap) if stock is not None else None

    # 5. 组装 dict
    return {
        "code": code,
        "trade_date": trade_date,
        # 收益
        "return_1d": _to_decimal(row.get("return_1d")),
        "return_5d": _to_decimal(row.get("return_5d")),
        "return_20d": _to_decimal(row.get("return_20d")),
        "return_60d": _to_decimal(row.get("return_60d")),
        # 均线
        "ma5": _to_decimal(row.get("ma5")),
        "ma10": _to_decimal(row.get("ma10")),
        "ma20": _to_decimal(row.get("ma20")),
        "ma60": _to_decimal(row.get("ma60")),
        "ma_position": _to_decimal(row.get("ma_position")),
        "ma_bull_arrange": _to_bool(row.get("ma_bull_arrange")),
        # 动量
        "macd": _to_decimal(row.get("macd")),
        "macd_signal": _to_decimal(row.get("macd_signal")),
        "macd_hist": _to_decimal(row.get("macd_hist")),
        "macd_golden_cross": _to_bool(row.get("macd_golden_cross")),
        "rsi_14": _to_decimal(row.get(f"rsi_{fcfg.rsi_window}")),
        "kdj_k": _to_decimal(row.get("kdj_k")),
        "kdj_d": _to_decimal(row.get("kdj_d")),
        "kdj_j": _to_decimal(row.get("kdj_j")),
        # 波动
        "atr_14": _to_decimal(row.get(f"atr_{fcfg.atr_window}")),
        "boll_upper": _to_decimal(row.get("boll_upper")),
        "boll_mid": _to_decimal(row.get("boll_mid")),
        "boll_lower": _to_decimal(row.get("boll_lower")),
        "boll_width": _to_decimal(row.get("boll_width")),
        # 量能
        "volume_ratio": _to_decimal(row.get("volume_ratio")),
        "turnover_rate": _to_decimal(row.get("turnover_rate")),
        "turnover_change": _to_decimal(row.get("turnover_change")),
        "amount_ma5": _to_decimal(row.get("amount_ma5")),
        # 突破
        "high_20d": _to_decimal(row.get(f"high_{fcfg.breakout_window}d")),
        "break_high_20d": _to_bool(row.get(f"break_high_{fcfg.breakout_window}d")),
        # 基本面
        **fin,
        "market_cap": market_cap,
        # 向量预留（本轮不填）
        "vector_version": None,
        "embedding_id": None,
        # 扩展 + 元
        "ext": None,
        "feature_version": feature_version,
        "created_at": datetime.utcnow(),
    }


def build_features_for_date(
    codes: list[str],
    trade_date: date,
    repos: Repositories,
    feature_version: str | None = None,
) -> tuple[list[dict], list[str]]:
    """批量构造。返回 (成功特征列表, 失败股票代码列表)。"""
    features: list[dict] = []
    failed: list[str] = []
    for i, code in enumerate(codes, 1):
        try:
            row = build_feature_row(code, trade_date, repos, feature_version=feature_version)
            if row is None:
                failed.append(code)
                continue
            features.append(row)
        except Exception as e:
            failed.append(code)
            if len(failed) <= 5:
                logger.warning("build feature {} 失败: {}", code, e)
        if i % 50 == 0:
            logger.info("feature 进度 {}/{}", i, len(codes))
    return features, failed
