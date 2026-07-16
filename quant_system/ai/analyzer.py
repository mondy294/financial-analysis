"""AI 分析器：把每只推荐股票的规则选股结果 + 完整指标喂给大模型，拿一段建议。

设计原则：
- **不做交易指令**：AI 只输出分析、观察点、风险提示，不说"买/卖"
- **单只单调用**：Top N 只每只一次 API 调用，用线程池并发
- **失败降级**：任何一只失败/超时/AI 拒答 → 那一段留空但不影响其它
- **纯函数化**：analyze_stocks(top_stocks, features, ...) -> dict[code, ai_text]
- **OpenAI 兼容**：DeepSeek 用的是 OpenAI 兼容协议，代码天然支持切换到其它厂商
"""
from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from loguru import logger

from quant_system.config.settings import AIConfig, get_settings

# 喂给 AI 的近 N 个交易日原始走势（弥补单日指标压不出的形态，如高开低走）
RECENT_KLINE_DAYS = 10


# ============================================================================
# 输入结构
# ============================================================================

@dataclass
class StockAIInput:
    """喂给 AI 的单只股票的全部信息。"""
    code: str
    name: str
    trade_date: date
    industry: str | None

    # 规则选股结果
    final_score: float
    tech_score: float
    capital_score: float
    fundamental_score: float
    hit_strategies: list[str]
    hit_reasons: list[str]

    # 价量快照（当日）
    close: float | None
    pct_change: float | None
    volume_ratio: float | None
    turnover_rate: float | None

    # 收益周期
    return_1d: float | None
    return_5d: float | None
    return_20d: float | None
    return_60d: float | None

    # 均线 & 位置
    ma5: float | None
    ma10: float | None
    ma20: float | None
    ma60: float | None
    ma_position: float | None
    ma_bull_arrange: bool | None

    # 动量指标
    rsi_14: float | None
    macd: float | None
    macd_signal: float | None
    macd_hist: float | None
    macd_golden_cross: bool | None
    kdj_k: float | None
    kdj_d: float | None
    kdj_j: float | None

    # 波动 & 布林
    atr_14: float | None
    boll_upper: float | None
    boll_mid: float | None
    boll_lower: float | None
    boll_width: float | None

    # 突破
    high_20d: float | None
    break_high_20d: bool | None

    # 基本面
    pe_ttm: float | None
    pb: float | None
    roe_latest: float | None
    net_profit_yoy_latest: float | None
    revenue_yoy_latest: float | None
    market_cap: float | None

    # v2 新增（带默认值，必须排在所有无默认字段之后，否则 dataclass 定义报错）
    # 风险标记（Soft Penalty 命中项）、共振度（信号跨类别数）
    risk_flags: list[str] = field(default_factory=list)
    resonance_count: int = 0
    resonance_categories: list[str] = field(default_factory=list)
    # 近 N 个交易日原始日线（最旧→最新），每项含 date/open/high/low/close/pct_change/
    # turnover_rate/amount_yi，用于让 AI 识别走势形态
    recent_klines: list[dict] = field(default_factory=list)
    # 大盘环境快照（已渲染好的 markdown，同一交易日所有股票共用），空串表示无数据
    market_context: str = ""


# ============================================================================
# Prompt 构造
# ============================================================================

SYSTEM_PROMPT = """你是一名严谨的 A 股量化分析师。你将收到一只股票在某个交易日的：
- **当日大盘环境**（主要指数涨跌、相对均线位置、大盘研判、市场宽度、**近若干日各指数逐日涨跌**）
- 规则量化系统给出的评分和命中策略
- **共振度**（信号跨越几个大类）
- **规则系统标记的风险**（Soft Penalty 命中项，例如 RSI 偏高、5 日涨幅偏高、波动率异常等）
- 完整技术指标（趋势/动量/波动/量能/突破）
- **近若干个交易日的原始日线明细**（开/高/低/收 + 涨跌幅 + 换手 + 成交额）
- 基本面快照（PE / PB / ROE / 增长率）
- 近期收益表现（1/5/20/60 日）

请基于这些数据做出**结构化、克制、专业**的分析。

严格约束：
1. **绝对不要给出"买入/卖出/持有"等交易指令**。可以描述"技术面偏多/偏空/中性"、"估值处于什么水位"等中性判断。
2. **只用数据说话**，不要编造未提供的信息（比如公司业务、消息面、行业地位等你不知道的都不要提）。
3. **必须结合大盘环境判断个股**：结合近 N 日各指数逐日涨跌看清大盘节奏（连跌/反弹/板块分化），大盘偏空/震荡时对个股技术信号要更谨慎（可能是普涨/普跌带动而非个股独立走强）；对比个股与对应指数的逐日涨跌，说明该股是强于还是弱于大盘。
4. **规则系统已标记的风险必须逐条呼应**，不能视而不见。风险越多，语气越谨慎。
5. **务必结合近 N 日日线明细判断走势形态**：单日指标压不出的信息要从原始 OHLC 里读，例如高开低走/冲高回落（开在高位但收在低位、上影线长）、连续放量拉升或缩量阴跌、量价背离、跳空缺口等，并纳入技术面判断。
6. 语言精炼，**总长不超过 300 字**。
7. 使用 Markdown 格式，包含以下 4 个小节：
   - **技术面**：均线/动量/量能的组合解读 + **近 N 日走势形态** + **与大盘的强弱对比**（结合共振度评估信号强度）
   - **基本面**：估值 & 增长的对比（如果有数据）
   - **风险提示**：**逐条呼应规则系统标记的 risk_flags**，并加上自己从走势/指标/大盘环境里发现的其它风险
   - **观察建议**：可跟踪的量化指标或价位阈值
8. 如果某类数据缺失（NULL），就跳过对应的判断，**不要说"数据缺失"这种废话**。

输出直接开始，不要复述题目、不要开场白。"""


def _fmt(v: Any, unit: str = "", digits: int = 2) -> str:
    """把可能为 None 的数值格式化成字符串。"""
    if v is None:
        return "N/A"
    if isinstance(v, bool):
        return "是" if v else "否"
    try:
        return f"{float(v):.{digits}f}{unit}"
    except (TypeError, ValueError):
        return str(v)


# ============================================================================
# 大盘环境上下文（同一交易日所有个股共用一份）
# ============================================================================

# 展示给 AI 的大盘指数（code -> 简称），覆盖主要板块 + 大中小盘
_AI_MARKET_INDICES: dict[str, str] = {
    "000001.SH": "上证指数",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
    "000688.SH": "科创50",
    "000300.SH": "沪深300",
    "000852.SH": "中证1000",
}

# regime 研判基准指数
_REGIME_INDEX = "000300.SH"

# 给 AI 看的大盘逐日明细天数（与个股 RECENT_KLINE_DAYS 对齐）
RECENT_MARKET_DAYS = 10


@dataclass
class _IndexSnap:
    name: str
    close: float | None
    pct_1d: float | None
    pct_5d: float | None
    pct_20d: float | None
    vs_ma20: float | None  # (close/ma20 - 1) * 100


def _index_series(session: Any, code: str, trade_date: date) -> list[float]:
    """取某指数 <= trade_date 的最近 65 个交易日收盘价（升序）。"""
    from sqlalchemy import select

    from quant_system.database.models import IndexDaily
    stmt = (
        select(IndexDaily.close)
        .where(IndexDaily.index_code == code)
        .where(IndexDaily.trade_date <= trade_date)
        .order_by(IndexDaily.trade_date.desc())
        .limit(65)
    )
    closes = [float(c) for c in session.scalars(stmt).all()]
    return list(reversed(closes))


def _index_recent(
    session: Any, code: str, trade_date: date, n: int,
) -> dict[date, tuple[float | None, float | None]]:
    """取某指数 <= trade_date 最近 n 个交易日的 {date: (close, pct_change)}。

    pct_change 缺失时用相邻收盘价现算（多取一天用于首日环比）。
    """
    from sqlalchemy import select

    from quant_system.database.models import IndexDaily
    stmt = (
        select(IndexDaily.trade_date, IndexDaily.close, IndexDaily.pct_change)
        .where(IndexDaily.index_code == code)
        .where(IndexDaily.trade_date <= trade_date)
        .order_by(IndexDaily.trade_date.desc())
        .limit(n + 1)
    )
    rows = list(reversed(session.execute(stmt).all()))
    out: dict[date, tuple[float | None, float | None]] = {}
    prev: float | None = None
    for td, close, pct in rows:
        c = float(close)
        p = float(pct) if pct is not None else ((c / prev - 1) * 100 if prev else None)
        out[td] = (c, p)
        prev = c
    # 只保留最近 n 天（丢掉多取的那一天）
    keep = sorted(out)[-n:]
    return {d: out[d] for d in keep}


def _snap_from_closes(name: str, closes: list[float]) -> _IndexSnap | None:
    if not closes:
        return None
    close = closes[-1]
    pct_1d = (close / closes[-2] - 1) * 100 if len(closes) >= 2 else None
    pct_5d = (close / closes[-6] - 1) * 100 if len(closes) >= 6 else None
    pct_20d = (close / closes[-21] - 1) * 100 if len(closes) >= 21 else None
    vs_ma20 = None
    if len(closes) >= 20:
        ma20 = sum(closes[-20:]) / 20
        if ma20:
            vs_ma20 = (close / ma20 - 1) * 100
    return _IndexSnap(name, close, pct_1d, pct_5d, pct_20d, vs_ma20)


def _judge_regime(closes: list[float]) -> tuple[str, str]:
    """用基准指数收盘序列粗判大盘 regime。返回 (标签, 依据)。"""
    if len(closes) < 21:
        return "未知", "基准指数历史不足"
    close = closes[-1]
    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else ma20
    ret20 = (close / closes[-21] - 1) * 100
    basis = (
        f"沪深300 收{close:.0f}，MA20={ma20:.0f}、MA60={ma60:.0f}，"
        f"20日{ret20:+.1f}%"
    )
    if close > ma20 and ma20 >= ma60 and ret20 > 0:
        return "偏多（多头趋势）", basis
    if close < ma20 and ma20 <= ma60 and ret20 < 0:
        return "偏空（空头趋势）", basis
    return "震荡/中性", basis


def build_market_context(repos: Any, trade_date: date) -> str:
    """构造大盘环境 markdown 块。无指数数据时返回空串。"""
    session = repos.feature._session  # type: ignore[attr-defined]

    snaps: list[_IndexSnap] = []
    for code, name in _AI_MARKET_INDICES.items():
        snap = _snap_from_closes(name, _index_series(session, code, trade_date))
        if snap is not None:
            snaps.append(snap)

    if not snaps:
        return ""

    regime_label, regime_basis = _judge_regime(
        _index_series(session, _REGIME_INDEX, trade_date)
    )

    # 市场宽度（涨跌家数 / 涨停数），来自 market_daily，可能没有
    breadth_line = ""
    try:
        from sqlalchemy import select

        from quant_system.database.models import MarketDaily
        md = session.scalars(
            select(MarketDaily).where(MarketDaily.trade_date == trade_date)
        ).first()
        if md is not None:
            breadth_line = (
                f"- 市场宽度：涨 {md.up_count} / 跌 {md.down_count} / 平 {md.flat_count}"
                f" | 涨停 {md.limit_up_count} / 跌停 {md.limit_down_count}"
            )
    except Exception:  # noqa: BLE001
        breadth_line = ""

    lines = [
        "## 当日大盘环境",
        f"- **大盘研判：{regime_label}**（{regime_basis}）",
        "",
        "| 指数 | 收盘 | 当日 | 5日 | 20日 | 相对MA20 |",
        "|---|---|---|---|---|---|",
    ]
    for s in snaps:
        lines.append(
            f"| {s.name} | {_fmt(s.close, digits=0)} | {_fmt(s.pct_1d, '%')} "
            f"| {_fmt(s.pct_5d, '%')} | {_fmt(s.pct_20d, '%')} | {_fmt(s.vs_ma20, '%')} |"
        )
    if breadth_line:
        lines.append("")
        lines.append(breadth_line)

    # 近 N 日各指数逐日涨跌矩阵（让 AI 读大盘节奏：连跌/反弹/分化）
    recent = {
        name: _index_recent(session, code, trade_date, RECENT_MARKET_DAYS)
        for code, name in _AI_MARKET_INDICES.items()
    }
    all_dates = sorted({d for m in recent.values() for d in m})[-RECENT_MARKET_DAYS:]
    if all_dates:
        shown = [name for name in _AI_MARKET_INDICES.values() if recent.get(name)]
        lines.append("")
        lines.append(f"近 {len(all_dates)} 日各指数逐日涨跌%（最旧 → 最新）：")
        lines.append("| 日期 | " + " | ".join(shown) + " |")
        lines.append("|---" * (len(shown) + 1) + "|")
        for d in all_dates:
            cells = []
            for name in shown:
                cell = recent[name].get(d)
                cells.append(_fmt(cell[1], "%") if cell else "-")
            lines.append(f"| {d.isoformat()} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_user_prompt(inp: StockAIInput) -> str:
    """构造发给 LLM 的用户消息。"""
    lines = [
        f"# 分析对象：{inp.name}（{inp.code}）",
        f"交易日：{inp.trade_date.isoformat()}",
    ]
    if inp.industry:
        lines.append(f"行业：{inp.industry}")
    lines.append("")

    # 大盘环境（同一交易日所有股票共用，放在最前面让 AI 先建立市场判断）
    if inp.market_context:
        lines.append(inp.market_context)
        lines.append("")

    # 规则打分
    lines.append("## 规则量化评分（0-100）")
    lines.append(f"- 综合得分：**{inp.final_score:.2f}**")
    lines.append(
        f"- 分维度：技术 {inp.tech_score:.2f} | 资金 {inp.capital_score:.2f} "
        f"| 基本面 {inp.fundamental_score:.2f}"
    )
    # v2 新增：共振度（信号跨类别数）
    if inp.resonance_count > 0:
        cats_str = "、".join(inp.resonance_categories) if inp.resonance_categories else ""
        lines.append(
            f"- 共振度：**{inp.resonance_count}** 类"
            f"（{cats_str}）— 数字越大信号越可信"
        )
    lines.append(f"- 命中策略：{', '.join(inp.hit_strategies) or '（仅评分未命中）'}")
    if inp.hit_reasons:
        lines.append("- 触发理由：")
        for r in inp.hit_reasons:
            lines.append(f"  - {r}")

    # v2 新增：规则系统标记的风险（关键信息，AI 必须回应）
    if inp.risk_flags:
        lines.append("- **⚠️ 规则系统已标记以下风险（分析时必须逐条呼应）**：")
        for rf in inp.risk_flags:
            lines.append(f"  - {rf}")
    lines.append("")

    # 价量
    lines.append("## 当日价量")
    lines.append(
        f"- 收盘：{_fmt(inp.close)} | 涨跌幅：{_fmt(inp.pct_change, '%')} "
        f"| 换手率：{_fmt(inp.turnover_rate, '%')} | 量比：{_fmt(inp.volume_ratio, 'x')}"
    )
    lines.append(
        f"- 近期收益：1D {_fmt(inp.return_1d, '%')} | 5D {_fmt(inp.return_5d, '%')} "
        f"| 20D {_fmt(inp.return_20d, '%')} | 60D {_fmt(inp.return_60d, '%')}"
    )
    lines.append("")

    # 近 N 日日线明细（让模型看形态：高开低走/冲高回落/放缩量/跳空等）
    if inp.recent_klines:
        lines.append(f"## 近 {len(inp.recent_klines)} 日日线明细（原始价，最旧 → 最新）")
        lines.append("| 日期 | 开 | 高 | 低 | 收 | 涨跌% | 换手% | 成交额(亿) |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for k in inp.recent_klines:
            lines.append(
                f"| {k.get('date', '')} | {_fmt(k.get('open'))} | {_fmt(k.get('high'))} "
                f"| {_fmt(k.get('low'))} | {_fmt(k.get('close'))} "
                f"| {_fmt(k.get('pct_change'), '%')} | {_fmt(k.get('turnover_rate'), '%')} "
                f"| {_fmt(k.get('amount_yi'))} |"
            )
        lines.append("")

    # 均线
    lines.append("## 均线")
    lines.append(
        f"- MA5={_fmt(inp.ma5)} | MA10={_fmt(inp.ma10)} "
        f"| MA20={_fmt(inp.ma20)} | MA60={_fmt(inp.ma60)}"
    )
    lines.append(
        f"- 相对 MA20 位置：{_fmt(inp.ma_position, '%')} "
        f"（正=站上，负=跌破）| 多头排列：{_fmt(inp.ma_bull_arrange)}"
    )
    lines.append("")

    # 动量
    lines.append("## 动量")
    lines.append(
        f"- RSI(14)：{_fmt(inp.rsi_14)} "
        f"（<20 超卖，>80 超买，30-70 常规）"
    )
    lines.append(
        f"- MACD：DIF={_fmt(inp.macd, digits=3)} DEA={_fmt(inp.macd_signal, digits=3)} "
        f"HIST={_fmt(inp.macd_hist, digits=3)} | 当日金叉：{_fmt(inp.macd_golden_cross)}"
    )
    lines.append(
        f"- KDJ：K={_fmt(inp.kdj_k)} D={_fmt(inp.kdj_d)} J={_fmt(inp.kdj_j)}"
    )
    lines.append("")

    # 波动 & 突破
    lines.append("## 波动与突破")
    lines.append(f"- ATR(14)：{_fmt(inp.atr_14)}")
    lines.append(
        f"- 布林带：上轨={_fmt(inp.boll_upper)} 中轨={_fmt(inp.boll_mid)} "
        f"下轨={_fmt(inp.boll_lower)} 带宽={_fmt(inp.boll_width, '%')}"
    )
    lines.append(
        f"- 20 日最高：{_fmt(inp.high_20d)} | 当日突破：{_fmt(inp.break_high_20d)}"
    )
    lines.append("")

    # 基本面
    lines.append("## 基本面")
    lines.append(
        f"- 估值：PE(TTM)={_fmt(inp.pe_ttm)} | PB={_fmt(inp.pb)} "
        f"| 市值={_fmt(inp.market_cap, '亿', digits=0) if inp.market_cap else 'N/A'}"
    )
    lines.append(
        f"- 盈利：ROE={_fmt(inp.roe_latest, '%')} "
        f"| 净利润同比={_fmt(inp.net_profit_yoy_latest, '%')} "
        f"| 营收同比={_fmt(inp.revenue_yoy_latest, '%')}"
    )

    return "\n".join(lines)


# ============================================================================
# 单只调用
# ============================================================================

def _call_llm(client: Any, cfg: AIConfig, user_prompt: str) -> str:
    """调用一次 LLM。返回纯文本。"""
    kwargs: dict[str, Any] = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "max_tokens": cfg.max_tokens,
        "timeout": cfg.timeout_sec,
    }
    # DeepSeek V4-pro 特有的推理参数
    if cfg.reasoning_effort:
        kwargs["reasoning_effort"] = cfg.reasoning_effort
    extra_body: dict[str, Any] = {}
    if cfg.thinking_enabled:
        extra_body["thinking"] = {"type": "enabled"}
    if extra_body:
        kwargs["extra_body"] = extra_body

    resp = client.chat.completions.create(**kwargs)
    choice = resp.choices[0]
    content = choice.message.content or ""
    if not content.strip():
        # 空正文通常是 max_tokens 被 thinking/reasoning 吃光（finish_reason=length）
        finish = getattr(choice, "finish_reason", None)
        logger.warning(
            "LLM 返回空正文（finish_reason={}，max_tokens={}）；"
            "若为 length 请调大 QS_AI__MAX_TOKENS",
            finish, cfg.max_tokens,
        )
    return content


def analyze_one(client: Any, cfg: AIConfig, inp: StockAIInput) -> tuple[str, str | None]:
    """分析单只，返回 (code, ai_text or None on failure)。"""
    try:
        prompt = build_user_prompt(inp)
        text = _call_llm(client, cfg, prompt)
        return inp.code, text.strip() if text else None
    except Exception as e:
        logger.warning("AI 分析 {} 失败: {}", inp.code, e)
        return inp.code, None


# ============================================================================
# 批量并发
# ============================================================================

def analyze_stocks(inputs: list[StockAIInput]) -> dict[str, str]:
    """并发分析多只股票。返回 {code: ai_text}，失败的 code 不会出现在结果里。

    调用方决定何时触发（一般在 daily_report 生成阶段）。
    """
    cfg = get_settings().ai
    if not cfg.enabled or not cfg.api_key:
        logger.info("AI 分析未启用，跳过")
        return {}

    if not inputs:
        return {}

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("未安装 openai SDK，跳过 AI 分析")
        return {}

    client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
    results: dict[str, str] = {}

    logger.info(
        "AI 分析开始：{} 只股票，模型={}，并发={}",
        len(inputs), cfg.model, cfg.concurrency,
    )

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=cfg.concurrency, thread_name_prefix="ai-analyze"
    ) as executor:
        futures = {
            executor.submit(analyze_one, client, cfg, inp): inp.code
            for inp in inputs
        }
        for fut in concurrent.futures.as_completed(futures):
            code, text = fut.result()
            if text:
                results[code] = text

    logger.info("AI 分析完成：成功 {}/{}", len(results), len(inputs))
    return results


# ============================================================================
# 从 SelectionReport + DailyFeature 组装输入的辅助函数
# ============================================================================

def _to_float(x: Any) -> float | None:
    if x is None:
        return None
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, bool):
        return float(x)
    try:
        f = float(x)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _to_bool(x: Any) -> bool | None:
    if x is None:
        return None
    return bool(x)


def build_inputs_from_selection(
    selection: Any,  # SelectionReport（避免循环 import）
    repos: Any,      # Repositories
    stock_name_map: dict[str, str],
) -> list[StockAIInput]:
    """把 SelectionReport 的 top_stocks + 从 DB 拉的特征拼成 AI 输入列表。"""
    from sqlalchemy import select

    from quant_system.database.models import DailyFeature, StockBasic

    if not selection.top_stocks:
        return []

    trade_date = selection.trade_date
    session = repos.feature._session  # type: ignore[attr-defined]

    # 大盘环境：整批只算一次，所有个股共用
    try:
        market_ctx = build_market_context(repos, trade_date)
    except Exception as e:  # noqa: BLE001
        logger.debug("构造大盘环境失败，AI 将不含大盘上下文: {}", e)
        market_ctx = ""

    codes = [s.code for s in selection.top_stocks]

    # 特征映射
    feats: dict[str, DailyFeature] = {}
    stmt = select(DailyFeature).where(
        DailyFeature.trade_date == trade_date,
        DailyFeature.code.in_(codes),
    )
    for row in session.scalars(stmt).all():
        feats[row.code] = row

    # 行业映射
    industry_map: dict[str, str | None] = {}
    stmt2 = select(StockBasic.code, StockBasic.industry_name).where(
        StockBasic.code.in_(codes)
    )
    for code, ind in session.execute(stmt2).all():
        industry_map[code] = ind

    # 从 daily_kline 拿当日收盘价 & 涨跌幅（feature 表本身不存这两个原始值）
    kline_map: dict[str, tuple[float | None, float | None]] = {}
    from quant_system.database.models import DailyKline
    stmt3 = select(
        DailyKline.code, DailyKline.close, DailyKline.pct_change,
    ).where(
        DailyKline.trade_date == trade_date, DailyKline.code.in_(codes),
    )
    for code, close, pct in session.execute(stmt3).all():
        kline_map[code] = (_to_float(close), _to_float(pct))

    # 近 N 个交易日原始日线（用于让 AI 读走势形态）。窗口多留些日历天保证够 N 个交易日。
    recent_map: dict[str, list[dict]] = {}
    win_start = trade_date - timedelta(days=RECENT_KLINE_DAYS * 2 + 12)
    for code in codes:
        try:
            kdf = repos.kline.read_kline(code, win_start, trade_date, adj="none")
        except Exception as e:  # noqa: BLE001
            logger.debug("读取 {} 近期 K 线失败，AI 将不含走势表: {}", code, e)
            continue
        if kdf is None or kdf.empty:
            continue
        tail = kdf.tail(RECENT_KLINE_DAYS)
        recent_map[code] = [
            {
                "date": (
                    r["trade_date"].isoformat()
                    if hasattr(r["trade_date"], "isoformat")
                    else str(r["trade_date"])
                ),
                "open": _to_float(r["open"]),
                "high": _to_float(r["high"]),
                "low": _to_float(r["low"]),
                "close": _to_float(r["close"]),
                "pct_change": _to_float(r["pct_change"]),
                "turnover_rate": _to_float(r["turnover_rate"]),
                "amount_yi": (
                    _to_float(r["amount"]) / 1e8 if r["amount"] is not None else None
                ),
            }
            for _, r in tail.iterrows()
        ]

    inputs: list[StockAIInput] = []
    for s in selection.top_stocks:
        f = feats.get(s.code)
        close, pct = kline_map.get(s.code, (None, None))
        inputs.append(StockAIInput(
            code=s.code,
            name=stock_name_map.get(s.code, s.code),
            trade_date=trade_date,
            industry=industry_map.get(s.code),
            final_score=s.final_score,
            tech_score=s.tech_score,
            capital_score=s.capital_score,
            fundamental_score=s.fundamental_score,
            hit_strategies=list(s.hit_strategies),
            # v2：优先用 positive_reasons（不含 ⚠️ 前缀），若无（老数据）退化到 reasons
            hit_reasons=list(getattr(s, "positive_reasons", None) or s.reasons),
            risk_flags=list(getattr(s, "risk_flags", []) or []),
            resonance_count=int(getattr(s, "resonance_count", 0) or 0),
            resonance_categories=list(getattr(s, "resonance_categories", []) or []),
            recent_klines=recent_map.get(s.code, []),
            market_context=market_ctx,
            close=close,
            pct_change=pct,
            volume_ratio=_to_float(f.volume_ratio if f else None),
            turnover_rate=_to_float(f.turnover_rate if f else None),
            return_1d=_to_float(f.return_1d if f else None),
            return_5d=_to_float(f.return_5d if f else None),
            return_20d=_to_float(f.return_20d if f else None),
            return_60d=_to_float(f.return_60d if f else None),
            ma5=_to_float(f.ma5 if f else None),
            ma10=_to_float(f.ma10 if f else None),
            ma20=_to_float(f.ma20 if f else None),
            ma60=_to_float(f.ma60 if f else None),
            ma_position=_to_float(f.ma_position if f else None),
            ma_bull_arrange=_to_bool(f.ma_bull_arrange if f else None),
            rsi_14=_to_float(f.rsi_14 if f else None),
            macd=_to_float(f.macd if f else None),
            macd_signal=_to_float(f.macd_signal if f else None),
            macd_hist=_to_float(f.macd_hist if f else None),
            macd_golden_cross=_to_bool(f.macd_golden_cross if f else None),
            kdj_k=_to_float(f.kdj_k if f else None),
            kdj_d=_to_float(f.kdj_d if f else None),
            kdj_j=_to_float(f.kdj_j if f else None),
            atr_14=_to_float(f.atr_14 if f else None),
            boll_upper=_to_float(f.boll_upper if f else None),
            boll_mid=_to_float(f.boll_mid if f else None),
            boll_lower=_to_float(f.boll_lower if f else None),
            boll_width=_to_float(f.boll_width if f else None),
            high_20d=_to_float(f.high_20d if f else None),
            break_high_20d=_to_bool(f.break_high_20d if f else None),
            pe_ttm=_to_float(f.pe_ttm if f else None),
            pb=_to_float(f.pb if f else None),
            roe_latest=_to_float(f.roe_latest if f else None),
            net_profit_yoy_latest=_to_float(f.net_profit_yoy_latest if f else None),
            revenue_yoy_latest=_to_float(f.revenue_yoy_latest if f else None),
            market_cap=_to_float(f.market_cap if f else None),
        ))

    return inputs
