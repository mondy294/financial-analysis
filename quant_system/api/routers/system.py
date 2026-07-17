from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text

from quant_system.api.deps import get_repos
from quant_system.data.repository import Repositories
from quant_system.database.models import DailyFeature, DailyKline, StockBasic

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/doctor")
def doctor(repos: Repositories = Depends(get_repos)) -> dict:
    session = repos.stock._session  # type: ignore[attr-defined]
    stock_n = session.scalar(select(func.count()).select_from(StockBasic)) or 0
    kline_latest = session.scalar(select(func.max(DailyKline.trade_date)))
    feature_latest = session.scalar(select(func.max(DailyFeature.trade_date)))
    pattern_latest = repos.abnormal.latest_trade_date()
    tables_ok = True
    try:
        session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        tables_ok = False
    return {
        "db_ok": tables_ok,
        "stock_count": int(stock_n),
        "kline_latest": kline_latest,
        "feature_latest": feature_latest,
        "pattern_latest": pattern_latest,
    }
