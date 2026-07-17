"""Market Representation 中台（设计 16 v3）。

全系统公共基建：Pipeline / DataCatalog / Common Structure Extraction / RepresentationBundle。
Similarity / Pattern / Feature / ML 应消费本包产出，而不是私有减指数。
"""
from __future__ import annotations

from quant_system.representation.facade import apply_return_pipeline, pipeline_meta_for_edges
from quant_system.representation.recipes import (
    RECIPE_RETURN_CFR_AUTO,
    RECIPE_RETURN_RAW,
    get_recipe,
)
from quant_system.representation.types import RepresentationBundle, SeriesPanel

__all__ = [
    "SeriesPanel",
    "RepresentationBundle",
    "apply_return_pipeline",
    "pipeline_meta_for_edges",
    "get_recipe",
    "RECIPE_RETURN_CFR_AUTO",
    "RECIPE_RETURN_RAW",
]
