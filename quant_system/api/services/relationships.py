from __future__ import annotations

from datetime import date
from typing import Any

from quant_system.data.repository import Repositories
from quant_system.relationship import queries


def _norm_window(window: str) -> str:
    w = (window or "W60").strip().upper()
    return w if w.startswith("W") else f"W{w}"


def stock_relationships(
    repos: Repositories,
    code: str,
    *,
    trade_date: date | None = None,
    window: str = "W60",
    limit: int = 30,
    relation_type: str = "PEARSON",
) -> dict[str, Any]:
    code = code.upper()
    win = _norm_window(window)
    rtype = relation_type.strip().upper()
    latest = repos.relation.latest_calc_date(rtype, win)
    calc_date = trade_date or latest

    if calc_date is None:
        return {
            "code": code,
            "window": win,
            "relation_type": rtype,
            "calc_date": None,
            "positive": [],
            "negative": [],
        }

    def _fetch(as_of: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        pos = queries.top_neighbors(
            repos, code, relation_type=rtype, window=win, sign=1, limit=limit, as_of=as_of,
        )
        neg = queries.top_neighbors(
            repos, code, relation_type=rtype, window=win, sign=-1, limit=limit, as_of=as_of,
        )
        pos.sort(key=lambda r: -float(r["relation_value"]))
        neg.sort(key=lambda r: float(r["relation_value"]))
        return pos, neg

    positive, negative = _fetch(calc_date)
    # 指定日无快照时回退到最近一次 build 日
    if (
        not positive
        and not negative
        and latest is not None
        and trade_date is not None
        and trade_date != latest
    ):
        calc_date = latest
        positive, negative = _fetch(calc_date)

    return {
        "code": code,
        "window": win,
        "relation_type": rtype,
        "calc_date": calc_date,
        "positive": positive,
        "negative": negative,
    }
