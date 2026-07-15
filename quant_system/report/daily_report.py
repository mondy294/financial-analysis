"""日报生成：Markdown + HTML 双输出。

流程：
1. 输入 SelectionReport（含 top_stocks）+ repos
2. 生成 Markdown（简洁纯文本，方便终端查看和复制）
3. 生成 HTML（带 plotly 迷你 K 线图）
4. 写文件到 reports/YYYY-MM-DD.md / .html
5. 落 daily_report + daily_report_item 表
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from loguru import logger

from quant_system.config.settings import Settings, get_settings
from quant_system.data.repository import Repositories
from quant_system.database.models import DailyReport, DailyReportItem, DataQualityCheck
from quant_system.report.charts import kline_mini_html
from quant_system.strategy.stock_selector import SelectionReport


@dataclass
class ReportOutput:
    trade_date: date
    md_path: Path | None
    html_path: Path | None
    item_count: int


# ============================================================================
# 生成 Markdown
# ============================================================================

def _render_markdown(
    selection: SelectionReport,
    stock_name_map: dict[str, str],
    dq_summary: dict[str, int],
    settings: Settings,
) -> str:
    lines: list[str] = []
    d = selection.trade_date
    lines.append(f"# 每日推荐 · {d}\n")

    # 概览
    lines.append("## 一、概览\n")
    lines.append(f"- **交易日**：{d}")
    lines.append(f"- **股票池**：{settings.stock_pool.pool.value}")
    lines.append(f"- **板块过滤**：{settings.board_filter}")
    lines.append(f"- **特征总数**：{selection.total_features}")
    lines.append(f"- **板块过滤后**：{selection.after_board_filter}")
    lines.append(f"- **数据质量过滤后**：{selection.after_dq_filter}")
    lines.append(f"- **命中策略的股票数**：{selection.hit_count}")
    lines.append(f"- **本报告 Top**：{len(selection.top_stocks)}")
    lines.append("")

    # 策略命中分布
    lines.append("## 二、策略命中分布\n")
    if selection.strategy_hit_stats:
        lines.append("| 策略 | 命中数 |")
        lines.append("|---|---|")
        for code, cnt in selection.strategy_hit_stats.items():
            lines.append(f"| {code} | {cnt} |")
    else:
        lines.append("_今日无策略命中。_")
    lines.append("")

    # 今日推荐
    lines.append("## 三、今日推荐\n")
    if not selection.top_stocks:
        lines.append("_今日无满足条件的推荐。_")
    else:
        for i, s in enumerate(selection.top_stocks, 1):
            name = stock_name_map.get(s.code, s.code)
            lines.append(f"### {i}. {name}（{s.code}）· 评分 **{s.final_score:.2f}**\n")
            lines.append(f"- 技术面：{s.tech_score:.2f}｜资金面：{s.capital_score:.2f}｜基本面：{s.fundamental_score:.2f}")
            lines.append(f"- 命中策略：{'、'.join(s.hit_strategies)}")
            lines.append("- 理由：")
            for r in s.reasons:
                lines.append(f"  - {r}")
            lines.append("")

    # 数据质量摘要
    if settings.report.include_dq_summary:
        lines.append("## 四、数据质量摘要\n")
        if not dq_summary:
            lines.append("_今日无数据质量问题。_")
        else:
            lines.append("| 严重级别 | 数量 |")
            lines.append("|---|---|")
            for sev in ["ERROR", "WARN", "INFO"]:
                if sev in dq_summary:
                    lines.append(f"| {sev} | {dq_summary[sev]} |")
        lines.append("")

    # 免责声明
    lines.append("---\n")
    lines.append("> 本报告由 quant_system 自动生成，**仅供研究学习使用，不构成投资建议**。基于本系统输出的任何交易决策，风险自负。")

    return "\n".join(lines)


# ============================================================================
# 生成 HTML
# ============================================================================

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>每日推荐 · {trade_date}</title>
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js"></script>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif;
         max-width: 1000px; margin: 30px auto; padding: 0 20px; color: #222; line-height: 1.7; }}
  h1 {{ border-bottom: 3px solid #d0021b; padding-bottom: 10px; }}
  h2 {{ border-left: 4px solid #d0021b; padding-left: 12px; margin-top: 40px; }}
  .stock-card {{ border: 1px solid #e5e5e5; border-radius: 8px; padding: 18px 20px; margin-bottom: 24px;
                 box-shadow: 0 2px 6px rgba(0,0,0,0.04); }}
  .stock-header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }}
  .stock-title {{ font-size: 18px; font-weight: 600; }}
  .stock-score {{ font-size: 22px; font-weight: 700; color: #d0021b; }}
  .stock-sub {{ color: #666; font-size: 13px; margin-bottom: 8px; }}
  .stock-strategies {{ margin: 8px 0; }}
  .tag {{ display: inline-block; background: #f0f4f8; color: #345; padding: 2px 10px; border-radius: 4px;
          font-size: 12px; margin-right: 6px; }}
  .reasons {{ padding-left: 20px; margin: 8px 0; }}
  .reasons li {{ font-size: 14px; }}
  table {{ border-collapse: collapse; margin: 10px 0; width: auto; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 14px; text-align: left; }}
  th {{ background: #fafafa; }}
  .overview li {{ font-size: 14px; }}
  .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; color: #999; font-size: 12px; }}
</style>
</head>
<body>
<h1>每日推荐 · {trade_date}</h1>

<h2>一、概览</h2>
<ul class="overview">
  <li>股票池：{pool}｜板块过滤：{board}</li>
  <li>特征总数：{total} → 板块后 {after_board} → 数据质量后 {after_dq}</li>
  <li>命中策略的股票数：<b>{hit_count}</b>｜Top {top_n}</li>
</ul>

<h2>二、策略命中分布</h2>
{strategy_table}

<h2>三、今日推荐</h2>
{stock_cards}

<h2>四、数据质量摘要</h2>
{dq_table}

<div class="footer">
  本报告由 quant_system 自动生成，仅供研究学习使用，<b>不构成投资建议</b>。基于本系统输出做出的任何交易决策，风险自负。<br>
  生成时间：{gen_at}
</div>
</body>
</html>
"""


def _render_html(
    selection: SelectionReport,
    stock_name_map: dict[str, str],
    dq_summary: dict[str, int],
    repos: Repositories,
    settings: Settings,
) -> str:
    d = selection.trade_date

    # 策略命中分布
    if selection.strategy_hit_stats:
        rows = "".join(
            f"<tr><td>{code}</td><td>{cnt}</td></tr>"
            for code, cnt in selection.strategy_hit_stats.items()
        )
        strategy_table = f"<table><tr><th>策略</th><th>命中数</th></tr>{rows}</table>"
    else:
        strategy_table = "<p><em>今日无策略命中。</em></p>"

    # 股票卡
    if not selection.top_stocks:
        stock_cards = "<p><em>今日无满足条件的推荐。</em></p>"
    else:
        cards = []
        for i, s in enumerate(selection.top_stocks, 1):
            name = stock_name_map.get(s.code, s.code)
            tags = "".join(f'<span class="tag">{c}</span>' for c in s.hit_strategies)
            reasons_html = "".join(f"<li>{r}</li>" for r in s.reasons)
            chart_html = kline_mini_html(s.code, d, repos, lookback_days=60)

            cards.append(f"""
            <div class="stock-card">
              <div class="stock-header">
                <div>
                  <span class="stock-title">#{i} {name} · {s.code}</span>
                </div>
                <div class="stock-score">{s.final_score:.2f}</div>
              </div>
              <div class="stock-sub">
                技术面 {s.tech_score:.2f}｜资金面 {s.capital_score:.2f}｜基本面 {s.fundamental_score:.2f}
              </div>
              <div class="stock-strategies">{tags}</div>
              <ul class="reasons">{reasons_html}</ul>
              {chart_html}
            </div>
            """)
        stock_cards = "\n".join(cards)

    # 数据质量摘要
    if not dq_summary:
        dq_table = "<p><em>今日无数据质量问题。</em></p>"
    else:
        rows = ""
        for sev in ["ERROR", "WARN", "INFO"]:
            if sev in dq_summary:
                rows += f"<tr><td>{sev}</td><td>{dq_summary[sev]}</td></tr>"
        dq_table = f"<table><tr><th>严重级别</th><th>数量</th></tr>{rows}</table>"

    return HTML_TEMPLATE.format(
        trade_date=d.isoformat(),
        pool=settings.stock_pool.pool.value,
        board=settings.board_filter,
        total=selection.total_features,
        after_board=selection.after_board_filter,
        after_dq=selection.after_dq_filter,
        hit_count=selection.hit_count,
        top_n=len(selection.top_stocks),
        strategy_table=strategy_table,
        stock_cards=stock_cards,
        dq_table=dq_table,
        gen_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


# ============================================================================
# 主入口
# ============================================================================

def generate_report(
    selection: SelectionReport,
    repos: Repositories,
    settings: Settings | None = None,
    formats: list[str] | None = None,
) -> ReportOutput:
    """生成日报文件 + 写数据库。"""
    settings = settings or get_settings()
    formats = formats or list(settings.report.formats)

    d = selection.trade_date
    out_dir = Path(settings.report.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 拿股票名字映射（一次性）
    codes_needed = [s.code for s in selection.top_stocks]
    stock_name_map: dict[str, str] = {}
    for code in codes_needed:
        stock = repos.stock.get_stock(code)
        stock_name_map[code] = stock.name if stock else code

    # 数据质量摘要（从 data_quality_check 汇总）
    from sqlalchemy import func, select
    session = repos.feature._session  # type: ignore[attr-defined]
    stmt = (
        select(DataQualityCheck.severity, func.count())
        .where(DataQualityCheck.check_date == d)
        .group_by(DataQualityCheck.severity)
    )
    dq_summary = {sev: int(cnt) for sev, cnt in session.execute(stmt)}

    md_path: Path | None = None
    html_path: Path | None = None

    if "md" in formats:
        md_content = _render_markdown(selection, stock_name_map, dq_summary, settings)
        md_path = out_dir / f"{d.isoformat()}.md"
        md_path.write_text(md_content, encoding="utf-8")
        logger.info("Markdown 日报写入: {}", md_path)

    if "html" in formats:
        html_content = _render_html(selection, stock_name_map, dq_summary, repos, settings)
        html_path = out_dir / f"{d.isoformat()}.html"
        html_path.write_text(html_content, encoding="utf-8")
        logger.info("HTML 日报写入: {}", html_path)

    # 写数据库
    _write_db(d, selection, stock_name_map, md_path, html_path, dq_summary, repos)

    return ReportOutput(
        trade_date=d,
        md_path=md_path,
        html_path=html_path,
        item_count=len(selection.top_stocks),
    )


def _write_db(
    trade_date: date,
    selection: SelectionReport,
    stock_name_map: dict[str, str],
    md_path: Path | None,
    html_path: Path | None,
    dq_summary: dict[str, int],
    repos: Repositories,
) -> None:
    """写 daily_report + daily_report_item。"""
    from sqlalchemy import delete
    session = repos.feature._session  # type: ignore[attr-defined]

    # 幂等：先删今日已有报告
    session.execute(delete(DailyReportItem).where(DailyReportItem.trade_date == trade_date))
    session.execute(delete(DailyReport).where(DailyReport.trade_date == trade_date))

    now = datetime.utcnow()

    summary_txt = (
        f"命中 {selection.hit_count} 只；Top {len(selection.top_stocks)}；"
        f"DQ ERROR={dq_summary.get('ERROR', 0)} WARN={dq_summary.get('WARN', 0)}"
    )

    session.add(DailyReport(
        trade_date=trade_date,
        market_trend=0,  # 后续接 market_features 时填
        sentiment_score=None,
        top_n=len(selection.top_stocks),
        md_path=str(md_path) if md_path else None,
        html_path=str(html_path) if html_path else None,
        summary=summary_txt,
        created_at=now,
    ))

    for rank, s in enumerate(selection.top_stocks, 1):
        session.add(DailyReportItem(
            trade_date=trade_date,
            rank=rank,
            code=s.code,
            name=stock_name_map.get(s.code, s.code),
            final_score=Decimal(str(s.final_score)),
            tech_score=Decimal(str(s.tech_score)),
            capital_score=Decimal(str(s.capital_score)),
            fundamental_score=Decimal(str(s.fundamental_score)),
            hit_strategies=s.hit_strategies,
            reasons=s.reasons,
            created_at=now,
        ))
