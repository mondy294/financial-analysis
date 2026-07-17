"""批处理任务执行体：复用现有 Service，不 subprocess CLI。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from quant_system.api.jobs.runner import JobRecord


def _parse_date(raw: Any) -> date:
    from quant_system.infra import trading_calendar as tc

    if raw is None or raw == "":
        return tc.latest_trading_day()
    if isinstance(raw, date):
        return raw
    return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()


def _parse_codes(raw: Any) -> list[str] | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, list):
        return [str(x).strip().upper() for x in raw if str(x).strip()]
    parts = [x.strip().upper() for x in str(raw).split(",") if x.strip()]
    return parts or None


def _parse_windows(raw: Any) -> list[str] | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    # "60,250" → ["W60","W250"] or keep as numbers for service
    out: list[str] = []
    for part in str(raw).split(","):
        p = part.strip().upper()
        if not p:
            continue
        if p.startswith("W"):
            out.append(p)
        else:
            out.append(f"W{p}" if p.isdigit() else p)
    return out or None


def _bool(raw: Any, default: bool = False) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    s = str(raw).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off", ""):
        return False
    return default


def _stats_dict(result: Any) -> dict[str, Any]:
    from quant_system.data.data_update import UpdateAllReport, UpdateStats

    if isinstance(result, UpdateStats):
        return result.to_dict()
    if isinstance(result, UpdateAllReport):
        return {
            "steps": [
                {
                    "name": name,
                    "processed": p,
                    "inserted": i,
                    "skipped": s,
                    "errors": e,
                }
                for name, p, i, s, e in result.summary_rows()
            ]
        }
    if isinstance(result, dict):
        return result
    return {"raw": str(result)}


def _providers() -> dict[str, Any]:
    from quant_system.data.provider_factory import (
        get_financial_provider,
        get_index_provider,
        get_sentiment_provider,
        get_stock_provider,
    )

    return {
        "stock": get_stock_provider(),
        "financial": get_financial_provider(),
        "index": get_index_provider(),
        "sentiment": get_sentiment_provider(),
    }


def execute_task(job: JobRecord, task_id: str, params: dict[str, Any]) -> None:
    """根据 task_id 执行并写入 job.result。"""
    runners = {
        "update.all": _run_update_all,
        "update.stock_basic": _run_update_stock_basic,
        "update.stock_pool": _run_update_stock_pool,
        "update.kline": _run_update_kline,
        "update.financial": _run_update_financial,
        "update.valuation": _run_update_valuation,
        "update.market": _run_update_market,
        "feature": _run_feature,
        "quality": _run_quality,
        "select": _run_select,
        "report": _run_report,
        "pipeline": _run_pipeline,
        "pattern.scan": _run_pattern_scan,
        "similarity.refresh": _run_similarity_refresh,
        "relationship.build": _run_similarity_refresh,
        "cluster.build": _run_cluster_build,
        "cache.clear": _run_cache_clear,
        "cache.rebuild": _run_cache_rebuild,
        "init_db": _run_init_db,
    }
    fn = runners.get(task_id)
    if fn is None:
        raise ValueError(f"未实现的任务: {task_id}")
    fn(job, params)


def _run_update_all(job: JobRecord, params: dict[str, Any]) -> None:
    from quant_system.config.settings import get_settings
    from quant_system.data.data_update import run_update_all
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope

    d = _parse_date(params.get("trade_date"))
    full = _bool(params.get("full"))
    job.message = f"update all → {d.isoformat()} full={full}"
    job.progress = 0.05
    p = _providers()
    with session_scope() as session:
        repos = build_repositories(session)
        report = run_update_all(
            stock_provider=p["stock"],
            financial_provider=p["financial"],
            index_provider=p["index"],
            sentiment_provider=p["sentiment"],
            repos=repos,
            settings=get_settings(),
            target_date=d,
            full=full,
        )
    job.progress = 1.0
    job.message = "update all done"
    job.result = _stats_dict(report)


def _run_update_stock_basic(job: JobRecord, params: dict[str, Any]) -> None:
    from quant_system.data.data_update import StockBasicUpdater
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope

    d = _parse_date(params.get("trade_date"))
    full = _bool(params.get("full"))
    job.message = f"update stock-basic → {d}"
    job.progress = 0.1
    with session_scope() as session:
        repos = build_repositories(session)
        stats = StockBasicUpdater(_providers()["stock"], repos).run(d, full=full)
    job.progress = 1.0
    job.message = "done"
    job.result = _stats_dict(stats)


def _run_update_stock_pool(job: JobRecord, params: dict[str, Any]) -> None:
    from quant_system.data.data_update import StockPoolUpdater
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope

    d = _parse_date(params.get("trade_date"))
    full = _bool(params.get("full"))
    pool = (params.get("pool") or None) or None
    if isinstance(pool, str) and not pool.strip():
        pool = None
    job.message = f"update stock-pool → {d}"
    job.progress = 0.1
    with session_scope() as session:
        repos = build_repositories(session)
        stats = StockPoolUpdater(_providers()["stock"], repos).run(
            d, full=full, pool=pool
        )
    job.progress = 1.0
    job.message = "done"
    job.result = _stats_dict(stats)


def _run_update_kline(job: JobRecord, params: dict[str, Any]) -> None:
    from quant_system.data.data_update import KlineUpdater
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope

    d = _parse_date(params.get("trade_date"))
    full = _bool(params.get("full"))
    dry_run = _bool(params.get("dry_run"))
    pool = params.get("pool") or None
    if isinstance(pool, str) and not pool.strip():
        pool = None
    codes = _parse_codes(params.get("codes"))
    job.message = f"update kline → {d}"
    job.progress = 0.1
    with session_scope() as session:
        repos = build_repositories(session)
        stats = KlineUpdater(_providers()["stock"], repos).run(
            d, full=full, pool=pool, codes=codes, dry_run=dry_run
        )
    job.progress = 1.0
    job.message = "done"
    job.result = _stats_dict(stats)


def _run_update_financial(job: JobRecord, params: dict[str, Any]) -> None:
    from quant_system.data.data_update import FinancialUpdater
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope

    d = _parse_date(params.get("trade_date"))
    full = _bool(params.get("full"))
    pool = params.get("pool") or None
    if isinstance(pool, str) and not pool.strip():
        pool = None
    codes = _parse_codes(params.get("codes"))
    job.message = f"update financial → {d}"
    job.progress = 0.1
    with session_scope() as session:
        repos = build_repositories(session)
        stats = FinancialUpdater(_providers()["financial"], repos).run(
            d, full=full, pool=pool, codes=codes
        )
    job.progress = 1.0
    job.message = "done"
    job.result = _stats_dict(stats)


def _run_update_valuation(job: JobRecord, params: dict[str, Any]) -> None:
    from quant_system.data.data_update import ValuationUpdater
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope

    d = _parse_date(params.get("trade_date"))
    full = _bool(params.get("full"))
    pool = params.get("pool") or None
    if isinstance(pool, str) and not pool.strip():
        pool = None
    codes = _parse_codes(params.get("codes"))
    job.message = f"update valuation → {d}"
    job.progress = 0.1
    with session_scope() as session:
        repos = build_repositories(session)
        stats = ValuationUpdater(_providers()["financial"], repos).run(
            d, full=full, pool=pool, codes=codes
        )
    job.progress = 1.0
    job.message = "done"
    job.result = _stats_dict(stats)


def _run_update_market(job: JobRecord, params: dict[str, Any]) -> None:
    from quant_system.data.data_update import MarketUpdater
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope

    d = _parse_date(params.get("trade_date"))
    full = _bool(params.get("full"))
    backfill = _bool(params.get("backfill"))
    job.message = f"update market → {d} backfill={backfill}"
    job.progress = 0.1
    p = _providers()
    with session_scope() as session:
        repos = build_repositories(session)
        stats = MarketUpdater(p["index"], p["sentiment"], repos).run(
            d, full=full, backfill=backfill
        )
    job.progress = 1.0
    job.message = "done"
    job.result = _stats_dict(stats)


def _run_feature(job: JobRecord, params: dict[str, Any]) -> None:
    from quant_system.config.settings import get_settings
    from quant_system.data.data_update import _filter_by_fetch_boards
    from quant_system.data.repository import build_repositories
    from quant_system.feature_store.builder import build_features_for_date
    from quant_system.infra.db import session_scope

    d = _parse_date(params.get("trade_date"))
    codes_list = _parse_codes(params.get("codes"))
    job.message = f"feature → {d}"
    job.progress = 0.1
    with session_scope() as session:
        repos = build_repositories(session)
        settings = get_settings()
        if codes_list:
            target_codes = codes_list
        else:
            pool_code = (params.get("pool") or "").upper() or None
            if pool_code is None:
                pool_code = settings.stock_pool.pool.value
            pool_code_db = "CUSTOM_DEFAULT" if pool_code == "CUSTOM" else pool_code
            target_codes = repos.stock.list_pool_members(pool_code_db)
            target_codes = _filter_by_fetch_boards(target_codes, settings)
        if not target_codes:
            raise RuntimeError("股票范围为空，请先跑 update stock-basic + stock-pool")
        job.message = f"feature → {d} ({len(target_codes)} 只)"
        job.progress = 0.2
        features, failed = build_features_for_date(target_codes, d, repos)
        inserted = repos.feature.upsert_features(features)
    job.progress = 1.0
    job.message = "feature done"
    job.result = {
        "trade_date": d.isoformat(),
        "processed": len(target_codes),
        "built": len(features),
        "failed": len(failed),
        "inserted": inserted,
        "failed_samples": failed[:5],
    }


def _run_quality(job: JobRecord, params: dict[str, Any]) -> None:
    from quant_system.data.repository import build_repositories
    from quant_system.data_quality.checker import run_checks
    from quant_system.infra.db import session_scope

    d = _parse_date(params.get("trade_date"))
    job.message = f"quality → {d}"
    job.progress = 0.2
    with session_scope() as session:
        repos = build_repositories(session)
        summary = run_checks(d, repos)
    job.progress = 1.0
    job.message = "quality done"
    job.result = {
        "trade_date": d.isoformat(),
        "error_count": summary.error_count,
        "warn_count": summary.warn_count,
        "info_count": summary.info_count,
        "checks_added": summary.checks_added,
    }


def _run_select(job: JobRecord, params: dict[str, Any]) -> None:
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope
    from quant_system.strategy.stock_selector import run_selector

    d = _parse_date(params.get("trade_date"))
    top_n = params.get("top_n")
    if top_n is not None and top_n != "":
        top_n = int(top_n)
    else:
        top_n = None
    job.message = f"select → {d}"
    job.progress = 0.2
    with session_scope() as session:
        repos = build_repositories(session)
        report = run_selector(d, repos, top_n=top_n)
        summary = report.summary() if hasattr(report, "summary") else {}
    job.progress = 1.0
    job.message = "select done"
    job.result = {
        "trade_date": d.isoformat(),
        "hit_count": getattr(report, "hit_count", None),
        "top_n": len(getattr(report, "top_stocks", []) or []),
        "summary": summary,
    }


def _run_report(job: JobRecord, params: dict[str, Any]) -> None:
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope
    from quant_system.report.daily_report import generate_report
    from quant_system.strategy.stock_selector import run_selector

    d = _parse_date(params.get("trade_date"))
    job.message = f"report → {d}"
    job.progress = 0.15
    with session_scope() as session:
        repos = build_repositories(session)
        selection = run_selector(d, repos)
        job.progress = 0.6
        out = generate_report(selection, repos)
    job.progress = 1.0
    job.message = "report done"
    job.result = {
        "trade_date": d.isoformat(),
        "md_path": str(out.md_path) if out.md_path else None,
        "html_path": str(out.html_path) if out.html_path else None,
        "item_count": out.item_count,
    }


def _run_pipeline(job: JobRecord, params: dict[str, Any]) -> None:
    from quant_system.config.settings import get_settings
    from quant_system.data.data_update import _filter_by_fetch_boards, run_update_all
    from quant_system.data.repository import build_repositories
    from quant_system.data_quality.checker import run_checks
    from quant_system.feature_store.builder import build_features_for_date
    from quant_system.infra.db import session_scope
    from quant_system.report.daily_report import generate_report
    from quant_system.strategy.stock_selector import run_selector

    d = _parse_date(params.get("trade_date"))
    skip_update = _bool(params.get("skip_update"))
    settings = get_settings()
    result: dict[str, Any] = {"trade_date": d.isoformat(), "steps": {}}

    with session_scope() as session:
        repos = build_repositories(session)
        if not skip_update:
            job.message = "pipeline 1/5 update"
            job.progress = 0.1
            p = _providers()
            try:
                report = run_update_all(
                    stock_provider=p["stock"],
                    financial_provider=p["financial"],
                    index_provider=p["index"],
                    sentiment_provider=p["sentiment"],
                    repos=repos,
                    settings=settings,
                    target_date=d,
                    full=False,
                )
                result["steps"]["update"] = _stats_dict(report)
            except Exception as exc:  # noqa: BLE001
                result["steps"]["update"] = {"error": str(exc), "continued": True}
        else:
            result["steps"]["update"] = {"skipped": True}

        job.message = "pipeline 2/5 feature"
        job.progress = 0.35
        pool_code_db = settings.stock_pool.pool.value
        pool_code_db = "CUSTOM_DEFAULT" if pool_code_db == "CUSTOM" else pool_code_db
        codes = repos.stock.list_pool_members(pool_code_db)
        codes = _filter_by_fetch_boards(codes, settings)
        features, failed = build_features_for_date(codes, d, repos)
        inserted = repos.feature.upsert_features(features)
        result["steps"]["feature"] = {
            "built": len(features),
            "failed": len(failed),
            "inserted": inserted,
        }

        job.message = "pipeline 3/5 quality"
        job.progress = 0.55
        summary = run_checks(d, repos)
        result["steps"]["quality"] = {
            "error_count": summary.error_count,
            "warn_count": summary.warn_count,
            "info_count": summary.info_count,
        }

        job.message = "pipeline 4/5 select"
        job.progress = 0.7
        selection = run_selector(d, repos, settings)
        result["steps"]["select"] = {
            "hit_count": selection.hit_count,
            "top_n": len(selection.top_stocks),
        }

        job.message = "pipeline 5/5 report"
        job.progress = 0.85
        out = generate_report(selection, repos, settings)
        result["steps"]["report"] = {
            "md_path": str(out.md_path) if out.md_path else None,
            "html_path": str(out.html_path) if out.html_path else None,
            "item_count": out.item_count,
        }

    job.progress = 1.0
    job.message = "pipeline done"
    job.result = result


def _run_pattern_scan(job: JobRecord, params: dict[str, Any]) -> None:
    from quant_system.api.jobs.runner import run_pattern_scan_job

    d = _parse_date(params.get("trade_date"))
    ids = _parse_codes(params.get("pattern_ids"))
    force = _bool(params.get("force"))
    run_pattern_scan_job(job, trade_date=d, pattern_ids=ids, force=force)


def _run_similarity_refresh(job: JobRecord, params: dict[str, Any]) -> None:
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope
    from quant_system.similarity.service import refresh_similarity

    d = _parse_date(params.get("trade_date"))
    wins = _parse_windows(params.get("windows") or "60,250")

    pool = params.get("pool") or None
    if isinstance(pool, str) and not pool.strip():
        pool = None
    threshold = float(params.get("threshold") if params.get("threshold") not in (None, "") else 0.3)
    min_sample = int(params.get("min_sample") if params.get("min_sample") not in (None, "") else 120)
    max_neighbors = int(
        params.get("max_neighbors") if params.get("max_neighbors") not in (None, "") else 200
    )
    dry_run = _bool(params.get("dry_run"))
    force = _bool(params.get("force"))
    with_cluster = _bool(params.get("with_cluster"), default=True)
    cluster_w_min = float(
        params.get("cluster_w_min") if params.get("cluster_w_min") not in (None, "") else 0.45
    )
    cluster_conf_min = float(
        params.get("cluster_conf_min")
        if params.get("cluster_conf_min") not in (None, "")
        else 0.5
    )
    pipeline_recipe = str(
        params.get("pipeline_recipe")
        if params.get("pipeline_recipe") not in (None, "")
        else "return_cfr_auto_v1"
    )

    job.message = f"similarity refresh → {d} cluster={with_cluster} recipe={pipeline_recipe}"
    job.progress = 0.1
    with session_scope() as session:
        repos = build_repositories(session)
        report = refresh_similarity(
            repos,
            session,
            calc_date=d,
            windows=wins,
            pool_code=pool,
            min_sample=min_sample,
            value_threshold=threshold,
            max_neighbors=max_neighbors,
            dry_run=dry_run,
            force=force,
            with_cluster=with_cluster,
            cluster_w_min=cluster_w_min,
            cluster_conf_min=cluster_conf_min,
            pipeline_recipe=pipeline_recipe,
        )
    job.progress = 1.0
    job.message = "similarity refresh done"
    job.result = report.to_dict()
    if report.error:
        raise RuntimeError(report.error)
    return


def _run_cluster_build(job: JobRecord, params: dict[str, Any]) -> None:
    from quant_system.infra.db import session_scope
    from quant_system.similarity.service import build_cluster_only

    profile_id = str(params.get("profile_id") or "pearson_w60")
    window = str(params.get("window") or "W60").upper()
    if not window.startswith("W"):
        window = f"W{window}"
    w_min = float(
        params.get("cluster_w_min") if params.get("cluster_w_min") not in (None, "") else 0.45
    )
    conf_min = float(
        params.get("cluster_conf_min")
        if params.get("cluster_conf_min") not in (None, "")
        else 0.5
    )
    job.message = f"cluster build → {profile_id} {window}"
    job.progress = 0.2
    with session_scope() as session:
        report = build_cluster_only(
            session,
            profile_id=profile_id,
            window=window,
            w_min=w_min,
            conf_min=conf_min,
        )
    job.progress = 1.0
    job.message = f"cluster {report.status}"
    job.result = {
        "run_id": report.run_id,
        "profile_id": report.profile_id,
        "status": report.status,
        "n_clusters": report.n_clusters,
        "edge_used": report.edge_used,
        "modularity": report.modularity,
        "resolution": report.resolution,
        "duration_ms": report.duration_ms,
        "error": report.error,
    }
    if report.status == "FAILED":
        raise RuntimeError(report.error or "cluster failed")
    return


def _run_cache_clear(job: JobRecord, params: dict[str, Any]) -> None:
    from quant_system.infra.cache import clear_namespace

    ns = params.get("namespace") or None
    if isinstance(ns, str) and not ns.strip():
        ns = None
    job.message = f"cache clear namespace={ns or 'ALL'}"
    job.progress = 0.3
    stats = clear_namespace(ns)
    job.progress = 1.0
    job.message = "cache cleared"
    job.result = {"cleared": stats}


def _run_cache_rebuild(job: JobRecord, params: dict[str, Any]) -> None:
    from quant_system.infra import trading_calendar as tc
    from quant_system.infra.cache import clear_namespace

    job.message = "cache rebuild"
    job.progress = 0.2
    cleared = clear_namespace()
    job.progress = 0.6
    n = tc.refresh()
    job.progress = 1.0
    job.message = "cache rebuild done"
    job.result = {"cleared": cleared, "trading_days": n}


def _run_init_db(job: JobRecord, params: dict[str, Any]) -> None:
    from quant_system.database.migrations import check_schema_integrity, init_db
    from quant_system.database.models import ALL_MODELS

    drop_first = _bool(params.get("drop_first"))
    job.message = f"init-db drop_first={drop_first}"
    job.progress = 0.2
    init_db(drop_first=drop_first)
    job.progress = 0.8
    ok, missing = check_schema_integrity()
    job.progress = 1.0
    job.message = "init-db done" if ok else "init-db incomplete"
    job.result = {
        "ok": ok,
        "missing": missing,
        "table_count": len(ALL_MODELS),
        "drop_first": drop_first,
    }
