from __future__ import annotations

from datetime import date
from typing import Any

from quant_system.api.errors import raise_bad_request, raise_not_found
from quant_system.data.repository import Repositories
from quant_system.patterns.context import build_pattern_context
from quant_system.patterns.matcher import GenericPatternMatcher
from quant_system.patterns.registry import PATTERN_REGISTRY, get_definitions


def list_pattern_meta() -> list[dict[str, Any]]:
    return [
        {
            "id": p.id,
            "display_name": p.display_name,
            "version": p.version,
            "threshold": p.threshold,
            "description": p.description,
        }
        for p in PATTERN_REGISTRY.values()
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
    trade_date: date | None,
    *,
    limit: int | None = 20,
) -> list[dict[str, Any]]:
    pid = pattern_id.strip().upper()
    if pid not in PATTERN_REGISTRY:
        raise_bad_request(f"未知 Pattern: {pid}")
    d = trade_date or repos.abnormal.latest_trade_date()
    if d is None:
        return []
    # limit<=0：返回全部命中
    fetch_limit = None if limit is not None and limit <= 0 else limit
    rows = repos.abnormal.top_by_pattern(d, pid, limit=fetch_limit)
    out = []
    for r in rows:
        stock = repos.stock.get_stock(r["code"])
        out.append(_hit_from_row(r, stock.name if stock else ""))
    # 相似度降序（与仓库排序一致，再按 code 稳定）
    out.sort(key=lambda x: (-float(x["pattern_score"]), x["code"]))
    return out


def hits_of_code(
    repos: Repositories,
    code: str,
    trade_date: date | None = None,
) -> list[dict[str, Any]]:
    code = code.upper()
    rows = repos.abnormal.hits_of(code, trade_date)
    stock = repos.stock.get_stock(code)
    name = stock.name if stock else ""
    return [_hit_from_row(r, name) for r in rows]


def pattern_stats(repos: Repositories, trade_date: date | None) -> dict[str, Any]:
    d = trade_date or repos.abnormal.latest_trade_date()
    if d is None:
        raise_not_found("暂无 Pattern 扫描数据")
    return {"trade_date": d, "stats": repos.abnormal.stats(d)}


def eval_pattern(
    repos: Repositories,
    *,
    code: str,
    trade_date: date | None,
    pattern_id: str,
) -> dict[str, Any]:
    code = code.upper()
    pid = pattern_id.strip().upper()
    definitions = get_definitions([pid])
    if not definitions:
        raise_bad_request(f"未知 Pattern: {pid}")
    definition = definitions[0]
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
