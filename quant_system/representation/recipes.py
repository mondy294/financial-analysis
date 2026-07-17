"""预置 PipelineRecipe。"""
from __future__ import annotations

from quant_system.representation.pipeline.recipe import PipelineRecipe, TransformNodeSpec

RECIPE_RETURN_RAW = "return_raw_v1"
RECIPE_RETURN_CFR_AUTO = "return_cfr_auto_v1"


def recipe_return_raw() -> PipelineRecipe:
    return PipelineRecipe(
        recipe_id=RECIPE_RETURN_RAW,
        nodes=(
            TransformNodeSpec(
                node_id="missing",
                transform_id="missing",
                params={"policy": "mask_no_fill"},
                inputs=(),
            ),
        ),
        outputs=("missing",),
    )


def recipe_return_cfr_auto() -> PipelineRecipe:
    return PipelineRecipe(
        recipe_id=RECIPE_RETURN_CFR_AUTO,
        nodes=(
            TransformNodeSpec(
                node_id="missing",
                transform_id="missing",
                params={"policy": "mask_no_fill"},
                inputs=(),
            ),
            TransformNodeSpec(
                node_id="cfr",
                transform_id="common_structure",
                params={
                    "mode": "AUTO",
                    "candidate_families": ["BROAD_INDEX"],
                    "selector_k": 5,
                    "redundancy_corr": 0.9,
                    "min_obs": 40,
                },
                inputs=("missing",),
            ),
        ),
        outputs=("cfr",),
    )


_REGISTRY: dict[str, PipelineRecipe] = {
    RECIPE_RETURN_RAW: recipe_return_raw(),
    RECIPE_RETURN_CFR_AUTO: recipe_return_cfr_auto(),
}


def get_recipe(recipe_id: str) -> PipelineRecipe:
    key = (recipe_id or RECIPE_RETURN_CFR_AUTO).strip()
    if key not in _REGISTRY:
        raise KeyError(f"未知 pipeline_recipe: {recipe_id}（可选 {list(_REGISTRY)}）")
    return _REGISTRY[key]
