"""Pattern 命中后的短期远期收益（相对信号日收盘，前复权）。

用于榜单「命中后有没有涨」的快速对照：
信号日收盘 → 其后第 h 个交易日收盘（与事件统计 return_h 语义一致）。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sqlalchemy import select

from quant_system.data.repository import Repositories
from quant_system.database.models import DailyKline

DEFAULT_HIT_HORIZONS = (1, 3, 5)


def attach_forward_returns(
    repos: Repositories,
    hits: list[dict[str, Any]],
    *,
    horizons: Iterable[int] = DEFAULT_HIT_HORIZONS,
) -> list[dict[str, Any]]:
    """原地为 hits 填充 return_1 / return_3 / return_5（不足则为 None）。"""
    hs = tuple(sorted({int(h) for h in horizons if int(h) > 0}))
    if not hits or not hs:
        return hits

    for hit in hits:
        for n in hs:
            hit.setdefault(f"return_{n}", None)

    by_signal: dict[date, list[dict[str, Any]]] = {}
    for hit in hits:
        raw = hit.get("trade_date")
        if isinstance(raw, date):
            sig = raw
        else:
            sig = date.fromisoformat(str(raw)[:10])
        by_signal.setdefault(sig, []).append(hit)

    session = repos.kline._session  # noqa: SLF001 — 与 repos 共享同一会话
    need = max(hs)

    for signal_date, group in by_signal.items():
        codes = sorted({str(h["code"]).upper() for h in group})
        end = signal_date + timedelta(days=max(40, int(need * 2.5) + 15))
        stmt = (
            select(
                DailyKline.code,
                DailyKline.trade_date,
                DailyKline.close,
                DailyKline.adj_factor,
            )
            .where(DailyKline.code.in_(codes))
            .where(DailyKline.trade_date >= signal_date)
            .where(DailyKline.trade_date <= end)
            .order_by(DailyKline.code, DailyKline.trade_date)
        )
        rows = session.execute(stmt).all()
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
        rets_by_code = _returns_by_code(df, signal_date=signal_date, horizons=hs)
        for hit in group:
            code = str(hit["code"]).upper()
            hit.update(rets_by_code.get(code) or {})

    return hits


def _f(v: float) -> float | None:
    if not np.isfinite(v):
        return None
    return float(v)


def _returns_by_code(
    df: pd.DataFrame,
    *,
    signal_date: date,
    horizons: tuple[int, ...],
) -> dict[str, dict[str, float | None]]:
    out: dict[str, dict[str, float | None]] = {}
    if df.empty:
        return out

    for code, g in df.groupby("code", sort=False):
        empty = {f"return_{h}": None for h in horizons}
        g = g.sort_values("trade_date").reset_index(drop=True)
        latest = float(g["adj_factor"].iloc[-1]) or 1.0
        ratio = g["adj_factor"] / latest
        closes = (g["close"] * ratio).to_numpy(dtype=float)
        dates = list(g["trade_date"])

        try:
            sig_i = dates.index(signal_date)
        except ValueError:
            out[str(code)] = empty
            continue

        anchor = float(closes[sig_i])
        if not np.isfinite(anchor) or anchor <= 0:
            out[str(code)] = empty
            continue

        forward = closes[sig_i + 1 :]
        row = dict(empty)
        for h in horizons:
            if len(forward) >= h:
                row[f"return_{h}"] = _f(float(forward[h - 1]) / anchor - 1.0)
        out[str(code)] = row
    return out
