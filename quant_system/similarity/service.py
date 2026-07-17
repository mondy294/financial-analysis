"""Similarity 编排：算边 +（默认）聚类。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional  # noqa: F401 — Any used by session

from loguru import logger

from quant_system.cluster.builder import (
    ClusterBuildReport,
    ClusterBuildRequest,
    build_clusters,
    default_pearson_profiles,
)
from quant_system.data.repository import Repositories
from quant_system.relationship.service import RunReport, build_relationships
from quant_system.representation.recipes import RECIPE_RETURN_CFR_AUTO
from quant_system.similarity.graph import SimilarityGraphRequest


@dataclass
class SimilarityRefreshReport:
    calc_date: date
    relationship: RunReport | None = None
    clusters: list[ClusterBuildReport] = field(default_factory=list)
    skipped_cluster: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "calc_date": self.calc_date.isoformat(),
            "relationship": {
                "universe_size": self.relationship.universe_size if self.relationship else 0,
                "pair_written_total": (
                    self.relationship.pair_written_total if self.relationship else 0
                ),
                "duration_ms": self.relationship.duration_ms if self.relationship else 0,
                "skipped": self.relationship.skipped if self.relationship else False,
                "dry_run": self.relationship.dry_run if self.relationship else False,
            } if self.relationship else None,
            "clusters": [
                {
                    "run_id": c.run_id,
                    "profile_id": c.profile_id,
                    "status": c.status,
                    "n_clusters": c.n_clusters,
                    "edge_used": c.edge_used,
                    "modularity": c.modularity,
                    "resolution": c.resolution,
                    "duration_ms": c.duration_ms,
                    "error": c.error,
                }
                for c in self.clusters
            ],
            "skipped_cluster": self.skipped_cluster,
            "error": self.error,
        }


def refresh_similarity(
    repos: Repositories,
    session: Any,
    *,
    calc_date: date,
    windows: Optional[list[str]] = None,
    pool_code: Optional[str] = None,
    board_filter: str = "MAIN",
    min_sample: int = 120,
    value_threshold: float = 0.3,
    max_neighbors: int = 200,
    dry_run: bool = False,
    force: bool = False,
    with_cluster: bool = True,
    cluster_w_min: float = 0.45,
    cluster_conf_min: float = 0.5,
    pipeline_recipe: str = RECIPE_RETURN_CFR_AUTO,
) -> SimilarityRefreshReport:
    """Pearson 边落库后，默认对 W60/W250 各跑一遍 Cluster。

    默认经 16 Pipeline（return_cfr_auto_v1）做公共结构剥离后再算相关。
    """
    report = SimilarityRefreshReport(calc_date=calc_date)
    rel = build_relationships(
        repos,
        calc_date=calc_date,
        relation_type="PEARSON",
        windows=windows,
        pool_code=pool_code,
        board_filter=board_filter,
        min_sample=min_sample,
        value_threshold=value_threshold,
        max_neighbors=max_neighbors,
        dry_run=dry_run,
        force=force,
        pipeline_recipe=pipeline_recipe,
        session=session,
    )
    report.relationship = rel
    if dry_run or not with_cluster:
        report.skipped_cluster = True
        return report
    if rel.skipped and not force:
        logger.info("关系批次 skip，继续聚类（使用已有边）")

    profiles = default_pearson_profiles(
        w_min=cluster_w_min,
        conf_min=cluster_conf_min,
        calc_date=calc_date,
    )
    for pref in profiles:
        cr = build_clusters(session, pref)
        report.clusters.append(cr)
        if cr.status == "FAILED":
            report.error = cr.error
            break
    return report


def build_cluster_only(
    session: Any,
    *,
    profile_id: str = "pearson_w60",
    window: str = "W60",
    w_min: float = 0.45,
    conf_min: float = 0.5,
    resolution: float | str = "auto",
    calc_date: date | None = None,
) -> ClusterBuildReport:
    req = ClusterBuildRequest(
        profile_id=profile_id,
        graph=SimilarityGraphRequest(
            types=("PEARSON",),
            window=window,
            merge_strategy="SINGLE",
            w_min=w_min,
            conf_min=conf_min,
            sign="pos",
            calc_date=calc_date,
        ),
        resolution=resolution if resolution != "auto" else "auto",
    )
    return build_clusters(session, req)
