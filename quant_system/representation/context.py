"""Pipeline / Extractor 运行时上下文。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from quant_system.representation.catalog.protocol import DataCatalog


@dataclass
class TransformContext:
    asof: date
    catalog: DataCatalog | None = None
    params: dict[str, Any] = field(default_factory=dict)
