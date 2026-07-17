from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from quant_system.cluster.detector import PartitionResult, auto_resolution, run_louvain
from quant_system.database.models import StockBasic, StockCluster, StockClusterMember, StockClusterRun
from quant_system.similarity.edges import RelationEdgeLoader
from quant_system.similarity.graph import SimilarityGraph, SimilarityGraphBuilder, SimilarityGraphRequest


@dataclass(frozen=True)
class ClusterBuildRequest:
    graph: SimilarityGraphRequest
    profile_id: str = "pearson_w60"
    algo: str = "LOUVAIN"
    resolution: float | Literal["auto"] = "auto"
    seed: int = 42
    target_k: tuple[int, int] = (30, 50)


@dataclass
class ClusterBuildReport:
    run_id: str
    profile_id: str
    calc_date: date | None
    n_clusters: int
    edge_used: int
    universe_size: int
    modularity: float
    resolution: float
    max_cluster_size: int
    singleton_count: int
    duration_ms: int
    status: str
    error: str | None = None


def _names(session: Session, codes: list[str]) -> dict[str, str]:
    if not codes:
        return {}
    rows = session.execute(
        select(StockBasic.code, StockBasic.name).where(StockBasic.code.in_(codes))
    ).all()
    return {c: (n or c) for c, n in rows}


def _enrich(
    graph: SimilarityGraph,
    part: PartitionResult,
    name_map: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """返回 clusters 行 + members 行。"""
    # 邻接权重
    adj: dict[str, dict[str, float]] = {}
    for e in graph.edges:
        adj.setdefault(e.code_a, {})[e.code_b] = e.weight
        adj.setdefault(e.code_b, {})[e.code_a] = e.weight

    by_cid: dict[int, list[str]] = {}
    for code, cid in part.membership.items():
        by_cid.setdefault(cid, []).append(code)

    clusters: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []
    for cid, codes in sorted(by_cid.items(), key=lambda x: -len(x[1])):
        # centrality = 与同簇邻居权重和
        cents: list[tuple[str, float]] = []
        internal_w = 0.0
        internal_e = 0
        code_set = set(codes)
        for c in codes:
            s = 0.0
            for peer, w in adj.get(c, {}).items():
                if peer in code_set:
                    s += w
                    if c < peer:
                        internal_w += w
                        internal_e += 1
            cents.append((c, s))
        cents.sort(key=lambda x: (-x[1], x[0]))
        n = len(codes)
        possible = n * (n - 1) / 2.0
        density = (internal_e / possible) if possible > 0 else 0.0
        avg_sim = (internal_w / internal_e) if internal_e > 0 else None
        rep = cents[0][0] if cents else codes[0]
        rep_name = name_map.get(rep, rep)
        label = f"{rep_name}等{n}只"
        top = [
            {"code": c, "name": name_map.get(c, c), "centrality": round(cent, 6)}
            for c, cent in cents[:8]
        ]
        clusters.append({
            "cluster_id": cid,
            "label": label,
            "size": n,
            "avg_internal_similarity": round(avg_sim, 4) if avg_sim is not None else None,
            "density": round(density, 4),
            "representative_code": rep,
            "top_members_json": top,
        })
        for rank, (c, cent) in enumerate(cents, start=1):
            members.append({
                "stock_code": c,
                "cluster_id": cid,
                "centrality": round(cent, 6),
                "rank_in_cluster": rank,
            })
    return clusters, members


class ClusterBuilder:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._graph_builder = SimilarityGraphBuilder(RelationEdgeLoader(session))

    def build(self, req: ClusterBuildRequest) -> ClusterBuildReport:
        t0 = time.monotonic()
        run_id = f"CLST_{uuid.uuid4().hex[:16]}"
        now = datetime.utcnow()
        try:
            graph = self._graph_builder.build(req.graph)
            if req.resolution == "auto":
                part = auto_resolution(
                    graph, target_k=req.target_k, seed=req.seed
                )
            else:
                part = run_louvain(
                    graph, resolution=float(req.resolution), seed=req.seed
                )

            # 生效 profile：删旧成员/簇/run（同 profile 的旧 SUCCESS）
            self._retire_profile(req.profile_id)

            calc_date = req.graph.calc_date
            if calc_date is None and graph.edges:
                # 从 loader 无法直接取；用今天占位不如留 None——从边无 calc_date
                # GraphEdge 不带 calc_date；从 request 或查库
                calc_date = self._infer_calc_date(req)

            name_map = _names(self._session, list(part.membership.keys()))
            clusters, members = _enrich(graph, part, name_map)

            sizes = [c["size"] for c in clusters] or [0]
            singleton_count = sum(1 for s in sizes if s == 1)
            duration_ms = int((time.monotonic() - t0) * 1000)

            self._session.add(
                StockClusterRun(
                    run_id=run_id,
                    calc_date=calc_date or date.today(),
                    profile_id=req.profile_id,
                    graph_spec_json=req.graph.to_dict(),
                    algo=req.algo,
                    resolution=part.resolution,
                    seed=req.seed,
                    universe_size=len(part.membership),
                    edge_used=len(graph.edges),
                    n_clusters=part.n_clusters,
                    modularity=part.modularity,
                    max_cluster_size=max(sizes),
                    singleton_count=singleton_count,
                    params_json={
                        "target_k": list(req.target_k),
                        "quality": {
                            "max_cluster_frac": max(sizes) / max(len(part.membership), 1),
                            "singleton_frac": singleton_count / max(len(part.membership), 1),
                        },
                    },
                    status="SUCCESS",
                    duration_ms=duration_ms,
                    created_at=now,
                )
            )
            for c in clusters:
                self._session.add(
                    StockCluster(
                        run_id=run_id,
                        cluster_id=c["cluster_id"],
                        label=c["label"],
                        size=c["size"],
                        avg_internal_similarity=c["avg_internal_similarity"],
                        density=c["density"],
                        representative_code=c["representative_code"],
                        top_members_json=c["top_members_json"],
                    )
                )
            for m in members:
                self._session.add(
                    StockClusterMember(
                        run_id=run_id,
                        stock_code=m["stock_code"],
                        cluster_id=m["cluster_id"],
                        centrality=m["centrality"],
                        rank_in_cluster=m["rank_in_cluster"],
                    )
                )
            self._session.flush()
            logger.info(
                "cluster OK profile={} clusters={} edges={} Q={:.3f} {}ms",
                req.profile_id, part.n_clusters, len(graph.edges), part.modularity, duration_ms,
            )
            return ClusterBuildReport(
                run_id=run_id,
                profile_id=req.profile_id,
                calc_date=calc_date,
                n_clusters=part.n_clusters,
                edge_used=len(graph.edges),
                universe_size=len(part.membership),
                modularity=part.modularity,
                resolution=part.resolution,
                max_cluster_size=max(sizes),
                singleton_count=singleton_count,
                duration_ms=duration_ms,
                status="SUCCESS",
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.exception("cluster FAILED profile={}", req.profile_id)
            self._session.add(
                StockClusterRun(
                    run_id=run_id,
                    calc_date=req.graph.calc_date or date.today(),
                    profile_id=req.profile_id,
                    graph_spec_json=req.graph.to_dict(),
                    algo=req.algo,
                    resolution=None,
                    seed=req.seed,
                    status="FAILED",
                    duration_ms=duration_ms,
                    error_msg=str(exc),
                    created_at=now,
                )
            )
            self._session.flush()
            return ClusterBuildReport(
                run_id=run_id,
                profile_id=req.profile_id,
                calc_date=req.graph.calc_date,
                n_clusters=0,
                edge_used=0,
                universe_size=0,
                modularity=0.0,
                resolution=0.0,
                max_cluster_size=0,
                singleton_count=0,
                duration_ms=duration_ms,
                status="FAILED",
                error=str(exc),
            )

    def _retire_profile(self, profile_id: str) -> None:
        old_ids = list(
            self._session.scalars(
                select(StockClusterRun.run_id).where(
                    StockClusterRun.profile_id == profile_id,
                    StockClusterRun.status == "SUCCESS",
                )
            ).all()
        )
        if not old_ids:
            return
        self._session.execute(
            delete(StockClusterMember).where(StockClusterMember.run_id.in_(old_ids))
        )
        self._session.execute(
            delete(StockCluster).where(StockCluster.run_id.in_(old_ids))
        )
        # 保留 run 元数据但标记 superseded
        runs = self._session.scalars(
            select(StockClusterRun).where(StockClusterRun.run_id.in_(old_ids))
        ).all()
        for r in runs:
            r.status = "SUPERSEDED"
        self._session.flush()

    def _infer_calc_date(self, req: ClusterBuildRequest) -> date | None:
        from quant_system.database.models import StockRelationship

        t = req.graph.types[0]
        w = req.graph.window_for(t)
        return self._session.scalars(
            select(StockRelationship.calc_date)
            .where(StockRelationship.relation_type == t)
            .where(StockRelationship.window == w)
            .order_by(StockRelationship.calc_date.desc())
            .limit(1)
        ).first()


def build_clusters(session: Session, req: ClusterBuildRequest) -> ClusterBuildReport:
    return ClusterBuilder(session).build(req)


def default_pearson_profiles(
    *,
    w_min: float = 0.45,
    conf_min: float = 0.5,
    calc_date: date | None = None,
) -> list[ClusterBuildRequest]:
    out: list[ClusterBuildRequest] = []
    for win in ("W60", "W250"):
        out.append(
            ClusterBuildRequest(
                profile_id=f"pearson_{win.lower()}",
                graph=SimilarityGraphRequest(
                    types=("PEARSON",),
                    window=win,
                    merge_strategy="SINGLE",
                    w_min=w_min,
                    conf_min=conf_min,
                    sign="pos",
                    calc_date=calc_date,
                ),
                resolution="auto",
            )
        )
    return out
