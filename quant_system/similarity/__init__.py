"""Similarity Framework：协议 / Graph / 编排。

DB 表名仍为 stock_relationship*（兼容）；代码中心在本包。
"""
from __future__ import annotations

from quant_system.similarity.protocol import (
    SimilarityContext,
    SimilarityEdge,
    SimilarityResult,
    SimilarityType,
)
from quant_system.similarity.graph import (
    GraphEdge,
    SimilarityGraph,
    SimilarityGraphBuilder,
    SimilarityGraphRequest,
)

__all__ = [
    "SimilarityType",
    "SimilarityResult",
    "SimilarityEdge",
    "SimilarityContext",
    "GraphEdge",
    "SimilarityGraph",
    "SimilarityGraphRequest",
    "SimilarityGraphBuilder",
]
