"""Pattern Definition 持久化：seed / draft / publish / load published。"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from quant_system.database.models import PatternDefinitionRevision, PatternDefinitionRow
from quant_system.patterns.definition import PatternDefinition
from quant_system.patterns.definitions import build_range_breakout_definition
from quant_system.patterns.serde import (
    DefinitionValidationError,
    bump_version,
    definition_from_dict,
    definition_to_dict,
)

_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")

DRAFT_VERSION = "__draft__"

# 内置种子 builders：id → callable
_SEED_BUILDERS: dict[str, Any] = {
    "RANGE_BREAKOUT": build_range_breakout_definition,
}


def _now() -> datetime:
    return datetime.utcnow()


def _body_json(definition: PatternDefinition) -> str:
    return json.dumps(definition_to_dict(definition), ensure_ascii=False, separators=(",", ":"))


def _parse_body(raw: str | dict[str, Any]) -> PatternDefinition:
    data = json.loads(raw) if isinstance(raw, str) else raw
    definition = definition_from_dict(data, validate_catalog=True)
    _validate_structure(definition)
    return definition


def _validate_structure(definition: PatternDefinition) -> None:
    names = {s.name for s in definition.timeline}
    for rel in definition.relations:
        for role, stage_name in rel.stage_map.items():
            if stage_name not in names:
                raise DefinitionValidationError(
                    f"relation {rel.name} stage_map[{role}]={stage_name} 不在 timeline 中"
                )


def ensure_seeded(session: Session) -> list[str]:
    """若 DB 无 seed 的 pattern，写入 draft + 同版 published。返回新 seed 的 id 列表。"""
    seeded: list[str] = []
    for pid, builder in _SEED_BUILDERS.items():
        row = session.get(PatternDefinitionRow, pid)
        if row is not None:
            continue
        definition = builder()
        now = _now()
        session.add(
            PatternDefinitionRow(
                id=definition.id,
                display_name=definition.display_name,
                description=definition.description,
                status="published",
                published_version=definition.version,
                created_at=now,
                updated_at=now,
            )
        )
        # 无 relationship 时需先 flush 父行，否则 SQLite FK 会失败
        session.flush()
        body = _body_json(definition)
        session.add(
            PatternDefinitionRevision(
                pattern_id=definition.id,
                version=DRAFT_VERSION,
                body_json=body,
                note="seed draft",
                created_at=now,
                created_by="seed",
            )
        )
        session.add(
            PatternDefinitionRevision(
                pattern_id=definition.id,
                version=definition.version,
                body_json=body,
                note="seed published",
                created_at=now,
                created_by="seed",
            )
        )
        seeded.append(definition.id)
    if seeded:
        session.flush()
    return seeded


def list_definitions(session: Session) -> list[dict[str, Any]]:
    ensure_seeded(session)
    rows = session.scalars(
        select(PatternDefinitionRow)
        .where(PatternDefinitionRow.status != "archived")
        .order_by(PatternDefinitionRow.id)
    ).all()
    out: list[dict[str, Any]] = []
    for row in rows:
        draft = _get_revision(session, row.id, DRAFT_VERSION)
        out.append(
            {
                "id": row.id,
                "display_name": row.display_name,
                "description": row.description or "",
                "status": row.status,
                "published_version": row.published_version,
                "has_draft": draft is not None,
                "deletable": row.id not in _SEED_BUILDERS,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return out


def _get_revision(
    session: Session, pattern_id: str, version: str
) -> PatternDefinitionRevision | None:
    return session.scalar(
        select(PatternDefinitionRevision).where(
            PatternDefinitionRevision.pattern_id == pattern_id,
            PatternDefinitionRevision.version == version,
        )
    )


def get_row(session: Session, pattern_id: str) -> PatternDefinitionRow:
    ensure_seeded(session)
    row = session.get(PatternDefinitionRow, pattern_id.upper())
    if row is None:
        raise KeyError(f"未知 Pattern: {pattern_id}")
    return row


def get_editable(session: Session, pattern_id: str) -> dict[str, Any]:
    """当前编辑态：draft 优先，否则 published body。"""
    row = get_row(session, pattern_id)
    draft = _get_revision(session, row.id, DRAFT_VERSION)
    if draft is not None:
        body = json.loads(draft.body_json)
        source = "draft"
        draft_updated_at = draft.created_at.isoformat()
    elif row.published_version:
        pub = _get_revision(session, row.id, row.published_version)
        if pub is None:
            raise RuntimeError(f"{row.id} published_version={row.published_version} 缺失 revision")
        body = json.loads(pub.body_json)
        source = "published"
        draft_updated_at = None
    else:
        raise RuntimeError(f"{row.id} 无 draft 也无 published")
    return {
        "id": row.id,
        "display_name": row.display_name,
        "description": row.description or "",
        "status": row.status,
        "published_version": row.published_version,
        "source": source,
        "draft_updated_at": draft_updated_at,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "body": body,
    }


def save_draft(
    session: Session,
    pattern_id: str,
    body: dict[str, Any],
    *,
    note: str | None = None,
) -> dict[str, Any]:
    row = get_row(session, pattern_id)
    payload = dict(body)
    payload["id"] = row.id
    # 草稿保留当前 published_version 作展示基准；真正 bump 在 publish
    if row.published_version:
        payload["version"] = row.published_version
    definition = _parse_body(payload)
    now = _now()
    body_str = _body_json(definition)
    rev = _get_revision(session, row.id, DRAFT_VERSION)
    if rev is None:
        session.add(
            PatternDefinitionRevision(
                pattern_id=row.id,
                version=DRAFT_VERSION,
                body_json=body_str,
                note=note or "draft save",
                created_at=now,
                created_by="local",
            )
        )
    else:
        rev.body_json = body_str
        rev.note = note or rev.note or "draft save"
        rev.created_at = now
        rev.created_by = "local"
    row.display_name = definition.display_name
    row.description = definition.description
    row.updated_at = now
    if row.status == "archived":
        row.status = "draft"
    session.flush()
    return get_editable(session, row.id)


def publish(
    session: Session,
    pattern_id: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    """draft → published；version 自动 bump。"""
    row = get_row(session, pattern_id)
    draft = _get_revision(session, row.id, DRAFT_VERSION)
    if draft is None:
        raise DefinitionValidationError("无草稿可发布，请先保存草稿")
    definition = _parse_body(draft.body_json)
    base_version = row.published_version or definition.version or "v0"
    new_version = bump_version(base_version)
    # 若 bump 撞到已有版本（极端），再 bump 一次
    while _get_revision(session, row.id, new_version) is not None:
        new_version = bump_version(new_version)

    now = _now()
    definition = replace(definition, version=new_version)
    body_str = _body_json(definition)
    session.add(
        PatternDefinitionRevision(
            pattern_id=row.id,
            version=new_version,
            body_json=body_str,
            note=note or f"publish {new_version}",
            created_at=now,
            created_by="local",
        )
    )
    # 草稿与 published 对齐
    draft.body_json = body_str
    draft.note = note or f"synced after publish {new_version}"
    draft.created_at = now
    row.published_version = new_version
    row.status = "published"
    row.display_name = definition.display_name
    row.description = definition.description
    row.updated_at = now
    session.flush()
    return {
        "id": row.id,
        "published_version": new_version,
        "status": row.status,
        "body": definition_to_dict(definition),
        "note": note,
    }


def load_published_definition(session: Session, pattern_id: str) -> PatternDefinition | None:
    ensure_seeded(session)
    row = session.get(PatternDefinitionRow, pattern_id.upper())
    if row is None or not row.published_version:
        return None
    rev = _get_revision(session, row.id, row.published_version)
    if rev is None:
        return None
    return _parse_body(rev.body_json)


def load_all_published(session: Session) -> list[PatternDefinition]:
    ensure_seeded(session)
    rows = session.scalars(
        select(PatternDefinitionRow).where(PatternDefinitionRow.status != "archived")
    ).all()
    out: list[PatternDefinition] = []
    for row in rows:
        if not row.published_version:
            continue
        rev = _get_revision(session, row.id, row.published_version)
        if rev is None:
            continue
        out.append(_parse_body(rev.body_json))
    return out


def load_draft_definition(session: Session, pattern_id: str) -> PatternDefinition:
    """调试用：draft 优先，否则 published。"""
    editable = get_editable(session, pattern_id)
    return _parse_body(editable["body"])


def list_revisions(session: Session, pattern_id: str) -> list[dict[str, Any]]:
    row = get_row(session, pattern_id)
    revs = session.scalars(
        select(PatternDefinitionRevision)
        .where(
            PatternDefinitionRevision.pattern_id == row.id,
            PatternDefinitionRevision.version != DRAFT_VERSION,
        )
        .order_by(PatternDefinitionRevision.created_at.desc())
    ).all()
    return [
        {
            "version": r.version,
            "note": r.note,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "created_by": r.created_by,
            "is_published": r.version == row.published_version,
        }
        for r in revs
    ]


def get_revision_body(session: Session, pattern_id: str, version: str) -> dict[str, Any]:
    row = get_row(session, pattern_id)
    rev = _get_revision(session, row.id, version)
    if rev is None:
        raise KeyError(f"版本不存在: {pattern_id}@{version}")
    return {
        "id": row.id,
        "version": rev.version,
        "note": rev.note,
        "created_at": rev.created_at.isoformat() if rev.created_at else None,
        "body": json.loads(rev.body_json),
    }


def feature_catalog_public(role: str | None = None) -> list[dict[str, Any]]:
    from quant_system.patterns.features.catalog import (
        FEATURE_CATALOG,
        feature_allows_role,
        feature_public_dict,
    )

    out: list[dict[str, Any]] = []
    for spec in FEATURE_CATALOG.values():
        if spec.kind not in ("stage", "relation", "context"):
            continue
        if role and spec.kind == "stage" and not feature_allows_role(spec.name, role):
            continue
        # role 过滤时 relation/context 仍返回（引导流程另块选用）
        out.append(feature_public_dict(spec))
    return out


def _suggest_clone_id(session: Session, source_id: str) -> str:
    base = f"{source_id}_COPY"
    if session.get(PatternDefinitionRow, base) is None:
        return base
    n = 2
    while True:
        cand = f"{source_id}_COPY{n}"
        if session.get(PatternDefinitionRow, cand) is None:
            return cand
        n += 1


def delete_definition(session: Session, pattern_id: str) -> dict[str, Any]:
    """删除策略及其全部 revision。内置 seed 不可删；已不存在则视为成功（幂等）。"""
    ensure_seeded(session)
    pid = pattern_id.strip().upper()
    if pid in _SEED_BUILDERS:
        raise DefinitionValidationError(
            f"内置策略 {pid} 不可删除，请复制后删除副本"
        )
    row = session.get(PatternDefinitionRow, pid)
    if row is None:
        return {"id": pid, "deleted": True, "already_gone": True}
    revs = session.scalars(
        select(PatternDefinitionRevision).where(
            PatternDefinitionRevision.pattern_id == pid
        )
    ).all()
    for rev in revs:
        session.delete(rev)
    session.flush()
    session.delete(row)
    session.flush()
    return {"id": pid, "deleted": True, "already_gone": False}


def clone_definition(
    session: Session,
    source_id: str,
    *,
    new_id: str | None = None,
    display_name: str | None = None,
) -> dict[str, Any]:
    """复制已有策略结构为新草稿（未发布，不进入正式 scan）。"""
    editable = get_editable(session, source_id)
    src_row = get_row(session, source_id)

    if new_id:
        pid = new_id.strip().upper()
    else:
        pid = _suggest_clone_id(session, src_row.id)

    if not _ID_RE.match(pid):
        raise DefinitionValidationError(
            "策略 ID 须为 2–32 位大写字母/数字/下划线，且以字母开头"
        )
    if session.get(PatternDefinitionRow, pid) is not None:
        raise DefinitionValidationError(f"策略 ID 已存在: {pid}")

    body = dict(editable["body"])
    body["id"] = pid
    body["version"] = "v0"
    body["display_name"] = (display_name or "").strip() or f"{src_row.display_name} (副本)"
    if body.get("description") and "克隆自" not in str(body.get("description")):
        body["description"] = f"{body['description']}（克隆自 {src_row.id}）"
    elif not body.get("description"):
        body["description"] = f"克隆自 {src_row.id}"

    definition = _parse_body(body)
    now = _now()
    session.add(
        PatternDefinitionRow(
            id=pid,
            display_name=definition.display_name,
            description=definition.description,
            status="draft",
            published_version=None,
            created_at=now,
            updated_at=now,
        )
    )
    session.flush()
    session.add(
        PatternDefinitionRevision(
            pattern_id=pid,
            version=DRAFT_VERSION,
            body_json=_body_json(definition),
            note=f"cloned from {src_row.id}",
            created_at=now,
            created_by="local",
        )
    )
    session.flush()
    return get_editable(session, pid)
