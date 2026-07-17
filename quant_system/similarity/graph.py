from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from quant_system.similarity.protocol import SimilarityEdge


@dataclass(frozen=True)
class GraphEdge:
    code_a: str
    code_b: str
    weight: float
    confidence: float
    breakdown: dict[str, float] = field(default_factory=dict)
    sources: tuple[str, ...] = ()


@dataclass
class SimilarityGraph:
    nodes: set[str]
    edges: list[GraphEdge]

    def to_weight_dict(self) -> dict[tuple[str, str], float]:
        return {(e.code_a, e.code_b): e.weight for e in self.edges}


@dataclass(frozen=True)
class SimilarityGraphRequest:
    types: tuple[str, ...]
    window: str | dict[str, str]
    merge_strategy: Literal["SINGLE", "WEIGHTED", "MAX", "MIN"] = "SINGLE"
    weights: dict[str, float] | None = None
    w_min: float = 0.45
    conf_min: float = 0.5
    sign: Literal["pos", "neg", "abs"] = "pos"
    calc_date: date | None = None

    def window_for(self, sim_type: str) -> str:
        if isinstance(self.window, dict):
            return self.window[sim_type]
        return self.window

    def to_dict(self) -> dict[str, Any]:
        return {
            "types": list(self.types),
            "window": self.window if isinstance(self.window, str) else dict(self.window),
            "merge_strategy": self.merge_strategy,
            "weights": self.weights,
            "w_min": self.w_min,
            "conf_min": self.conf_min,
            "sign": self.sign,
            "calc_date": self.calc_date.isoformat() if self.calc_date else None,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> SimilarityGraphRequest:
        cd = d.get("calc_date")
        calc_date = date.fromisoformat(cd) if isinstance(cd, str) and cd else None
        win = d.get("window", "W60")
        types = tuple(d.get("types") or ["PEARSON"])
        return SimilarityGraphRequest(
            types=types,
            window=win,
            merge_strategy=d.get("merge_strategy") or "SINGLE",
            weights=d.get("weights"),
            w_min=float(d.get("w_min", 0.45)),
            conf_min=float(d.get("conf_min", 0.5)),
            sign=d.get("sign") or "pos",
            calc_date=calc_date,
        )


def _signed_score(score: float, sign: str) -> float | None:
    if sign == "pos":
        return score if score > 0 else None
    if sign == "neg":
        return -score if score < 0 else None
    return abs(score)


class SimilarityGraphBuilder:
    """从边仓储构图；支持 SINGLE / WEIGHTED merge。"""

    def __init__(self, edge_loader: Any) -> None:
        """edge_loader: 暴露 list_edges(similarity_type, window, as_of) -> list[SimilarityEdge]"""
        self._loader = edge_loader

    def build(self, req: SimilarityGraphRequest) -> SimilarityGraph:
        if req.merge_strategy == "SINGLE":
            if len(req.types) != 1:
                raise ValueError("SINGLE 策略要求 types 长度为 1")
            return self._build_single(req, req.types[0])
        if req.merge_strategy == "WEIGHTED":
            return self._build_weighted(req)
        if req.merge_strategy == "MAX":
            return self._build_reduce(req, mode="max")
        if req.merge_strategy == "MIN":
            return self._build_reduce(req, mode="min")
        raise ValueError(f"未知 merge_strategy: {req.merge_strategy}")

    def _load_type(self, req: SimilarityGraphRequest, sim_type: str) -> list[SimilarityEdge]:
        return list(
            self._loader.list_edges(
                similarity_type=sim_type,
                window=req.window_for(sim_type),
                as_of=req.calc_date,
            )
        )

    def _build_single(self, req: SimilarityGraphRequest, sim_type: str) -> SimilarityGraph:
        raw = self._load_type(req, sim_type)
        nodes: set[str] = set()
        edges: list[GraphEdge] = []
        for e in raw:
            w = _signed_score(e.score, req.sign)
            if w is None:
                continue
            conf = e.confidence if e.confidence is not None else 1.0
            if w < req.w_min or conf < req.conf_min:
                continue
            nodes.add(e.code_a)
            nodes.add(e.code_b)
            edges.append(
                GraphEdge(
                    code_a=e.code_a,
                    code_b=e.code_b,
                    weight=float(w),
                    confidence=float(conf),
                    breakdown=dict(e.breakdown or {}),
                    sources=(sim_type,),
                )
            )
        return SimilarityGraph(nodes=nodes, edges=edges)

    def _build_weighted(self, req: SimilarityGraphRequest) -> SimilarityGraph:
        weights = dict(req.weights or {})
        if not weights:
            # 等权
            n = len(req.types)
            weights = {t: 1.0 / n for t in req.types}
        # 按对聚合
        bucket: dict[tuple[str, str], list[tuple[str, float, float, dict[str, float]]]] = {}
        for t in req.types:
            for e in self._load_type(req, t):
                w = _signed_score(e.score, req.sign)
                if w is None:
                    continue
                conf = e.confidence if e.confidence is not None else 1.0
                key = (e.code_a, e.code_b)
                bucket.setdefault(key, []).append(
                    (t, float(w), float(conf), dict(e.breakdown or {}))
                )

        nodes: set[str] = set()
        edges: list[GraphEdge] = []
        for (a, b), parts in bucket.items():
            present = {t for t, _, _, _ in parts}
            # 仅对存在的类型重新归一
            wsum = sum(weights.get(t, 0.0) for t in present)
            if wsum <= 0:
                continue
            score = 0.0
            conf = 0.0
            bd: dict[str, float] = {}
            srcs: list[str] = []
            for t, s, c, breakdown in parts:
                wi = weights.get(t, 0.0) / wsum
                score += wi * s
                conf += wi * c
                srcs.append(t)
                for k, v in breakdown.items():
                    bd[k] = bd.get(k, 0.0) + wi * float(v)
            if score < req.w_min or conf < req.conf_min:
                continue
            nodes.add(a)
            nodes.add(b)
            edges.append(
                GraphEdge(
                    code_a=a,
                    code_b=b,
                    weight=float(score),
                    confidence=float(conf),
                    breakdown=bd,
                    sources=tuple(srcs),
                )
            )
        return SimilarityGraph(nodes=nodes, edges=edges)

    def _build_reduce(
        self, req: SimilarityGraphRequest, *, mode: str
    ) -> SimilarityGraph:
        bucket: dict[tuple[str, str], list[tuple[str, float, float, dict[str, float]]]] = {}
        for t in req.types:
            for e in self._load_type(req, t):
                w = _signed_score(e.score, req.sign)
                if w is None:
                    continue
                conf = e.confidence if e.confidence is not None else 1.0
                key = (e.code_a, e.code_b)
                bucket.setdefault(key, []).append(
                    (t, float(w), float(conf), dict(e.breakdown or {}))
                )
        nodes: set[str] = set()
        edges: list[GraphEdge] = []
        for (a, b), parts in bucket.items():
            if mode == "max":
                t, s, c, bd = max(parts, key=lambda x: x[1])
            else:
                t, s, c, bd = min(parts, key=lambda x: x[1])
            if s < req.w_min or c < req.conf_min:
                continue
            nodes.add(a)
            nodes.add(b)
            edges.append(
                GraphEdge(
                    code_a=a, code_b=b, weight=s, confidence=c,
                    breakdown=bd, sources=(t,),
                )
            )
        return SimilarityGraph(nodes=nodes, edges=edges)
