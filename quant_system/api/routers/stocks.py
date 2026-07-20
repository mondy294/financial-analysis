from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from sqlalchemy.orm import Session

from quant_system.api.deps import get_db_session, get_repos
from quant_system.api.schemas.relationships import StockRelationshipsOut
from quant_system.api.schemas.stocks import (
    DisclosuresByDateOut,
    EarningsFairAnchorOut,
    FeaturePointOut,
    FinancialHighlightsOut,
    ForecastFactorAnalysisOut,
    KlineBarOut,
    SnapshotOut,
    StockBriefOut,
    StockDetailOut,
    StockDisclosuresOut,
)
from quant_system.api.services import relationships as rel_svc
from quant_system.api.services import stocks as stock_svc
from quant_system.cluster import queries as cluster_q  # noqa: I001 — 勿经 cluster 包级拉 networkx
from quant_system.data.repository import Repositories

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/search", response_model=list[StockBriefOut])
def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=50),
    repos: Repositories = Depends(get_repos),
) -> list[StockBriefOut]:
    return [StockBriefOut(**x) for x in stock_svc.search_stocks(repos, q, limit=limit)]


@router.get("/disclosures", response_model=DisclosuresByDateOut)
def disclosures(
    start_date: date | None = Query(None, description="公告日起始"),
    end_date: date | None = Query(None, description="公告日结束"),
    notice_date: date | None = Query(None, description="单日（兼容旧参数）"),
    main_only: bool = Query(False, description="仅沪深主板（含原中小板）"),
    enrich_forecast: bool = Query(
        False, description="挂上业绩预告/报表指标与单季环比（首次拉全市场表，稍慢）"
    ),
    enrich_returns: bool = Query(
        False, description="挂上公告后股价涨跌（扫 K 线，较慢；默认关闭）"
    ),
    category: str | None = Query(
        None,
        description="逗号分隔类别：forecast,express,interim,annual,q1,q3,other",
    ),
    repos: Repositories = Depends(get_repos),
) -> DisclosuresByDateOut:
    """按公告日/区间查看谁发了业绩预告/快报/财报等。"""
    cats = [c.strip() for c in (category or "").split(",") if c.strip()] or None
    return DisclosuresByDateOut(
        **stock_svc.get_disclosures_by_date(
            repos,
            notice_date,
            start_date=start_date,
            end_date=end_date,
            categories=cats,
            main_only=main_only,
            enrich_forecast=enrich_forecast,
            enrich_returns=enrich_returns,
        )
    )


@router.get("/disclosures/factor-analysis", response_model=ForecastFactorAnalysisOut)
def disclosure_factor_analysis(
    start_date: date | None = Query(None, description="公告日起始"),
    end_date: date | None = Query(None, description="公告日结束"),
    notice_date: date | None = Query(None, description="单日（兼容）"),
    main_only: bool = Query(True, description="仅沪深主板"),
    repos: Repositories = Depends(get_repos),
) -> ForecastFactorAnalysisOut:
    """中报预告样本：PE/市值/年化预告利润 vs 公告后涨跌的 OLS 系数。"""
    return ForecastFactorAnalysisOut(
        **stock_svc.get_disclosure_factor_analysis(
            repos,
            start_date=start_date,
            end_date=end_date,
            notice_date=notice_date,
            main_only=main_only,
        )
    )


@router.get("/{code}", response_model=StockDetailOut)
def detail(code: str, repos: Repositories = Depends(get_repos)) -> StockDetailOut:
    return StockDetailOut(**stock_svc.get_stock_detail(repos, code))


@router.get("/{code}/earnings-fair-anchor", response_model=EarningsFairAnchorOut)
def earnings_fair_anchor(
    code: str,
    lookback_days: int = Query(5, ge=1, le=30),
    use_cluster: bool = Query(False),
    repos: Repositories = Depends(get_repos),
) -> EarningsFairAnchorOut:
    """近 lookback_days 日有业绩且可算公允价时，返回 K 线合理价锚点。"""
    from quant_system.earnings_analytics import service as eea

    return EarningsFairAnchorOut(
        **eea.service_earnings_fair_anchor(
            repos,
            code,
            lookback_days=lookback_days,
            use_cluster=use_cluster,
        )
    )


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


@router.get("/{code}/financials", response_model=FinancialHighlightsOut)
def financials(
    code: str,
    years: int = Query(5, ge=1, le=20, description="最近年报年数"),
    repos: Repositories = Depends(get_repos),
) -> FinancialHighlightsOut:
    """近 N 年年报主要财务指标，并附上晚于最新年报的季报/中报。"""
    return FinancialHighlightsOut(
        **stock_svc.get_financial_highlights(repos, code, years=years)
    )


@router.get("/{code}/disclosures", response_model=StockDisclosuresOut)
def stock_disclosures(
    code: str,
    around_date: date | None = Query(
        None, description="围绕该日取窗口（披露页跳转时传列表上的公告日）"
    ),
    lookback_days: int = Query(21, ge=1, le=30),
    repos: Repositories = Depends(get_repos),
) -> StockDisclosuresOut:
    """个股近期财务类公告，与 /stocks/disclosures 列表同源。"""
    return StockDisclosuresOut(
        **stock_svc.get_stock_disclosures(
            repos,
            code,
            around_date=around_date,
            lookback_days=lookback_days,
        )
    )


@router.get("/{code}/parent-profit", response_model=FinancialHighlightsOut)
def parent_profit(
    code: str,
    years: int = Query(5, ge=1, le=20, description="最近年报年数"),
    repos: Repositories = Depends(get_repos),
) -> FinancialHighlightsOut:
    """兼容旧路径，同 /financials。"""
    return FinancialHighlightsOut(
        **stock_svc.get_financial_highlights(repos, code, years=years)
    )


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


@router.get("/{code}/cluster")
def stock_cluster(
    code: str,
    profile_id: str = Query("pearson_w60"),
    peers: int = Query(12, ge=1, le=50),
    session: Session = Depends(get_db_session),
) -> dict:
    data = cluster_q.stock_cluster(
        session, code.upper(), profile_id=profile_id, peers=peers
    )
    return data or {
        "profile_id": profile_id,
        "cluster_id": None,
        "label": None,
        "size": 0,
        "peers": [],
    }
