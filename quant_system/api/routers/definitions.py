"""Pattern Definition 编辑与草稿调试路由。"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends

from quant_system.api.deps import get_repos
from quant_system.api.jobs.runner import (
    get_job,
    job_to_dict,
    run_pattern_dry_scan_job,
    submit_job,
)
from quant_system.api.schemas.common import JobOut
from quant_system.api.schemas.definitions import (
    DefinitionCloneIn,
    DefinitionDeleteOut,
    DefinitionEditableOut,
    DefinitionListItemOut,
    DefinitionPublishIn,
    DefinitionPublishOut,
    DefinitionSaveIn,
    DryScanIn,
    EvalPreviewIn,
    RevisionBodyOut,
    RevisionMetaOut,
)
from quant_system.api.schemas.patterns import PatternEvalOut
from quant_system.api.services import definitions as def_svc
from quant_system.api.errors import raise_not_found
from quant_system.data.repository import Repositories
from quant_system.infra import trading_calendar as tc

router = APIRouter(prefix="/patterns/definitions", tags=["definitions"])


def _parse_day(raw: str | date | None) -> date:
    if raw is None:
        return tc.latest_trading_day()
    if isinstance(raw, date):
        return raw
    return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()


@router.get("", response_model=list[DefinitionListItemOut])
def list_definitions() -> list[DefinitionListItemOut]:
    return [DefinitionListItemOut(**x) for x in def_svc.list_definitions()]


@router.get("/{pattern_id}", response_model=DefinitionEditableOut)
def get_definition(pattern_id: str) -> DefinitionEditableOut:
    return DefinitionEditableOut(**def_svc.get_editable(pattern_id))


@router.put("/{pattern_id}", response_model=DefinitionEditableOut)
def put_definition(pattern_id: str, body: DefinitionSaveIn) -> DefinitionEditableOut:
    return DefinitionEditableOut(**def_svc.save_draft(pattern_id, body.body, note=body.note))


@router.post("/{pattern_id}/publish", response_model=DefinitionPublishOut)
def publish_definition(
    pattern_id: str, body: DefinitionPublishIn | None = None
) -> DefinitionPublishOut:
    note = body.note if body else None
    return DefinitionPublishOut(**def_svc.publish(pattern_id, note=note))


@router.post("/{pattern_id}/clone", response_model=DefinitionEditableOut)
def clone_definition(
    pattern_id: str, body: DefinitionCloneIn | None = None
) -> DefinitionEditableOut:
    payload = body or DefinitionCloneIn()
    return DefinitionEditableOut(
        **def_svc.clone_definition(
            pattern_id,
            new_id=payload.new_id,
            display_name=payload.display_name,
        )
    )


@router.delete("/{pattern_id}", response_model=DefinitionDeleteOut)
def delete_definition(pattern_id: str) -> DefinitionDeleteOut:
    return DefinitionDeleteOut(**def_svc.delete_definition(pattern_id))


@router.get("/{pattern_id}/revisions", response_model=list[RevisionMetaOut])
def revisions(pattern_id: str) -> list[RevisionMetaOut]:
    return [RevisionMetaOut(**x) for x in def_svc.list_revisions(pattern_id)]


@router.get("/{pattern_id}/revisions/{version}", response_model=RevisionBodyOut)
def revision_body(pattern_id: str, version: str) -> RevisionBodyOut:
    return RevisionBodyOut(**def_svc.get_revision(pattern_id, version))


@router.post("/{pattern_id}/eval-preview", response_model=PatternEvalOut)
def eval_preview(
    pattern_id: str,
    body: EvalPreviewIn,
    repos: Repositories = Depends(get_repos),
) -> PatternEvalOut:
    return PatternEvalOut(
        **def_svc.eval_preview(
            repos,
            pattern_id,
            code=body.code,
            trade_date=body.trade_date,
            body=body.body,
        )
    )


@router.post("/{pattern_id}/dry-scan", response_model=JobOut)
def dry_scan(pattern_id: str, body: DryScanIn) -> JobOut:
    d = _parse_day(body.trade_date)
    pid = pattern_id.strip().upper()
    payload = body.body

    def _fn(job) -> None:
        run_pattern_dry_scan_job(
            job,
            pattern_id=pid,
            trade_date=d,
            limit=body.limit,
            body=payload,
        )

    job = submit_job("pattern.dry_scan", _fn)
    return JobOut(**job_to_dict(job))


@router.get("/{pattern_id}/dry-scan/{job_id}", response_model=JobOut)
def dry_scan_job(pattern_id: str, job_id: str) -> JobOut:
    job = get_job(job_id)
    if job is None or job.kind != "pattern.dry_scan":
        raise_not_found(f"试扫 Job 不存在: {job_id}")
    return JobOut(**job_to_dict(job))
