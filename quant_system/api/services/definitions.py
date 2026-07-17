"""Pattern Definition 编辑 / 发布 / 草稿调试 API 服务。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from quant_system.api.errors import raise_bad_request, raise_not_found
from quant_system.api.services import patterns as pattern_svc
from quant_system.data.repository import Repositories
from quant_system.infra.db import session_scope
from quant_system.patterns.registry import invalidate_definition_cache
from quant_system.patterns.serde import DefinitionValidationError, definition_from_dict
from quant_system.patterns import store as def_store


def _parse_date(raw: str | date | None) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw
    return datetime.strptime(raw[:10], "%Y-%m-%d").date()


def list_definitions() -> list[dict[str, Any]]:
    with session_scope() as session:
        return def_store.list_definitions(session)


def get_editable(pattern_id: str) -> dict[str, Any]:
    try:
        with session_scope() as session:
            return def_store.get_editable(session, pattern_id)
    except KeyError as exc:
        raise_not_found(str(exc))


def save_draft(pattern_id: str, body: dict[str, Any], note: str | None = None) -> dict[str, Any]:
    try:
        with session_scope() as session:
            return def_store.save_draft(session, pattern_id, body, note=note)
    except KeyError as exc:
        raise_not_found(str(exc))
    except DefinitionValidationError as exc:
        raise_bad_request(str(exc))
    except ValueError as exc:
        raise_bad_request(str(exc))


def publish(pattern_id: str, note: str | None = None) -> dict[str, Any]:
    try:
        with session_scope() as session:
            out = def_store.publish(session, pattern_id, note=note)
        invalidate_definition_cache()
        return out
    except KeyError as exc:
        raise_not_found(str(exc))
    except DefinitionValidationError as exc:
        raise_bad_request(str(exc))
    except ValueError as exc:
        raise_bad_request(str(exc))


def clone_definition(
    pattern_id: str,
    *,
    new_id: str | None = None,
    display_name: str | None = None,
) -> dict[str, Any]:
    try:
        with session_scope() as session:
            return def_store.clone_definition(
                session, pattern_id, new_id=new_id, display_name=display_name
            )
    except KeyError as exc:
        raise_not_found(str(exc))
    except DefinitionValidationError as exc:
        raise_bad_request(str(exc))
    except ValueError as exc:
        raise_bad_request(str(exc))


def delete_definition(pattern_id: str) -> dict[str, Any]:
    try:
        with session_scope() as session:
            out = def_store.delete_definition(session, pattern_id)
        invalidate_definition_cache()
        return out
    except KeyError as exc:
        raise_not_found(str(exc))
    except DefinitionValidationError as exc:
        raise_bad_request(str(exc))


def list_revisions(pattern_id: str) -> list[dict[str, Any]]:
    try:
        with session_scope() as session:
            return def_store.list_revisions(session, pattern_id)
    except KeyError as exc:
        raise_not_found(str(exc))


def get_revision(pattern_id: str, version: str) -> dict[str, Any]:
    try:
        with session_scope() as session:
            return def_store.get_revision_body(session, pattern_id, version)
    except KeyError as exc:
        raise_not_found(str(exc))


def feature_catalog(role: str | None = None) -> list[dict[str, Any]]:
    return def_store.feature_catalog_public(role=role)


def _resolve_draft_definition(
    pattern_id: str, body: dict[str, Any] | None
) -> Any:
    if body is not None:
        payload = dict(body)
        payload["id"] = pattern_id.upper()
        try:
            return definition_from_dict(payload, validate_catalog=True)
        except (DefinitionValidationError, ValueError) as exc:
            raise_bad_request(str(exc))
    try:
        with session_scope() as session:
            return def_store.load_draft_definition(session, pattern_id)
    except KeyError as exc:
        raise_not_found(str(exc))
    except DefinitionValidationError as exc:
        raise_bad_request(str(exc))
    except ValueError as exc:
        raise_bad_request(str(exc))


def eval_preview(
    repos: Repositories,
    pattern_id: str,
    *,
    code: str,
    trade_date: str | date | None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    definition = _resolve_draft_definition(pattern_id, body)
    return pattern_svc.eval_with_definition(
        repos, definition, code=code, trade_date=_parse_date(trade_date)
    )


def run_dry_scan(
    repos: Repositories,
    pattern_id: str,
    *,
    trade_date: date,
    limit: int,
    body: dict[str, Any] | None = None,
    progress_cb: Any | None = None,
) -> dict[str, Any]:
    definition = _resolve_draft_definition(pattern_id, body)
    return pattern_svc.dry_scan_with_definition(
        repos,
        definition,
        trade_date=trade_date,
        limit=limit,
        progress_cb=progress_cb,
    )
