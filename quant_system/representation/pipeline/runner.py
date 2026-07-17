"""SeriesPipeline 线性执行器。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from quant_system.representation.context import TransformContext
from quant_system.representation.pipeline.recipe import PipelineRecipe, assert_linear_chain
from quant_system.representation.types import RepresentationBundle, SeriesPanel

TransformFn = Callable[[SeriesPanel, TransformContext, dict[str, Any]], SeriesPanel]


@dataclass
class StepTrace:
    node_id: str
    transform_id: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    panel: SeriesPanel
    exposures: RepresentationBundle | None
    step_traces: tuple[StepTrace, ...]
    recipe: PipelineRecipe
    meta: dict[str, Any] = field(default_factory=dict)


class SeriesPipeline:
    def __init__(self, registry: dict[str, TransformFn]) -> None:
        self._registry = registry

    def run(
        self,
        panel: SeriesPanel,
        *,
        recipe: PipelineRecipe,
        ctx: TransformContext,
    ) -> PipelineResult:
        assert_linear_chain(recipe)
        # 拓扑序：root → …
        by_id = {n.node_id: n for n in recipe.nodes}
        root = next(n for n in recipe.nodes if not n.inputs)
        order = [root.node_id]
        while True:
            nxt = next((n for n in recipe.nodes if n.inputs == (order[-1],)), None)
            if nxt is None:
                break
            order.append(nxt.node_id)

        current = panel
        traces: list[StepTrace] = []
        exposures: RepresentationBundle | None = None

        for nid in order:
            node = by_id[nid]
            fn = self._registry.get(node.transform_id)
            if fn is None:
                raise KeyError(f"未注册 transform: {node.transform_id}")
            before_meta = dict(current.meta)
            current = fn(current, ctx, dict(node.params))
            # common_structure 会把 bundle 挂到 panel.meta
            if "representation_bundle" in current.meta:
                exposures = current.meta.pop("representation_bundle")
            traces.append(
                StepTrace(
                    node_id=nid,
                    transform_id=node.transform_id,
                    meta={
                        "params": dict(node.params),
                        "panel_meta_keys": sorted(set(current.meta) | set(before_meta)),
                    },
                )
            )

        out_id = recipe.outputs[0] if recipe.outputs else order[-1]
        if out_id != order[-1]:
            raise ValueError(f"P0 输出节点必须是链尾，got {out_id} tail={order[-1]}")

        return PipelineResult(
            panel=current,
            exposures=exposures,
            step_traces=tuple(traces),
            recipe=recipe,
            meta={"recipe_id": recipe.recipe_id},
        )
