"""构建 / 加载 Event Panel。"""
from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from quant_system.data.repository import Repositories
from quant_system.database.models import EarningsDisclosureEvent, EarningsEventPanel
from quant_system.earnings_analytics.features.builder import (
    build_derived_features,
    load_cluster_membership,
    resolve_cluster_run_id,
)
from quant_system.earnings_analytics.targets.builder import compute_forward_returns


def _panel_id(event_id: str, panel_tag: str) -> str:
    return hashlib.sha1(f"{panel_tag}|{event_id}".encode()).hexdigest()[:24]


def build_panel(
    repos: Repositories,
    *,
    start: date | None = None,
    end: date | None = None,
    panel_tag: str = "default",
    cluster_run_id: str | None = None,
    progress_cb: Any | None = None,
) -> dict[str, Any]:
    session: Session = repos.kline._session  # noqa: SLF001
    if progress_cb:
        progress_cb(0.05, "加载业绩事件…")
    stmt = select(EarningsDisclosureEvent)
    if start is not None:
        stmt = stmt.where(EarningsDisclosureEvent.event_date >= start)
    if end is not None:
        stmt = stmt.where(EarningsDisclosureEvent.event_date <= end)
    events = list(session.execute(stmt).scalars().all())
    if not events:
        if progress_cb:
            progress_cb(1.0, "无事件可构建")
        return {
            "panel_tag": panel_tag,
            "n_events": 0,
            "n_upserted": 0,
            "cluster_run_id": None,
        }

    run_id = resolve_cluster_run_id(session, cluster_run_id=cluster_run_id)
    cmap = load_cluster_membership(session, run_id)

    event_dicts: list[dict[str, Any]] = []
    for e in events:
        event_dicts.append(
            {
                "id": e.id,
                "code": e.code,
                "name": e.name,
                "event_date": e.event_date,
                "report_period": e.report_period,
                "event_kind": e.event_kind,
                "title": e.title,
                "parent_np": float(e.parent_np) if e.parent_np is not None else None,
                "parent_np_yoy": float(e.parent_np_yoy) if e.parent_np_yoy is not None else None,
                "predict_type": e.predict_type,
                "source": e.source,
                "raw_extra_json": e.raw_extra_json,
            }
        )

    if progress_cb:
        progress_cb(0.15, f"计算前瞻收益…（{len(event_dicts)} 条）")
    targets = compute_forward_returns(repos, event_dicts)
    now = datetime.utcnow()
    upserted = 0
    total = max(len(event_dicts), 1)

    for i, (ev, tgt) in enumerate(zip(event_dicts, targets)):
        if progress_cb and (i % 25 == 0 or i + 1 == total):
            progress_cb(
                0.2 + 0.75 * (i / total),
                f"特征+落库 {i + 1}/{total} {ev.get('code')}",
            )
        derived = build_derived_features(
            repos, ev, cluster_run_id=run_id, cluster_map=cmap
        )
        pid = _panel_id(ev["id"], panel_tag)
        row = session.get(EarningsEventPanel, pid)
        payload = dict(
            event_id=ev["id"],
            code=ev["code"],
            event_date=ev["event_date"],
            report_period=ev["report_period"],
            event_kind=ev["event_kind"],
            source=ev["source"] or "",
            parent_np=ev["parent_np"],
            parent_np_yoy=ev["parent_np_yoy"],
            predict_type=ev["predict_type"],
            title=ev["title"],
            raw_extra_json=ev.get("raw_extra_json"),
            annualized_parent_np=derived.get("annualized_parent_np"),
            pe_ttm=derived.get("pe_ttm"),
            mcap=derived.get("mcap"),
            ln_mcap=derived.get("ln_mcap"),
            ey_event=derived.get("ey_event"),
            ey_event_pct=derived.get("ey_event_pct"),
            pe_event=derived.get("pe_event"),
            pe_rel=derived.get("pe_rel"),
            yoy_pct=derived.get("yoy_pct"),
            range_pos_250d=derived.get("range_pos_250d"),
            range_pos_750d=derived.get("range_pos_750d"),
            dist_to_high_250d=derived.get("dist_to_high_250d"),
            cluster_run_id=derived.get("cluster_run_id"),
            cluster_id=derived.get("cluster_id"),
            valuation_date=derived.get("valuation_date"),
            feature_asof_date=derived.get("feature_asof_date"),
            derived_extra_json=derived.get("derived_extra_json"),
            ret_5d=tgt.get("ret_5d"),
            ret_10d=tgt.get("ret_10d"),
            ret_20d=tgt.get("ret_20d"),
            target_extra_json=None,
            panel_tag=panel_tag,
            built_at=now,
        )
        if row is None:
            session.add(EarningsEventPanel(id=pid, **payload))
        else:
            for k, v in payload.items():
                setattr(row, k, v)
        upserted += 1

    session.flush()
    if progress_cb:
        progress_cb(1.0, f"Panel 完成 upserted={upserted}")
    logger.info(
        "EEA panel built tag={} events={} cluster_run={}",
        panel_tag,
        upserted,
        run_id,
    )
    return {
        "panel_tag": panel_tag,
        "n_events": len(events),
        "n_upserted": upserted,
        "cluster_run_id": run_id,
        "start_date": start,
        "end_date": end,
    }


def load_panel_rows(
    session: Session,
    *,
    panel_tag: str = "default",
) -> list[dict[str, Any]]:
    rows = list(
        session.execute(
            select(EarningsEventPanel).where(EarningsEventPanel.panel_tag == panel_tag)
        )
        .scalars()
        .all()
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "event_id": r.event_id,
                "code": r.code,
                "event_date": r.event_date,
                "report_period": r.report_period,
                "event_kind": r.event_kind,
                "source": r.source,
                "parent_np": float(r.parent_np) if r.parent_np is not None else None,
                "parent_np_yoy": float(r.parent_np_yoy) if r.parent_np_yoy is not None else None,
                "predict_type": r.predict_type,
                "title": r.title,
                "annualized_parent_np": float(r.annualized_parent_np)
                if r.annualized_parent_np is not None
                else None,
                "pe_ttm": float(r.pe_ttm) if r.pe_ttm is not None else None,
                "mcap": float(r.mcap) if r.mcap is not None else None,
                "ln_mcap": float(r.ln_mcap) if r.ln_mcap is not None else None,
                "ey_event": float(r.ey_event) if r.ey_event is not None else None,
                "ey_event_pct": float(r.ey_event_pct) if r.ey_event_pct is not None else None,
                "pe_event": float(r.pe_event) if r.pe_event is not None else None,
                "pe_rel": float(r.pe_rel) if r.pe_rel is not None else None,
                "yoy_pct": float(r.yoy_pct) if r.yoy_pct is not None else None,
                "range_pos_250d": float(r.range_pos_250d)
                if r.range_pos_250d is not None
                else None,
                "range_pos_750d": float(r.range_pos_750d)
                if r.range_pos_750d is not None
                else None,
                "dist_to_high_250d": float(r.dist_to_high_250d)
                if r.dist_to_high_250d is not None
                else None,
                "cluster_run_id": r.cluster_run_id,
                "cluster_id": r.cluster_id,
                "ret_5d": float(r.ret_5d) if r.ret_5d is not None else None,
                "ret_10d": float(r.ret_10d) if r.ret_10d is not None else None,
                "ret_20d": float(r.ret_20d) if r.ret_20d is not None else None,
            }
        )
    return out
