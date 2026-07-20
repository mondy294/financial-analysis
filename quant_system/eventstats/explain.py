from __future__ import annotations

from typing import Any

from quant_system.patterns.definition import CONTEXT_STAGE, PatternDefinition
from quant_system.patterns.result import PatternMatchResult


def _lookup_target(
    definition: PatternDefinition, key: str
) -> tuple[float | None, float]:
    """返回 (ideal, weight)。"""
    if "." not in key:
        return None, 1.0
    stage_name, feat = key.split(".", 1)
    if stage_name == CONTEXT_STAGE:
        for cf in definition.context_features:
            if cf.result_key == feat or cf.name == feat:
                return cf.target.ideal, cf.target.weight
        return None, 1.0
    for stage in definition.timeline:
        if stage.name == stage_name and feat in stage.targets:
            t = stage.targets[feat]
            return t.ideal, t.weight
    for rel in definition.relations:
        if rel.attach_to_stage == stage_name and rel.name == feat:
            return rel.target.ideal, rel.target.weight
    return None, 1.0


def build_match_explain(
    result: PatternMatchResult,
    definition: PatternDefinition,
    *,
    top_k: int = 8,
) -> dict[str, Any]:
    values = (result.metrics or {}).get("values") or {}
    hard = set(result.hard_failed or [])
    feature_explain: dict[str, Any] = {}
    contrib: list[dict[str, Any]] = []

    for key, sim in (result.feature_similarity or {}).items():
        ideal, weight = _lookup_target(definition, key)
        row = {
            "similarity": round(float(sim), 4),
            "value": values.get(key),
            "ideal": ideal,
            "weight": weight,
            "hard_failed": key in hard,
        }
        feature_explain[key] = row
        # 贡献：权重 × 缺口（100 - sim），越大越「拖分」；同时保留高分特征
        gap = max(0.0, 100.0 - float(sim))
        contrib.append(
            {
                "key": key,
                "similarity": row["similarity"],
                "weight": weight,
                "value": row["value"],
                "score_gap": round(gap * weight, 4),
            }
        )

    # Top：先按 similarity 降序取表现最好的特征（回答「为什么像」）
    top = sorted(contrib, key=lambda x: (-x["similarity"], -x["weight"]))[:top_k]
    stage_explain = {
        name: {"similarity": round(float(sim), 4), "weight": float(definition.stage_weights.get(name, 1.0))}
        for name, sim in (result.stage_similarity or {}).items()
    }
    ranges = (result.metrics or {}).get("chosen_window_ranges") or {}

    return {
        "entry_similarity": round(float(result.similarity), 4),
        "threshold": float(definition.threshold),
        "top_feature_contribution": top,
        "stage_explain": stage_explain,
        "feature_explain": feature_explain,
        "hard_failed": list(result.hard_failed or []),
        "chosen_windows": dict(result.chosen_windows or {}),
        "chosen_window_ranges": ranges,
        "reasons": list(result.reasons or []),
    }


def build_entry_snapshot(result: PatternMatchResult) -> dict[str, Any]:
    return {
        "similarity": result.similarity,
        "distance": result.distance,
        "stage_similarity": dict(result.stage_similarity or {}),
        "feature_similarity": dict(result.feature_similarity or {}),
        "chosen_windows": dict(result.chosen_windows or {}),
        "values": (result.metrics or {}).get("values") or {},
        "hard_failed": list(result.hard_failed or []),
    }
