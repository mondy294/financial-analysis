from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from quant_system.api.deps import get_repos
from quant_system.data.repository import Repositories
from quant_system.database.models import StrategySignal

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("")
def list_signals(
    trade_date: date | None = None,
    limit: int = Query(50, ge=1, le=200),
    hit_only: bool = True,
    repos: Repositories = Depends(get_repos),
) -> list[dict]:
    session = repos.stock._session  # type: ignore[attr-defined]
    d = trade_date
    if d is None:
        d = session.scalar(select(StrategySignal.trade_date).order_by(StrategySignal.trade_date.desc()).limit(1))
    if d is None:
        return []
    stmt = (
        select(StrategySignal)
        .where(StrategySignal.trade_date == d)
        .order_by(StrategySignal.final_score.desc())
        .limit(limit)
    )
    if hit_only:
        stmt = stmt.where(StrategySignal.hit.is_(True))
    rows = session.scalars(stmt).all()
    out = []
    for r in rows:
        stock = repos.stock.get_stock(r.code)
        out.append(
            {
                "trade_date": r.trade_date,
                "code": r.code,
                "name": stock.name if stock else "",
                "strategy_code": r.strategy_code,
                "signal_type": r.signal_type,
                "hit": r.hit,
                "final_score": float(r.final_score) if r.final_score is not None else None,
                "sub_score": float(r.sub_score) if r.sub_score is not None else None,
                "reasons": r.reasons or [],
            }
        )
    return out
