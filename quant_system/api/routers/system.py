from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from quant_system.api.deps import get_repos
from quant_system.api.schemas.common import JobOut
from quant_system.api.tasks.service import catalog_payload, run_task
from quant_system.data.repository import Repositories
from quant_system.database.models import DailyFeature, DailyKline, StockBasic

router = APIRouter(prefix="/system", tags=["system"])


class TaskRunIn(BaseModel):
    task_id: str = Field(..., min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


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


@router.get("/tasks")
def list_system_tasks() -> dict:
    """批处理任务目录（分组）+ 当前重任务占用。"""
    return catalog_payload()


@router.post("/tasks/run", response_model=JobOut)
def run_system_task(body: TaskRunIn) -> JobOut:
    return JobOut(**run_task(body.task_id, body.params))


@router.get("/cache/stats")
def cache_stats() -> dict[str, Any]:
    from quant_system.infra.cache import cache_stats as _stats

    return {"namespaces": _stats()}
