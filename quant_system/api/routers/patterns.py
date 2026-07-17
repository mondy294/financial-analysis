from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from quant_system.api.deps import get_repos
from quant_system.api.jobs.runner import job_to_dict, run_pattern_scan_job, submit_job
from quant_system.api.schemas.common import EvalRequest, JobOut, ScanRequest
from quant_system.api.schemas.patterns import PatternEvalOut, PatternHitOut, PatternStatsOut
from quant_system.api.services import patterns as pattern_svc
from quant_system.data.repository import Repositories
from quant_system.infra import trading_calendar as tc

router = APIRouter(prefix="/patterns", tags=["patterns"])


@router.get("/stats", response_model=PatternStatsOut)
def stats(
    trade_date: date | None = None,
    repos: Repositories = Depends(get_repos),
) -> PatternStatsOut:
    return PatternStatsOut(**pattern_svc.pattern_stats(repos, trade_date))


@router.get("/hits/{code}", response_model=list[PatternHitOut])
def hits(
    code: str,
    trade_date: date | None = None,
    repos: Repositories = Depends(get_repos),
) -> list[PatternHitOut]:
    return [PatternHitOut(**x) for x in pattern_svc.hits_of_code(repos, code, trade_date)]


@router.get("/{pattern_id}/top", response_model=list[PatternHitOut])
def top(
    pattern_id: str,
    trade_date: date | None = None,
    limit: int = Query(
        0,
        ge=0,
        le=5000,
        description="返回条数；0=全部命中（按相似度降序）",
    ),
    repos: Repositories = Depends(get_repos),
) -> list[PatternHitOut]:
    return [
        PatternHitOut(**x)
        for x in pattern_svc.top_hits(repos, pattern_id, trade_date, limit=limit)
    ]


@router.post("/eval", response_model=PatternEvalOut)
def eval_pattern(
    body: EvalRequest,
    repos: Repositories = Depends(get_repos),
) -> PatternEvalOut:
    return PatternEvalOut(
        **pattern_svc.eval_pattern(
            repos,
            code=body.code,
            trade_date=body.trade_date,
            pattern_id=body.pattern_id,
        )
    )


@router.post("/scan", response_model=JobOut)
def scan(body: ScanRequest) -> JobOut:
    d = body.trade_date or tc.latest_trading_day()

    def _fn(job) -> None:
        run_pattern_scan_job(
            job,
            trade_date=d,
            pattern_ids=body.pattern_ids,
            force=body.force,
        )

    job = submit_job("pattern.scan", _fn)
    return JobOut(**job_to_dict(job))
