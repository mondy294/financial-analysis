"""AUTO = 选 Extractor 的策略（P0 可恒定 ols_selected，禁止写死四指数）。"""
from __future__ import annotations

from quant_system.representation.catalog.protocol import DataCatalog
from quant_system.representation.context import TransformContext
from quant_system.representation.extract.protocol import ExtractorSpec
from quant_system.representation.types import SeriesPanel


class ConstantOlsAutoPolicy:
    """P0：恒定选择 ols_selected；参数来自 recipe，不绑死因子 id。"""

    def choose(
        self,
        target: SeriesPanel,
        *,
        catalog: DataCatalog,
        ctx: TransformContext,
    ) -> ExtractorSpec:
        return ExtractorSpec(
            method_id="ols_selected",
            params={
                "k": int(ctx.params.get("selector_k", 5)),
                "redundancy_corr": float(ctx.params.get("redundancy_corr", 0.9)),
                "min_obs": int(ctx.params.get("min_obs", 40)),
                "candidate_families": list(
                    ctx.params.get("candidate_families") or ["BROAD_INDEX"]
                ),
            },
        )
