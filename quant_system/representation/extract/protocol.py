"""CommonComponentExtractor 协议。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from quant_system.representation.catalog.protocol import DataCatalog
from quant_system.representation.context import TransformContext
from quant_system.representation.types import RepresentationBundle, SeriesPanel


@dataclass(frozen=True)
class ExtractorSpec:
    method_id: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractionResult:
    residual: SeriesPanel
    representation: RepresentationBundle
    method_id: str
    method_version: str
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class CommonComponentExtractor(Protocol):
    method_id: str
    version: str

    def extract(
        self,
        target: SeriesPanel,
        *,
        catalog: DataCatalog,
        ctx: TransformContext,
        params: dict[str, Any] | None = None,
    ) -> ExtractionResult: ...


@runtime_checkable
class ExtractionAutoPolicy(Protocol):
    def choose(
        self,
        target: SeriesPanel,
        *,
        catalog: DataCatalog,
        ctx: TransformContext,
    ) -> ExtractorSpec: ...
