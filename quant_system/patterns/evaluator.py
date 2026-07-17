from __future__ import annotations

from dataclasses import dataclass

from quant_system.patterns.definition import TargetValue
from quant_system.patterns.result import FeatureSimilarity, FeatureValue


@dataclass
class LinearToleranceEvaluator:
    """可解释默认 Evaluator：按 mode 修正后的线性容差距离。"""

    epsilon: float = 1e-12

    def evaluate(self, feature: FeatureValue, target: TargetValue) -> FeatureSimilarity:
        if feature.value is None:
            return FeatureSimilarity(
                name=feature.name,
                similarity=0.0,
                distance=1.0,
                actual=None,
                ideal=target.ideal,
                weight=target.weight,
            )

        actual = float(feature.value)
        ideal = float(target.ideal)
        tol = max(float(target.tolerance), self.epsilon)
        raw = abs(actual - ideal)

        if target.mode == "one_sided_high":
            # 达到 ideal 后更高不罚；低于 ideal 按距离罚
            distance = 0.0 if actual >= ideal else (ideal - actual) / tol
        elif target.mode == "one_sided_low":
            distance = 0.0 if actual <= ideal else (actual - ideal) / tol
        else:
            distance = raw / tol

        similarity = max(0.0, 1.0 - distance) * 100.0
        return FeatureSimilarity(
            name=feature.name,
            similarity=round(similarity, 4),
            distance=round(distance, 6),
            actual=actual,
            ideal=ideal,
            weight=target.weight,
        )
