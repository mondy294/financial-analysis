"""DataCatalog：一切可作为结构抽取来源的数据宇宙。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol, Sequence, runtime_checkable

import pandas as pd


@dataclass(frozen=True)
class DataSeriesDef:
    data_id: str
    name: str
    family: str
    source: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class DataPanel:
    """列=data_id，行=date，值=日收益（或约定口径）。"""

    data_ids: list[str]
    dates: list[date]
    values: pd.DataFrame
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class DataCatalog(Protocol):
    catalog_id: str
    version: str

    def list(self, *, families: Sequence[str] | None = None) -> list[DataSeriesDef]: ...

    def load(
        self,
        data_ids: Sequence[str],
        *,
        start: date,
        end: date,
    ) -> DataPanel: ...
