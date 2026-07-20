"""EEA 高层服务：供 API / CLI 调用。"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from quant_system.data.repository import Repositories
from quant_system.database.models import EarningsAnalyticsModel
from quant_system.earnings_analytics.events.builder import build_events
from quant_system.earnings_analytics.explain.engine import run_explain
from quant_system.earnings_analytics.fair_value.protocol import FairValueModel
from quant_system.earnings_analytics.features.builder import build_online_features
from quant_system.earnings_analytics.fit import fit_models
from quant_system.earnings_analytics.panel.build import build_panel, load_panel_rows
from quant_system.earnings_analytics.prediction.layer import run_prediction
from quant_system.earnings_analytics.regression.protocol import FittedModel
from quant_system.earnings_analytics.score.layer import run_score


def service_build_events(
    repos: Repositories,
    start: date,
    end: date,
    *,
    main_only: bool = True,
    progress_cb: Any | None = None,
) -> dict[str, Any]:
    session = repos.kline._session  # noqa: SLF001
    return build_events(
        session, start, end, main_only=main_only, progress_cb=progress_cb
    )


def service_build_panel(
    repos: Repositories,
    *,
    start: date | None = None,
    end: date | None = None,
    panel_tag: str = "default",
    cluster_run_id: str | None = None,
    progress_cb: Any | None = None,
) -> dict[str, Any]:
    return build_panel(
        repos,
        start=start,
        end=end,
        panel_tag=panel_tag,
        cluster_run_id=cluster_run_id,
        progress_cb=progress_cb,
    )


def service_fit(
    repos: Repositories,
    *,
    panel_tag: str = "default",
    scopes: list[str] | None = None,
    cluster_modes: list[str] | None = None,
    progress_cb: Any | None = None,
) -> dict[str, Any]:
    session = repos.kline._session  # noqa: SLF001
    return fit_models(
        session,
        panel_tag=panel_tag,
        scopes=scopes,
        cluster_modes=cluster_modes,
        progress_cb=progress_cb,
    )


def list_models(session: Session, *, panel_tag: str | None = None) -> list[dict[str, Any]]:
    stmt = select(EarningsAnalyticsModel).where(EarningsAnalyticsModel.status == "ready")
    if panel_tag:
        stmt = stmt.where(EarningsAnalyticsModel.panel_tag == panel_tag)
    stmt = stmt.order_by(EarningsAnalyticsModel.fitted_at.desc())
    rows = session.execute(stmt).scalars().all()
    return [
        {
            "model_id": r.model_id,
            "fitted_at": r.fitted_at,
            "panel_tag": r.panel_tag,
            "model_scope": r.model_scope,
            "cluster_mode": r.cluster_mode,
            "cluster_id": r.cluster_id,
            "backend_id": r.backend_id,
            "estimator_id": r.estimator_id,
            "n_samples": r.n_samples,
            "metrics": r.metrics_json,
            "feature_cols": r.feature_cols_json,
        }
        for r in rows
    ]


def get_model(session: Session, model_id: str) -> EarningsAnalyticsModel | None:
    return session.get(EarningsAnalyticsModel, model_id)


def _resolve_model(
    session: Session,
    *,
    panel_tag: str,
    model_scope: str,
    use_cluster: bool,
    cluster_id: int | None,
    model_id: str | None,
) -> tuple[EarningsAnalyticsModel, str]:
    if model_id:
        m = session.get(EarningsAnalyticsModel, model_id)
        if m is None:
            raise LookupError(f"model not found: {model_id}")
        return m, "explicit_model_id"

    def _find(scope: str, mode: str, cid: int | None) -> EarningsAnalyticsModel | None:
        stmt = (
            select(EarningsAnalyticsModel)
            .where(EarningsAnalyticsModel.panel_tag == panel_tag)
            .where(EarningsAnalyticsModel.model_scope == scope)
            .where(EarningsAnalyticsModel.cluster_mode == mode)
            .where(EarningsAnalyticsModel.status == "ready")
            .order_by(EarningsAnalyticsModel.fitted_at.desc())
        )
        if mode == "per_cluster":
            stmt = stmt.where(EarningsAnalyticsModel.cluster_id == cid)
        else:
            stmt = stmt.where(EarningsAnalyticsModel.cluster_id.is_(None))
        return session.execute(stmt).scalars().first()

    if use_cluster and cluster_id is not None:
        m = _find(model_scope, "per_cluster", cluster_id)
        if m is not None:
            return m, "per_cluster"
        m = _find(model_scope, "fixed_effect", None)
        if m is not None:
            return m, "fixed_effect_fallback"
    m = _find(model_scope, "none", None)
    if m is None:
        raise LookupError(
            f"no model for panel_tag={panel_tag} scope={model_scope} cluster_mode=none"
        )
    reason = "none"
    if use_cluster:
        reason = "none_fallback"
    return m, reason


def _unpack_model(m: EarningsAnalyticsModel) -> tuple[dict[str, FittedModel], FairValueModel]:
    reg = {
        k: FittedModel.from_json(v) for k, v in (m.regression_json or {}).items()
    }
    fair = FairValueModel.from_json(m.fair_value_json or {})
    return reg, fair


def service_predict(
    repos: Repositories,
    *,
    code: str,
    event_kind: str,
    parent_np: float,
    as_of: date | None = None,
    parent_np_yoy: float | None = None,
    report_period: date | None = None,
    model_scope: str = "all",
    use_cluster: bool = False,
    model_id: str | None = None,
    panel_tag: str = "default",
    with_explain: bool = False,
) -> dict[str, Any]:
    session = repos.kline._session  # noqa: SLF001
    as_of = as_of or date.today()
    row = build_online_features(
        repos,
        code=code,
        event_kind=event_kind,
        parent_np=parent_np,
        parent_np_yoy=parent_np_yoy,
        as_of=as_of,
        report_period=report_period,
    )
    if row.get("annualized_parent_np") is not None and float(row["annualized_parent_np"]) <= 0:
        return {
            "ok": False,
            "unavailable_reason": "loss_making",
            "row": row,
        }

    model, resolve_reason = _resolve_model(
        session,
        panel_tag=panel_tag,
        model_scope=model_scope,
        use_cluster=use_cluster,
        cluster_id=row.get("cluster_id"),
        model_id=model_id,
    )
    reg, fair = _unpack_model(model)
    pred = run_prediction(
        row,
        regression_by_horizon=reg,
        fair_model=fair,
        meta={
            "model_id": model.model_id,
            "model_scope": model.model_scope,
            "cluster_mode": model.cluster_mode,
            "resolve_reason": resolve_reason,
            "use_cluster": use_cluster,
            "cluster_id": row.get("cluster_id"),
        },
    )
    panel_rows = load_panel_rows(session, panel_tag=panel_tag)
    ey_vals = [
        float(r["ey_event"])
        for r in panel_rows
        if r.get("ey_event") is not None and r.get("event_kind") == event_kind
    ]
    score = run_score(pred, panel_ey_values=ey_vals, row=row)
    out: dict[str, Any] = {
        "ok": True,
        "code": code.upper(),
        "as_of": as_of,
        "event_kind": event_kind,
        "features": row,
        "prediction": pred,
        "score": score,
        "model": {
            "model_id": model.model_id,
            "model_scope": model.model_scope,
            "cluster_mode": model.cluster_mode,
            "cluster_id": model.cluster_id,
            "metrics": model.metrics_json,
            "resolve_reason": resolve_reason,
        },
    }
    if with_explain:
        out["explain"] = run_explain(row, pred, score, regression_by_horizon=reg)
    return out


def service_explain(
    repos: Repositories,
    **kwargs: Any,
) -> dict[str, Any]:
    kwargs["with_explain"] = True
    return service_predict(repos, **kwargs)


def find_recent_earnings_event(
    repos: Repositories,
    code: str,
    *,
    lookback_days: int = 5,
) -> dict[str, Any] | None:
    """近 lookback_days 日内带归母利润的最新业绩事件。"""
    from datetime import timedelta

    from sqlalchemy import select

    from quant_system.database.models import EarningsDisclosureEvent

    session = repos.kline._session  # noqa: SLF001
    code_u = code.upper()
    start = date.today() - timedelta(days=max(1, lookback_days))
    row = session.execute(
        select(EarningsDisclosureEvent)
        .where(EarningsDisclosureEvent.code == code_u)
        .where(EarningsDisclosureEvent.event_date >= start)
        .where(EarningsDisclosureEvent.parent_np.is_not(None))
        .order_by(
            EarningsDisclosureEvent.event_date.desc(),
            EarningsDisclosureEvent.updated_at.desc(),
        )
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return None
    ed = row.event_date
    rp = row.report_period
    return {
        "event_date": ed.isoformat() if hasattr(ed, "isoformat") else str(ed)[:10],
        "event_kind": row.event_kind,
        "report_period": rp.isoformat() if rp is not None and hasattr(rp, "isoformat") else rp,
        "parent_np": float(row.parent_np) if row.parent_np is not None else None,
        "parent_np_yoy": float(row.parent_np_yoy) if row.parent_np_yoy is not None else None,
        "predict_type": row.predict_type,
        "title": row.title,
        "source": row.source,
    }


def service_earnings_fair_anchor(
    repos: Repositories,
    code: str,
    *,
    lookback_days: int = 5,
    panel_tag: str = "default",
    use_cluster: bool = False,
) -> dict[str, Any]:
    """近几日业绩 → 公允价锚点（供详情页 K 线展示）。

    fair_price ≈ 最新收盘 / (1 + premium_pct)
    """
    from quant_system.earnings_analytics.constants import is_interim_season

    code_u = code.upper()
    event = find_recent_earnings_event(repos, code_u, lookback_days=lookback_days)
    if event is None or event.get("parent_np") is None:
        return {
            "available": False,
            "reason": "no_recent_earnings_with_profit",
            "lookback_days": lookback_days,
            "code": code_u,
        }

    kind = str(event["event_kind"] or "interim")

    def _as_date(v: Any) -> date | None:
        if v is None:
            return None
        if isinstance(v, date):
            return v
        try:
            return date.fromisoformat(str(v)[:10])
        except ValueError:
            return None

    event_date = _as_date(event.get("event_date")) or date.today()
    report_period = _as_date(event.get("report_period"))
    scope = (
        "interim"
        if is_interim_season(kind, report_period)
        else ("annual" if kind == "annual" else "all")
    )
    # 有 interim 模型用 interim，否则回退 all
    try:
        pred = service_predict(
            repos,
            code=code_u,
            event_kind=kind,
            parent_np=float(event["parent_np"]),
            parent_np_yoy=event.get("parent_np_yoy"),
            report_period=report_period,
            as_of=event_date,
            model_scope=scope,
            use_cluster=use_cluster,
            panel_tag=panel_tag,
            with_explain=False,
        )
    except LookupError:
        if scope != "all":
            try:
                pred = service_predict(
                    repos,
                    code=code_u,
                    event_kind=kind,
                    parent_np=float(event["parent_np"]),
                    parent_np_yoy=event.get("parent_np_yoy"),
                    report_period=report_period,
                    as_of=event_date,
                    model_scope="all",
                    use_cluster=use_cluster,
                    panel_tag=panel_tag,
                    with_explain=False,
                )
                scope = "all"
            except LookupError as e:
                return {
                    "available": False,
                    "reason": "no_model",
                    "detail": str(e),
                    "event": event,
                    "code": code_u,
                }
        else:
            return {
                "available": False,
                "reason": "no_model",
                "event": event,
                "code": code_u,
            }

    if not pred.get("ok"):
        return {
            "available": False,
            "reason": pred.get("unavailable_reason") or "predict_failed",
            "event": event,
            "code": code_u,
            "prediction": pred,
        }

    # 最新收盘（前复权）
    from quant_system.api.services import stocks as stock_svc

    klines = stock_svc.get_kline(repos, code_u, limit=5, adj="qfq")
    ref_close = None
    ref_date = None
    if klines:
        last = klines[-1]
        ref_close = float(last["close"])
        rd = last["trade_date"]
        ref_date = rd.isoformat() if hasattr(rd, "isoformat") else str(rd)[:10]

    premium = (pred.get("prediction") or {}).get("premium_pct")
    fair_price = None
    if ref_close is not None and premium is not None and (1.0 + float(premium)) != 0:
        fair_price = float(ref_close) / (1.0 + float(premium))

    e20 = (pred.get("prediction") or {}).get("expected_return_20d")
    price_e20 = None
    if ref_close is not None and e20 is not None:
        price_e20 = float(ref_close) * (1.0 + float(e20) / 100.0)

    return {
        "available": fair_price is not None,
        "reason": None if fair_price is not None else "missing_premium_or_price",
        "code": code_u,
        "lookback_days": lookback_days,
        "event": event,
        "model_scope": scope,
        "ref_close": ref_close,
        "ref_date": ref_date,
        "fair_price": fair_price,
        "premium_pct": premium,
        "implied_fair_mcap": (pred.get("prediction") or {}).get("implied_fair_mcap"),
        "expected_return_20d": e20,
        "price_at_expected_20d": price_e20,
        "model": pred.get("model"),
    }


def panel_by_cluster_summary(
    repos: Repositories, *, panel_tag: str = "default"
) -> dict[str, Any]:
    session = repos.kline._session  # noqa: SLF001
    rows = load_panel_rows(session, panel_tag=panel_tag)
    by: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        if r.get("cluster_id") is None:
            continue
        by.setdefault(int(r["cluster_id"]), []).append(r)

    clusters = []
    for cid, items in sorted(by.items()):
        def _mean(key: str) -> float | None:
            vals = [float(x[key]) for x in items if x.get(key) is not None]
            if not vals:
                return None
            return sum(vals) / len(vals)

        up = sum(1 for x in items if (x.get("ret_20d") or 0) > 0)
        clusters.append(
            {
                "cluster_id": cid,
                "n": len(items),
                "up_rate_20d": up / len(items) if items else None,
                "mean_ret_5d": _mean("ret_5d"),
                "mean_ret_10d": _mean("ret_10d"),
                "mean_ret_20d": _mean("ret_20d"),
                "mean_ey_event": _mean("ey_event"),
            }
        )
    global_ret20 = [
        float(r["ret_20d"]) for r in rows if r.get("ret_20d") is not None
    ]
    g_mean = sum(global_ret20) / len(global_ret20) if global_ret20 else None
    for c in clusters:
        if c["mean_ret_20d"] is not None and g_mean is not None:
            c["excess_ret_20d"] = c["mean_ret_20d"] - g_mean
        else:
            c["excess_ret_20d"] = None
    return {
        "panel_tag": panel_tag,
        "n_rows": len(rows),
        "global_mean_ret_20d": g_mean,
        "clusters": clusters,
    }
