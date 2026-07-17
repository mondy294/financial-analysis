"""PatternDefinition ↔ JSON/dict 序列化与校验。"""
from __future__ import annotations

from typing import Any

from quant_system.patterns.definition import (
    CONTEXT_STAGE,
    ContextSpec,
    HardConstraints,
    PatternDefinition,
    RelationSpec,
    Stage,
    StageRole,
    TargetValue,
    WindowConstraint,
)
from quant_system.patterns.features.catalog import FEATURE_CATALOG, feature_allows_role


class DefinitionValidationError(ValueError):
    pass


_VALID_ROLES = frozenset({"range", "up", "down"})


def infer_stage_role(name: str) -> StageRole | None:
    """旧 Stage 名 → 角色启发式（仅迁移/展示）。"""
    n = (name or "").strip().lower()
    if n in ("platform", "range", "box", "consolidate", "横盘"):
        return "range"
    if n in ("breakout", "up", "rally", "上涨", "突破"):
        return "up"
    if n in ("down", "drop", "selloff", "下跌", "回调"):
        return "down"
    if n.startswith("range") or n.startswith("platform"):
        return "range"
    if n.startswith("up") or n.startswith("break"):
        return "up"
    if n.startswith("down"):
        return "down"
    return None


def _parse_role(raw: Any, _stage_name: str) -> StageRole | None:
    """解析 role；缺省保持 None（不在反序列化时强行推断）。"""
    if raw is None or raw == "":
        return None
    role = str(raw).strip().lower()
    if role not in _VALID_ROLES:
        raise DefinitionValidationError(f"非法 stage.role: {raw}")
    return role  # type: ignore[return-value]


def target_to_dict(t: TargetValue) -> dict[str, Any]:
    d: dict[str, Any] = {
        "ideal": t.ideal,
        "tolerance": t.tolerance,
        "weight": t.weight,
        "mode": t.mode,
    }
    if t.hard:
        d["hard"] = True
        d["hard_min_similarity"] = t.hard_min_similarity
    if t.hard_min is not None:
        d["hard_min"] = t.hard_min
    if t.hard_max is not None:
        d["hard_max"] = t.hard_max
    return d


def target_from_dict(raw: dict[str, Any]) -> TargetValue:
    return TargetValue(
        ideal=float(raw["ideal"]),
        tolerance=float(raw["tolerance"]),
        weight=float(raw.get("weight", 1.0)),
        mode=raw.get("mode", "two_sided"),
        hard=bool(raw.get("hard", False)),
        hard_min_similarity=float(raw.get("hard_min_similarity", 100.0)),
        hard_min=float(raw["hard_min"]) if raw.get("hard_min") is not None else None,
        hard_max=float(raw["hard_max"]) if raw.get("hard_max") is not None else None,
    )


def definition_to_dict(d: PatternDefinition) -> dict[str, Any]:
    return {
        "id": d.id,
        "version": d.version,
        "display_name": d.display_name,
        "description": d.description,
        "threshold": d.threshold,
        "history_bars": d.history_bars,
        "stage_weights": dict(d.stage_weights),
        "timeline": [
            {
                "name": s.name,
                "role": s.role,
                "window": {
                    "min_length": s.window.min_length,
                    "max_length": s.window.max_length,
                },
                "targets": {k: target_to_dict(v) for k, v in s.targets.items()},
            }
            for s in d.timeline
        ],
        "relations": [
            {
                "name": r.name,
                "attach_to_stage": r.attach_to_stage,
                "stage_map": dict(r.stage_map),
                "target": target_to_dict(r.target),
            }
            for r in d.relations
        ],
        "context_features": [
            {
                "name": c.name,
                "lookback_bars": c.lookback_bars,
                "key": c.key,
                "target": target_to_dict(c.target),
            }
            for c in d.context_features
        ],
        "constraints": (
            {
                "exclude_st": d.constraints.exclude_st,
                "min_list_days": d.constraints.min_list_days,
                "min_amount": d.constraints.min_amount,
                "min_market_cap": d.constraints.min_market_cap,
                "allow_suspended": d.constraints.allow_suspended,
            }
            if d.constraints
            else None
        ),
        "metadata": dict(d.metadata),
    }


def definition_from_dict(raw: dict[str, Any], *, validate_catalog: bool = True) -> PatternDefinition:
    try:
        timeline = []
        for s in raw.get("timeline") or []:
            targets = {k: target_from_dict(v) for k, v in (s.get("targets") or {}).items()}
            win = s.get("window") or {}
            stage_name = str(s["name"])
            timeline.append(
                Stage(
                    name=stage_name,
                    window=WindowConstraint(
                        min_length=int(win["min_length"]),
                        max_length=int(win["max_length"]),
                    ),
                    targets=targets,
                    role=_parse_role(s.get("role"), stage_name),
                )
            )
        relations = [
            RelationSpec(
                name=str(r["name"]),
                attach_to_stage=str(r["attach_to_stage"]),
                stage_map={str(k): str(v) for k, v in (r.get("stage_map") or {}).items()},
                target=target_from_dict(r["target"]),
            )
            for r in (raw.get("relations") or [])
        ]
        context_features = [
            ContextSpec(
                name=str(c["name"]),
                lookback_bars=c.get("lookback_bars"),
                key=c.get("key"),
                target=target_from_dict(c["target"]),
            )
            for c in (raw.get("context_features") or [])
        ]
        c_raw = raw.get("constraints")
        constraints = None
        if isinstance(c_raw, dict):
            constraints = HardConstraints(
                exclude_st=bool(c_raw.get("exclude_st", True)),
                min_list_days=c_raw.get("min_list_days"),
                min_amount=c_raw.get("min_amount"),
                min_market_cap=c_raw.get("min_market_cap"),
                allow_suspended=bool(c_raw.get("allow_suspended", False)),
            )
        definition = PatternDefinition(
            id=str(raw["id"]).upper(),
            version=str(raw.get("version") or "v0"),
            display_name=str(raw.get("display_name") or raw["id"]),
            description=str(raw.get("description") or ""),
            timeline=timeline,
            threshold=float(raw.get("threshold", 80.0)),
            stage_weights={str(k): float(v) for k, v in (raw.get("stage_weights") or {}).items()},
            relations=relations,
            context_features=context_features,
            history_bars=raw.get("history_bars"),
            constraints=constraints,
            metadata=dict(raw.get("metadata") or {}),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DefinitionValidationError(f"Definition 解析失败: {exc}") from exc

    if validate_catalog:
        validate_against_catalog(definition)
    return definition


def validate_against_catalog(definition: PatternDefinition) -> None:
    errors: list[str] = []
    for stage in definition.timeline:
        for name in stage.targets:
            spec = FEATURE_CATALOG.get(name)
            if spec is None:
                errors.append(f"stage.{stage.name}: 未知特征 {name}")
            elif spec.kind not in ("stage",):
                errors.append(f"stage.{stage.name}: {name} 不是 stage 特征 (kind={spec.kind})")
            elif stage.role and not feature_allows_role(name, stage.role):
                errors.append(
                    f"stage.{stage.name}(role={stage.role}): 特征 {name} 不适用于该角色"
                )
    for rel in definition.relations:
        spec = FEATURE_CATALOG.get(rel.name)
        if spec is None:
            errors.append(f"relation: 未知特征 {rel.name}")
        elif spec.kind != "relation":
            errors.append(f"relation: {rel.name} 不是 relation 特征")
    for ctx in definition.context_features:
        spec = FEATURE_CATALOG.get(ctx.name)
        if spec is None:
            errors.append(f"context: 未知特征 {ctx.name}")
        elif spec.kind != "context":
            errors.append(f"context: {ctx.name} 不是 context 特征")
        if ctx.name == CONTEXT_STAGE:
            errors.append("context 特征名不能为保留字 context")
    if errors:
        raise DefinitionValidationError("; ".join(errors))


def bump_version(version: str) -> str:
    """tl-v2.5 → tl-v2.6；无数字则追加 -1。"""
    import re

    m = re.search(r"(.*?)(\d+)(\D*)$", version.strip())
    if not m:
        return f"{version}-1" if version else "v1"
    prefix, num, suffix = m.group(1), m.group(2), m.group(3)
    return f"{prefix}{int(num) + 1}{suffix}"
