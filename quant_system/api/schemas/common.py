from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class HealthOut(BaseModel):
    status: str = "ok"
    version: str


class TradingDayOut(BaseModel):
    latest_trading_day: date | None
    pattern_latest_date: date | None = None


class PatternMetaOut(BaseModel):
    id: str
    display_name: str
    version: str
    threshold: float
    description: str = ""


class JobOut(BaseModel):
    job_id: str
    kind: str
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    progress: float = 0.0
    message: str | None = None
    error: str | None = None
    result: dict | None = None


class ScanRequest(BaseModel):
    trade_date: date | None = None
    pattern_ids: list[str] | None = None
    force: bool = False


class EvalRequest(BaseModel):
    code: str = Field(..., min_length=4)
    trade_date: date | None = None
    pattern_id: str = "RANGE_BREAKOUT"
