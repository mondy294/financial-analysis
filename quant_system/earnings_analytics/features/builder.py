"""Feature Builder：事件 → Derived Features。"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

import numpy as np
from sqlalchemy import select

from quant_system.data.repository import Repositories
from quant_system.database.models import DailyFeature, DailyKline, StockClusterMember, StockClusterRun
from quant_system.earnings_analytics.features.annualize import annualize_parent_np


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    return x


def resolve_cluster_run_id(session: Any, *, cluster_run_id: str | None = None) -> str | None:
    if cluster_run_id:
        return cluster_run_id
    # 库内状态为 SUCCESS（大写）；兼容历史小写
    row = session.execute(
        select(StockClusterRun.run_id)
        .where(StockClusterRun.status.in_(("SUCCESS", "success")))
        .order_by(StockClusterRun.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return str(row) if row else None


def load_cluster_membership(session: Any, run_id: str | None) -> dict[str, int]:
    if not run_id:
        return {}
    rows = session.execute(
        select(StockClusterMember.stock_code, StockClusterMember.cluster_id).where(
            StockClusterMember.run_id == run_id
        )
    ).all()
    return {str(c).upper(): int(cid) for c, cid in rows}


def _range_pos_from_closes(closes: np.ndarray) -> float | None:
    if closes.size < 5:
        return None
    lo = float(np.min(closes))
    hi = float(np.max(closes))
    if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
        return None
    last = float(closes[-1])
    return (last - lo) / (hi - lo)


def price_position_features(
    repos: Repositories,
    code: str,
    event_date: date,
) -> dict[str, Any]:
    """特征用 T-1：event_date 之前最近交易日。"""
    session = repos.kline._session  # noqa: SLF001
    start = event_date - timedelta(days=1200)
    rows = session.execute(
        select(DailyKline.trade_date, DailyKline.close, DailyKline.adj_factor)
        .where(DailyKline.code == code.upper())
        .where(DailyKline.trade_date >= start)
        .where(DailyKline.trade_date < event_date)
        .order_by(DailyKline.trade_date)
    ).all()
    out: dict[str, Any] = {
        "feature_asof_date": None,
        "range_pos_250d": None,
        "range_pos_750d": None,
        "dist_to_high_250d": None,
    }
    if not rows:
        return out
    dates = [r[0] for r in rows]
    closes_raw = np.array([float(r[1]) for r in rows], dtype=float)
    adjs = np.array([float(r[2]) if r[2] is not None else 1.0 for r in rows], dtype=float)
    latest_adj = adjs[-1] or 1.0
    closes = closes_raw * (adjs / latest_adj)
    out["feature_asof_date"] = dates[-1]
    win250 = closes[-250:] if closes.size >= 20 else closes
    win750 = closes[-750:] if closes.size >= 20 else closes
    out["range_pos_250d"] = _range_pos_from_closes(win250)
    out["range_pos_750d"] = _range_pos_from_closes(win750)
    if win250.size >= 5:
        hi = float(np.max(win250))
        last = float(win250[-1])
        if hi > 0 and math.isfinite(hi):
            out["dist_to_high_250d"] = last / hi - 1.0

    # 若 DailyFeature 有现成 range_pos_250d 则优先
    feat = session.execute(
        select(DailyFeature.range_pos_250d)
        .where(DailyFeature.code == code.upper())
        .where(DailyFeature.trade_date == dates[-1])
    ).scalar_one_or_none()
    if feat is not None:
        out["range_pos_250d"] = _f(feat)
    return out


def build_derived_features(
    repos: Repositories,
    event: dict[str, Any],
    *,
    cluster_run_id: str | None = None,
    cluster_map: dict[str, int] | None = None,
) -> dict[str, Any]:
    code = str(event.get("code") or "").upper()
    event_date = event["event_date"]
    if not isinstance(event_date, date):
        event_date = date.fromisoformat(str(event_date)[:10])
    kind = str(event.get("event_kind") or "")
    rp = event.get("report_period")
    if isinstance(rp, str):
        try:
            rp = date.fromisoformat(rp[:10])
        except Exception:
            rp = None

    parent_np = _f(event.get("parent_np"))
    yoy = _f(event.get("parent_np_yoy"))
    ann = (
        annualize_parent_np(parent_np, kind, rp)
        if parent_np is not None
        else None
    )

    val = repos.valuation.get_latest_valuation(code, as_of=event_date)
    pe = _f(val.pe_ttm) if val is not None else None
    mcap = _f(val.market_cap) if val is not None else None
    val_date = val.trade_date if val is not None else None

    ey = pe_event = pe_rel = ln_mcap = ey_pct = None
    if ann is not None and mcap is not None and mcap > 0 and ann != 0:
        mcap_yuan = mcap * 1e8
        ey = ann / mcap_yuan
        ey_pct = ey * 100.0
        pe_event = mcap_yuan / ann
        if pe is not None and pe_event != 0:
            pe_rel = pe / pe_event - 1.0
        ln_mcap = math.log(mcap)

    px = price_position_features(repos, code, event_date)
    cid = None
    if cluster_map is not None:
        cid = cluster_map.get(code)

    return {
        "annualized_parent_np": ann,
        "pe_ttm": pe,
        "mcap": mcap,
        "ln_mcap": ln_mcap,
        "ey_event": ey,
        "ey_event_pct": ey_pct,
        "pe_event": pe_event,
        "pe_rel": pe_rel,
        "yoy_pct": (yoy * 100.0) if yoy is not None else None,
        "range_pos_250d": px.get("range_pos_250d"),
        "range_pos_750d": px.get("range_pos_750d"),
        "dist_to_high_250d": px.get("dist_to_high_250d"),
        "cluster_run_id": cluster_run_id,
        "cluster_id": cid,
        "valuation_date": val_date,
        "feature_asof_date": px.get("feature_asof_date"),
        "derived_extra_json": None,
    }


def build_online_features(
    repos: Repositories,
    *,
    code: str,
    event_kind: str,
    parent_np: float,
    parent_np_yoy: float | None,
    as_of: date,
    report_period: date | None = None,
    cluster_run_id: str | None = None,
) -> dict[str, Any]:
    session = repos.kline._session  # noqa: SLF001
    run_id = resolve_cluster_run_id(session, cluster_run_id=cluster_run_id)
    cmap = load_cluster_membership(session, run_id)
    event = {
        "code": code.upper(),
        "event_date": as_of,
        "event_kind": event_kind,
        "report_period": report_period,
        "parent_np": parent_np,
        "parent_np_yoy": parent_np_yoy,
    }
    derived = build_derived_features(
        repos, event, cluster_run_id=run_id, cluster_map=cmap
    )
    return {
        **event,
        **derived,
        "yoy_pct": derived.get("yoy_pct"),
    }
