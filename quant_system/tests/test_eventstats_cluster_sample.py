"""簇分层抽样：可复现、偏中心权重、轮询自动分配。"""

from __future__ import annotations

import random
from types import SimpleNamespace

from quant_system.eventstats.cluster_sample import (
    _pick_from_cluster,
    _sample_round_robin,
    _weighted_sample_without_replacement,
)


def test_weighted_sample_deterministic():
    items = [f"S{i}" for i in range(10)]
    weights = [1.0 / (i + 1) for i in range(10)]
    a = _weighted_sample_without_replacement(items, weights, 3, random.Random(7))
    b = _weighted_sample_without_replacement(items, weights, 3, random.Random(7))
    c = _weighted_sample_without_replacement(items, weights, 3, random.Random(8))
    assert a == b
    assert a != c


def test_central_prefers_top_ranks_more_often():
    members = [(f"C{i}", i) for i in range(1, 21)]  # rank 1..20
    hits: dict[str, int] = {}
    for seed in range(200):
        picked = _pick_from_cluster(members, k=1, prefer="central", rng=random.Random(seed))
        hits[picked[0]] = hits.get(picked[0], 0) + 1
    # rank1 应显著高于 rank20
    assert hits.get("C1", 0) > hits.get("C20", 0) * 2


def test_uniform_uses_all_roughly():
    members = [(f"U{i}", i) for i in range(1, 6)]
    hits = {c: 0 for c, _ in members}
    for seed in range(500):
        picked = _pick_from_cluster(members, k=1, prefer="uniform", rng=random.Random(seed))
        hits[picked[0]] += 1
    # 均匀抽样：各股出现次数不应差太离谱
    vals = list(hits.values())
    assert min(vals) > 50
    assert max(vals) < 200


def test_round_robin_covers_clusters_before_deepening():
    """小样本应先覆盖更多簇，而不是在少数簇上抽满。"""
    order = [SimpleNamespace(cluster_id=i, representative_code=None) for i in range(1, 6)]
    by_cid = {
        i: [(f"C{i}_{j}", j) for j in range(1, 6)]  # 每簇 5 只
        for i in range(1, 6)
    }
    picked, n_used, _auto = _sample_round_robin(
        order, by_cid, target=5, prefer="uniform", rng=random.Random(1)
    )
    assert len(picked) == 5
    assert n_used == 5  # 5 只 → 5 个簇各 1 只

    picked2, n_used2, auto2 = _sample_round_robin(
        order, by_cid, target=12, prefer="uniform", rng=random.Random(1)
    )
    assert len(picked2) == 12
    assert n_used2 == 5
    assert auto2 >= 2  # 加深到每簇约 2+
