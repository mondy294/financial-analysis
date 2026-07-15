"""策略基类与结果结构。

原则：
- 策略是**纯函数**：输入特征 DataFrame，输出 StrategyResult 列表，不读 DB，不判数据质量；
- 策略只关心「符合我这条策略的标准吗 + 打个子分 + 说清理由」；
- 综合评分、板块过滤、黑名单、写库都由 selector 完成。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


# ============================================================================
# 结果结构
# ============================================================================

# signal_type 语义（对应 strategy_signal 表）
SIGNAL_HIT = "HIT"
SIGNAL_WATCH = "WATCH"
SIGNAL_NEAR_MISS = "NEAR_MISS"
SIGNAL_FILTERED = "FILTERED"


@dataclass
class StrategyResult:
    """单只股票在单条策略上的评估结果。"""
    code: str
    strategy_code: str
    signal_type: str = SIGNAL_HIT          # HIT / WATCH / NEAR_MISS / FILTERED
    sub_score: float = 0.0                 # 0-100 该策略维度得分
    reasons: list[str] = field(default_factory=list)
    filter_reason: str | None = None       # signal_type=FILTERED 时说明
    near_miss_gap: float | None = None     # signal_type=NEAR_MISS 时的差距
    # 便于评分器分类计算
    category: str = "technical"            # technical / momentum / value / capital / composite

    @property
    def hit(self) -> bool:
        return self.signal_type == SIGNAL_HIT


# ============================================================================
# 基类
# ============================================================================

class BaseStrategy(ABC):
    """所有策略的基类。

    子类实现：
    - code / name / category / version（元信息）
    - evaluate(features_df) → list[StrategyResult]

    features_df 约定：
    - index 无关，含 code 列，一行一只股票，是**目标交易日**的特征快照
    - 已经过板块过滤、数据质量黑名单过滤
    """

    code: str = ""
    name: str = ""
    category: str = "technical"
    version: str = "v1.0"

    def __init__(self, params: dict | None = None) -> None:
        self.params = params or {}

    @abstractmethod
    def evaluate(self, features: pd.DataFrame) -> list[StrategyResult]:
        """对一批股票的特征快照做策略判定，返回结果列表（包含未命中的 WATCH/NEAR_MISS 可选）。

        默认只需返回 HIT 的股票；WATCH / NEAR_MISS 由子类可选实现。
        """
        raise NotImplementedError

    # -------------------- 辅助工具 --------------------

    @staticmethod
    def _as_float(v: Any) -> float | None:
        if v is None:
            return None
        try:
            f = float(v)
            if f != f:  # NaN
                return None
            return f
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_bool(v: Any) -> bool:
        if v is None:
            return False
        try:
            return bool(v) and str(v).lower() != "nan"
        except Exception:
            return False
