from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from quant_system.api.deps import get_db_session
from quant_system.api.errors import raise_not_found
from quant_system.cluster import queries as cq  # 仅 queries，避免启动时强依赖 networkx

router = APIRouter(prefix="/clusters", tags=["clusters"])


@router.get("/meta")
def clusters_meta(session: Session = Depends(get_db_session)) -> dict:
    return {"profiles": cq.list_profiles(session)}


@router.get("")
def clusters_list(
    profile_id: str = Query("pearson_w60"),
    hide_singletons: bool = Query(True),
    session: Session = Depends(get_db_session),
) -> dict:
    return cq.list_clusters(
        session, profile_id=profile_id, hide_singletons=hide_singletons
    )


@router.get("/{cluster_id}")
def clusters_detail(
    cluster_id: int,
    profile_id: str = Query("pearson_w60"),
    limit: int = Query(100, ge=1, le=5000),
    session: Session = Depends(get_db_session),
) -> dict:
    data = cq.cluster_detail(
        session, cluster_id, profile_id=profile_id, limit=limit
    )
    if data is None:
        raise_not_found(f"cluster {cluster_id} not found for {profile_id}")
    return data

