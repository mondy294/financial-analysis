"""PipelineRecipe：协议支持 DAG；P0 runner 要求必须是链。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TransformNodeSpec:
    node_id: str
    transform_id: str
    params: dict[str, Any] = field(default_factory=dict)
    inputs: tuple[str, ...] = ()


@dataclass(frozen=True)
class PipelineRecipe:
    recipe_id: str
    nodes: tuple[TransformNodeSpec, ...]
    outputs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipe_id": self.recipe_id,
            "nodes": [
                {
                    "node_id": n.node_id,
                    "transform_id": n.transform_id,
                    "params": dict(n.params),
                    "inputs": list(n.inputs),
                }
                for n in self.nodes
            ],
            "outputs": list(self.outputs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineRecipe:
        nodes = tuple(
            TransformNodeSpec(
                node_id=n["node_id"],
                transform_id=n["transform_id"],
                params=dict(n.get("params") or {}),
                inputs=tuple(n.get("inputs") or ()),
            )
            for n in data["nodes"]
        )
        return cls(
            recipe_id=str(data["recipe_id"]),
            nodes=nodes,
            outputs=tuple(data.get("outputs") or ()),
        )


def assert_linear_chain(recipe: PipelineRecipe) -> None:
    """P0：DAG 必须退化为单链（每个节点至多 1 个输入，按拓扑一条路径）。"""
    if not recipe.nodes:
        raise ValueError("recipe.nodes 为空")
    by_id = {n.node_id: n for n in recipe.nodes}
    if len(by_id) != len(recipe.nodes):
        raise ValueError("node_id 重复")
    roots = [n for n in recipe.nodes if not n.inputs]
    if len(roots) != 1:
        raise ValueError(f"P0 仅支持单根线性链，根节点数={len(roots)}")
    for n in recipe.nodes:
        if len(n.inputs) > 1:
            raise ValueError(f"P0 不支持多输入节点: {n.node_id}")
        for inp in n.inputs:
            if inp not in by_id:
                raise ValueError(f"未知上游 {inp} <- {n.node_id}")
    # 从 root 走唯一后继
    succ: dict[str, list[str]] = {n.node_id: [] for n in recipe.nodes}
    for n in recipe.nodes:
        for inp in n.inputs:
            succ[inp].append(n.node_id)
    for nid, children in succ.items():
        if len(children) > 1:
            raise ValueError(f"P0 不支持分叉: {nid} -> {children}")
    order = []
    cur = roots[0].node_id
    seen = set()
    while cur:
        if cur in seen:
            raise ValueError("recipe 存在环")
        seen.add(cur)
        order.append(cur)
        children = succ.get(cur) or []
        cur = children[0] if children else ""
    if set(order) != set(by_id):
        raise ValueError("recipe 不是单连通链")
