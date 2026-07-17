from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Protocol, Sequence


class SimilarityType:
    PEARSON = "PEARSON"
    SPEARMAN = "SPEARMAN"
    LEAD_LAG = "LEAD_LAG"
    PATTERN = "PATTERN"
    FEATURE = "FEATURE"
    EMBEDDING = "EMBEDDING"
    EVENT = "EVENT"
    COMPOSITE = "COMPOSITE"


@dataclass(frozen=True)
class SimilarityResult:
    score: float
    confidence: float
    sample_size: int | None
    direction: int = 0
    breakdown: dict[str, float] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.breakdown:
            raise ValueError("breakdown 必填，至少包含一个分量")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence 必须在 [0,1]")


@dataclass(frozen=True)
class SimilarityEdge:
    code_a: str
    code_b: str
    similarity_type: str
    window: str
    calc_date: date
    score: float
    confidence: float
    sample_size: int | None
    direction: int = 0
    breakdown: dict[str, float] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    is_same_industry: bool | None = None


@dataclass(frozen=True)
class SimilarityContext:
    calc_date: date
    window: str
    min_sample: int = 120
    extra: dict[str, Any] = field(default_factory=dict)


class SimilarityCalculator(Protocol):
    similarity_type: str

    def pair(
        self, a: str, b: str, *, ctx: SimilarityContext
    ) -> SimilarityResult | None: ...

    def batch(
        self, codes: Sequence[str], *, ctx: SimilarityContext
    ) -> Iterable[tuple[str, str, SimilarityResult]]: ...


def pearson_confidence(sample_size: int, window_days: int) -> float:
    if window_days <= 0:
        return 0.0
    return float(max(0.0, min(1.0, sample_size / float(window_days))))


def window_days(window: str) -> int:
    w = window.upper().strip()
    if w.startswith("W") and w[1:].isdigit():
        return int(w[1:])
    if w == "FULL":
        return 500
    return 60


def enrich_pearson_pair(
    value: float,
    sample_size: int,
    window: str,
    *,
    extra_meta: dict | None = None,
) -> SimilarityResult:
    days = window_days(window)
    conf = pearson_confidence(sample_size, days)
    score = float(value)
    meta: dict = {"window": window, "method": "pearson"}
    if extra_meta:
        meta.update(extra_meta)
    return SimilarityResult(
        score=score,
        confidence=conf,
        sample_size=int(sample_size),
        direction=0,
        breakdown={"price": score},
        meta=meta,
    )
