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
from quant_system.strategy.risk_filter import REASON_DESCRIPTIONS as HARD_REASON_DESC
from quant_system.strategy.scoring import (
    SCORING_REASON_DESCRIPTIONS as SCORING_REASON_DESC,
)
from quant_system.strategy.stock_selector import SelectionReport


def _reason_desc(reason: str) -> str:
    """把硬过滤 reason 常量转成中文描述。"""
    return (
        HARD_REASON_DESC.get(reason)
        or SCORING_REASON_DESC.get(reason)
        or reason
    )


# 阶段 A：类别到中文的展示映射（用于共振度标签）
_CATEGORY_CN: dict[str, str] = {
    "trend": "趋势", "reversal": "反转",
    "volume_price": "量价", "fundamental": "基本面",
}


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
    ai_advice: dict[str, str] | None = None,
) -> str:
    ai_advice = ai_advice or {}
    lines: list[str] = []
    d = selection.trade_date
    lines.append(f"# 每日推荐 · {d}\n")

    # 概览
    lines.append("## 一、概览\n")
    lines.append(f"- **交易日**：{d}")
    lines.append(f"- **市场态势（Regime）**：{getattr(selection, 'regime', 'UNKNOWN')}")
    lines.append(f"- **股票池**：{settings.stock_pool.pool.value}")
    lines.append(f"- **板块过滤**：{settings.board_filter}")
    lines.append(f"- **特征总数**：{selection.total_features}")
    lines.append(f"- **板块过滤后**：{selection.after_board_filter}")
    lines.append(f"- **数据质量过滤后**：{selection.after_dq_filter}")
    after_hard = getattr(selection, "after_hard_filter", None)
    if after_hard is not None:
        lines.append(f"- **风险硬过滤后**：{after_hard}")
    lines.append(f"- **命中策略的股票数**：{selection.hit_count}")
    lines.append(f"- **本报告 Top**：{len(selection.top_stocks)}")

    # v2 新增：硬过滤汇总
    hard_filtered = getattr(selection, "hard_filtered", []) or []
    if hard_filtered:
        by_reason: dict[str, int] = {}
        for f in hard_filtered:
            by_reason[f["reason"]] = by_reason.get(f["reason"], 0) + 1
        detail = "、".join(
            f"{_reason_desc(k)} {v} 只" for k, v in sorted(by_reason.items())
        )
        lines.append(f"- **风险剔除**：共 {len(hard_filtered)} 只 · {detail}")
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
            lines.append(
                f"- 技术面：{s.tech_score:.2f}｜资金面：{s.capital_score:.2f}"
                f"｜基本面：{s.fundamental_score:.2f}"
            )

            # v2 新增：共振度标签
            resonance_cats = getattr(s, "resonance_categories", []) or []
            resonance_count = getattr(s, "resonance_count", 0)
            if resonance_cats:
                cats_cn = "+".join(_CATEGORY_CN.get(c, c) for c in resonance_cats)
                lines.append(f"- 共振度：**{resonance_count} 类**（{cats_cn}）")

            lines.append(f"- 命中策略：{'、'.join(s.hit_strategies)}")

            # v2 新增：风险标记（红色警告）
            risk_flags = getattr(s, "risk_flags", []) or []
            if risk_flags:
                lines.append(f"- ⚠️ **风险提示**：{'；'.join(risk_flags)}")

            # 正向理由（v2 优先用 positive_reasons，向后兼容用 reasons）
            positive = getattr(s, "positive_reasons", None) or s.reasons
            if positive:
                lines.append("- 理由：")
                for r in positive:
                    lines.append(f"  - {r}")

            # AI 分析（可选）
            advice = ai_advice.get(s.code)
            if advice:
                lines.append("")
                lines.append("#### AI 分析")
                lines.append(advice)
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
  .ai-advice {{ margin-top: 14px; padding: 12px 16px; background: #f7f9fc;
                border-left: 4px solid #4a90e2; border-radius: 4px; font-size: 14px; }}
  .ai-advice .ai-title {{ font-weight: 600; color: #4a90e2; margin-bottom: 6px; font-size: 13px; }}
  .ai-advice p {{ margin: 6px 0; line-height: 1.6; }}
  .resonance {{ display: inline-block; background: #eaf5ea; color: #2c7a2c; padding: 2px 10px;
                border-radius: 4px; font-size: 12px; margin-left: 8px; font-weight: 600; }}
  .risk-flags {{ margin: 10px 0; padding: 10px 14px; background: #fff5f5;
                 border-left: 4px solid #e74c3c; border-radius: 4px;
                 color: #a94442; font-size: 13px; }}
  .risk-flags .risk-title {{ font-weight: 600; margin-right: 6px; }}
  .filter-summary {{ padding: 10px 14px; background: #fafafa; border-left: 3px solid #ccc;
                     border-radius: 4px; margin: 10px 0; font-size: 13px; color: #555; }}
  .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; color: #999; font-size: 12px; }}
</style>
</head>
<body>
<h1>每日推荐 · {trade_date}</h1>

<h2>一、概览</h2>
<ul class="overview">
  <li>市场态势（Regime）：<b>{regime}</b>｜股票池：{pool}｜板块过滤：{board}</li>
  <li>特征总数：{total} → 板块后 {after_board} → 数据质量后 {after_dq} → 风险硬过滤后 {after_hard}</li>
  <li>命中策略的股票数：<b>{hit_count}</b>｜Top {top_n}</li>
</ul>
{filter_summary_html}

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
    ai_advice: dict[str, str] | None = None,
) -> str:
    ai_advice = ai_advice or {}
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

            # AI 分析（可选）：markdown 里 ** 加粗等直接放进 HTML 里可能不渲染，
            # 用 <pre>-friendly 但保留基础换行 & 加粗
            advice = ai_advice.get(s.code)
            advice_html = ""
            if advice:
                # 简单的 markdown → html 处理：** → <b>，换行 → <br>
                import html as _html
                import re as _re
                _safe = _html.escape(advice)
                _safe = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", _safe)
                # 空行分段 → 段落
                paragraphs = [
                    p.strip().replace("\n", "<br>")
                    for p in _safe.split("\n\n") if p.strip()
                ]
                advice_html = (
                    '<div class="ai-advice">'
                    '<div class="ai-title">🤖 AI 分析</div>'
                    + "".join(f"<p>{p}</p>" for p in paragraphs)
                    + "</div>"
                )

            # v2：共振度标签
            resonance_cats = getattr(s, "resonance_categories", []) or []
            resonance_count = getattr(s, "resonance_count", 0)
            resonance_html = ""
            if resonance_cats:
                cats_cn = "+".join(_CATEGORY_CN.get(c, c) for c in resonance_cats)
                resonance_html = (
                    f'<span class="resonance">共振 {resonance_count} 类·{cats_cn}</span>'
                )

            # v2：风险提示
            risk_flags = getattr(s, "risk_flags", []) or []
            risk_html = ""
            if risk_flags:
                items = "；".join(risk_flags)
                risk_html = (
                    f'<div class="risk-flags">'
                    f'<span class="risk-title">⚠️ 风险提示：</span>{items}'
                    f'</div>'
                )

            # 正向理由优先
            positive = getattr(s, "positive_reasons", None) or s.reasons
            reasons_html = "".join(f"<li>{r}</li>" for r in positive)

            cards.append(f"""
            <div class="stock-card">
              <div class="stock-header">
                <div>
                  <span class="stock-title">#{i} {name} · {s.code}</span>
                  {resonance_html}
                </div>
                <div class="stock-score">{s.final_score:.2f}</div>
              </div>
              <div class="stock-sub">
                技术面 {s.tech_score:.2f}｜资金面 {s.capital_score:.2f}｜基本面 {s.fundamental_score:.2f}
              </div>
              <div class="stock-strategies">{tags}</div>
              {risk_html}
              <ul class="reasons">{reasons_html}</ul>
              {chart_html}
              {advice_html}
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

    # v2: 硬过滤汇总
    hard_filtered = getattr(selection, "hard_filtered", []) or []
    after_hard = getattr(selection, "after_hard_filter", None)
    if after_hard is None:
        after_hard = selection.after_dq_filter
    if hard_filtered:
        by_reason: dict[str, int] = {}
        for f in hard_filtered:
            by_reason[f["reason"]] = by_reason.get(f["reason"], 0) + 1
        detail = "、".join(
            f"{_reason_desc(k)} <b>{v}</b> 只" for k, v in sorted(by_reason.items())
        )
        filter_summary_html = (
            f'<div class="filter-summary">🔍 风险剔除共 <b>{len(hard_filtered)}</b> 只 · {detail}</div>'
        )
    else:
        filter_summary_html = ""

    return HTML_TEMPLATE.format(
        trade_date=d.isoformat(),
        regime=getattr(selection, "regime", "UNKNOWN"),
        pool=settings.stock_pool.pool.value,
        board=settings.board_filter,
        total=selection.total_features,
        after_board=selection.after_board_filter,
        after_dq=selection.after_dq_filter,
        after_hard=after_hard,
        hit_count=selection.hit_count,
        top_n=len(selection.top_stocks),
        filter_summary_html=filter_summary_html,
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

    # AI 分析（如果启用）：针对 Top N 股票，每只调用一次 LLM 拿建议
    ai_advice: dict[str, str] = {}
    if settings.ai.enabled and settings.ai.api_key and selection.top_stocks:
        try:
            from quant_system.ai.analyzer import (
                analyze_stocks,
                build_inputs_from_selection,
            )
            inputs = build_inputs_from_selection(selection, repos, stock_name_map)
            ai_advice = analyze_stocks(inputs)
        except Exception as e:
            logger.warning("AI 分析异常，报告将不含 AI 建议: {}", e)

    md_path: Path | None = None
    html_path: Path | None = None

    if "md" in formats:
        md_content = _render_markdown(
            selection, stock_name_map, dq_summary, settings, ai_advice,
        )
        md_path = out_dir / f"{d.isoformat()}.md"
        md_path.write_text(md_content, encoding="utf-8")
        logger.info("Markdown 日报写入: {}", md_path)

    if "html" in formats:
        html_content = _render_html(
            selection, stock_name_map, dq_summary, repos, settings, ai_advice,
        )
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
