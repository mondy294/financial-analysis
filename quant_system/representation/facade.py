"""对外入口：收益率面板 → Pipeline → 变换后面板 + Representation。"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from quant_system.representation.catalog.index_catalog import build_default_catalog
from quant_system.representation.context import TransformContext
from quant_system.representation.pipeline.runner import PipelineResult, SeriesPipeline
from quant_system.representation.pipeline.transforms import DEFAULT_REGISTRY
from quant_system.representation.recipes import RECIPE_RETURN_RAW, get_recipe
from quant_system.representation.types import SeriesPanel


def apply_return_pipeline(
    returns: pd.DataFrame,
    *,
    session: Session,
    asof: date,
    recipe_id: str = "return_cfr_auto_v1",
) -> PipelineResult:
    recipe = get_recipe(recipe_id)
    panel = SeriesPanel.from_dataframe(returns, series_kind="RETURN", meta={"asof": asof.isoformat()})
    catalog = None if recipe.recipe_id == RECIPE_RETURN_RAW else build_default_catalog(session)
    ctx = TransformContext(
        asof=asof,
        catalog=catalog,
        params={"recipe_id": recipe.recipe_id},
    )
    pipe = SeriesPipeline(DEFAULT_REGISTRY)
    return pipe.run(panel, recipe=recipe, ctx=ctx)


def pipeline_meta_for_edges(result: PipelineResult) -> dict[str, Any]:
    """写入边 meta / run 统计的可复现快照。"""
    snap: dict[str, Any] = {
        "pipeline_recipe": result.recipe.to_dict(),
        "recipe_id": result.recipe.recipe_id,
    }
    if result.exposures is not None:
        snap["representation"] = {
            "recipe_id": result.exposures.recipe_id,
            "n_codes_with_features": len(result.exposures.features or {}),
            "meta": dict(result.exposures.meta),
        }
    for tr in result.step_traces:
        if tr.transform_id == "common_structure":
            snap["common_structure"] = tr.meta
    return snap
