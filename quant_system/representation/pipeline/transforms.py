"""内置 Transform 实现。"""
from __future__ import annotations

from typing import Any

from quant_system.representation.context import TransformContext
from quant_system.representation.extract.auto_policy import ConstantOlsAutoPolicy
from quant_system.representation.extract.ols_selected import get_extractor
from quant_system.representation.types import SeriesPanel


def transform_missing(
    panel: SeriesPanel,
    ctx: TransformContext,
    params: dict[str, Any],
) -> SeriesPanel:
    """P0：mask_no_fill — 不插值，原样传递。"""
    policy = str(params.get("policy") or "mask_no_fill")
    meta = {**panel.meta, "missing_policy": policy}
    return SeriesPanel(
        series_kind=panel.series_kind,
        codes=list(panel.codes),
        dates=list(panel.dates),
        values=panel.values,
        meta=meta,
    )


def transform_common_structure(
    panel: SeriesPanel,
    ctx: TransformContext,
    params: dict[str, Any],
) -> SeriesPanel:
    """Common Structure Extraction：mode=AUTO 走 Policy，再调 Extractor。"""
    if ctx.catalog is None:
        raise RuntimeError("common_structure 需要 TransformContext.catalog")

    mode = str(params.get("mode") or "AUTO").upper()
    ctx.params = {
        **ctx.params,
        "selector_k": params.get("selector_k", params.get("k", 5)),
        "redundancy_corr": params.get("redundancy_corr", 0.9),
        "min_obs": params.get("min_obs", 40),
        "candidate_families": params.get("candidate_families") or ["BROAD_INDEX"],
        "recipe_id": ctx.params.get("recipe_id"),
    }

    if mode == "AUTO":
        policy = ConstantOlsAutoPolicy()
        spec = policy.choose(panel, catalog=ctx.catalog, ctx=ctx)
        method_id = spec.method_id
        extract_params = {**spec.params, **{k: v for k, v in params.items() if k not in ("mode",)}}
    elif mode == "OLS_SELECTED":
        method_id = "ols_selected"
        extract_params = {
            "k": params.get("selector_k", params.get("k", 5)),
            "redundancy_corr": params.get("redundancy_corr", 0.9),
            "min_obs": params.get("min_obs", 40),
            "candidate_families": params.get("candidate_families") or ["BROAD_INDEX"],
        }
    else:
        raise ValueError(f"未知 common_structure mode: {mode}")

    extractor = get_extractor(method_id)
    result = extractor.extract(
        panel, catalog=ctx.catalog, ctx=ctx, params=extract_params
    )
    out = result.residual
    out.meta = {
        **out.meta,
        "representation_bundle": result.representation,
        "extractor": {
            "method_id": result.method_id,
            "version": result.method_version,
            **result.meta,
        },
    }
    return out


DEFAULT_REGISTRY = {
    "missing": transform_missing,
    "common_structure": transform_common_structure,
}
