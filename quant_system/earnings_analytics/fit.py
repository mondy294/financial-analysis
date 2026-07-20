"""Fit：scopes × cluster_modes → earnings_analytics_model。"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from quant_system.database.models import EarningsAnalyticsModel
from quant_system.earnings_analytics.constants import (
    CLUSTER_MODES,
    DEFAULT_FEATURE_COLS,
    DEFAULT_HORIZONS,
    MIN_SAMPLES_GLOBAL,
    MIN_SAMPLES_PER_CLUSTER,
    MODEL_SCOPES,
    filter_spec_for_scope,
    row_matches_scope,
)
from quant_system.earnings_analytics.fair_value.median_ey import get_estimator
from quant_system.earnings_analytics.panel.build import load_panel_rows
from quant_system.earnings_analytics.regression.ols import get_backend
from quant_system.earnings_analytics.regression.protocol import FittedModel


def _model_id(
    panel_tag: str,
    scope: str,
    cluster_mode: str,
    cluster_id: int | None,
    backend: str,
    estimator: str,
) -> str:
    raw = f"{panel_tag}|{scope}|{cluster_mode}|{cluster_id}|{backend}|{estimator}"
    return hashlib.sha1(raw.encode()).hexdigest()[:20]


def _filter_scope(rows: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
    return [r for r in rows if row_matches_scope(r, scope)]


def fit_models(
    session: Session,
    *,
    panel_tag: str = "default",
    scopes: list[str] | None = None,
    cluster_modes: list[str] | None = None,
    feature_cols: list[str] | None = None,
    backend_id: str = "ols",
    estimator_id: str = "median_ey",
    progress_cb: Any | None = None,
) -> dict[str, Any]:
    scopes = list(scopes or MODEL_SCOPES)
    cluster_modes = list(cluster_modes or ["none", "fixed_effect", "per_cluster"])
    feature_cols = list(feature_cols or DEFAULT_FEATURE_COLS)
    backend = get_backend(backend_id)
    estimator = get_estimator(estimator_id)
    if progress_cb:
        progress_cb(0.05, f"加载 Panel tag={panel_tag}")
    all_rows = load_panel_rows(session, panel_tag=panel_tag)
    now = datetime.utcnow()
    saved: list[str] = []
    errors: list[dict[str, str]] = []
    # 预估步数：scope × mode（per_cluster 再按簇拆）
    rough_steps = max(len(scopes) * max(len(cluster_modes), 1), 1)
    step_i = 0

    for scope in scopes:
        if scope not in MODEL_SCOPES:
            errors.append({"scope": scope, "error": "unknown_scope"})
            continue
        sub = _filter_scope(all_rows, scope)
        fair = estimator.fit(sub)

        for mode in cluster_modes:
            if mode not in CLUSTER_MODES:
                continue
            step_i += 1
            if progress_cb:
                progress_cb(
                    min(0.95, 0.1 + 0.85 * (step_i / (rough_steps + 3))),
                    f"拟合 scope={scope} mode={mode} n={len(sub)}",
                )
            if mode == "none":
                try:
                    mid = _persist_one(
                        session,
                        rows=sub,
                        panel_tag=panel_tag,
                        scope=scope,
                        cluster_mode="none",
                        cluster_id=None,
                        feature_cols=feature_cols,
                        backend=backend,
                        fair=fair,
                        backend_id=backend_id,
                        estimator_id=estimator_id,
                        fe=False,
                        now=now,
                    )
                    saved.append(mid)
                except Exception as e:
                    logger.warning("EEA fit failed scope={} mode=none: {}", scope, e)
                    errors.append({"scope": scope, "cluster_mode": "none", "error": str(e)})
            elif mode == "fixed_effect":
                try:
                    mid = _persist_one(
                        session,
                        rows=sub,
                        panel_tag=panel_tag,
                        scope=scope,
                        cluster_mode="fixed_effect",
                        cluster_id=None,
                        feature_cols=feature_cols,
                        backend=backend,
                        fair=fair,
                        backend_id=backend_id,
                        estimator_id=estimator_id,
                        fe=True,
                        now=now,
                    )
                    saved.append(mid)
                except Exception as e:
                    logger.warning("EEA fit failed scope={} mode=fe: {}", scope, e)
                    errors.append(
                        {"scope": scope, "cluster_mode": "fixed_effect", "error": str(e)}
                    )
            elif mode == "per_cluster":
                by_c: dict[int, list[dict[str, Any]]] = {}
                for r in sub:
                    if r.get("cluster_id") is None:
                        continue
                    by_c.setdefault(int(r["cluster_id"]), []).append(r)
                eligible = [
                    (cid, crow)
                    for cid, crow in by_c.items()
                    if len(crow)
                    >= max(MIN_SAMPLES_PER_CLUSTER, 8 * len(feature_cols))
                ]
                for j, (cid, crow) in enumerate(eligible):
                    if progress_cb:
                        progress_cb(
                            min(0.98, 0.1 + 0.85 * ((step_i + j / max(len(eligible), 1)) / (rough_steps + 3))),
                            f"分簇拟合 scope={scope} cluster={cid} ({j + 1}/{len(eligible)})",
                        )
                    try:
                        mid = _persist_one(
                            session,
                            rows=crow,
                            panel_tag=panel_tag,
                            scope=scope,
                            cluster_mode="per_cluster",
                            cluster_id=cid,
                            feature_cols=feature_cols,
                            backend=backend,
                            fair=estimator.fit(crow),
                            backend_id=backend_id,
                            estimator_id=estimator_id,
                            fe=False,
                            now=now,
                        )
                        saved.append(mid)
                    except Exception as e:
                        errors.append(
                            {
                                "scope": scope,
                                "cluster_mode": "per_cluster",
                                "cluster_id": str(cid),
                                "error": str(e),
                            }
                        )

    session.flush()
    if progress_cb:
        progress_cb(1.0, f"拟合完成 saved={len(saved)}")
    return {
        "panel_tag": panel_tag,
        "saved_model_ids": saved,
        "n_saved": len(saved),
        "errors": errors,
        "n_panel_rows": len(all_rows),
    }


def _persist_one(
    session: Session,
    *,
    rows: list[dict[str, Any]],
    panel_tag: str,
    scope: str,
    cluster_mode: str,
    cluster_id: int | None,
    feature_cols: list[str],
    backend: Any,
    fair: Any,
    backend_id: str,
    estimator_id: str,
    fe: bool,
    now: datetime,
) -> str:
    if len(rows) < MIN_SAMPLES_GLOBAL and cluster_mode != "per_cluster":
        raise ValueError(f"n={len(rows)} < {MIN_SAMPLES_GLOBAL}")

    reg_json: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    cluster_run_id = None
    for r in rows:
        if r.get("cluster_run_id"):
            cluster_run_id = r["cluster_run_id"]
            break

    for h in DEFAULT_HORIZONS:
        target = f"ret_{h}d"
        fitted: FittedModel = backend.fit(
            rows,
            feature_cols,
            target,
            params={"cluster_fixed_effect": fe, "min_n": 20 if cluster_mode == "per_cluster" else MIN_SAMPLES_GLOBAL},
        )
        reg_json[target] = fitted.to_json()
        metrics[f"r2_{h}d"] = fitted.metrics.get("r_squared")
        metrics[f"n_{h}d"] = fitted.n

    mid = _model_id(panel_tag, scope, cluster_mode, cluster_id, backend_id, estimator_id)
    existing = session.get(EarningsAnalyticsModel, mid)
    payload = dict(
        fitted_at=now,
        panel_tag=panel_tag,
        model_scope=scope,
        cluster_mode=cluster_mode,
        cluster_id=cluster_id,
        cluster_run_id=cluster_run_id,
        backend_id=backend_id,
        estimator_id=estimator_id,
        feature_cols_json=feature_cols,
        filter_spec_json=filter_spec_for_scope(scope),
        n_samples=len(rows),
        metrics_json=metrics,
        regression_json=reg_json,
        fair_value_json=fair.to_json(),
        notes=None,
        status="ready",
    )
    if existing is None:
        session.add(EarningsAnalyticsModel(model_id=mid, **payload))
    else:
        for k, v in payload.items():
            setattr(existing, k, v)
    return mid
