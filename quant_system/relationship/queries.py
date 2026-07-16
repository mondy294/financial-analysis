"""查询封装：在 RelationRepository 之上补股票名称，供 report / ai / cli 复用。"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from quant_system.data.repository import Repositories


def _name_map(repos: "Repositories", codes: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in dict.fromkeys(codes):
        obj = repos.stock.get_stock(c)
        if obj is not None:
            out[c] = obj.name
    return out


def top_neighbors(
    repos: "Repositories", code: str, *,
    relation_type: str = "PEARSON", window: str = "W250",
    sign: Optional[int] = None, limit: int = 20, min_sample: int = 1,
    as_of: Optional[date] = None,
) -> list[dict]:
    rows = repos.relation.neighbors(
        code, relation_type=relation_type, window=window,
        sign=sign, limit=limit, min_sample=min_sample, as_of=as_of,
    )
    names = _name_map(repos, [r["peer"] for r in rows])
    for r in rows:
        r["peer_name"] = names.get(r["peer"], "")
    return rows


def get_pair(
    repos: "Repositories", code_x: str, code_y: str, *,
    relation_type: str = "PEARSON", window: str = "W250",
    as_of: Optional[date] = None,
) -> Optional[dict]:
    return repos.relation.get_pair(
        code_x, code_y, relation_type=relation_type, window=window, as_of=as_of,
    )


def strong(
    repos: "Repositories", *,
    relation_type: str = "PEARSON", window: str = "W250", sign: int = 1,
    min_abs: float = 0.8, limit: int = 50, as_of: Optional[date] = None,
) -> list[dict]:
    rows = repos.relation.list_strong(
        relation_type=relation_type, window=window, sign=sign,
        min_abs=min_abs, limit=limit, as_of=as_of,
    )
    return _attach_pair_names(repos, rows)


def changed(
    repos: "Repositories", *,
    relation_type: str = "PEARSON", short_window: str = "W60", long_window: str = "W250",
    min_delta: float = 0.3, limit: int = 50, as_of: Optional[date] = None,
) -> list[dict]:
    rows = repos.relation.list_strengthening(
        relation_type=relation_type, short_window=short_window, long_window=long_window,
        min_delta=min_delta, limit=limit, as_of=as_of,
    )
    return _attach_pair_names(repos, rows)


def _attach_pair_names(repos: "Repositories", rows: list[dict]) -> list[dict]:
    codes = [r["stock_code_a"] for r in rows] + [r["stock_code_b"] for r in rows]
    names = _name_map(repos, codes)
    for r in rows:
        r["name_a"] = names.get(r["stock_code_a"], "")
        r["name_b"] = names.get(r["stock_code_b"], "")
    return rows
