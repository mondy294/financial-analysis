from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from quant_system.database.models import (
    StockBasic,
    StockCluster,
    StockClusterMember,
    StockClusterRun,
)


def latest_run(session: Session, profile_id: str) -> StockClusterRun | None:
    return session.scalars(
        select(StockClusterRun)
        .where(StockClusterRun.profile_id == profile_id)
        .where(StockClusterRun.status == "SUCCESS")
        .order_by(StockClusterRun.created_at.desc())
        .limit(1)
    ).first()


def list_profiles(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        select(
            StockClusterRun.profile_id,
            StockClusterRun.run_id,
            StockClusterRun.calc_date,
            StockClusterRun.n_clusters,
            StockClusterRun.modularity,
            StockClusterRun.universe_size,
            StockClusterRun.edge_used,
            StockClusterRun.created_at,
        )
        .where(StockClusterRun.status == "SUCCESS")
        .order_by(StockClusterRun.created_at.desc())
    ).all()
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for pid, rid, cd, nc, mod, uni, edges, created in rows:
        if pid in seen:
            continue
        seen.add(pid)
        out.append({
            "profile_id": pid,
            "run_id": rid,
            "calc_date": cd.isoformat() if cd else None,
            "n_clusters": nc,
            "modularity": float(mod) if mod is not None else None,
            "universe_size": uni,
            "edge_used": edges,
            "created_at": created.isoformat() if created else None,
        })
    return out


def list_clusters(
    session: Session,
    *,
    profile_id: str = "pearson_w60",
    hide_singletons: bool = True,
) -> dict[str, Any]:
    run = latest_run(session, profile_id)
    if run is None:
        return {"profile_id": profile_id, "run": None, "clusters": []}
    stmt = (
        select(StockCluster)
        .where(StockCluster.run_id == run.run_id)
        .order_by(StockCluster.size.desc())
    )
    clusters = []
    for c in session.scalars(stmt).all():
        if hide_singletons and c.size <= 1:
            continue
        clusters.append({
            "cluster_id": c.cluster_id,
            "label": c.label,
            "size": c.size,
            "avg_internal_similarity": (
                float(c.avg_internal_similarity)
                if c.avg_internal_similarity is not None else None
            ),
            "density": float(c.density) if c.density is not None else None,
            "representative_code": c.representative_code,
            "top_members": c.top_members_json or [],
        })
    return {
        "profile_id": profile_id,
        "run": {
            "run_id": run.run_id,
            "calc_date": run.calc_date.isoformat(),
            "n_clusters": run.n_clusters,
            "modularity": float(run.modularity) if run.modularity is not None else None,
            "universe_size": run.universe_size,
            "edge_used": run.edge_used,
            "resolution": float(run.resolution) if run.resolution is not None else None,
            "graph_spec": run.graph_spec_json,
        },
        "clusters": clusters,
    }


def cluster_detail(
    session: Session,
    cluster_id: int,
    *,
    profile_id: str = "pearson_w60",
    limit: int = 100,
) -> dict[str, Any] | None:
    run = latest_run(session, profile_id)
    if run is None:
        return None
    c = session.scalars(
        select(StockCluster)
        .where(StockCluster.run_id == run.run_id)
        .where(StockCluster.cluster_id == cluster_id)
    ).first()
    if c is None:
        return None
    mem_rows = session.scalars(
        select(StockClusterMember)
        .where(StockClusterMember.run_id == run.run_id)
        .where(StockClusterMember.cluster_id == cluster_id)
        .order_by(StockClusterMember.rank_in_cluster)
        .limit(limit)
    ).all()
    codes = [m.stock_code for m in mem_rows]
    names = {}
    if codes:
        names = {
            code: name
            for code, name in session.execute(
                select(StockBasic.code, StockBasic.name).where(StockBasic.code.in_(codes))
            ).all()
        }
    return {
        "profile_id": profile_id,
        "run_id": run.run_id,
        "cluster": {
            "cluster_id": c.cluster_id,
            "label": c.label,
            "size": c.size,
            "avg_internal_similarity": (
                float(c.avg_internal_similarity)
                if c.avg_internal_similarity is not None else None
            ),
            "density": float(c.density) if c.density is not None else None,
            "representative_code": c.representative_code,
        },
        "members": [
            {
                "code": m.stock_code,
                "name": names.get(m.stock_code, m.stock_code),
                "centrality": float(m.centrality),
                "rank_in_cluster": m.rank_in_cluster,
            }
            for m in mem_rows
        ],
    }


def stock_cluster(
    session: Session,
    code: str,
    *,
    profile_id: str = "pearson_w60",
    peers: int = 12,
) -> dict[str, Any] | None:
    run = latest_run(session, profile_id)
    if run is None:
        return None
    m = session.scalars(
        select(StockClusterMember)
        .where(StockClusterMember.run_id == run.run_id)
        .where(StockClusterMember.stock_code == code)
    ).first()
    if m is None:
        return None
    c = session.scalars(
        select(StockCluster)
        .where(StockCluster.run_id == run.run_id)
        .where(StockCluster.cluster_id == m.cluster_id)
    ).first()
    peer_rows = session.scalars(
        select(StockClusterMember)
        .where(StockClusterMember.run_id == run.run_id)
        .where(StockClusterMember.cluster_id == m.cluster_id)
        .order_by(StockClusterMember.rank_in_cluster)
        .limit(peers)
    ).all()
    codes = [p.stock_code for p in peer_rows]
    names = {
        code_: name
        for code_, name in session.execute(
            select(StockBasic.code, StockBasic.name).where(StockBasic.code.in_(codes))
        ).all()
    } if codes else {}
    return {
        "profile_id": profile_id,
        "run_id": run.run_id,
        "cluster_id": m.cluster_id,
        "label": c.label if c else "",
        "size": c.size if c else 0,
        "rank_in_cluster": m.rank_in_cluster,
        "centrality": float(m.centrality),
        "peers": [
            {
                "code": p.stock_code,
                "name": names.get(p.stock_code, p.stock_code),
                "rank_in_cluster": p.rank_in_cluster,
                "centrality": float(p.centrality),
            }
            for p in peer_rows
            if p.stock_code != code
        ],
    }
