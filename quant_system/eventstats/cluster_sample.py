"""从相关簇分层抽样股票，作为事件统计宇宙。

设计原则：
1. 按簇分层，而不是全市场纯随机 —— 保留风格/板块多样性
2. 跳过过小簇（默认 size<2），避免孤立点稀释样本
3. 用户只给「大概样本数」；每簇抽几只由算法轮询分配（先尽量覆盖更多簇，再加深）
4. 固定 seed，开跑时锁定 codes，全区间复现一致
"""

from __future__ import annotations

import math
import random
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from quant_system.cluster.queries import latest_run
from quant_system.database.models import StockCluster, StockClusterMember

DEFAULT_PROFILE = "pearson_w60"
DEFAULT_MIN_CLUSTER_SIZE = 2
DEFAULT_TARGET_SAMPLES = 80
DEFAULT_SEED = 42
DEFAULT_PREFER = "central"  # central | uniform

# 兼容旧字段名
DEFAULT_MAX_TOTAL = DEFAULT_TARGET_SAMPLES


def sample_codes_from_clusters(
    session: Session,
    *,
    profile_id: str = DEFAULT_PROFILE,
    target_samples: int | None = None,
    max_total: int | None = None,
    min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE,
    seed: int = DEFAULT_SEED,
    prefer: str = DEFAULT_PREFER,
    # 兼容旧调用：若显式传入 per_cluster 仍可用，但默认由算法决定
    per_cluster: int | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """返回 (codes, meta)。无可用簇时抛 ValueError。

    抽样策略（per_cluster 未指定时）：
    - 在合格簇上轮询，每轮每簇最多再取 1 只，直到凑满 target_samples
    - 这样小样本会优先覆盖更多簇；大样本再自动加深每簇只数
    """
    profile_id = (profile_id or DEFAULT_PROFILE).strip() or DEFAULT_PROFILE
    min_cluster_size = max(1, int(min_cluster_size))
    target = int(
        target_samples
        if target_samples is not None
        else max_total
        if max_total is not None
        else DEFAULT_TARGET_SAMPLES
    )
    target = max(1, target)
    seed = int(seed)
    prefer = (prefer or DEFAULT_PREFER).strip().lower()
    if prefer not in ("central", "uniform"):
        prefer = DEFAULT_PREFER

    run = latest_run(session, profile_id)
    if run is None:
        raise ValueError(f"无成功聚类快照: profile={profile_id}，请先跑相似度+聚类")

    clusters = list(
        session.scalars(
            select(StockCluster)
            .where(StockCluster.run_id == run.run_id)
            .order_by(StockCluster.size.desc())
        ).all()
    )
    eligible = [c for c in clusters if int(c.size or 0) >= min_cluster_size]
    if not eligible:
        raise ValueError(
            f"聚类快照无可用簇（min_size>={min_cluster_size}）: profile={profile_id}"
        )

    mem_rows = list(
        session.scalars(
            select(StockClusterMember)
            .where(StockClusterMember.run_id == run.run_id)
            .order_by(
                StockClusterMember.cluster_id.asc(),
                StockClusterMember.rank_in_cluster.asc(),
            )
        ).all()
    )
    by_cid: dict[int, list[tuple[str, int]]] = {}
    for m in mem_rows:
        by_cid.setdefault(int(m.cluster_id), []).append(
            (str(m.stock_code).upper(), int(m.rank_in_cluster or 9999))
        )

    rng = random.Random(seed)
    order = list(eligible)
    rng.shuffle(order)

    # 旧接口：固定每簇 k 只（一轮扫完）
    if per_cluster is not None:
        codes, clusters_used, auto_per = _sample_fixed_per_cluster(
            order,
            by_cid,
            per_cluster=max(1, int(per_cluster)),
            target=target,
            prefer=prefer,
            rng=rng,
        )
    else:
        codes, clusters_used, auto_per = _sample_round_robin(
            order,
            by_cid,
            target=target,
            prefer=prefer,
            rng=rng,
        )

    if not codes:
        raise ValueError(f"簇抽样结果为空: profile={profile_id}")

    codes = sorted(codes)
    meta = {
        "profile_id": profile_id,
        "cluster_run_id": run.run_id,
        "calc_date": run.calc_date.isoformat() if run.calc_date else None,
        "n_clusters_total": len(clusters),
        "n_clusters_eligible": len(eligible),
        "n_clusters_used": clusters_used,
        "per_cluster": auto_per,  # 算法实际平均/等效每簇深度
        "per_cluster_auto": per_cluster is None,
        "min_cluster_size": min_cluster_size,
        "target_samples": target,
        "max_total": target,  # 兼容旧字段
        "seed": seed,
        "prefer": prefer,
        "n_sampled": len(codes),
    }
    return codes, meta


def _sample_round_robin(
    order: list[Any],
    by_cid: dict[int, list[tuple[str, int]]],
    *,
    target: int,
    prefer: str,
    rng: random.Random,
) -> tuple[list[str], int, int]:
    """轮询加深：每轮每簇最多再取 1 只，直到凑满 target。"""
    picked: list[str] = []
    seen: set[str] = set()
    # 每簇已取数量 & 成员池（按偏好预排序后的可选序列）
    taken: dict[int, int] = {}
    pools: dict[int, list[str]] = {}

    for c in order:
        cid = int(c.cluster_id)
        members = by_cid.get(cid, [])
        if members:
            # 按权重抽一个全排列近似：反复 weighted pick 建池；均匀则打乱
            pools[cid] = _ordered_pool(members, prefer=prefer, rng=rng)
        else:
            rep = (c.representative_code or "").strip().upper()
            pools[cid] = [rep] if rep else []
        taken[cid] = 0

    max_depth = max((len(p) for p in pools.values()), default=0)
    clusters_touched: set[int] = set()

    for depth in range(max_depth):
        if len(picked) >= target:
            break
        for c in order:
            if len(picked) >= target:
                break
            cid = int(c.cluster_id)
            pool = pools.get(cid) or []
            idx = taken[cid]
            if idx >= len(pool):
                continue
            code = pool[idx]
            taken[cid] = idx + 1
            if not code or code in seen:
                continue
            seen.add(code)
            picked.append(code)
            clusters_touched.add(cid)

    n_used = len(clusters_touched)
    # 等效每簇深度：实际抽取 / 使用簇数（向上取整，便于展示）
    auto_per = max(1, math.ceil(len(picked) / n_used)) if n_used else 1
    return picked, n_used, auto_per


def _sample_fixed_per_cluster(
    order: list[Any],
    by_cid: dict[int, list[tuple[str, int]]],
    *,
    per_cluster: int,
    target: int,
    prefer: str,
    rng: random.Random,
) -> tuple[list[str], int, int]:
    picked: list[str] = []
    seen: set[str] = set()
    clusters_used = 0

    for c in order:
        before = len(picked)
        cid = int(c.cluster_id)
        members = by_cid.get(cid, [])
        if not members:
            rep = (c.representative_code or "").strip().upper()
            if rep and rep not in seen:
                seen.add(rep)
                picked.append(rep)
        else:
            k = min(per_cluster, len(members))
            chosen = _pick_from_cluster(members, k=k, prefer=prefer, rng=rng)
            for code in chosen:
                if code in seen:
                    continue
                seen.add(code)
                picked.append(code)
                if len(picked) >= target:
                    break
        if len(picked) > before:
            clusters_used += 1
        if len(picked) >= target:
            break

    return picked, clusters_used, per_cluster


def _ordered_pool(
    members: list[tuple[str, int]],
    *,
    prefer: str,
    rng: random.Random,
) -> list[str]:
    """生成簇内抽取顺序：均匀=打乱；偏中心=按权重无放回排成序列。"""
    if not members:
        return []
    codes = [c for c, _ in members]
    if prefer == "uniform":
        pool = list(codes)
        rng.shuffle(pool)
        return pool
    # central：用加权无放回依次抽出全部，得到偏中心优先的顺序
    weights = [1.0 / max(1, rank) for _, rank in members]
    return _weighted_sample_without_replacement(codes, weights, len(codes), rng)


def _pick_from_cluster(
    members: list[tuple[str, int]],
    *,
    k: int,
    prefer: str,
    rng: random.Random,
) -> list[str]:
    if k <= 0:
        return []
    if k >= len(members):
        return [c for c, _ in members]

    if prefer == "uniform":
        pool = [c for c, _ in members]
        return rng.sample(pool, k)

    weights: list[float] = []
    codes: list[str] = []
    for code, rank in members:
        codes.append(code)
        weights.append(1.0 / max(1, rank))
    return _weighted_sample_without_replacement(codes, weights, k, rng)


def _weighted_sample_without_replacement(
    items: list[str],
    weights: list[float],
    k: int,
    rng: random.Random,
) -> list[str]:
    chosen: list[str] = []
    pool_i = list(range(len(items)))
    pool_w = list(weights)
    for _ in range(k):
        total = sum(pool_w)
        if total <= 0:
            break
        r = rng.random() * total
        acc = 0.0
        pick_pos = 0
        for j, w in enumerate(pool_w):
            acc += w
            if r <= acc:
                pick_pos = j
                break
        idx = pool_i[pick_pos]
        chosen.append(items[idx])
        del pool_i[pick_pos]
        del pool_w[pick_pos]
    return chosen


def expand_cluster_sample_spec(session: Session, spec: dict[str, Any]) -> dict[str, Any]:
    """将 cluster_sample 规范展开为锁定 codes 的 universe_spec。"""
    locked = spec.get("codes")
    if isinstance(locked, list) and locked:
        return {
            **spec,
            "kind": "cluster_sample",
            "codes": [str(c).strip().upper() for c in locked if str(c).strip()],
        }

    target = spec.get("target_samples")
    if target is None:
        target = spec.get("max_total")
    # 仅当调用方显式传 per_cluster 时沿用旧逻辑；默认 None = 算法轮询
    raw_per = spec.get("per_cluster")
    per_arg = int(raw_per) if raw_per is not None else None

    codes, meta = sample_codes_from_clusters(
        session,
        profile_id=str(spec.get("profile") or spec.get("profile_id") or DEFAULT_PROFILE),
        target_samples=int(target) if target is not None else DEFAULT_TARGET_SAMPLES,
        min_cluster_size=int(spec.get("min_cluster_size") or DEFAULT_MIN_CLUSTER_SIZE),
        seed=int(spec.get("seed") if spec.get("seed") is not None else DEFAULT_SEED),
        prefer=str(spec.get("prefer") or DEFAULT_PREFER),
        per_cluster=per_arg,
    )
    out = {
        "kind": "cluster_sample",
        "profile": meta["profile_id"],
        "target_samples": meta["target_samples"],
        "max_total": meta["target_samples"],
        "min_cluster_size": meta["min_cluster_size"],
        "seed": meta["seed"],
        "prefer": meta["prefer"],
        "codes": codes,
        "sample_meta": meta,
    }
    return out
