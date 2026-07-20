"""中报业绩预告 × 估值 × 公告后涨跌：样本组装与 OLS 系数。"""
from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

import numpy as np

FEATURE_KEYS = ("pe_ttm", "ln_mcap", "parent_np_yoy_pct", "forecast_ey_pct")
FEATURE_LABELS = {
    "pe_ttm": "PE(TTM)",
    "ln_mcap": "ln(市值亿元)",
    "parent_np_yoy_pct": "归母同比%",
    "forecast_ey_pct": "预告盈利收益率%",
}

_INTERIM_RE = re.compile(r"半年度|中报|中期业绩|1-6月|1－6月|1—6月")


def is_interim_forecast(item: dict[str, Any]) -> bool:
    if str(item.get("category") or "") != "forecast":
        return False
    text = f"{item.get('title') or ''} {item.get('notice_type') or ''}"
    return bool(_INTERIM_RE.search(text))


def _as_date(raw: Any) -> date | None:
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw)[:10])
    except Exception:
        return None


def _finite(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return v


def build_features(
    *,
    pe_ttm: float,
    market_cap_yi: float,
    parent_np_value: float,
    parent_np_yoy: float,
) -> dict[str, float] | None:
    """半年归母 ×2 年化后算预告 PE / 盈利收益率；市值单位亿元。"""
    if market_cap_yi <= 0:
        return None
    np_h1 = parent_np_value
    np_annualized = np_h1 * 2.0
    if np_annualized == 0:
        return None
    mcap_yuan = market_cap_yi * 1e8
    forecast_pe = mcap_yuan / np_annualized
    forecast_ey = np_annualized / mcap_yuan
    return {
        "pe_ttm": pe_ttm,
        "market_cap": market_cap_yi,
        "ln_mcap": math.log(market_cap_yi),
        "parent_np_h1": np_h1,
        "parent_np_annualized": np_annualized,
        "parent_np_yoy": parent_np_yoy,
        "parent_np_yoy_pct": parent_np_yoy * 100.0,
        "forecast_pe": forecast_pe,
        "forecast_ey": forecast_ey,
        "forecast_ey_pct": forecast_ey * 100.0,
    }


def pick_primary_interim(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一股票多条中报预告时保留公告日最新的一条。"""
    best: dict[str, dict[str, Any]] = {}
    for item in items:
        if not is_interim_forecast(item):
            continue
        code = str(item.get("code") or "").upper()
        if not code:
            continue
        nd = _as_date(item.get("notice_date"))
        prev = best.get(code)
        if prev is None:
            best[code] = item
            continue
        prev_nd = _as_date(prev.get("notice_date"))
        if nd and (prev_nd is None or nd >= prev_nd):
            best[code] = item
    return list(best.values())


def build_cohort(
    repos: Any,
    start: date,
    end: date,
    *,
    main_only: bool = True,
) -> dict[str, Any]:
    """拉取中报预告样本，挂估值与衍生指标。"""
    from quant_system.api.services.stocks import _valuation_fields, get_disclosures_by_date

    raw = get_disclosures_by_date(
        repos,
        start_date=start,
        end_date=end,
        categories=["forecast"],
        main_only=main_only,
        enrich_forecast=True,
    )
    candidates = pick_primary_interim(list(raw.get("items") or []))
    rows: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []

    for item in candidates:
        code = str(item.get("code") or "").upper()
        notice_date = _as_date(item.get("notice_date"))
        pe: float | None = None
        mcap: float | None = None
        val_date = None
        if notice_date is not None:
            val = _valuation_fields(repos, code, as_of=notice_date)
            pe = _finite(val.get("pe_ttm"))
            mcap = _finite(val.get("market_cap"))
            val_date = val.get("valuation_date")

        yoy = _finite(item.get("parent_np_yoy"))
        np_val = _finite(item.get("parent_np_value"))
        ret = _finite(item.get("return_since_notice"))

        reason: str | None = None
        if notice_date is None:
            reason = "missing_notice_date"
        elif pe is None:
            reason = "missing_pe"
        elif mcap is None or mcap <= 0:
            reason = "missing_market_cap"
        elif yoy is None:
            reason = "missing_parent_np_yoy"
        elif np_val is None:
            reason = "missing_parent_np_value"
        elif ret is None:
            reason = "missing_return"
        else:
            feats = build_features(
                pe_ttm=pe,
                market_cap_yi=mcap,
                parent_np_value=np_val,
                parent_np_yoy=yoy,
            )
            if feats is None:
                reason = "invalid_profit_or_mcap"
            else:
                y_pct = ret * 100.0
                rows.append(
                    {
                        "code": code,
                        "name": str(item.get("name") or ""),
                        "notice_date": notice_date,
                        "predict_type": item.get("predict_type"),
                        "report_period": item.get("report_period"),
                        "valuation_date": val_date,
                        "return_since_notice": ret,
                        "return_pct": y_pct,
                        **feats,
                    }
                )
                continue
        dropped.append({"code": code, "reason": reason or "unknown"})

    return {
        "start_date": start,
        "end_date": end,
        "main_only": main_only,
        "candidates": len(candidates),
        "n": len(rows),
        "dropped_n": len(dropped),
        "dropped": dropped,
        "rows": rows,
    }


def _ols(y: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, float]:
    """带截距 OLS；返回 [intercept, betas...], r_squared。"""
    n, k = x.shape
    ones = np.ones((n, 1), dtype=float)
    a = np.hstack([ones, x])
    coef, _, _, _ = np.linalg.lstsq(a, y, rcond=None)
    y_hat = a @ coef
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return coef, r2


def _corr_matrix(
    mat: np.ndarray, names: list[str]
) -> dict[str, dict[str, float | None]]:
    if mat.shape[0] < 2:
        return {n: {m: (1.0 if n == m else None) for m in names} for n in names}
    c = np.corrcoef(mat, rowvar=False)
    out: dict[str, dict[str, float | None]] = {}
    for i, ni in enumerate(names):
        out[ni] = {}
        for j, nj in enumerate(names):
            v = float(c[i, j])
            out[ni][nj] = v if math.isfinite(v) else None
    return out


def _group_means(rows: list[dict[str, Any]]) -> dict[str, Any]:
    up = [r for r in rows if r["return_pct"] > 0]
    down = [r for r in rows if r["return_pct"] < 0]
    flat = [r for r in rows if r["return_pct"] == 0]
    keys = ["pe_ttm", "market_cap", "parent_np_yoy_pct", "forecast_pe", "forecast_ey_pct", "return_pct"]

    def means(group: list[dict[str, Any]]) -> dict[str, float | None]:
        if not group:
            return {k: None for k in keys}
        return {k: float(np.mean([g[k] for g in group])) for k in keys}

    return {
        "up_n": len(up),
        "down_n": len(down),
        "flat_n": len(flat),
        "up_rate": (len(up) / len(rows)) if rows else 0.0,
        "down_rate": (len(down) / len(rows)) if rows else 0.0,
        "up_means": means(up),
        "down_means": means(down),
        "diff_down_minus_up": {
            k: (
                None
                if means(down)[k] is None or means(up)[k] is None
                else float(means(down)[k]) - float(means(up)[k])  # type: ignore[arg-type]
            )
            for k in keys
            if k != "return_pct"
        },
    }


def run_ols(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """对 return_pct 做原始尺度 + z-score 标准化 OLS。"""
    if len(rows) < len(FEATURE_KEYS) + 2:
        return {
            "ok": False,
            "message": f"有效样本不足（需至少 {len(FEATURE_KEYS) + 2}，当前 {len(rows)}）",
            "n": len(rows),
            "feature_keys": list(FEATURE_KEYS),
            "feature_labels": dict(FEATURE_LABELS),
            "coefficients": [],
            "intercept": None,
            "r_squared": None,
            "std_intercept": None,
            "std_r_squared": None,
            "formula": None,
            "corr": {},
            "groups": _group_means(rows),
            "rows": rows,
        }

    y = np.array([r["return_pct"] for r in rows], dtype=float)
    x_raw = np.array([[r[k] for k in FEATURE_KEYS] for r in rows], dtype=float)
    means = x_raw.mean(axis=0)
    stds = x_raw.std(axis=0, ddof=0)
    stds_safe = np.where(stds < 1e-12, 1.0, stds)
    x_z = (x_raw - means) / stds_safe

    coef_raw, r2 = _ols(y, x_raw)
    coef_z, r2_z = _ols(y, x_z)
    y_hat = coef_raw[0] + x_raw @ coef_raw[1:]

    for i, r in enumerate(rows):
        r["fitted_return_pct"] = float(y_hat[i])
        r["residual_pct"] = float(y[i] - y_hat[i])

    coefficients = []
    for i, key in enumerate(FEATURE_KEYS):
        coefficients.append(
            {
                "key": key,
                "label": FEATURE_LABELS[key],
                "coef": float(coef_raw[i + 1]),
                "std_coef": float(coef_z[i + 1]),
                "mean": float(means[i]),
                "std": float(stds[i]),
            }
        )

    intercept = float(coef_raw[0])
    parts = [f"{intercept:.4f}"]
    for c in coefficients:
        sign = "+" if c["coef"] >= 0 else "-"
        parts.append(f" {sign} {abs(c['coef']):.6f}·{c['key']}")
    formula_text = "E[return_pct] = " + "".join(parts)

    corr_names = list(FEATURE_KEYS) + ["return_pct"]
    corr_mat = np.column_stack([x_raw, y])
    groups = _group_means(rows)

    return {
        "ok": True,
        "message": None,
        "n": len(rows),
        "feature_keys": list(FEATURE_KEYS),
        "feature_labels": dict(FEATURE_LABELS),
        "intercept": intercept,
        "r_squared": float(r2),
        "std_intercept": float(coef_z[0]),
        "std_r_squared": float(r2_z),
        "coefficients": coefficients,
        "formula": {
            "text": formula_text,
            "intercept": intercept,
            "coefs": {c["key"]: c["coef"] for c in coefficients},
            "means": {c["key"]: c["mean"] for c in coefficients},
            "stds": {c["key"]: c["std"] for c in coefficients},
            "note": (
                "return_pct 为公告后至今涨跌幅（百分点）。"
                "forecast_ey_pct = 年化预告归母(半年×2) / 市值 ×100。"
                "套用：代入 pe_ttm、ln(市值亿元)、归母同比%、预告盈利收益率%。"
            ),
        },
        "corr": _corr_matrix(corr_mat, corr_names),
        "groups": groups,
        "rows": rows,
    }


def analyze_forecast_return_factors(
    repos: Any,
    start: date,
    end: date,
    *,
    main_only: bool = True,
) -> dict[str, Any]:
    cohort = build_cohort(repos, start, end, main_only=main_only)
    ols = run_ols(list(cohort["rows"]))
    return {
        "start_date": cohort["start_date"],
        "end_date": cohort["end_date"],
        "main_only": cohort["main_only"],
        "candidates": cohort["candidates"],
        "dropped_n": cohort["dropped_n"],
        "dropped": cohort["dropped"][:50],
        "drop_hint": (
            "缺 PE/市值时请先同步 daily_valuation；"
            "缺预告利润或公告后收益的样本已剔除。"
            if cohort["dropped_n"]
            else None
        ),
        **ols,
    }
