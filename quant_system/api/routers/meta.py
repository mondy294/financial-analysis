from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from quant_system.api.deps import get_repos
from quant_system.api.schemas.common import PatternMetaOut, TradingDayOut
from quant_system.api.schemas.definitions import FeatureCatalogItemOut
from quant_system.api.services import definitions as def_svc
from quant_system.api.services import patterns as pattern_svc
from quant_system.data.repository import Repositories
from quant_system.infra import trading_calendar as tc

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/trading-day", response_model=TradingDayOut)
def trading_day(repos: Repositories = Depends(get_repos)) -> TradingDayOut:
    return TradingDayOut(
        latest_trading_day=tc.latest_trading_day(),
        pattern_latest_date=repos.abnormal.latest_trade_date(),
    )


@router.get("/patterns", response_model=list[PatternMetaOut])
def patterns() -> list[PatternMetaOut]:
    return [PatternMetaOut(**item) for item in pattern_svc.list_pattern_meta()]


@router.get("/feature-catalog", response_model=list[FeatureCatalogItemOut])
def feature_catalog(
    role: str | None = Query(
        None,
        description="可选：按 Stage 角色过滤 stage 特征（range|up|down）",
        pattern="^(range|up|down)$",
    ),
) -> list[FeatureCatalogItemOut]:
    return [FeatureCatalogItemOut(**x) for x in def_svc.feature_catalog(role=role)]
