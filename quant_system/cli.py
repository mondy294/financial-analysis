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

app.add_typer(update_app, name="update")
app.add_typer(pool_app, name="pool")
app.add_typer(signal_app, name="signal")
app.add_typer(cache_app, name="cache")

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
        console.print("[green]✓ 数据库初始化完成，22 张表齐全[/green]")
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
        table.add_row("Schema 完整性", "✓", "22 张表齐全")
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
            target_codes = codes_list
        else:
            pool_code = (pool or "").upper() or None
            if pool_code is None:
                from quant_system.config.settings import get_settings
                pool_code = get_settings().stock_pool.pool.value
            pool_code_db = "CUSTOM_DEFAULT" if pool_code == "CUSTOM" else pool_code
            target_codes = repos.stock.list_pool_members(pool_code_db)

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

    # 展示
    table = Table(title=f"选股结果 · {d}")
    table.add_column("#", justify="right")
    table.add_column("code")
    table.add_column("score", justify="right")
    table.add_column("技术", justify="right")
    table.add_column("资金", justify="right")
    table.add_column("基本", justify="right")
    table.add_column("命中策略")

    for i, s in enumerate(report_obj.top_stocks, 1):
        table.add_row(
            str(i), s.code, f"{s.final_score:.2f}",
            f"{s.tech_score:.2f}", f"{s.capital_score:.2f}", f"{s.fundamental_score:.2f}",
            ",".join(s.hit_strategies),
        )
    console.print(table)
    console.print(
        f"命中数 [bold]{report_obj.hit_count}[/bold]；策略分布 {report_obj.strategy_hit_stats}"
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
        pool_code_db = settings.stock_pool.pool.value
        pool_code_db = "CUSTOM_DEFAULT" if pool_code_db == "CUSTOM" else pool_code_db
        codes = repos.stock.list_pool_members(pool_code_db)
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


if __name__ == "__main__":
    app()
