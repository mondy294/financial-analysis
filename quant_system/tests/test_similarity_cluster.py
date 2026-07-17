"""Similarity Graph + Cluster 单元测试（不依赖真实边表）。"""
from __future__ import annotations

from datetime import date

from quant_system.cluster.detector import auto_resolution, run_louvain
from quant_system.similarity.graph import (
    SimilarityGraph,
    SimilarityGraphBuilder,
    SimilarityGraphRequest,
    GraphEdge,
)
from quant_system.similarity.protocol import SimilarityEdge, SimilarityResult, enrich_pearson_pair


def test_enrich_pearson_has_breakdown_and_confidence() -> None:
    r = enrich_pearson_pair(0.8, sample_size=48, window="W60")
    assert r.breakdown == {"price": 0.8}
    assert 0.7 <= r.confidence <= 1.0
    assert r.score == 0.8


def test_similarity_result_requires_breakdown() -> None:
    try:
        SimilarityResult(score=0.5, confidence=0.9, sample_size=10, breakdown={})
        assert False, "should raise"
    except ValueError:
        pass


class _FakeLoader:
    def __init__(self, edges: list[SimilarityEdge]) -> None:
        self.edges = edges

    def list_edges(self, *, similarity_type: str, window: str, as_of=None):
        return [
            e
            for e in self.edges
            if e.similarity_type == similarity_type and e.window == window
        ]


def _edge(a: str, b: str, score: float, t: str = "PEARSON") -> SimilarityEdge:
    return SimilarityEdge(
        code_a=a,
        code_b=b,
        similarity_type=t,
        window="W60",
        calc_date=date(2026, 7, 16),
        score=score,
        confidence=0.9,
        sample_size=60,
        breakdown={"price": score},
    )


def test_graph_builder_single_filters() -> None:
    edges = [
        _edge("A", "B", 0.8),
        _edge("A", "C", 0.2),  # below w_min
        _edge("B", "C", 0.7),
    ]
    g = SimilarityGraphBuilder(_FakeLoader(edges)).build(
        SimilarityGraphRequest(
            types=("PEARSON",),
            window="W60",
            merge_strategy="SINGLE",
            w_min=0.45,
            conf_min=0.5,
            sign="pos",
        )
    )
    assert len(g.edges) == 2
    assert g.nodes == {"A", "B", "C"}


def test_graph_builder_weighted_merge() -> None:
    edges = [
        _edge("A", "B", 1.0, "PEARSON"),
        SimilarityEdge(
            code_a="A",
            code_b="B",
            similarity_type="PATTERN",
            window="W60",
            calc_date=date(2026, 7, 16),
            score=0.5,
            confidence=0.8,
            sample_size=20,
            breakdown={"platform": 0.5},
        ),
    ]
    g = SimilarityGraphBuilder(_FakeLoader(edges)).build(
        SimilarityGraphRequest(
            types=("PEARSON", "PATTERN"),
            window="W60",
            merge_strategy="WEIGHTED",
            weights={"PEARSON": 0.5, "PATTERN": 0.5},
            w_min=0.1,
            conf_min=0.1,
            sign="pos",
        )
    )
    assert len(g.edges) == 1
    assert abs(g.edges[0].weight - 0.75) < 1e-6
    assert "PEARSON" in g.edges[0].sources and "PATTERN" in g.edges[0].sources


def test_louvain_two_communities() -> None:
    # 两个团：ABC 强连，DEF 强连，跨团弱
    pairs = [
        ("A", "B", 0.9), ("A", "C", 0.9), ("B", "C", 0.9),
        ("D", "E", 0.9), ("D", "F", 0.9), ("E", "F", 0.9),
        ("A", "D", 0.1),
    ]
    edges = [
        GraphEdge(a, b, w, 0.9, {"price": w}, ("PEARSON",))
        for a, b, w in pairs
    ]
    graph = SimilarityGraph(nodes={x for p in pairs for x in p[:2]}, edges=edges)
    part = run_louvain(graph, resolution=1.0, seed=42)
    assert part.n_clusters >= 2
    # A,B,C 应多数同簇
    c_a = part.membership["A"]
    assert part.membership["B"] == c_a
    assert part.membership["C"] == c_a


def test_auto_resolution_returns_partition() -> None:
    edges = [
        GraphEdge("A", "B", 0.8, 0.9, {}, ("T",)),
        GraphEdge("B", "C", 0.8, 0.9, {}, ("T",)),
        GraphEdge("C", "A", 0.8, 0.9, {}, ("T",)),
    ]
    g = SimilarityGraph(nodes={"A", "B", "C"}, edges=edges)
    part = auto_resolution(g, target_k=(1, 5), seed=1)
    assert part.n_clusters >= 1
