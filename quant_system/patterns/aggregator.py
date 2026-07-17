from __future__ import annotations

from quant_system.patterns.result import FeatureSimilarity


def aggregate_weighted(items: list[FeatureSimilarity]) -> float:
    total_w = 0.0
    acc = 0.0
    for item in items:
        if item.weight <= 0:
            continue
        total_w += item.weight
        acc += item.similarity * item.weight
    if total_w <= 0:
        return 0.0
    return round(acc / total_w, 4)


def aggregate_stages(
    stage_scores: dict[str, float],
    stage_weights: dict[str, float],
) -> float:
    if not stage_scores:
        return 0.0
    if not stage_weights:
        vals = list(stage_scores.values())
        return round(sum(vals) / len(vals), 4)

    total_w = 0.0
    acc = 0.0
    for name, score in stage_scores.items():
        w = float(stage_weights.get(name, 1.0))
        if w <= 0:
            continue
        total_w += w
        acc += score * w
    if total_w <= 0:
        return 0.0
    return round(acc / total_w, 4)
