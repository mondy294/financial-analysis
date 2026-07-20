from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from quant_system.api.deps import get_repos
from quant_system.api.errors import raise_bad_request, raise_not_found
from quant_system.api.schemas.earnings_events import (
    BuildPanelIn,
    FitIn,
    ModelBriefOut,
    PredictIn,
)
from quant_system.data.repository import Repositories
from quant_system.earnings_analytics import service as eea
from quant_system.earnings_analytics.panel.build import load_panel_rows

router = APIRouter(prefix="/analysis/earnings-events", tags=["earnings-events"])


@router.post("/build-panel")
def build_panel(body: BuildPanelIn, repos: Repositories = Depends(get_repos)) -> dict:
    """构建 Event Panel；可选先跑 Event Builder。"""
    try:
        if body.build_events:
            if body.start_date is None or body.end_date is None:
                raise_bad_request("build_events=true 时需要 start_date / end_date")
            eea.service_build_events(
                repos,
                body.start_date,
                body.end_date,
                main_only=body.main_only,
            )
        result = eea.service_build_panel(
            repos,
            start=body.start_date,
            end=body.end_date,
            panel_tag=body.panel_tag,
            cluster_run_id=body.cluster_run_id,
        )
        repos.kline._session.commit()  # noqa: SLF001
        return result
    except ValueError as e:
        raise_bad_request(str(e))


@router.post("/fit")
def fit(body: FitIn, repos: Repositories = Depends(get_repos)) -> dict:
    try:
        result = eea.service_fit(
            repos,
            panel_tag=body.panel_tag,
            scopes=body.scopes,
            cluster_modes=body.cluster_modes,
        )
        repos.kline._session.commit()  # noqa: SLF001
        return result
    except ValueError as e:
        raise_bad_request(str(e))


@router.post("/predict")
def predict(body: PredictIn, repos: Repositories = Depends(get_repos)) -> dict:
    try:
        return eea.service_predict(
            repos,
            code=body.code,
            event_kind=body.event_kind,
            parent_np=body.parent_np,
            parent_np_yoy=body.parent_np_yoy,
            report_period=body.report_period,
            as_of=body.as_of,
            model_scope=body.model_scope,
            use_cluster=body.use_cluster,
            model_id=body.model_id,
            panel_tag=body.panel_tag,
            with_explain=body.with_explain,
        )
    except LookupError as e:
        raise_not_found(str(e))
    except ValueError as e:
        raise_bad_request(str(e))


@router.post("/explain")
def explain(body: PredictIn, repos: Repositories = Depends(get_repos)) -> dict:
    body.with_explain = True
    return predict(body, repos)


@router.post("/score")
def score(body: PredictIn, repos: Repositories = Depends(get_repos)) -> dict:
    """便利端点：predict + score + explain。"""
    body.with_explain = True
    return predict(body, repos)


@router.get("/models", response_model=list[ModelBriefOut])
def models(
    panel_tag: str | None = Query(None),
    repos: Repositories = Depends(get_repos),
) -> list[ModelBriefOut]:
    session = repos.kline._session  # noqa: SLF001
    return [ModelBriefOut(**x) for x in eea.list_models(session, panel_tag=panel_tag)]


@router.get("/models/{model_id}")
def model_detail(model_id: str, repos: Repositories = Depends(get_repos)) -> dict:
    session = repos.kline._session  # noqa: SLF001
    m = eea.get_model(session, model_id)
    if m is None:
        raise_not_found(f"model not found: {model_id}")
    return {
        "model_id": m.model_id,
        "fitted_at": m.fitted_at,
        "panel_tag": m.panel_tag,
        "model_scope": m.model_scope,
        "cluster_mode": m.cluster_mode,
        "cluster_id": m.cluster_id,
        "cluster_run_id": m.cluster_run_id,
        "backend_id": m.backend_id,
        "estimator_id": m.estimator_id,
        "feature_cols": m.feature_cols_json,
        "filter_spec": m.filter_spec_json,
        "n_samples": m.n_samples,
        "metrics": m.metrics_json,
        "regression": m.regression_json,
        "fair_value": m.fair_value_json,
        "notes": m.notes,
        "status": m.status,
    }


@router.get("/panel/by-cluster")
def panel_by_cluster(
    panel_tag: str = Query("default"),
    repos: Repositories = Depends(get_repos),
) -> dict:
    return eea.panel_by_cluster_summary(repos, panel_tag=panel_tag)


@router.get("/panel/summary")
def panel_summary(
    panel_tag: str = Query("default"),
    repos: Repositories = Depends(get_repos),
) -> dict:
    session = repos.kline._session  # noqa: SLF001
    rows = load_panel_rows(session, panel_tag=panel_tag)
    n = len(rows)
    with_ret = sum(1 for r in rows if r.get("ret_20d") is not None)
    with_ey = sum(1 for r in rows if r.get("ey_event") is not None)
    return {
        "panel_tag": panel_tag,
        "n_rows": n,
        "n_with_ret_20d": with_ret,
        "n_with_ey": with_ey,
        "kinds": _count_by(rows, "event_kind"),
    }


def _count_by(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        k = str(r.get(key) or "")
        out[k] = out.get(k, 0) + 1
    return out
