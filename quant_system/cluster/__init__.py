"""Cluster Framework：只消费 SimilarityGraph。

注意：不要在包级 import builder/detector（会强制依赖 networkx），
API 只读查询应只 import quant_system.cluster.queries。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["ClusterBuildRequest", "ClusterBuilder", "build_clusters"]

if TYPE_CHECKING:
    from quant_system.cluster.builder import ClusterBuildRequest, ClusterBuilder


def __getattr__(name: str) -> Any:
    if name in ("ClusterBuildRequest", "ClusterBuilder", "build_clusters"):
        from quant_system.cluster import builder as _builder

        return getattr(_builder, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
