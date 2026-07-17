from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from quant_system.api.deps import get_repos
from quant_system.api.schemas.relationships import StockRelationshipsOut
from quant_system.api.schemas.stocks import (
    FeaturePointOut,
    KlineBarOut,
    SnapshotOut,
    StockBriefOut,
    StockDetailOut,
)
from quant_system.api.services import relationships as rel_svc
from quant_system.api.services import stocks as stock_svc
from quant_system.data.repository import Repositories

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/search", response_model=list[StockBriefOut])
def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=50),
    repos: Repositories = Depends(get_repos),
) -> list[StockBriefOut]:
    return [StockBriefOut(**x) for x in stock_svc.search_stocks(repos, q, limit=limit)]


@router.get("/{code}", response_model=StockDetailOut)
def detail(code: str, repos: Repositories = Depends(get_repos)) -> StockDetailOut:
    return StockDetailOut(**stock_svc.get_stock_detail(repos, code))


@router.get("/{code}/kline", response_model=list[KlineBarOut])
def kline(
    code: str,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(250, ge=10, le=2000),
    adj: str = Query("qfq", pattern="^(none|qfq|hfq)$"),
    repos: Repositories = Depends(get_repos),
) -> list[KlineBarOut]:
    return [
        KlineBarOut(**x)
        for x in stock_svc.get_kline(repos, code, start=start, end=end, limit=limit, adj=adj)
    ]


@router.get("/{code}/features", response_model=list[FeaturePointOut])
def features(
    code: str,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(250, ge=10, le=2000),
    repos: Repositories = Depends(get_repos),
) -> list[FeaturePointOut]:
    return [
        FeaturePointOut(**x)
        for x in stock_svc.get_features(repos, code, start=start, end=end, limit=limit)
    ]


@router.get("/{code}/snapshot", response_model=SnapshotOut)
def snapshot(
    code: str,
    trade_date: date | None = None,
    repos: Repositories = Depends(get_repos),
) -> SnapshotOut:
    return SnapshotOut(**stock_svc.get_snapshot(repos, code, trade_date))


@router.get("/{code}/relationships", response_model=StockRelationshipsOut)
def relationships(
    code: str,
    trade_date: date | None = None,
    window: str = Query("W60", description="W60 / W250"),
    limit: int = Query(40, ge=1, le=200),
    repos: Repositories = Depends(get_repos),
) -> StockRelationshipsOut:
    return StockRelationshipsOut(
        **rel_svc.stock_relationships(
            repos,
            code,
            trade_date=trade_date,
            window=window,
            limit=limit,
        )
    )
