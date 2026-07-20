"""Event Builder：从披露源写入 earnings_disclosure_event。"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from quant_system.data.disclosure_provider import (
    CATEGORY_ANNUAL,
    CATEGORY_EXPRESS,
    CATEGORY_FORECAST,
    CATEGORY_INTERIM,
    CATEGORY_Q1,
    CATEGORY_Q3,
    MAX_RANGE_DAYS,
    DisclosureProvider,
)
from quant_system.database.models import EarningsDisclosureEvent, FinancialSnapshot
from quant_system.infra.board import Board

_CATEGORY_TO_KIND = {
    CATEGORY_FORECAST: "forecast",
    CATEGORY_EXPRESS: "express",
    CATEGORY_INTERIM: "interim",
    CATEGORY_ANNUAL: "annual",
    CATEGORY_Q1: "q1",
    CATEGORY_Q3: "q3",
}


def _event_id(code: str, event_date: date, kind: str, report_period: date | None) -> str:
    raw = f"{code}|{event_date.isoformat()}|{kind}|{report_period or ''}"
    return hashlib.sha1(raw.encode()).hexdigest()[:24]


def _chunks(start: date, end: date, max_days: int = MAX_RANGE_DAYS) -> list[tuple[date, date]]:
    out: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        chunk_end = min(end, cur + timedelta(days=max_days - 1))
        out.append((cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return out


def _infer_report_period(kind: str, event_date: date, title: str) -> date | None:
    y = event_date.year
    text = title or ""
    import re

    m = re.search(r"(20\d{2})", text)
    if m:
        y = int(m.group(1))
    if kind == "annual" or (kind in ("forecast", "express") and "年度" in text and "半年度" not in text):
        # 次年披露上年年报常见
        if event_date.month <= 4 and not m:
            y = event_date.year - 1
        return date(y, 12, 31)
    if kind == "interim" or "半年度" in text or "中报" in text:
        return date(y, 6, 30)
    if kind == "q1":
        return date(y, 3, 31)
    if kind == "q3":
        return date(y, 9, 30)
    if kind in ("forecast", "express"):
        if "一季" in text:
            return date(y, 3, 31)
        if "三季" in text:
            return date(y, 9, 30)
        if "年度" in text and "半年度" not in text:
            if event_date.month <= 4:
                y = event_date.year - 1
            return date(y, 12, 31)
        return date(y, 6, 30)
    return None


def _attach_snapshot_profit(
    session: Session, events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """正式报告缺归母时，用 financial_snapshot.net_profit 兜底。"""
    need = [
        e
        for e in events
        if e.get("parent_np") is None
        and e.get("report_period") is not None
        and e.get("event_kind") in ("annual", "interim", "q1", "q3", "express")
    ]
    if not need:
        return events
    codes = sorted({e["code"] for e in need})
    periods = sorted({e["report_period"] for e in need})
    rows = session.execute(
        select(
            FinancialSnapshot.code,
            FinancialSnapshot.report_period,
            FinancialSnapshot.net_profit,
            FinancialSnapshot.net_profit_yoy,
        )
        .where(FinancialSnapshot.code.in_(codes))
        .where(FinancialSnapshot.report_period.in_(periods))
    ).all()
    mp = {(str(c).upper(), p): (np, yoy) for c, p, np, yoy in rows}
    for e in need:
        hit = mp.get((e["code"], e["report_period"]))
        if not hit:
            continue
        np_v, yoy = hit
        if np_v is not None:
            e["parent_np"] = float(np_v)
            e["source"] = "financial_snapshot"
        if e.get("parent_np_yoy") is None and yoy is not None:
            e["parent_np_yoy"] = float(yoy)
    return events


def build_events(
    session: Session,
    start: date,
    end: date,
    *,
    main_only: bool = True,
    provider: DisclosureProvider | None = None,
    progress_cb: Any | None = None,
) -> dict[str, Any]:
    """按日区间拉取披露并 upsert 事件。区间可超过 31 天（内部分块）。"""
    if end < start:
        start, end = end, start
    provider = provider or DisclosureProvider()
    now = datetime.utcnow()
    collected: list[dict[str, Any]] = []
    chunks = _chunks(start, end)
    n_chunks = max(len(chunks), 1)

    for i, (c_start, c_end) in enumerate(chunks):
        if progress_cb:
            progress_cb(
                0.05 + 0.55 * (i / n_chunks),
                f"拉取披露 {c_start}~{c_end} ({i + 1}/{n_chunks})",
            )
        try:
            items = provider.fetch_financial_notices(c_start, c_end)
        except Exception as e:
            logger.warning("EEA EventBuilder 拉取失败 {}~{}: {}", c_start, c_end, e)
            continue
        if main_only:
            items = [x for x in items if x.get("board") == Board.MAIN.value]
        # 预告 enrich
        try:
            items = provider.enrich_forecast_metrics(items, start=c_start, end=c_end)
        except Exception as e:
            logger.warning("EEA forecast enrich 失败: {}", e)

        for item in items:
            cat = str(item.get("category") or "")
            kind = _CATEGORY_TO_KIND.get(cat)
            if not kind:
                continue
            code = str(item.get("code") or "").upper()
            ed = item.get("notice_date")
            if not isinstance(ed, date):
                try:
                    ed = date.fromisoformat(str(ed)[:10])
                except Exception:
                    continue
            title = str(item.get("title") or "")
            rp = item.get("report_period")
            if not isinstance(rp, date):
                rp = _infer_report_period(kind, ed, title)
            parent_np = item.get("parent_np_value")
            yoy = item.get("parent_np_yoy")
            collected.append(
                {
                    "id": _event_id(code, ed, kind, rp),
                    "code": code,
                    "name": str(item.get("name") or ""),
                    "event_date": ed,
                    "report_period": rp,
                    "event_kind": kind,
                    "title": title or None,
                    "parent_np": float(parent_np) if parent_np is not None else None,
                    "parent_np_yoy": float(yoy) if yoy is not None else None,
                    "predict_type": item.get("predict_type"),
                    "source": "em_yjyg" if parent_np is not None and kind == "forecast" else "em_notice",
                    "raw_extra_json": {
                        "notice_type": item.get("notice_type"),
                        "category": cat,
                        "url": item.get("url"),
                    },
                }
            )

    if progress_cb:
        progress_cb(0.65, f"匹配财报快照利润…（{len(collected)} 条）")
    collected = _attach_snapshot_profit(session, collected)

    # 同 identity 保留首次（已按日期块顺序；同日多条取已有）
    by_id: dict[str, dict[str, Any]] = {}
    for e in collected:
        by_id.setdefault(e["id"], e)

    if progress_cb:
        progress_cb(0.75, f"写入事件表…（{len(by_id)} 只）")
    upserted = 0
    for e in by_id.values():
        row = session.get(EarningsDisclosureEvent, e["id"])
        if row is None:
            session.add(
                EarningsDisclosureEvent(
                    id=e["id"],
                    code=e["code"],
                    name=e["name"],
                    event_date=e["event_date"],
                    report_period=e["report_period"],
                    event_kind=e["event_kind"],
                    title=e["title"],
                    parent_np=e["parent_np"],
                    parent_np_yoy=e["parent_np_yoy"],
                    predict_type=e["predict_type"],
                    source=e["source"],
                    raw_extra_json=e["raw_extra_json"],
                    created_at=now,
                    updated_at=now,
                )
            )
            upserted += 1
        else:
            # 首次优先：仅补空字段
            changed = False
            if row.parent_np is None and e["parent_np"] is not None:
                row.parent_np = e["parent_np"]
                changed = True
            if row.parent_np_yoy is None and e["parent_np_yoy"] is not None:
                row.parent_np_yoy = e["parent_np_yoy"]
                changed = True
            if row.report_period is None and e["report_period"] is not None:
                row.report_period = e["report_period"]
                changed = True
            if changed:
                row.updated_at = now
                upserted += 1

    session.flush()
    if progress_cb:
        progress_cb(0.9, f"事件构建完成 unique={len(by_id)}")
    return {
        "start_date": start,
        "end_date": end,
        "main_only": main_only,
        "fetched": len(collected),
        "unique": len(by_id),
        "upserted": upserted,
    }
