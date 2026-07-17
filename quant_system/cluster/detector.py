from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
from networkx.algorithms.community import louvain_communities, modularity

from quant_system.similarity.graph import SimilarityGraph


@dataclass
class PartitionResult:
    membership: dict[str, int]  # code -> cluster_id
    modularity: float
    resolution: float
    n_clusters: int


def run_louvain(
    graph: SimilarityGraph,
    *,
    resolution: float = 1.0,
    seed: int = 42,
) -> PartitionResult:
    g = nx.Graph()
    g.add_nodes_from(graph.nodes)
    for e in graph.edges:
        g.add_edge(e.code_a, e.code_b, weight=e.weight)
    if g.number_of_nodes() == 0:
        return PartitionResult(membership={}, modularity=0.0, resolution=resolution, n_clusters=0)

    communities = louvain_communities(
        g, weight="weight", resolution=resolution, seed=seed
    )
    membership: dict[str, int] = {}
    for cid, comm in enumerate(communities):
        for code in comm:
            membership[str(code)] = cid
    # 孤立点（无边）各自一簇
    next_id = len(communities)
    for n in g.nodes:
        code = str(n)
        if code not in membership:
            membership[code] = next_id
            next_id += 1

    q = 0.0
    if g.number_of_edges() > 0 and communities:
        try:
            q = float(modularity(g, communities, weight="weight", resolution=resolution))
        except Exception:
            q = 0.0
    return PartitionResult(
        membership=membership,
        modularity=q,
        resolution=resolution,
        n_clusters=len(set(membership.values())),
    )


def auto_resolution(
    graph: SimilarityGraph,
    *,
    target_k: tuple[int, int] = (30, 50),
    seed: int = 42,
    candidates: tuple[float, ...] = (0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0),
) -> PartitionResult:
    k_lo, k_hi = target_k
    k_mid = (k_lo + k_hi) / 2.0
    best: PartitionResult | None = None
    best_score = float("-inf")
    n = max(len(graph.nodes), 1)
    for res in candidates:
        part = run_louvain(graph, resolution=res, seed=seed)
        if part.n_clusters == 0:
            continue
        sizes: dict[int, int] = {}
        for cid in part.membership.values():
            sizes[cid] = sizes.get(cid, 0) + 1
        max_frac = max(sizes.values()) / n if sizes else 1.0
        singleton_frac = sum(1 for s in sizes.values() if s == 1) / n
        score = (
            -abs(part.n_clusters - k_mid)
            - 20.0 * max(0.0, max_frac - 0.15)
            - 10.0 * singleton_frac
            + 5.0 * part.modularity
        )
        if k_lo <= part.n_clusters <= k_hi:
            score += 5.0
        if score > best_score:
            best_score = score
            best = part
    return best or run_louvain(graph, resolution=1.0, seed=seed)
