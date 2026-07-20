from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


TargetMode = Literal["two_sided", "one_sided_high", "one_sided_low"]
StageRole = Literal["range", "up", "down"]


@dataclass(frozen=True)
class WindowConstraint:
    min_length: int
    max_length: int

    def __post_init__(self) -> None:
        if self.min_length < 1:
            raise ValueError("min_length must be >= 1")
        if self.max_length < self.min_length:
            raise ValueError("max_length must be >= min_length")

    @property
    def span(self) -> int:
        return self.max_length - self.min_length + 1

    @property
    def midpoint(self) -> float:
        return (self.min_length + self.max_length) / 2.0


@dataclass(frozen=True)
class TargetValue:
    """特征目标。

    软评分：ideal / tolerance / mode → similarity（计入加权分）。
    硬约束（二选一，优先值域）：
      - hard_min / hard_max：直接约束特征值，如 slope 在 [-0.01, 0.005]
        只写 hard_min → actual >= hard_min；只写 hard_max → actual <= hard_max
      - hard=True + hard_min_similarity：按相似度门槛（旧写法，不直观）
    """

    ideal: float
    tolerance: float
    weight: float = 1.0
    mode: TargetMode = "two_sided"
    hard: bool = False
    hard_min_similarity: float = 100.0
    # 特征值硬约束（比 hard_min_similarity 更直观）
    hard_min: float | None = None
    hard_max: float | None = None

    def __post_init__(self) -> None:
        if self.tolerance <= 0:
            raise ValueError("tolerance must be > 0")
        if self.weight < 0:
            raise ValueError("weight must be >= 0")
        if not (0.0 <= self.hard_min_similarity <= 100.0):
            raise ValueError("hard_min_similarity must be in [0, 100]")
        if (
            self.hard_min is not None
            and self.hard_max is not None
            and self.hard_min > self.hard_max
        ):
            raise ValueError("hard_min must be <= hard_max")

    @property
    def has_value_hard(self) -> bool:
        return self.hard_min is not None or self.hard_max is not None

    def hard_failed(self, actual: float | None, similarity: float) -> bool:
        """是否触发硬失败（True = 整票否决）。"""
        if self.has_value_hard:
            if actual is None:
                return True
            if self.hard_min is not None and actual + 1e-12 < self.hard_min:
                return True
            if self.hard_max is not None and actual - 1e-12 > self.hard_max:
                return True
            return False
        if self.hard:
            return similarity + 1e-9 < self.hard_min_similarity
        return False


@dataclass(frozen=True)
class Stage:
    name: str
    window: WindowConstraint
    targets: dict[str, TargetValue] = field(default_factory=dict)
    # 引导编辑角色；None=未分类（高级/旧数据）。Matcher 打分不读此字段。
    role: StageRole | None = None


@dataclass(frozen=True)
class RelationSpec:
    """跨 Stage 关系特征绑定：公式在 FeatureCatalog，这里只声明用法与 Target。"""

    name: str
    attach_to_stage: str
    target: TargetValue
    # 角色 -> 实际 Stage.name，例如 {"platform": "platform", "breakout": "breakout"}
    stage_map: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextSpec:
    """股票级 / asof 级特征：对历史序列算一次，不随 Stage 窗口组合变化。

    lookback_bars:
      - int  → 只用最近 N 根交易日（如 252≈一年）
      - None → 使用 Context 载入的全部可用历史（可配合 history_bars=上市至今）
    key:
      结果字典键；默认 name，或 name@lookback，避免同一特征多 lookback 冲突。
    """

    name: str
    target: TargetValue
    lookback_bars: int | None = None
    key: str | None = None

    def __post_init__(self) -> None:
        if self.lookback_bars is not None and self.lookback_bars < 2:
            raise ValueError("lookback_bars must be >= 2 when set")

    @property
    def result_key(self) -> str:
        if self.key:
            return self.key
        if self.lookback_bars is None:
            return self.name
        return f"{self.name}@{self.lookback_bars}"


# 虚拟 Stage 名：context 特征聚合进 overall 时使用
CONTEXT_STAGE = "context"


@dataclass(frozen=True)
class HardConstraints:
    exclude_st: bool = True
    min_list_days: int | None = 120
    min_amount: float | None = 2.0e8
    # 总市值下限，单位与 stock_basic.market_cap 一致：亿元；None=不限制
    min_market_cap: float | None = None
    allow_suspended: bool = False


@dataclass(frozen=True)
class PatternDefinition:
    id: str
    version: str
    display_name: str
    description: str
    timeline: list[Stage]
    display_name_en: str = ""
    threshold: float = 80.0
    stage_weights: dict[str, float] = field(default_factory=dict)
    relations: list[RelationSpec] = field(default_factory=list)
    # 股票级特征（价位分位等）；与 timeline 短窗解耦
    context_features: list[ContextSpec] = field(default_factory=list)
    # Context 至少加载多少根 K；None 时由 required_history_bars() 推导
    history_bars: int | None = None
    constraints: HardConstraints | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timeline:
            raise ValueError("timeline must not be empty")
        if len(self.timeline) > 4:
            raise ValueError("allows at most 4 stages")
        names = [s.name for s in self.timeline]
        if len(set(names)) != len(names):
            raise ValueError("stage names must be unique")
        if CONTEXT_STAGE in names:
            raise ValueError(f"stage name '{CONTEXT_STAGE}' is reserved")
        for rel in self.relations:
            if rel.attach_to_stage not in names:
                raise ValueError(f"relation {rel.name} attach_to_stage unknown: {rel.attach_to_stage}")
        keys = [c.result_key for c in self.context_features]
        if len(set(keys)) != len(keys):
            raise ValueError("context_features result_key must be unique")
        if self.history_bars is not None and self.history_bars < self.max_window:
            raise ValueError("history_bars must be >= max_window")

    @property
    def min_window(self) -> int:
        return sum(s.window.min_length for s in self.timeline)

    @property
    def max_window(self) -> int:
        return sum(s.window.max_length for s in self.timeline)

    def required_history_bars(self) -> int:
        """扫描时应加载的最少交易日根数（形态窗 + context lookback）。"""
        need = self.max_window + 5
        if self.history_bars is not None:
            need = max(need, self.history_bars)
        for cf in self.context_features:
            if cf.lookback_bars is not None:
                need = max(need, cf.lookback_bars)
            else:
                # 全历史：给一个足够大的默认上限（约 10 年交易日）
                need = max(need, self.history_bars or 2520)
        return need
