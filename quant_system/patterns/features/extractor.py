from __future__ import annotations

import pandas as pd

from quant_system.patterns.definition import ContextSpec, PatternDefinition, RelationSpec, Stage
from quant_system.patterns.features.catalog import (
    StageAtoms,
    StageFrames,
    compute_stage_atoms,
    get_feature,
)
from quant_system.patterns.result import FeatureValue


class FeatureExtractor:
    """只负责 K 线 → FeatureValue，不算相似度。"""

    def extract_stage_features(
        self, stage: Stage, bars: pd.DataFrame,
    ) -> dict[str, FeatureValue]:
        out: dict[str, FeatureValue] = {}
        for name in stage.targets:
            spec = get_feature(name)
            if spec.kind != "stage" or spec.extract_stage is None:
                raise ValueError(f"feature {name} is not a stage feature")
            out[name] = spec.extract_stage(bars)
        return out

    def extract_atoms(self, bars: pd.DataFrame) -> StageAtoms:
        return compute_stage_atoms(bars)

    def extract_relation(
        self,
        relation: RelationSpec,
        atoms_by_stage: dict[str, StageAtoms],
        frames_by_stage: StageFrames | None = None,
    ) -> FeatureValue:
        spec = get_feature(relation.name)
        if spec.kind != "relation" or spec.extract_relation is None:
            raise ValueError(f"feature {relation.name} is not a relation feature")
        return spec.extract_relation(atoms_by_stage, relation.stage_map, frames_by_stage)

    def extract_context_features(
        self,
        context_specs: list[ContextSpec],
        history: pd.DataFrame,
    ) -> dict[str, FeatureValue]:
        """对股票级历史序列抽取 context 特征（每个 ContextSpec 各算一次）。"""
        out: dict[str, FeatureValue] = {}
        for ctx in context_specs:
            spec = get_feature(ctx.name)
            if spec.kind != "context" or spec.extract_context is None:
                raise ValueError(f"feature {ctx.name} is not a context feature")
            bars = history if ctx.lookback_bars is None else history.tail(ctx.lookback_bars)
            fv = spec.extract_context(bars.reset_index(drop=True))
            out[ctx.result_key] = FeatureValue(
                name=ctx.result_key,
                value=fv.value,
                unit=fv.unit,
                meta={
                    **fv.meta,
                    "feature": ctx.name,
                    "lookback_bars": ctx.lookback_bars,
                    "bars_used": int(len(bars)),
                },
            )
        return out

    def required_stage_features(self, definition: PatternDefinition) -> set[str]:
        names: set[str] = set()
        for stage in definition.timeline:
            names.update(stage.targets)
        return names
