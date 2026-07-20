from __future__ import annotations

from datetime import date
from typing import Any

from quant_system.api.errors import raise_bad_request, raise_not_found
from quant_system.data.repository import Repositories
from quant_system.patterns.context import build_pattern_context
from quant_system.patterns.definition import PatternDefinition
from quant_system.patterns.matcher import GenericPatternMatcher
from quant_system.patterns.registry import get_definitions, get_registry


def list_pattern_meta() -> list[dict[str, Any]]:
    """策略元数据：中英文名以 DB 行准（保存草稿后即生效），其余取 published body。"""
    try:
        from quant_system.infra.db import session_scope
        from quant_system.patterns.store import list_definitions, load_published_definition

        with session_scope() as session:
            rows = list_definitions(session)
            out: list[dict[str, Any]] = []
            for item in rows:
                pub = load_published_definition(session, item["id"])
                out.append(
                    {
                        "id": item["id"],
                        "display_name": item["display_name"],
                        "display_name_en": item.get("display_name_en") or "",
                        "version": item.get("published_version")
                        or (pub.version if pub else ""),
                        "threshold": float(pub.threshold) if pub else 0.0,
                        "description": item.get("description") or "",
                    }
                )
            if out:
                return out
    except Exception:
        pass
    return [
        {
            "id": p.id,
            "display_name": p.display_name,
            "display_name_en": getattr(p, "display_name_en", "") or "",
            "version": p.version,
            "threshold": p.threshold,
            "description": p.description,
        }
        for p in get_registry().values()
    ]


def _parse_ranges(raw: Any) -> dict[str, dict[str, Any]] | None:
    if not isinstance(raw, dict):
        return None
    out: dict[str, dict[str, Any]] = {}
    for k, v in raw.items():
        if isinstance(v, dict) and "start" in v and "end" in v:
            out[k] = {
                "length": int(v.get("length") or 0),
                "start": str(v["start"]),
                "end": str(v["end"]),
            }
    return out or None


def _hit_from_row(row: dict[str, Any], name: str = "") -> dict[str, Any]:
    components = row.get("score_components") or {}
    if isinstance(components, str):
        import json
        components = json.loads(components)
    metrics = components.get("metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}
    ranges = (
        components.get("chosen_window_ranges")
        or metrics.get("chosen_window_ranges")
        or (row.get("inputs_snapshot") or {}).get("chosen_window_ranges")
    )
    values = metrics.get("values") or (row.get("inputs_snapshot") or {}).get("values") or {}
    return {
        "trade_date": row["trade_date"],
        "code": row["code"],
        "name": name,
        "pattern_id": row["pattern_id"],
        "pattern_score": float(row["pattern_score"]),
        "pattern_rank": int(row["pattern_rank"]),
        "reasons": row.get("reasons") or [],
        "chosen_windows": components.get("chosen_windows") or {},
        "chosen_window_ranges": _parse_ranges(ranges),
        "stage_similarity": components.get("stage_similarity") or {},
        "feature_similarity": components.get("feature_similarity") or {},
        "distance": float(components.get("distance") or 0.0),
        "hard_failed": list(metrics.get("hard_failed") or []),
        "metrics_values": values,
    }


def top_hits(
    repos: Repositories,
    pattern_id: str,
    trade_date: date | None = None,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int | None = 20,
) -> list[dict[str, Any]]:
    from quant_system.patterns.forward_returns import attach_forward_returns

    pid = pattern_id.strip().upper()
    if pid not in get_registry():
        raise_bad_request(f"未知 Pattern: {pid}")

    start = start_date or trade_date
    end = end_date or trade_date
    if start is None and end is None:
        latest = repos.abnormal.latest_trade_date()
        if latest is None:
            return []
        start = end = latest
    elif start is None:
        start = end
    elif end is None:
        end = start
    assert start is not None and end is not None
    if start > end:
        start, end = end, start

    # limit<=0：返回全部命中
    fetch_limit = None if limit is not None and limit <= 0 else limit
    rows = repos.abnormal.top_by_pattern(
        None,
        pid,
        limit=fetch_limit,
        start_date=start,
        end_date=end,
    )
    out = []
    for r in rows:
        stock = repos.stock.get_stock(r["code"])
        out.append(_hit_from_row(r, stock.name if stock else ""))
    # 相似度降序，同日按 code 稳定
    out.sort(
        key=lambda x: (
            -float(x["pattern_score"]),
            str(x.get("trade_date") or ""),
            x["code"],
        )
    )
    return attach_forward_returns(repos, out)


def hits_of_code(
    repos: Repositories,
    code: str,
    trade_date: date | None = None,
) -> list[dict[str, Any]]:
    from quant_system.patterns.forward_returns import attach_forward_returns

    code = code.upper()
    rows = repos.abnormal.hits_of(code, trade_date)
    stock = repos.stock.get_stock(code)
    name = stock.name if stock else ""
    out = [_hit_from_row(r, name) for r in rows]
    return attach_forward_returns(repos, out)


def pattern_stats(repos: Repositories, trade_date: date | None) -> dict[str, Any]:
    d = trade_date or repos.abnormal.latest_trade_date()
    if d is None:
        raise_not_found("暂无 Pattern 扫描数据")
    return {"trade_date": d, "stats": repos.abnormal.stats(d)}


def eval_with_definition(
    repos: Repositories,
    definition: PatternDefinition,
    *,
    code: str,
    trade_date: date | None,
) -> dict[str, Any]:
    code = code.upper()
    from quant_system.infra import trading_calendar as tc

    d = trade_date or tc.latest_trading_day()
    stock = repos.stock.get_stock(code)
    ctx = build_pattern_context(
        repos,
        d,
        codes=[code],
        max_bars=definition.required_history_bars(),
    )
    series = ctx["kline_by_code"].get(code)
    if series is None or series.empty:
        raise_not_found(f"{code} 在 {d} 无可用 K 线")
    result = GenericPatternMatcher().match(
        code,
        d,
        series,
        definition,
        meta=ctx["stock_meta"].get(code, {}),
        last_amount=ctx["amount_by_code"].get(code),
    )
    ranges_raw = (result.metrics or {}).get("chosen_window_ranges") or {}
    return {
        "code": code,
        "name": stock.name if stock else "",
        "trade_date": d,
        "pattern_id": definition.id,
        "matched": result.matched,
        "similarity": float(result.similarity),
        "threshold": float(definition.threshold),
        "distance": float(result.distance),
        "version": definition.version,
        "chosen_windows": result.chosen_windows or {},
        "chosen_window_ranges": _parse_ranges(ranges_raw) or {},
        "stage_similarity": result.stage_similarity or {},
        "feature_similarity": result.feature_similarity or {},
        "hard_failed": result.hard_failed or [],
        "reasons": result.reasons or [],
        "metrics_values": (result.metrics or {}).get("values") or {},
    }


def eval_pattern(
    repos: Repositories,
    *,
    code: str,
    trade_date: date | None,
    pattern_id: str,
) -> dict[str, Any]:
    pid = pattern_id.strip().upper()
    definitions = get_definitions([pid])
    if not definitions:
        raise_bad_request(f"未知 Pattern: {pid}")
    return eval_with_definition(
        repos, definitions[0], code=code, trade_date=trade_date
    )


def dry_scan_with_definition(
    repos: Repositories,
    definition: PatternDefinition,
    *,
    trade_date: date,
    limit: int = 50,
    progress_cb: Any | None = None,
) -> dict[str, Any]:
    """用指定 Definition 全市场试扫，不落库。"""
    from quant_system.patterns.runner import PatternRunner, rank_records

    if progress_cb:
        progress_cb(0.08, f"加载上下文 {trade_date.isoformat()}…")
    max_bars = definition.required_history_bars()
    context = build_pattern_context(repos, trade_date, max_bars=max_bars)
    uni = int(context.get("universe_size") or 0)
    if progress_cb:
        progress_cb(0.15, f"上下文就绪，宇宙 {uni} 只")

    def _match_progress(frac: float, msg: str) -> None:
        if progress_cb:
            progress_cb(0.15 + 0.7 * frac, msg)

    run = PatternRunner(
        keep_unmatched=False,
        show_progress=False,
        progress_cb=_match_progress if progress_cb else None,
    ).run(definition, trade_date, context)
    records = rank_records(run.results)
    if progress_cb:
        progress_cb(0.9, f"排序命中 hit={run.stats.get('matched_count', 0)}")
    hits: list[dict[str, Any]] = []
    for i, record in enumerate(records[:limit]):
        code = record["code"]
        stock = repos.stock.get_stock(code)
        components = record.get("score_components") or {}
        metrics = components.get("metrics") or {}
        ranges = components.get("chosen_window_ranges") or metrics.get("chosen_window_ranges")
        hits.append(
            {
                "rank": i + 1,
                "trade_date": trade_date.isoformat(),
                "code": code,
                "name": stock.name if stock else "",
                "pattern_id": definition.id,
                "pattern_score": float(record["pattern_score"]),
                "chosen_windows": components.get("chosen_windows") or {},
                "chosen_window_ranges": _parse_ranges(ranges) or {},
                "stage_similarity": components.get("stage_similarity") or {},
                "hard_failed": list(metrics.get("hard_failed") or []),
            }
        )
    return {
        "trade_date": trade_date.isoformat(),
        "pattern_id": definition.id,
        "version": definition.version,
        "threshold": definition.threshold,
        "universe_size": int(context.get("universe_size", 0)),
        "matched_count": int(run.stats.get("matched_count", 0)),
        "limit": limit,
        "hits": hits,
        "persisted": False,
    }
