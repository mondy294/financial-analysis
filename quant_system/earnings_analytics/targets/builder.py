"""Target Builder：公告日后固定 horizon 前复权收益。"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sqlalchemy import select

from quant_system.data.repository import Repositories
from quant_system.database.models import DailyKline
from quant_system.earnings_analytics.constants import DEFAULT_HORIZONS


def compute_forward_returns(
    repos: Repositories,
    events: list[dict[str, Any]],
    *,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
) -> list[dict[str, Any]]:
    """为事件填充 ret_{h}d；锚点为 event_date 当日或其后首个交易日收盘。"""
    hs = tuple(sorted({int(h) for h in horizons if int(h) > 0}))
    if not events or not hs:
        return [{f"ret_{h}d": None for h in DEFAULT_HORIZONS} for _ in events]

    by_date: dict[date, list[int]] = {}
    for i, ev in enumerate(events):
        ed = ev.get("event_date")
        if not isinstance(ed, date):
            ed = date.fromisoformat(str(ed)[:10])
        by_date.setdefault(ed, []).append(i)

    session = repos.kline._session  # noqa: SLF001
    out: list[dict[str, Any]] = [{f"ret_{h}d": None for h in hs} for _ in events]
    need = max(hs)

    for event_date, idxs in by_date.items():
        codes = sorted({str(events[i]["code"]).upper() for i in idxs})
        end = event_date + timedelta(days=max(60, int(need * 2.5) + 20))
        rows = session.execute(
            select(
                DailyKline.code,
                DailyKline.trade_date,
                DailyKline.close,
                DailyKline.adj_factor,
            )
            .where(DailyKline.code.in_(codes))
            .where(DailyKline.trade_date >= event_date)
            .where(DailyKline.trade_date <= end)
            .order_by(DailyKline.code, DailyKline.trade_date)
        ).all()
        if not rows:
            continue
        df = pd.DataFrame(
            [
                {
                    "code": str(c).upper(),
                    "trade_date": d,
                    "close": float(cl),
                    "adj_factor": float(af) if af is not None else 1.0,
                }
                for c, d, cl, af in rows
            ]
        )
        for code, g in df.groupby("code", sort=False):
            g = g.sort_values("trade_date").reset_index(drop=True)
            latest = float(g["adj_factor"].iloc[-1]) or 1.0
            closes = (g["close"] * (g["adj_factor"] / latest)).to_numpy(dtype=float)
            # 锚点：首根 >= event_date（当日或下一交易日）
            if closes.size < 1:
                continue
            anchor = float(closes[0])
            if not np.isfinite(anchor) or anchor <= 0:
                continue
            forward = closes[1:]
            rets = {}
            for h in hs:
                if len(forward) >= h:
                    v = float(forward[h - 1] / anchor - 1.0)
                    rets[f"ret_{h}d"] = v if np.isfinite(v) else None
                else:
                    rets[f"ret_{h}d"] = None
            for i in idxs:
                if str(events[i]["code"]).upper() == str(code):
                    out[i] = rets
    return out
