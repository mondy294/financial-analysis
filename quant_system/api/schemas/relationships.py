from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class NeighborOut(BaseModel):
    peer: str
    peer_name: str = ""
    relation_value: float
    sample_size: int = 0
    is_same_industry: bool = False


class StockRelationshipsOut(BaseModel):
    code: str
    window: str
    relation_type: str = "PEARSON"
    calc_date: date | None = None
    positive: list[NeighborOut] = []
    negative: list[NeighborOut] = []
