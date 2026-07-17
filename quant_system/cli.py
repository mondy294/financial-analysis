"""命令行入口（Typer）。

命令一览：
  qs init-db
  qs update stock-basic|stock-pool|kline|financial|market|all
  qs feature [--date]
  qs quality [--date]
  qs select [--date]
  qs report [--date]
  qs pipeline [--date]
  qs backtest --config path.toml
  qs benchmark [--strategy --days]
  qs doctor
  qs schedule
  qs pool list|show <code>
  qs signal stats
  qs cache stats|clear
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="qs",
    help="个人 A 股量化分析系统 CLI",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)

update_app = typer.Typer(help="数据更新（子命令）")
pool_app = typer.Typer(help="股票池管理")
signal_app = typer.Typer(help="策略信号查询")
cache_app = typer.Typer(help="缓存管理")
relationship_app = typer.Typer(help="股票关系层（相关度/联动）")
similarity_app = typer.Typer(help="Similarity Framework（边+聚类编排）")
abnormal_app = typer.Typer(help="异动 Pattern Engine（分模式检测）")

app.add_typer(update_app, name="update")
app.add_typer(pool_app, name="pool")
app.add_typer(signal_app, name="signal")
app.add_typer(cache_app, name="cache")
app.add_typer(relationship_app, name="relationship")
app.add_typer(similarity_app, name="similarity")
app.add_typer(abnormal_app, name="abnormal")

console = Console()


# ============================================================================
# 辅助
# ============================================================================

def _parse_date(s: Optional[str]) -> date:
    """解析 --date；None 时返回最近交易日。"""
    if s:
        return datetime.strptime(s, "%Y-%m-%d").date()
    from quant_system.infra import trading_calendar as tc
    return tc.latest_trading_day()


def _parse_codes(s: Optional[str]) -> Optional[list[str]]:
    if not s:
        return None
    return [c.strip() for c in s.split(",") if c.strip()]


def _boot():
    """通用启动：初始化日志。"""
    from quant_system.infra.logger import setup_logging
    setup_logging()


# ============================================================================
# 顶层
# ============================================================================

@app.command("serve")
def serve_cmd(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8000,
    reload: Annotated[
        bool,
        typer.Option("--reload/--no-reload", help="后端热重载（改 quant_system/*.py 自动重启）"),
    ] = False,
    frontend: Annotated[
        bool,
        typer.Option("--frontend/--no-frontend", help="同时启动 Vite 前端（HMR，默认 :5173）"),
    ] = False,
    dev: Annotated[
        bool,
        typer.Option("--dev", help="开发模式：等价于 --reload --frontend"),
    ] = False,
    vite_port: Annotated[int, typer.Option("--vite-port", help="Vite 开发服务器端口")] = 5173,
) -> None:
    """启动 Web Console（FastAPI）。开发请用 `qs serve --dev`（后端 reload + 前端 HMR）。"""
    import atexit
    import os
    import shutil
    import signal
    import subprocess
    from pathlib import Path

    _boot()
    try:
        import uvicorn
    except ImportError as exc:
        console.print("[red]缺少 uvicorn/fastapi，请执行: pip install -e '.[api]'[/red]")
        raise typer.Exit(code=1) from exc

    if dev:
        reload = True
        frontend = True

    root = Path(__file__).resolve().parents[1]
    pkg_dir = Path(__file__).resolve().parent
    web_dir = root / "web"
    vite_proc: subprocess.Popen | None = None

    if frontend:
        if not (web_dir / "package.json").exists():
            console.print(f"[red]未找到前端目录: {web_dir}[/red]")
            raise typer.Exit(code=1)
        npm = shutil.which("npm")
        if not npm:
            console.print("[red]未找到 npm，无法启动前端 HMR[/red]")
            raise typer.Exit(code=1)
        if not (web_dir / "node_modules").exists():
            console.print("[yellow]web/node_modules 不存在，正在 npm install…[/yellow]")
            subprocess.run([npm, "install"], cwd=web_dir, check=True)

        # 开发时不要挂载旧的 web/dist，避免和 Vite 混淆
        os.environ["QS_SERVE_MOUNT_FRONTEND"] = "0"
        env = os.environ.copy()
        env["VITE_API_PROXY"] = f"http://{host}:{port}"
        vite_proc = subprocess.Popen(
            [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", str(vite_port)],
            cwd=web_dir,
            env=env,
        )

        def _stop_vite() -> None:
            if vite_proc is None or vite_proc.poll() is not None:
                return
            vite_proc.send_signal(signal.SIGTERM)
            try:
                vite_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                vite_proc.kill()

        atexit.register(_stop_vite)

    console.print(f"[bold]API[/bold]      → http://{host}:{port}")
    console.print(f"API docs  → http://{host}:{port}/api/docs")
    if frontend:
        console.print(f"[bold]前端 HMR[/bold] → http://127.0.0.1:{vite_port}  （请用这个地址开发）")
    elif (web_dir / "dist" / "index.html").exists():
        console.print(f"[bold]静态 UI[/bold] → http://{host}:{port}  （无 HMR，改前端请用 --dev）")
    if reload:
        console.print("[dim]后端热重载已开启：监听 quant_system/[/dim]")

    try:
        uvicorn.run(
            "quant_system.api.app:create_app",
            factory=True,
            host=host,
            port=port,
            reload=reload,
            reload_dirs=[str(pkg_dir)] if reload else None,
            reload_includes=["*.py"] if reload else None,
        )
    finally:
        if vite_proc is not None:
            if vite_proc.poll() is None:
                vite_proc.send_signal(signal.SIGTERM)
                try:
                    vite_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    vite_proc.kill()


@app.command("init-db")
def init_db_cmd(
    drop_first: Annotated[bool, typer.Option("--drop-first")] = False,
) -> None:
    """初始化数据库表结构。"""
    from quant_system.database.migrations import check_schema_integrity, init_db
    _boot()
    if drop_first:
        typer.confirm("⚠️  将删除所有现有表！确认继续？", abort=True)
    init_db(drop_first=drop_first)
    ok, missing = check_schema_integrity()
    if ok:
        from quant_system.database.models import ALL_MODELS
        console.print(f"[green]✓ 数据库初始化完成，{len(ALL_MODELS)} 张表齐全[/green]")
    else:
        console.print(f"[red]✗ 缺失表: {missing}[/red]")
        raise typer.Exit(code=1)


@app.command()
def doctor() -> None:
    """数据完整性 + 数据库健康检查。"""
    from quant_system.config.settings import get_settings
    from quant_system.database.migrations import check_schema_integrity
    from quant_system.infra.db import get_engine

    _boot()
    settings = get_settings()

    table = Table(title="quant_system doctor 检查报告")
    table.add_column("检查项", style="cyan")
    table.add_column("状态", style="green")
    table.add_column("详情")

    table.add_row("Env", "✓", settings.env.value)
    table.add_row("DB URL", "✓", settings.database.url)
    table.add_row("Stock Pool", "✓", settings.stock_pool.pool.value)
    table.add_row("Board Filter", "✓", settings.board_filter)
    table.add_row("Kline 起始日", "✓", settings.data.kline_start_date)
    table.add_row("Feature Version", "✓", settings.feature.version)
    table.add_row("Signal Record Level", "✓", settings.signal.record_level.value)
    table.add_row("DQ Filter Level", "✓", settings.data_quality.filter_level.value)

    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        table.add_row("DB 连接", "✓", f"dialect={engine.dialect.name}")
    except Exception as e:
        table.add_row("DB 连接", "✗", str(e))
        console.print(table)
        raise typer.Exit(code=1) from e

    ok, missing = check_schema_integrity()
    if ok:
        from quant_system.database.models import ALL_MODELS
        table.add_row("Schema 完整性", "✓", f"{len(ALL_MODELS)} 张表齐全")
    else:
        table.add_row("Schema 完整性", "✗", f"缺失: {missing}")

    console.print(table)
    if not ok:
        raise typer.Exit(code=1)


# ============================================================================
# update 子命令组
# ============================================================================

def _run_updater(runner_fn, job_desc: str) -> None:
    """通用编排：起 session → 依赖注入 → 跑 runner → 打印统计。"""
    from quant_system.data.data_update import UpdateStats
    from quant_system.data.provider_factory import (
        get_financial_provider,
        get_index_provider,
        get_sentiment_provider,
        get_stock_provider,
    )
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope

    _boot()
    console.print(f"[bold cyan]▶ {job_desc}[/bold cyan]")

    with session_scope() as session:
        repos = build_repositories(session)
        providers = {
            "stock": get_stock_provider(),
            "financial": get_financial_provider(),
            "index": get_index_provider(),
            "sentiment": get_sentiment_provider(),
        }
        result = runner_fn(providers, repos)

    _print_update_result(result)


def _print_update_result(result) -> None:
    from quant_system.data.data_update import UpdateAllReport, UpdateStats

    if isinstance(result, UpdateAllReport):
        table = Table(title="update all 汇总")
        table.add_column("步骤")
        table.add_column("processed", justify="right")
        table.add_column("inserted", justify="right")
        table.add_column("skipped", justify="right")
        table.add_column("errors", justify="right", style="red")
        for name, p, i, s, e in result.summary_rows():
            table.add_row(name, str(p), str(i), str(s), str(e))
        console.print(table)
    elif isinstance(result, UpdateStats):
        console.print(
            f"[green]✓[/green] {result.job_name} "
            f"processed={result.processed} inserted={result.inserted} "
            f"skipped={result.skipped} [red]errors={result.errors}[/red]"
        )
        if result.error_samples:
            console.print("[yellow]错误样本:[/yellow]")
            for s in result.error_samples:
                console.print(f"  - {s}")


@update_app.command("stock-basic")
def update_stock_basic_cmd(
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
    full: Annotated[bool, typer.Option("--full")] = False,
) -> None:
    """更新股票基础信息表 stock_basic。"""
    d = _parse_date(trade_date)
    from quant_system.data.data_update import StockBasicUpdater
    _run_updater(
        lambda p, r: StockBasicUpdater(p["stock"], r).run(d, full=full),
        f"update stock-basic → {d}",
    )


@update_app.command("stock-pool")
def update_stock_pool_cmd(
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
    full: Annotated[bool, typer.Option("--full")] = False,
    pool: Annotated[Optional[str], typer.Option("--pool")] = None,
) -> None:
    """更新股票池成分股（默认根据 QS_STOCK_POOL__POOL 配置）。"""
    d = _parse_date(trade_date)
    from quant_system.data.data_update import StockPoolUpdater
    _run_updater(
        lambda p, r: StockPoolUpdater(p["stock"], r).run(d, full=full, pool=pool),
        f"update stock-pool → {d} pool={pool or 'auto'}",
    )


@update_app.command("kline")
def update_kline_cmd(
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
    full: Annotated[bool, typer.Option("--full")] = False,
    pool: Annotated[Optional[str], typer.Option("--pool")] = None,
    codes: Annotated[Optional[str], typer.Option("--codes", help="逗号分隔")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """更新日 K 线 daily_kline（增量）。"""
    d = _parse_date(trade_date)
    from quant_system.data.data_update import KlineUpdater
    codes_list = _parse_codes(codes)
    _run_updater(
        lambda p, r: KlineUpdater(p["stock"], r).run(
            d, full=full, pool=pool, codes=codes_list, dry_run=dry_run,
        ),
        f"update kline → {d}",
    )


@update_app.command("financial")
def update_financial_cmd(
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
    full: Annotated[bool, typer.Option("--full")] = False,
    pool: Annotated[Optional[str], typer.Option("--pool")] = None,
    codes: Annotated[Optional[str], typer.Option("--codes")] = None,
) -> None:
    """更新财务快照 financial_snapshot。"""
    d = _parse_date(trade_date)
    from quant_system.data.data_update import FinancialUpdater
    codes_list = _parse_codes(codes)
    _run_updater(
        lambda p, r: FinancialUpdater(p["financial"], r).run(
            d, full=full, pool=pool, codes=codes_list,
        ),
        f"update financial → {d}",
    )


@update_app.command("valuation")
def update_valuation_cmd(
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
    full: Annotated[bool, typer.Option("--full")] = False,
    pool: Annotated[Optional[str], typer.Option("--pool")] = None,
    codes: Annotated[Optional[str], typer.Option("--codes")] = None,
) -> None:
    """更新日频估值 daily_valuation（PE/PB/市值，东财为主、百度兜底）。"""
    d = _parse_date(trade_date)
    from quant_system.data.data_update import ValuationUpdater
    codes_list = _parse_codes(codes)
    _run_updater(
        lambda p, r: ValuationUpdater(p["financial"], r).run(
            d, full=full, pool=pool, codes=codes_list,
        ),
        f"update valuation → {d}",
    )


@update_app.command("market")
def update_market_cmd(
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
    full: Annotated[bool, typer.Option("--full")] = False,
    backfill: Annotated[bool, typer.Option("--backfill", help="回填历史市场情绪")] = False,
) -> None:
    """更新指数日线 + 市场情绪。默认只拉当日快照，加 --backfill 回填历史。"""
    d = _parse_date(trade_date)
    from quant_system.data.data_update import MarketUpdater
    _run_updater(
        lambda p, r: MarketUpdater(p["index"], p["sentiment"], r).run(
            d, full=full, backfill=backfill,
        ),
        f"update market → {d} backfill={backfill}",
    )


@update_app.command("all")
def update_all_cmd(
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
    full: Annotated[bool, typer.Option("--full")] = False,
) -> None:
    """按依赖顺序全跑：basic → pool → kline → financial → market(仅快照)。"""
    d = _parse_date(trade_date)
    from quant_system.config.settings import get_settings
    from quant_system.data.data_update import run_update_all
    _run_updater(
        lambda p, r: run_update_all(
            stock_provider=p["stock"],
            financial_provider=p["financial"],
            index_provider=p["index"],
            sentiment_provider=p["sentiment"],
            repos=r,
            settings=get_settings(),
            target_date=d,
            full=full,
        ),
        f"update all → {d} full={full}",
    )


# ============================================================================
# cache 子命令组
# ============================================================================

@cache_app.command("stats")
def cache_stats_cmd() -> None:
    """查看缓存条数和体积。"""
    from quant_system.infra.cache import cache_stats
    _boot()
    stats = cache_stats()
    if not stats:
        console.print("(缓存目录为空)")
        return
    table = Table(title="缓存统计")
    table.add_column("namespace")
    table.add_column("条数", justify="right")
    table.add_column("大小(MB)", justify="right")
    for ns, info in sorted(stats.items()):
        table.add_row(
            ns, str(info.get("count", 0)),
            f"{info.get('volume_bytes', 0) / 1024 / 1024:.2f}",
        )
    console.print(table)


@cache_app.command("clear")
def cache_clear_cmd(
    namespace: Annotated[Optional[str], typer.Option("--namespace")] = None,
) -> None:
    """清空缓存。--namespace=akshare 只清 akshare；不指定清全部。"""
    from quant_system.infra.cache import clear_namespace
    _boot()
    stats = clear_namespace(namespace)
    for ns, cnt in stats.items():
        console.print(f"[green]✓[/green] {ns}: 清除 {cnt} 条")


@cache_app.command("rebuild")
def cache_rebuild_cmd() -> None:
    """清空并触发交易日历重建。"""
    from quant_system.infra import trading_calendar as tc
    from quant_system.infra.cache import clear_namespace

    _boot()
    stats = clear_namespace()
    for ns, cnt in stats.items():
        console.print(f"清空 {ns}: {cnt} 条")
    n = tc.refresh()
    console.print(f"[green]✓[/green] 交易日历重建完成: {n} 个交易日")


# ============================================================================
# 其它命令（占位）
# ============================================================================

@app.command()
def feature(
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
    codes: Annotated[Optional[str], typer.Option("--codes")] = None,
    pool: Annotated[Optional[str], typer.Option("--pool", help="覆盖默认股票池")] = None,
) -> None:
    """计算并落地某个交易日的 daily_feature（HS300 池全员，数据层不做板块过滤）。"""
    from quant_system.data.repository import build_repositories
    from quant_system.feature_store.builder import build_features_for_date
    from quant_system.infra.db import session_scope

    _boot()
    d = _parse_date(trade_date)
    codes_list = _parse_codes(codes)

    with session_scope() as session:
        repos = build_repositories(session)

        # 决定股票范围
        if codes_list:
            # 用户显式 --codes：尊重用户意愿，不做 fetch_boards 过滤
            target_codes = codes_list
        else:
            from quant_system.config.settings import get_settings
            from quant_system.data.data_update import _filter_by_fetch_boards
            settings = get_settings()
            pool_code = (pool or "").upper() or None
            if pool_code is None:
                pool_code = settings.stock_pool.pool.value
            pool_code_db = "CUSTOM_DEFAULT" if pool_code == "CUSTOM" else pool_code
            target_codes = repos.stock.list_pool_members(pool_code_db)
            # 与 kline/financial 拉取阶段一致：默认只算主板特征，避免为无 K 线的股票白跑
            target_codes = _filter_by_fetch_boards(target_codes, settings)

        if not target_codes:
            console.print("[red]股票范围为空，请先跑 update stock-basic + stock-pool[/red]")
            raise typer.Exit(code=1)

        console.print(f"[bold cyan]▶ feature → {d}  ({len(target_codes)} 只股票)[/bold cyan]")

        # 起 job log
        job_id = repos.job_log.start_job("feature.build", d)
        try:
            features, failed = build_features_for_date(target_codes, d, repos)
            inserted = repos.feature.upsert_features(features)
            stats = {
                "processed": len(target_codes),
                "built": len(features),
                "failed": len(failed),
                "inserted": inserted,
                "failed_samples": failed[:5],
            }
            repos.job_log.finish_job(job_id, "SUCCESS", stats=stats)
            console.print(
                f"[green]✓[/green] 特征生成: 输入={len(target_codes)} "
                f"成功={len(features)} 失败={len(failed)} inserted={inserted}"
            )
            if failed:
                console.print(f"[yellow]失败样本[/yellow]: {failed[:5]}")
        except Exception as e:
            repos.job_log.finish_job(job_id, "FAILED", error=str(e))
            raise


@app.command()
def quality(
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
) -> None:
    """数据质量检查。结果写 data_quality_check，selector 可前置过滤 ERROR 级。"""
    from quant_system.data.repository import build_repositories
    from quant_system.data_quality.checker import run_checks
    from quant_system.infra.db import session_scope

    _boot()
    d = _parse_date(trade_date)

    with session_scope() as session:
        repos = build_repositories(session)
        console.print(f"[bold cyan]▶ quality checks → {d}[/bold cyan]")
        summary = run_checks(d, repos)

    table = Table(title=f"quality {d}")
    table.add_column("级别")
    table.add_column("数量", justify="right")
    table.add_row("[red]ERROR[/red]", str(summary.error_count))
    table.add_row("[yellow]WARN[/yellow]", str(summary.warn_count))
    table.add_row("[cyan]INFO[/cyan]", str(summary.info_count))
    table.add_row("总计", str(summary.checks_added))
    console.print(table)


@app.command()
def select(
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
    top_n: Annotated[Optional[int], typer.Option("--top-n")] = None,
) -> None:
    """跑策略 → 综合评分 → 写 strategy_signal 表。"""
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope
    from quant_system.strategy.stock_selector import run_selector

    _boot()
    d = _parse_date(trade_date)

    with session_scope() as session:
        repos = build_repositories(session)
        console.print(f"[bold cyan]▶ select → {d}[/bold cyan]")
        job_id = repos.job_log.start_job("select", d)
        try:
            report_obj = run_selector(d, repos, top_n=top_n)
            repos.job_log.finish_job(job_id, "SUCCESS", stats=report_obj.summary())
        except Exception as e:
            repos.job_log.finish_job(job_id, "FAILED", error=str(e))
            raise

    # 展示（附带股票名称）
    with session_scope() as _s2:
        _repos2 = build_repositories(_s2)
        codes_in_top = [s.code for s in report_obj.top_stocks]
        name_map: dict[str, str] = {}
        if codes_in_top:
            from sqlalchemy import select as _sel

            from quant_system.database.models import StockBasic
            rows = _s2.execute(
                _sel(StockBasic.code, StockBasic.name).where(
                    StockBasic.code.in_(codes_in_top)
                )
            ).all()
            name_map = {c: n for c, n in rows}

    table = Table(title=f"选股结果 · {d}（regime={getattr(report_obj, 'regime', 'UNKNOWN')}）")
    table.add_column("#", justify="right")
    table.add_column("code")
    table.add_column("name")
    table.add_column("score", justify="right")
    table.add_column("技术", justify="right")
    table.add_column("资金", justify="right")
    table.add_column("基本", justify="right")
    table.add_column("共振")
    table.add_column("命中策略")
    table.add_column("风险")

    for i, s in enumerate(report_obj.top_stocks, 1):
        cats = getattr(s, "resonance_categories", []) or []
        rc = getattr(s, "resonance_count", 0)
        resonance_str = f"{rc}[{'+'.join(cats)}]" if cats else "-"
        risk_flags = getattr(s, "risk_flags", []) or []
        risk_str = f"[red]⚠️ {len(risk_flags)}[/red]" if risk_flags else ""
        table.add_row(
            str(i), s.code, name_map.get(s.code, ""),
            f"{s.final_score:.2f}",
            f"{s.tech_score:.2f}", f"{s.capital_score:.2f}", f"{s.fundamental_score:.2f}",
            resonance_str,
            ",".join(s.hit_strategies),
            risk_str,
        )
    console.print(table)
    console.print(
        f"命中数 [bold]{report_obj.hit_count}[/bold]；策略分布 {report_obj.strategy_hit_stats}"
    )
    # v2：硬过滤汇总
    hard_filtered = getattr(report_obj, "hard_filtered", []) or []
    if hard_filtered:
        by_reason: dict[str, int] = {}
        for f in hard_filtered:
            by_reason[f["reason"]] = by_reason.get(f["reason"], 0) + 1
        detail = "、".join(f"{k}={v}" for k, v in sorted(by_reason.items()))
        console.print(
            f"[yellow]因风险硬过滤剔除[/yellow] [bold]{len(hard_filtered)}[/bold] 只 · {detail}"
        )


@app.command()
def report(
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
    formats: Annotated[Optional[str], typer.Option("--format", help="md,html")] = None,
) -> None:
    """基于最近一次 select 结果生成日报文件。

    如果当天没跑 select，会先自动跑一次再出报告。
    """
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope
    from quant_system.report.daily_report import generate_report
    from quant_system.strategy.stock_selector import run_selector

    _boot()
    d = _parse_date(trade_date)
    fmts = [f.strip() for f in (formats or "").split(",") if f.strip()] or None

    with session_scope() as session:
        repos = build_repositories(session)
        console.print(f"[bold cyan]▶ report → {d}[/bold cyan]")
        selection = run_selector(d, repos)
        out = generate_report(selection, repos, formats=fmts)

    if out.md_path:
        console.print(f"[green]✓[/green] Markdown: {out.md_path}")
    if out.html_path:
        console.print(f"[green]✓[/green] HTML:     {out.html_path}")
    console.print(f"共 {out.item_count} 条推荐入库（daily_report_item）")


@app.command()
def pipeline(
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
    skip_update: Annotated[bool, typer.Option("--skip-update", help="跳过数据更新")] = False,
) -> None:
    """端到端：update → feature → quality → select → report。"""
    from quant_system.config.settings import get_settings as _gs
    from quant_system.data.data_update import run_update_all
    from quant_system.data.provider_factory import (
        get_financial_provider,
        get_index_provider,
        get_sentiment_provider,
        get_stock_provider,
    )
    from quant_system.data.repository import build_repositories
    from quant_system.data_quality.checker import run_checks
    from quant_system.feature_store.builder import build_features_for_date
    from quant_system.infra.db import session_scope
    from quant_system.report.daily_report import generate_report
    from quant_system.strategy.stock_selector import run_selector

    _boot()
    d = _parse_date(trade_date)
    settings = _gs()

    console.print(f"[bold cyan]═══ pipeline → {d} ═══[/bold cyan]\n")

    with session_scope() as session:
        repos = build_repositories(session)

        # 1. update
        if not skip_update:
            console.print("[bold]▶ 1/5 update[/bold]")
            try:
                run_update_all(
                    stock_provider=get_stock_provider(),
                    financial_provider=get_financial_provider(),
                    index_provider=get_index_provider(),
                    sentiment_provider=get_sentiment_provider(),
                    repos=repos, settings=settings, target_date=d, full=False,
                )
            except Exception as e:
                console.print(f"[yellow]update 异常继续: {e}[/yellow]")
        else:
            console.print("[dim]▶ 1/5 update  (skipped)[/dim]")

        # 2. feature
        console.print("\n[bold]▶ 2/5 feature[/bold]")
        from quant_system.data.data_update import _filter_by_fetch_boards
        pool_code_db = settings.stock_pool.pool.value
        pool_code_db = "CUSTOM_DEFAULT" if pool_code_db == "CUSTOM" else pool_code_db
        codes = repos.stock.list_pool_members(pool_code_db)
        # 与拉取阶段一致：默认只算主板
        codes = _filter_by_fetch_boards(codes, settings)
        features, failed = build_features_for_date(codes, d, repos)
        repos.feature.upsert_features(features)
        console.print(f"  特征生成 {len(features)}，失败 {len(failed)}")

        # 3. quality
        console.print("\n[bold]▶ 3/5 quality[/bold]")
        summary = run_checks(d, repos)
        console.print(f"  DQ: ERROR={summary.error_count} WARN={summary.warn_count} INFO={summary.info_count}")

        # 4. select
        console.print("\n[bold]▶ 4/5 select[/bold]")
        selection = run_selector(d, repos, settings)
        console.print(f"  命中 {selection.hit_count} 只，Top {len(selection.top_stocks)}")

        # 5. report
        console.print("\n[bold]▶ 5/5 report[/bold]")
        out = generate_report(selection, repos, settings)
        if out.md_path:
            console.print(f"  [green]✓[/green] {out.md_path}")
        if out.html_path:
            console.print(f"  [green]✓[/green] {out.html_path}")

    console.print(f"\n[bold green]═══ pipeline 完成[/bold green]")


@app.command()
def backtest(
    config_path: Annotated[str, typer.Option("--config")],
) -> None:
    """跑回测。（下一步实现）"""
    console.print("[yellow]TODO: 第 7 步之后实现[/yellow]")
    raise typer.Exit(code=2)


@app.command()
def benchmark(
    strategy: Annotated[Optional[str], typer.Option("--strategy")] = None,
    lookback_days: Annotated[int, typer.Option("--days")] = 90,
) -> None:
    """策略性能测试。（下一步实现）"""
    console.print("[yellow]TODO: 第 7 步之后实现[/yellow]")
    raise typer.Exit(code=2)


@app.command()
def schedule() -> None:
    """启动调度器。（下一步实现）"""
    console.print("[yellow]TODO: 第 7 步实现[/yellow]")
    raise typer.Exit(code=2)


# ============================================================================
# pool 子命令
# ============================================================================

@pool_app.command("list")
def pool_list_cmd() -> None:
    from quant_system.data.repository import list_active_stock_pools
    from quant_system.infra.db import session_scope

    _boot()
    table = Table(title="股票池")
    table.add_column("code"); table.add_column("name")
    table.add_column("type"); table.add_column("description")

    with session_scope() as session:
        for pool in list_active_stock_pools(session):
            table.add_row(pool.code, pool.name, pool.pool_type, pool.description or "")
    console.print(table)


@pool_app.command("show")
def pool_show_cmd(
    code: Annotated[str, typer.Argument()],
    limit: Annotated[int, typer.Option("--limit")] = 30,
) -> None:
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope

    _boot()
    with session_scope() as session:
        repos = build_repositories(session)
        members = repos.stock.list_pool_members(code)

    console.print(f"[bold]{code}[/bold] 当前成分数: {len(members)}")
    if members:
        show = members[:limit]
        console.print(", ".join(show) + (f" ... (+{len(members) - limit})" if len(members) > limit else ""))


# ============================================================================
# signal 子命令
# ============================================================================

@signal_app.command("stats")
def signal_stats_cmd(
    strategy: Annotated[Optional[str], typer.Option("--strategy")] = None,
    lookback_days: Annotated[int, typer.Option("--days")] = 30,
) -> None:
    console.print("[yellow]TODO: 第 6 步之后实现[/yellow]")
    raise typer.Exit(code=2)


# ============================================================================
# relationship 子命令组
# ============================================================================

def _parse_windows_arg(raw: Optional[str]) -> list[str]:
    """'60,250' 或 'W60,W250' → ['W60','W250']。None → 默认。"""
    from quant_system.relationship.service import DEFAULT_WINDOWS
    if not raw:
        return list(DEFAULT_WINDOWS)
    out: list[str] = []
    for tok in raw.split(","):
        t = tok.strip().upper()
        if not t:
            continue
        out.append(t if t.startswith("W") else f"W{t}")
    return out or list(DEFAULT_WINDOWS)


@similarity_app.command("refresh")
def similarity_refresh_cmd(
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
    windows: Annotated[Optional[str], typer.Option("--windows", help="如 60,250")] = None,
    pool: Annotated[Optional[str], typer.Option("--pool")] = None,
    board_filter: Annotated[Optional[str], typer.Option("--board")] = None,
    min_sample: Annotated[int, typer.Option("--min-sample")] = 120,
    threshold: Annotated[float, typer.Option("--threshold")] = 0.3,
    max_neighbors: Annotated[int, typer.Option("--max-neighbors")] = 200,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    force: Annotated[bool, typer.Option("--force")] = False,
    no_cluster: Annotated[bool, typer.Option("--no-cluster")] = False,
    cluster_w_min: Annotated[float, typer.Option("--cluster-w-min")] = 0.45,
    cluster_conf_min: Annotated[float, typer.Option("--cluster-conf-min")] = 0.5,
    pipeline_recipe: Annotated[
        str,
        typer.Option(
            "--pipeline-recipe",
            help="16 Pipeline：return_cfr_auto_v1（默认残差）/ return_raw_v1（毛收益对照）",
        ),
    ] = "return_cfr_auto_v1",
) -> None:
    """Pearson 边 +（默认）W60/W250 聚类，一次完成。默认经公共结构剥离后再相关。"""
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope
    from quant_system.similarity.service import refresh_similarity

    _boot()
    d = _parse_date(trade_date)
    wins = _parse_windows_arg(windows)
    console.print(
        f"[bold]similarity.refresh[/bold] → {d} windows={wins} "
        f"recipe={pipeline_recipe} "
        f"cluster={'off' if no_cluster or dry_run else 'on'}"
    )
    with session_scope() as session:
        repos = build_repositories(session)
        job_id = None if dry_run else repos.job_log.start_job("similarity.refresh", d)
        try:
            report = refresh_similarity(
                repos,
                session,
                calc_date=d,
                windows=wins,
                pool_code=pool,
                board_filter=board_filter or "MAIN",
                min_sample=min_sample,
                value_threshold=threshold,
                max_neighbors=max_neighbors,
                dry_run=dry_run,
                force=force,
                with_cluster=not no_cluster,
                cluster_w_min=cluster_w_min,
                cluster_conf_min=cluster_conf_min,
                pipeline_recipe=pipeline_recipe,
            )
            if job_id is not None:
                repos.job_log.finish_job(
                    job_id,
                    "FAILED" if report.error else "SUCCESS",
                    stats=report.to_dict(),
                    error=report.error,
                )
        except Exception as e:
            if job_id is not None:
                repos.job_log.finish_job(job_id, "FAILED", error=str(e))
            raise

    if report.relationship and report.relationship.skipped:
        console.print("[yellow]关系批次已存在（跳过重算边）；聚类仍会执行[/yellow]")
    if report.relationship:
        console.print(
            f"边：宇宙 {report.relationship.universe_size} 写入 "
            f"{report.relationship.pair_written_total} 耗时 {report.relationship.duration_ms}ms"
        )
    for c in report.clusters:
        style = "green" if c.status == "SUCCESS" else "red"
        console.print(
            f"[{style}]簇 {c.profile_id}: {c.status} n={c.n_clusters} "
            f"edges={c.edge_used} Q={c.modularity:.3f} res={c.resolution:.2f} "
            f"{c.duration_ms}ms[/{style}]"
        )
        if c.error:
            console.print(f"[red]{c.error}[/red]")


@relationship_app.command("build")
def relationship_build_cmd(
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
    relation_type: Annotated[str, typer.Option("--type")] = "pearson",
    windows: Annotated[Optional[str], typer.Option("--windows", help="如 60,250")] = None,
    pool: Annotated[Optional[str], typer.Option("--pool")] = None,
    board_filter: Annotated[Optional[str], typer.Option("--board")] = None,
    min_sample: Annotated[int, typer.Option("--min-sample")] = 120,
    threshold: Annotated[float, typer.Option("--threshold")] = 0.3,
    max_neighbors: Annotated[int, typer.Option("--max-neighbors")] = 200,
    full_lookback: Annotated[int, typer.Option("--full-lookback")] = 750,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    force: Annotated[bool, typer.Option("--force")] = False,
    no_cache: Annotated[bool, typer.Option("--no-cache")] = False,
    no_cluster: Annotated[bool, typer.Option("--no-cluster")] = False,
) -> None:
    """兼容入口：默认走 similarity.refresh（边+簇）；--no-cluster 只算边。"""
    if relation_type.upper() == "PEARSON" and not no_cluster:
        similarity_refresh_cmd(
            trade_date=trade_date,
            windows=windows,
            pool=pool,
            board_filter=board_filter,
            min_sample=min_sample,
            threshold=threshold,
            max_neighbors=max_neighbors,
            dry_run=dry_run,
            force=force,
            no_cluster=False,
        )
        return

    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope
    from quant_system.relationship.service import build_relationships

    _boot()
    d = _parse_date(trade_date)
    wins = _parse_windows_arg(windows)
    mode = "[yellow]DRY-RUN[/yellow]" if dry_run else "[bold]BUILD[/bold]"
    console.print(f"{mode} relationship → {d} type={relation_type} windows={wins}")

    with session_scope() as session:
        repos = build_repositories(session)
        job_id = None if dry_run else repos.job_log.start_job("relationship.build", d)
        try:
            report = build_relationships(
                repos, calc_date=d, relation_type=relation_type, windows=wins,
                pool_code=pool, board_filter=board_filter, min_sample=min_sample,
                value_threshold=threshold, max_neighbors=max_neighbors,
                full_lookback=full_lookback, dry_run=dry_run, force=force,
                use_cache=not no_cache,
                session=session,
            )
            if job_id is not None:
                repos.job_log.finish_job(job_id, "SUCCESS", stats={
                    "universe": report.universe_size,
                    "written": report.pair_written_total,
                    "skipped": report.skipped,
                })
        except Exception as e:
            if job_id is not None:
                repos.job_log.finish_job(job_id, "FAILED", error=str(e))
            raise

    if report.skipped:
        console.print("[yellow]已存在 SUCCESS 快照，跳过（--force 强制重算）[/yellow]")
        return
    if report.universe_size < 2:
        console.print("[red]计算宇宙不足，请先跑 update stock-pool + kline[/red]")
        raise typer.Exit(code=1)

    table = Table(title=f"relationship {'dry-run' if dry_run else 'build'} · {d} · 宇宙 {report.universe_size} 只")
    table.add_column("window")
    table.add_column("有效股票", justify="right")
    table.add_column("达标候选对", justify="right")
    table.add_column("落库/预估", justify="right")
    table.add_column("裁剪", justify="right")
    table.add_column("|v|≥0.6 / ≥0.7 / ≥0.8", justify="right")
    for w in report.per_window:
        ge = w.hist.get("ge", {})
        ge_str = f"{ge.get('0.6', 0)} / {ge.get('0.7', 0)} / {ge.get('0.8', 0)}"
        table.add_row(
            w.window, str(w.universe_effective), str(w.evaluated),
            str(w.written), str(w.capped), ge_str,
        )
    console.print(table)
    console.print(f"总写入 {report.pair_written_total} 行，耗时 {report.duration_ms}ms")
    if dry_run:
        console.print("[dim]dry-run 未落库；根据「|v|≥阈值」列微调 --threshold 后再正式 build[/dim]")


@relationship_app.command("top")
def relationship_top_cmd(
    code: Annotated[str, typer.Argument()],
    window: Annotated[str, typer.Option("--window")] = "W250",
    relation_type: Annotated[str, typer.Option("--type")] = "pearson",
    limit: Annotated[int, typer.Option("--limit")] = 20,
    neg: Annotated[bool, typer.Option("--neg", help="只看负相关")] = False,
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
) -> None:
    """查某只股票的 Top 邻居。"""
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope
    from quant_system.relationship import queries

    _boot()
    as_of = _parse_date(trade_date) if trade_date else None
    win = window.upper() if window.upper().startswith("W") else f"W{window}"
    with session_scope() as session:
        repos = build_repositories(session)
        snapshot_date = repos.relation.latest_calc_date(relation_type.upper(), win)
        rows = queries.top_neighbors(
            repos, code, relation_type=relation_type.upper(), window=win,
            sign=-1 if neg else None, limit=limit, as_of=as_of,
        )

    if not rows:
        if snapshot_date is None:
            console.print(f"[yellow]{win} 暂无关系快照，请先跑：qs relationship build --windows {win[1:]}[/yellow]")
        elif neg:
            console.print(
                f"[yellow]{code} 在 {win} 无强负相关邻居"
                f"（阈值下 A 股强负相关极少见，去掉 --neg 看正相关）[/yellow]"
            )
        else:
            console.print(
                f"[yellow]{code} 在 {win} 快照({snapshot_date})中无邻居"
                f"（可能未在计算宇宙内，或相关度未达落库阈值）[/yellow]"
            )
        return
    table = Table(title=f"{code} · {win} · Top {len(rows)} 邻居")
    table.add_column("#", justify="right")
    table.add_column("peer"); table.add_column("name")
    table.add_column("corr", justify="right")
    table.add_column("样本", justify="right")
    table.add_column("同行业")
    for i, r in enumerate(rows, 1):
        table.add_row(
            str(i), r["peer"], r.get("peer_name", ""),
            f"{r['relation_value']:+.3f}", str(r["sample_size"]),
            "✓" if r["is_same_industry"] else "",
        )
    console.print(table)


@relationship_app.command("pair")
def relationship_pair_cmd(
    base: Annotated[str, typer.Argument()],
    peer: Annotated[str, typer.Argument()],
    window: Annotated[str, typer.Option("--window")] = "W250",
    relation_type: Annotated[str, typer.Option("--type")] = "pearson",
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
) -> None:
    """查两只股票的关系值。"""
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope
    from quant_system.relationship import queries

    _boot()
    as_of = _parse_date(trade_date) if trade_date else None
    win = window.upper() if window.upper().startswith("W") else f"W{window}"
    with session_scope() as session:
        repos = build_repositories(session)
        row = queries.get_pair(
            repos, base, peer, relation_type=relation_type.upper(), window=win, as_of=as_of,
        )
    if row is None:
        console.print(f"[yellow]{base} × {peer} 在 {win} 无关系数据（可能低于落库阈值）[/yellow]")
        return
    console.print(
        f"[bold]{row['stock_code_a']} × {row['stock_code_b']}[/bold] · {win}\n"
        f"  corr = [bold]{row['relation_value']:+.4f}[/bold]  样本={row['sample_size']}  "
        f"同行业={'是' if row['is_same_industry'] else '否'}  快照日={row['calc_date']}"
    )


@relationship_app.command("changed")
def relationship_changed_cmd(
    short_window: Annotated[str, typer.Option("--short")] = "W60",
    long_window: Annotated[str, typer.Option("--long")] = "W250",
    min_delta: Annotated[float, typer.Option("--min-delta")] = 0.3,
    limit: Annotated[int, typer.Option("--limit")] = 30,
    relation_type: Annotated[str, typer.Option("--type")] = "pearson",
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
) -> None:
    """联动增强榜：短窗 − 长窗 的相关度变化。"""
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope
    from quant_system.relationship import queries

    _boot()
    as_of = _parse_date(trade_date) if trade_date else None
    with session_scope() as session:
        repos = build_repositories(session)
        rows = queries.changed(
            repos, relation_type=relation_type.upper(),
            short_window=short_window.upper(), long_window=long_window.upper(),
            min_delta=min_delta, limit=limit, as_of=as_of,
        )
    if not rows:
        console.print("[yellow]无联动增强数据（需 build 含短/长两个窗口）[/yellow]")
        return
    table = Table(title=f"联动增强 · {short_window}−{long_window} ≥ {min_delta}")
    table.add_column("a"); table.add_column("name_a")
    table.add_column("b"); table.add_column("name_b")
    table.add_column("短", justify="right"); table.add_column("长", justify="right")
    table.add_column("Δ", justify="right"); table.add_column("同行业")
    for r in rows:
        table.add_row(
            r["stock_code_a"], r["name_a"], r["stock_code_b"], r["name_b"],
            f"{r['v_short']:+.3f}", f"{r['v_long']:+.3f}", f"{r['delta']:+.3f}",
            "✓" if r["is_same_industry"] else "",
        )
    console.print(table)


@relationship_app.command("strong")
def relationship_strong_cmd(
    window: Annotated[str, typer.Option("--window")] = "W250",
    sign: Annotated[int, typer.Option("--sign", help="+1 正相关 / -1 负相关")] = 1,
    min_abs: Annotated[float, typer.Option("--min-abs")] = 0.8,
    limit: Annotated[int, typer.Option("--limit")] = 30,
    relation_type: Annotated[str, typer.Option("--type")] = "pearson",
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
) -> None:
    """全局强相关榜（--sign -1 看强负相关）。"""
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope
    from quant_system.relationship import queries

    _boot()
    as_of = _parse_date(trade_date) if trade_date else None
    win = window.upper() if window.upper().startswith("W") else f"W{window}"
    with session_scope() as session:
        repos = build_repositories(session)
        rows = queries.strong(
            repos, relation_type=relation_type.upper(), window=win,
            sign=sign, min_abs=min_abs, limit=limit, as_of=as_of,
        )
    if not rows:
        console.print(f"[yellow]{win} 无满足 |corr|≥{min_abs} 的数据[/yellow]")
        return
    label = "正相关" if sign > 0 else "负相关"
    table = Table(title=f"强{label} · {win} · |corr|≥{min_abs}")
    table.add_column("a"); table.add_column("name_a")
    table.add_column("b"); table.add_column("name_b")
    table.add_column("corr", justify="right"); table.add_column("样本", justify="right")
    table.add_column("同行业")
    for r in rows:
        table.add_row(
            r["stock_code_a"], r["name_a"], r["stock_code_b"], r["name_b"],
            f"{r['relation_value']:+.3f}", str(r["sample_size"]),
            "✓" if r["is_same_industry"] else "",
        )
    console.print(table)


@relationship_app.command("leadlag")
def relationship_leadlag_cmd(
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
    window: Annotated[str, typer.Option("--window")] = "W60",
    candidate_min: Annotated[float, typer.Option("--candidate-min", help="候选对同期|corr|门槛")] = 0.5,
    max_lag: Annotated[int, typer.Option("--max-lag")] = 5,
    threshold: Annotated[float, typer.Option("--threshold", help="最优lag下相关度门槛")] = 0.6,
    min_gain: Annotated[float, typer.Option("--min-gain", help="领先相关度需比同期高出")] = 0.03,
    force: Annotated[bool, typer.Option("--force")] = False,
    no_cache: Annotated[bool, typer.Option("--no-cache")] = False,
) -> None:
    """计算领先-滞后关系（候选对取自同期 PEARSON 快照，需先跑 build）。"""
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope
    from quant_system.relationship.service import build_lead_lag

    _boot()
    d = _parse_date(trade_date)
    win = window.upper() if window.upper().startswith("W") else f"W{window}"
    console.print(f"[bold]LEAD-LAG[/bold] → {d} window={win} max_lag=±{max_lag}")

    with session_scope() as session:
        repos = build_repositories(session)
        job_id = repos.job_log.start_job("relationship.leadlag", d)
        try:
            report = build_lead_lag(
                repos, calc_date=d, window=win, candidate_min_abs=candidate_min,
                max_lag=max_lag, value_threshold=threshold, min_lead_gain=min_gain,
                force=force, use_cache=not no_cache,
            )
            repos.job_log.finish_job(job_id, "SUCCESS", stats={
                "candidates": report.per_window[0].evaluated if report.per_window else 0,
                "written": report.pair_written_total, "skipped": report.skipped,
            })
        except Exception as e:
            repos.job_log.finish_job(job_id, "FAILED", error=str(e))
            raise

    if report.skipped:
        console.print("[yellow]已存在 LEAD_LAG 快照，跳过（--force 重算）[/yellow]")
        return
    if report.universe_size == 0:
        console.print(f"[red]无候选对，请先跑：qs relationship build --windows {win[1:]}[/red]")
        raise typer.Exit(code=1)
    w = report.per_window[0]
    console.print(
        f"[green]✓[/green] 候选 {w.evaluated} 对 → 领先-滞后 {report.pair_written_total} 个"
        f"（涉及 {report.universe_size} 只），耗时 {report.duration_ms}ms"
    )
    console.print("用 [cyan]qs relationship leads <代码>[/cyan] 查某只票的领先/跟随关系")


@relationship_app.command("leads")
def relationship_leads_cmd(
    code: Annotated[str, typer.Argument()],
    window: Annotated[str, typer.Option("--window")] = "W60",
    role: Annotated[str, typer.Option("--role", help="leads=它领先谁 / follows=它跟随谁 / all")] = "all",
    limit: Annotated[int, typer.Option("--limit")] = 20,
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
) -> None:
    """查某只股票的领先-滞后关系（lag>0=它领先，lag<0=它跟随）。"""
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope

    _boot()
    as_of = _parse_date(trade_date) if trade_date else None
    win = window.upper() if window.upper().startswith("W") else f"W{window}"
    with session_scope() as session:
        repos = build_repositories(session)
        snapshot = repos.relation.latest_calc_date("LEAD_LAG", win)
        rows = repos.relation.lead_lag_of(
            code, window=win, role=role, limit=limit, as_of=as_of,
        )
        names = {r["peer"]: (repos.stock.get_stock(r["peer"]).name
                             if repos.stock.get_stock(r["peer"]) else "") for r in rows}

    if not rows:
        if snapshot is None:
            console.print(f"[yellow]{win} 暂无 LEAD_LAG 快照，先跑：qs relationship leadlag --window {win[1:]}[/yellow]")
        else:
            console.print(f"[yellow]{code} 在 {win} 无领先/跟随关系[/yellow]")
        return
    table = Table(title=f"{code} · {win} · 领先-滞后（lag>0=它领先，lag<0=它跟随）")
    table.add_column("peer"); table.add_column("name")
    table.add_column("关系"); table.add_column("lag(交易日)", justify="right")
    table.add_column("corr", justify="right"); table.add_column("样本", justify="right")
    for r in rows:
        lag = r["lag_days"]
        rel = f"[green]领先[/green]" if lag > 0 else "[cyan]跟随[/cyan]"
        table.add_row(
            r["peer"], names.get(r["peer"], ""), rel, f"{abs(lag)}",
            f"{r['corr']:+.3f}", str(r["sample_size"]),
        )
    console.print(table)


@relationship_app.command("stats")
def relationship_stats_cmd(
    relation_type: Annotated[str, typer.Option("--type")] = "pearson",
) -> None:
    """当前快照概览：各窗口行数 / 平均样本 / 正负分布。"""
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope

    _boot()
    with session_scope() as session:
        repos = build_repositories(session)
        stats = repos.relation.snapshot_stats(relation_type=relation_type.upper())

    wins = stats.get("windows", [])
    if not wins:
        console.print("[yellow]暂无关系快照，先跑 relationship build[/yellow]")
        return
    table = Table(title=f"关系快照 · {stats['relation_type']}")
    table.add_column("window")
    table.add_column("行数", justify="right")
    table.add_column("快照日")
    table.add_column("平均样本", justify="right")
    table.add_column("正", justify="right")
    table.add_column("负", justify="right")
    for w in wins:
        table.add_row(
            w["window"], str(w["rows"]), w["calc_date"] or "-",
            str(w["avg_sample"]), str(w["positive"]), str(w["negative"]),
        )
    console.print(table)


# ============================================================================
# abnormal 子命令组（Pattern Similarity Framework）
# ============================================================================

@abnormal_app.command("scan")
def abnormal_scan_cmd(
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
    patterns: Annotated[Optional[str], typer.Option("--patterns", help="逗号分隔 Pattern ID")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """跑形态相似度扫描（Prototype -> Similarity -> Pattern Rank）。"""
    from quant_system.patterns.registry import get_registry
    from quant_system.patterns.service import build_patterns
    from quant_system.data.repository import build_repositories
    from quant_system.database.migrations import ensure_schema_columns
    from quant_system.infra.db import session_scope

    _boot()
    ensure_schema_columns()
    d = _parse_date(trade_date)
    pids = [x.strip().upper() for x in patterns.split(",")] if patterns else None
    mode = "[yellow]DRY-RUN[/yellow]" if dry_run else "[bold]SCAN[/bold]"
    console.print(f"{mode} pattern scan → {d} patterns={pids or list(get_registry())}")

    with session_scope() as session:
        repos = build_repositories(session)
        job_id = None if dry_run else repos.job_log.start_job("pattern.scan", d)
        try:
            report = build_patterns(
                repos, trade_date=d, pattern_ids=pids, dry_run=dry_run, force=force,
            )
            if job_id is not None:
                repos.job_log.finish_job(job_id, "SUCCESS", stats={
                    "universe": report.universe_size,
                    "written": sum(p.written for p in report.per_pattern),
                    "skipped": report.skipped,
                })
        except Exception as e:
            if job_id is not None:
                repos.job_log.finish_job(job_id, "FAILED", error=str(e))
            raise

    if report.skipped:
        console.print("[yellow]已存在 SUCCESS 批次，跳过（--force 重算）[/yellow]")
        return
    if report.universe_size == 0:
        console.print("[red]无特征数据，请先 qs feature[/red]")
        raise typer.Exit(code=1)

    table = Table(title=f"abnormal · {d} · 宇宙 {report.universe_size} · median={report.market_median_return}")
    table.add_column("pattern")
    table.add_column("命中", justify="right")
    table.add_column("写入", justify="right")
    table.add_column("Top1", justify="left")
    for pr in report.per_pattern:
        top1 = ""
        if pr.top_hits:
            h = pr.top_hits[0]
            top1 = f"{h['code']} sim={h['pattern_score']:.1f}"
        table.add_row(pr.display_name, str(pr.matched_count), str(pr.written), top1)
    console.print(table)
    console.print(f"耗时 {report.duration_ms}ms  params={report.params_version}")
    if dry_run:
        console.print("[dim]dry-run 未落库；正式跑去掉 --dry-run[/dim]")
    else:
        console.print(
            "查看: [cyan]qs abnormal top --all[/cyan] / "
            "[cyan]qs abnormal show <代码>[/cyan] / "
            "[cyan]qs abnormal eval <代码> --date YYYY-MM-DD[/cyan]"
        )


def _fmt_metric_num(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        v = float(value)
        if abs(v) >= 100:
            return f"{v:.2f}"
        if abs(v) >= 1:
            return f"{v:.4f}"
        return f"{v:.6f}"
    return str(value)


def _extract_feature_rows(components: dict) -> list[tuple[str, object, object]]:
    """从 score_components 抽出 (feature, value, sim)。"""
    feat_sim = components.get("feature_similarity") or {}
    metrics = components.get("metrics") or {}
    values = metrics.get("values") if isinstance(metrics, dict) else None
    if values is None:
        snap = components.get("inputs_snapshot") or {}
        values = snap.get("values") if isinstance(snap, dict) else {}
    values = values or {}
    keys = sorted(set(feat_sim) | set(values))
    return [(k, values.get(k), feat_sim.get(k)) for k in keys]


def _window_range_label(components: dict, stage: str, length: object) -> str:
    """长度 + 起止交易日，如 10d 2026-07-01~2026-07-14。"""
    ranges = components.get("chosen_window_ranges")
    if not ranges:
        metrics = components.get("metrics") or {}
        if isinstance(metrics, dict):
            ranges = metrics.get("chosen_window_ranges")
    if not ranges:
        snap = components.get("inputs_snapshot") or {}
        if isinstance(snap, dict):
            ranges = snap.get("chosen_window_ranges")
    rng = (ranges or {}).get(stage) or {}
    base = f"{length}d" if length is not None else "-"
    start, end = rng.get("start"), rng.get("end")
    if start and end:
        return f"{base} {start}~{end}"
    return base


def _print_pattern_metrics(
    components: dict,
    *,
    title: str,
) -> None:
    """打印 stage / window / 各特征 value+similarity。"""
    stages = components.get("stage_similarity") or {}
    windows = components.get("chosen_windows") or {}
    if stages or windows:
        head = Table(title=title, show_header=True)
        head.add_column("stage")
        head.add_column("window")
        head.add_column("sim", justify="right")
        stage_names = list(dict.fromkeys([*windows.keys(), *stages.keys()]))
        for name in stage_names:
            win = windows.get(name)
            sim = stages.get(name)
            head.add_row(
                name,
                _window_range_label(components, name, win),
                f"{float(sim):.1f}" if sim is not None else "-",
            )
        console.print(head)

    rows = _extract_feature_rows(components)
    if not rows:
        console.print("[dim]无特征明细（可能是旧扫描结果，请重新 qs abnormal scan）[/dim]")
        return
    table = Table(show_header=True, title="features")
    table.add_column("feature")
    table.add_column("value", justify="right")
    table.add_column("sim", justify="right")
    for name, value, sim in rows:
        table.add_row(
            name,
            _fmt_metric_num(value),
            f"{float(sim):.1f}" if sim is not None else "-",
        )
    console.print(table)


@abnormal_app.command("top")
def abnormal_top_cmd(
    pattern: Annotated[Optional[str], typer.Option("--pattern", help="Pattern ID；与 --all 二选一")] = None,
    all_patterns: Annotated[bool, typer.Option("--all", help="打印全部 Pattern 榜")] = False,
    limit: Annotated[int, typer.Option("--limit")] = 10,
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
    detail: Annotated[
        bool,
        typer.Option(
            "--detail/--compact",
            help="--detail 展开每只股票的特征 value/sim/窗口；默认 --compact 只打榜单",
        ),
    ] = False,
) -> None:
    """查看某模式相似度 TopN（或 --all 全部模式）。默认只打榜单，加 --detail 看指标明细。"""
    from quant_system.patterns.registry import PATTERN_REGISTRY
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope

    _boot()
    if not all_patterns and not pattern:
        console.print("[yellow]请指定 --pattern RANGE_BREAKOUT 或 --all[/yellow]")
        raise typer.Exit(code=1)

    with session_scope() as session:
        repos = build_repositories(session)
        d = _parse_date(trade_date) if trade_date else repos.abnormal.latest_trade_date()
        if d is None:
            console.print("[yellow]暂无异动数据，先跑 qs abnormal scan[/yellow]")
            return
        pids = list(PATTERN_REGISTRY) if all_patterns else [pattern.strip().upper()]  # type: ignore[union-attr]
        for pid in pids:
            meta = PATTERN_REGISTRY.get(pid)
            name = meta.display_name if meta else pid  # type: ignore[attr-defined]
            rows = repos.abnormal.top_by_pattern(d, pid, limit=limit)
            names = {}
            for r in rows:
                s = repos.stock.get_stock(r["code"])
                names[r["code"]] = s.name if s else ""
            table = Table(title=f"{name} · {d} · TOP{limit}")
            table.add_column("#", justify="right")
            table.add_column("code")
            table.add_column("name")
            table.add_column("sim", justify="right")
            table.add_column("dist", justify="right")
            table.add_column("reasons")
            if not rows:
                console.print(f"[dim]{name}: 今日无命中[/dim]")
                continue
            for r in rows:
                components = r.get("score_components") or {}
                table.add_row(
                    str(r["pattern_rank"]), r["code"], names.get(r["code"], ""),
                    f"{r['pattern_score']:.1f}",
                    f"{float(components.get('distance', 0.0)):.3f}",
                    " · ".join(r["reasons"][:4]),
                )
            console.print(table)
            if detail:
                for r in rows:
                    components = r.get("score_components") or {}
                    # 兼容旧数据：values 可能只在 inputs_snapshot
                    if "inputs_snapshot" not in components and r.get("inputs_snapshot"):
                        components = {
                            **components,
                            "inputs_snapshot": r["inputs_snapshot"],
                        }
                    title = (
                        f"#{r['pattern_rank']} {r['code']} "
                        f"{names.get(r['code'], '')} · metrics"
                    )
                    _print_pattern_metrics(components, title=title)


@abnormal_app.command("eval")
def abnormal_eval_cmd(
    code: Annotated[str, typer.Argument(help="股票代码，如 001258.SZ")],
    trade_date: Annotated[Optional[str], typer.Option("--date", help="asof 交易日；默认最近交易日")] = None,
    pattern: Annotated[
        Optional[str],
        typer.Option("--pattern", help="Pattern ID；默认 RANGE_BREAKOUT"),
    ] = "RANGE_BREAKOUT",
    detail: Annotated[
        bool,
        typer.Option("--detail/--compact", help="展开特征 value/sim；默认展开"),
    ] = True,
) -> None:
    """用当前 Definition 对单票现场重算（不落库，不受历史 scan 结果限制）。"""
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope
    from quant_system.patterns.context import build_pattern_context
    from quant_system.patterns.matcher import GenericPatternMatcher
    from quant_system.patterns.registry import PATTERN_REGISTRY, get_definitions

    _boot()
    code = code.strip().upper()
    d = _parse_date(trade_date)
    pid = (pattern or "RANGE_BREAKOUT").strip().upper()
    definitions = get_definitions([pid])
    if not definitions:
        console.print(f"[red]未知 Pattern: {pid}；可选 {list(PATTERN_REGISTRY)}[/red]")
        raise typer.Exit(code=1)
    definition = definitions[0]

    with session_scope() as session:
        repos = build_repositories(session)
        ctx = build_pattern_context(
            repos,
            d,
            codes=[code],
            max_bars=definition.required_history_bars(),
        )
        series = ctx["kline_by_code"].get(code)
        if series is None or series.empty:
            console.print(f"[yellow]{code} 在 {d} 无可用 K 线[/yellow]")
            raise typer.Exit(code=1)
        stock = repos.stock.get_stock(code)
        name = stock.name if stock else ""
        result = GenericPatternMatcher().match(
            code,
            d,
            series,
            definition,
            meta=ctx["stock_meta"].get(code, {}),
            last_amount=ctx["amount_by_code"].get(code),
        )

    status = "[green]MATCHED[/green]" if result.matched else "[red]NOT MATCHED[/red]"
    console.print(
        f"{status}  {code} {name}  ·  {definition.display_name}({definition.id})  ·  {d}"
    )
    summary = Table(show_header=True)
    summary.add_column("field")
    summary.add_column("value")
    summary.add_row("similarity", f"{result.similarity:.2f}")
    summary.add_row("threshold", f"{definition.threshold:.2f}")
    summary.add_row("distance", f"{result.distance:.4f}")
    summary.add_row("version", definition.version)
    ranges = (result.metrics or {}).get("chosen_window_ranges") or {}
    if result.chosen_windows:
        win_bits = []
        for k, v in result.chosen_windows.items():
            rng = ranges.get(k) or {}
            if rng.get("start") and rng.get("end"):
                win_bits.append(f"{k}={v}d {rng['start']}~{rng['end']}")
            else:
                win_bits.append(f"{k}={v}d")
        summary.add_row("windows", ", ".join(win_bits))
    else:
        summary.add_row("windows", "-")
    summary.add_row(
        "stage_sim",
        ", ".join(f"{k}={v:.1f}" for k, v in (result.stage_similarity or {}).items()) or "-",
    )
    summary.add_row("hard_failed", ", ".join(result.hard_failed) if result.hard_failed else "-")
    summary.add_row("reasons", " · ".join(result.reasons[:6]) if result.reasons else "-")
    console.print(summary)

    if detail:
        has_features = bool(result.feature_similarity) or bool(
            (result.metrics or {}).get("values")
        )
        if not has_features:
            console.print("[dim]未进入特征评分（硬约束/历史不足等已拦截）[/dim]")
        else:
            components = {
                "distance": result.distance,
                "stage_similarity": result.stage_similarity,
                "feature_similarity": result.feature_similarity,
                "chosen_windows": result.chosen_windows,
                "chosen_window_ranges": (result.metrics or {}).get("chosen_window_ranges"),
                "metrics": result.metrics,
                "inputs_snapshot": {
                    "chosen_windows": result.chosen_windows,
                    "chosen_window_ranges": (result.metrics or {}).get("chosen_window_ranges"),
                    "values": (result.metrics or {}).get("values"),
                },
            }
            _print_pattern_metrics(
                components,
                title=f"{code} · {definition.display_name} · live metrics",
            )


@abnormal_app.command("show")
def abnormal_show_cmd(
    code: Annotated[str, typer.Argument()],
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
    detail: Annotated[
        bool,
        typer.Option("--detail/--compact", help="展开特征 value/sim；默认展开"),
    ] = True,
) -> None:
    """查看某只股票命中了哪些 Pattern（历史 scan 落库结果）。"""
    from quant_system.patterns.registry import PATTERN_REGISTRY
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope

    _boot()
    with session_scope() as session:
        repos = build_repositories(session)
        d = _parse_date(trade_date) if trade_date else None
        rows = repos.abnormal.hits_of(code, d)
    if not rows:
        console.print(f"[yellow]{code} 未命中任何 Pattern[/yellow]")
        return
    table = Table(title=f"{code} · 异动命中")
    table.add_column("pattern")
    table.add_column("rank", justify="right")
    table.add_column("sim", justify="right")
    table.add_column("dist", justify="right")
    table.add_column("reasons")
    for r in rows:
        meta = PATTERN_REGISTRY.get(r["pattern_id"])
        name = meta.display_name if meta else r["pattern_id"]  # type: ignore[attr-defined]
        components = r.get("score_components") or {}
        table.add_row(
            name, str(r["pattern_rank"]),
            f"{r['pattern_score']:.1f}", f"{float(components.get('distance', 0.0)):.3f}",
            " · ".join(r["reasons"][:5]),
        )
    console.print(table)
    if detail:
        for r in rows:
            meta = PATTERN_REGISTRY.get(r["pattern_id"])
            name = meta.display_name if meta else r["pattern_id"]  # type: ignore[attr-defined]
            components = r.get("score_components") or {}
            if "inputs_snapshot" not in components and r.get("inputs_snapshot"):
                components = {
                    **components,
                    "inputs_snapshot": r["inputs_snapshot"],
                }
            _print_pattern_metrics(components, title=f"{code} · {name} · metrics")


@abnormal_app.command("stats")
def abnormal_stats_cmd(
    trade_date: Annotated[Optional[str], typer.Option("--date")] = None,
) -> None:
    """各 Pattern 当日命中统计。"""
    from quant_system.patterns.registry import PATTERN_REGISTRY
    from quant_system.data.repository import build_repositories
    from quant_system.infra.db import session_scope

    _boot()
    with session_scope() as session:
        repos = build_repositories(session)
        d = _parse_date(trade_date) if trade_date else repos.abnormal.latest_trade_date()
        if d is None:
            console.print("[yellow]暂无数据[/yellow]")
            return
        stats = repos.abnormal.stats(d)
    table = Table(title=f"abnormal stats · {d}")
    table.add_column("pattern")
    table.add_column("hits", justify="right")
    for pid, meta in PATTERN_REGISTRY.items():
        s = stats.get(pid, {})
        table.add_row(
            meta.display_name,  # type: ignore[attr-defined]
            str(s.get("L1", 0)),
        )
    console.print(table)


if __name__ == "__main__":
    app()
