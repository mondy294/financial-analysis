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
from datetime import date
from decimal import Decimal
from typing import Any

from loguru import logger

from quant_system.config.settings import AIConfig, get_settings


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

    # v2 新增：风险标记（Soft Penalty 命中项），阶段 A 不塞 regime
    risk_flags: list[str] = field(default_factory=list)
    # 共振度（用于 AI 判断信号强度）
    resonance_count: int = 0
    resonance_categories: list[str] = field(default_factory=list)

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


# ============================================================================
# Prompt 构造
# ============================================================================

SYSTEM_PROMPT = """你是一名严谨的 A 股量化分析师。你将收到一只股票在某个交易日的：
- 规则量化系统给出的评分和命中策略
- **共振度**（信号跨越几个大类）
- **规则系统标记的风险**（Soft Penalty 命中项，例如 RSI 偏高、5 日涨幅偏高、波动率异常等）
- 完整技术指标（趋势/动量/波动/量能/突破）
- 基本面快照（PE / PB / ROE / 增长率）
- 近期收益表现（1/5/20/60 日）

请基于这些数据做出**结构化、克制、专业**的分析。

严格约束：
1. **绝对不要给出"买入/卖出/持有"等交易指令**。可以描述"技术面偏多/偏空/中性"、"估值处于什么水位"等中性判断。
2. **只用数据说话**，不要编造未提供的信息（比如公司业务、消息面、行业地位等你不知道的都不要提）。
3. **规则系统已标记的风险必须逐条呼应**，不能视而不见。风险越多，语气越谨慎。
4. 语言精炼，**总长不超过 250 字**。
5. 使用 Markdown 格式，包含以下 4 个小节：
   - **技术面**：均线/动量/量能的组合解读（结合共振度评估信号强度）
   - **基本面**：估值 & 增长的对比（如果有数据）
   - **风险提示**：**逐条呼应规则系统标记的 risk_flags**，并加上自己发现的其它风险
   - **观察建议**：可跟踪的量化指标或价位阈值
6. 如果某类数据缺失（NULL），就跳过对应的判断，**不要说"数据缺失"这种废话**。

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


def build_user_prompt(inp: StockAIInput) -> str:
    """构造发给 LLM 的用户消息。"""
    lines = [
        f"# 分析对象：{inp.name}（{inp.code}）",
        f"交易日：{inp.trade_date.isoformat()}",
    ]
    if inp.industry:
        lines.append(f"行业：{inp.industry}")
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
    return resp.choices[0].message.content or ""


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
