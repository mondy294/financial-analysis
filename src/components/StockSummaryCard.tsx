import { useEffect, useState } from "react";
import { analyzeStockWithAgent, getSavedStockAgentAnalysis } from "../api/client";
import type { FundAgentForecastScenario, StockAgentAnalysisRecord, StockAnalysisResponse } from "../types";
import { formatAmount, formatDateTime, formatPercent, signedClass } from "../utils/fund";
import { FundAgentNewsDigest } from "./FundAgentNewsDigest";
import { StockKLineChartPanel } from "./StockKLineChartPanel";

type StockSummaryCardProps = {
  detail: StockAnalysisResponse;
};

const performanceCards = [
  { label: "近 1 周", key: "oneWeek" },
  { label: "近 1 月", key: "oneMonth" },
  { label: "近 3 月", key: "threeMonths" },
  { label: "近 6 月", key: "sixMonths" },
  { label: "近 1 年", key: "oneYear" },
  { label: "年初至今", key: "yearToDate" },
  { label: "可见区间以来", key: "sinceInception" },
] as const;

function formatPrice(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }
  return Number(value).toFixed(2);
}

function formatSignedPrice(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }
  const numeric = Number(value);
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(2)}`;
}

function formatVolume(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }
  const numeric = Number(value);
  if (numeric >= 1e8) {
    return `${(numeric / 1e8).toFixed(2)} 亿股`;
  }
  if (numeric >= 1e4) {
    return `${(numeric / 1e4).toFixed(2)} 万股`;
  }
  return `${numeric.toFixed(0)} 股`;
}

function ensureStringList(value: unknown) {
  if (!Array.isArray(value)) {
    return [] as string[];
  }
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function ensureText(value: string | null | undefined, fallback = "--") {
  return typeof value === "string" && value.trim().length > 0 ? value : fallback;
}

function renderList(items: unknown, emptyText = "暂无可展示内容") {
  const safeItems = ensureStringList(items);
  if (safeItems.length === 0) {
    return <p className="empty-state compact-empty">{emptyText}</p>;
  }
  return (
    <ul className="agent-analysis-list">
      {safeItems.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function renderPlanLevels(levels: StockAgentAnalysisRecord["report"]["planLevels"]) {
  if (!Array.isArray(levels) || levels.length === 0) {
    return <p className="empty-state compact-empty">暂无关键价位计划</p>;
  }

  return (
    <div className="agent-tool-trace-list">
      {levels.map((level, index) => (
        <article key={`${level.kind}-${level.reference}-${index}`} className="agent-tool-trace-item">
          <h4>{level.kind}</h4>
          <p>参考位：{formatPrice(level.nav)}{level.relativeToLatest !== null && level.relativeToLatest !== undefined ? `（相对当前 ${formatPercent(level.relativeToLatest)}）` : ""}</p>
          <p>依据：{ensureText(level.reference, "--")}</p>
          <p>触发条件：{ensureText(level.condition, "--")}</p>
          <p>执行动作：{ensureText(level.action, "--")}</p>
          <p>原因：{ensureText(level.reason, "--")}</p>
        </article>
      ))}
    </div>
  );
}

function renderForecastScenarios(scenarios: FundAgentForecastScenario[] | null | undefined) {
  if (!Array.isArray(scenarios) || scenarios.length === 0) {
    return <p className="empty-state compact-empty">暂无可展示的未来路径预测</p>;
  }

  return (
    <div className="agent-tool-trace-list forecast-scenario-list">
      {scenarios.map((scenario) => (
        <article key={scenario.id} className="agent-tool-trace-item forecast-scenario-item">
          <h4>{scenario.label}</h4>
          <p>概率：{Math.round(scenario.probability)}% · 目标涨跌：{formatPercent(scenario.targetReturn)} · 目标价：{formatPrice(scenario.targetNav)}</p>
          <p>路径风格：{ensureText(scenario.pathStyle, "--")} · 波动级别：{ensureText(scenario.volatility, "--")}</p>
          <p>分支说明：{ensureText(scenario.summary, "--")}</p>
          <p>更可能触发于：{ensureText(scenario.trigger, "--")}</p>
        </article>
      ))}
    </div>
  );
}

export function StockSummaryCard({ detail }: StockSummaryCardProps) {
  const { stock, performance, kline, trendAnalysis } = detail;
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [agentResult, setAgentResult] = useState<StockAgentAnalysisRecord | null>(null);
  const [savedAgentRecord, setSavedAgentRecord] = useState<StockAgentAnalysisRecord | null>(null);
  const [savedAgentLoading, setSavedAgentLoading] = useState(false);
  const [savedAgentError, setSavedAgentError] = useState<string | null>(null);
  const [analysisPromptOpen, setAnalysisPromptOpen] = useState(false);
  const [analysisUserQuestion, setAnalysisUserQuestion] = useState("");

  useEffect(() => {
    setAgentLoading(false);
    setAgentError(null);
    setAgentResult(null);
    setSavedAgentRecord(null);
    setSavedAgentLoading(false);
    setSavedAgentError(null);
    setAnalysisPromptOpen(false);
    setAnalysisUserQuestion("");
  }, [stock.code]);

  useEffect(() => {
    let cancelled = false;
    setSavedAgentLoading(true);
    setSavedAgentError(null);

    void getSavedStockAgentAnalysis(stock.code)
      .then((payload) => {
        if (!cancelled) {
          setSavedAgentRecord(payload);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setSavedAgentRecord(null);
          setSavedAgentError(error instanceof Error ? error.message : "加载股票 AI 分析记录失败。");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setSavedAgentLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [stock.code]);

  async function handleRunAgentAnalysis(extraUserQuestion?: string) {
    const nextUserQuestion = (extraUserQuestion ?? analysisUserQuestion).trim();
    setAgentLoading(true);
    setAgentError(null);

    try {
      const payload = await analyzeStockWithAgent(stock.code, {
        horizon: "未来 1-3 个月",
        userQuestion: nextUserQuestion || undefined,
      });
      setAgentResult(payload);
      setSavedAgentRecord(payload);
      setSavedAgentError(null);
      setAnalysisPromptOpen(false);
      setAnalysisUserQuestion("");
    } catch (error) {
      setAgentError(error instanceof Error ? error.message : "股票 AI 分析失败，请稍后再试。");
    } finally {
      setAgentLoading(false);
    }
  }

  const displayedAgentRecord = agentResult ?? savedAgentRecord;
  const agentReport = displayedAgentRecord?.report ?? null;
  const agentForecast = displayedAgentRecord?.forecast ?? null;
  const agentToolTrace = Array.isArray(displayedAgentRecord?.toolTrace) ? displayedAgentRecord.toolTrace : [];
  const showingSavedAgentRecord = Boolean(savedAgentRecord && !agentResult && displayedAgentRecord);

  return (
    <div className="content-grid">
      <section className="panel spotlight-panel">
        <div className="section-head">
          <div>
            <div className="eyebrow">当前查看</div>
            <h2 className="spotlight-title">{stock.name}</h2>
            <p className="spotlight-subtitle">股票代码 {stock.code} · {stock.exchange ?? "--"} · 最新交易日 {stock.latestTradeDate}</p>
          </div>
          <div className="badge-wrap">
            <span className="badge badge-muted">{trendAnalysis.latest.signal}</span>
            <span className="badge badge-muted">{savedAgentRecord ? `已存分析 ${formatDateTime(savedAgentRecord.updatedAt)}` : "暂未缓存 AI 结果"}</span>
          </div>
        </div>

        <div className="metric-grid">
          <article className="metric-card">
            <span>最新价</span>
            <strong>{formatPrice(stock.latestPrice ?? stock.latestClose)}</strong>
          </article>
          <article className="metric-card">
            <span>涨跌额</span>
            <strong className={signedClass(stock.changeAmount)}>{formatSignedPrice(stock.changeAmount)}</strong>
          </article>
          <article className="metric-card">
            <span>涨跌幅</span>
            <strong className={signedClass(stock.changeRate)}>{formatPercent(stock.changeRate)}</strong>
          </article>
          <article className="metric-card">
            <span>昨收</span>
            <strong>{formatPrice(stock.previousClose)}</strong>
          </article>
        </div>

        <div className="detail-grid">
          <div className="detail-card"><span>开盘</span><strong>{formatPrice(stock.openPrice)}</strong></div>
          <div className="detail-card"><span>最高</span><strong>{formatPrice(stock.highPrice)}</strong></div>
          <div className="detail-card"><span>最低</span><strong>{formatPrice(stock.lowPrice)}</strong></div>
          <div className="detail-card"><span>振幅</span><strong>{formatPercent(stock.amplitude)}</strong></div>
          <div className="detail-card"><span>换手率</span><strong>{formatPercent(stock.turnoverRate)}</strong></div>
          <div className="detail-card"><span>成交量</span><strong>{formatVolume(stock.volume)}</strong></div>
          <div className="detail-card"><span>成交额</span><strong>{formatAmount(stock.amount)}</strong></div>
          <div className="detail-card"><span>K 线窗口</span><strong>{trendAnalysis.windowDays} 天</strong></div>
        </div>

        <div className="summary-actions">
          <button type="button" className="primary-button" onClick={() => setAnalysisPromptOpen(true)} disabled={agentLoading}>
            {agentLoading ? "AI 分析中..." : "AI 分析未来走势"}
          </button>
          {savedAgentLoading ? <span className="section-note">正在读取已保存记录...</span> : null}
          {savedAgentError ? <span className="section-note danger-text">{savedAgentError}</span> : null}
        </div>

        {analysisPromptOpen ? (
          <div className="utility-drawer-overlay" onClick={() => !agentLoading && setAnalysisPromptOpen(false)}>
            <section className="utility-drawer utility-drawer--narrow" onClick={(event) => event.stopPropagation()}>
              <div className="utility-drawer-head">
                <div>
                  <span className="eyebrow">AI Analysis Input</span>
                  <h3>补充你的股票分析关注点</h3>
                  <p>可选。你可以告诉 AI 你更关注突破、回踩、风控、短线节奏还是未来 1-3 个月的路径分支。</p>
                </div>
                <button type="button" className="secondary-button" onClick={() => setAnalysisPromptOpen(false)} disabled={agentLoading}>
                  关闭
                </button>
              </div>

              <div className="utility-drawer-content">
                <label>
                  <span>补充说明</span>
                  <textarea
                    value={analysisUserQuestion}
                    onChange={(event) => setAnalysisUserQuestion(event.target.value)}
                    placeholder="例如：我更关注回踩 MA20 后是否还能继续拿；或者我只打算做一个月波段，想知道当前更适合等突破还是等回落。"
                  />
                </label>

                <div className="utility-note-panel">
                  <div className="section-note">
                    默认会分析最近一周变化、当前 K 线结构、关键价位计划、未来 1-3 个月路径分支和重新评估条件。
                  </div>
                </div>

                <div className="form-actions">
                  <button type="button" className="primary-button" onClick={() => void handleRunAgentAnalysis()} disabled={agentLoading}>
                    {agentLoading ? "AI 分析中..." : "开始分析"}
                  </button>
                  <button type="button" className="secondary-button" onClick={() => void handleRunAgentAnalysis("")} disabled={agentLoading}>
                    跳过补充直接分析
                  </button>
                </div>
              </div>
            </section>
          </div>
        ) : null}

        {displayedAgentRecord ? (
          <div className="agent-record-inline-note">
            <span className="subtle-label">股票 AI 记录</span>
            <strong>{showingSavedAgentRecord ? `当前显示的是缓存记录，保存于 ${formatDateTime(displayedAgentRecord.updatedAt)}` : `当前显示的是本次新分析，生成于 ${formatDateTime(displayedAgentRecord.generatedAt)}`}</strong>
            <p>新的股票分析结果会直接覆盖保存到现有缓存，下次再搜同一只股票会自动回显。</p>
          </div>
        ) : null}

        {agentError ? (
          <div className="warning-box agent-analysis-block">
            <strong>AI 分析失败</strong>
            <p>{agentError}</p>
          </div>
        ) : null}

        {displayedAgentRecord && agentReport ? (
          <section className="agent-analysis-card">
            <div className="section-head compact-head">
              <div>
                <span className="eyebrow">Stock Agent Analysis</span>
                <h3>未来走势、操作建议与路径预测</h3>
                <p>股票分析会单独使用股票 skill 和股票推理流程，重点看 K 线、均线、布林带、换手与外部扰动。</p>
              </div>
              <div className="badge-wrap">
                <span className="badge badge-emerald">{ensureText(agentReport.outlook, "无法判断")}</span>
                <span className="badge badge-muted">置信度 {agentReport.confidence ?? "--"}</span>
                <span className="badge badge-muted">{showingSavedAgentRecord ? "已保存记录" : "本次新分析"}</span>
                <span className="badge badge-muted">{formatDateTime(displayedAgentRecord.generatedAt)}</span>
              </div>
            </div>

            <div className="agent-analysis-hero">
              <article className="agent-analysis-highlight">
                <span>结论摘要</span>
                <strong>{ensureText(agentReport.summary, "暂无分析摘要")}</strong>
                <p>{ensureText(agentReport.actionAdvice, "暂无具体操作建议")}</p>
              </article>
              <article className="agent-analysis-highlight">
                <span>当前计划</span>
                <strong>{ensureText(agentReport.actionTag, "待补充")}</strong>
                <p>{ensureText(agentReport.planSummary, "暂无可执行计划")}</p>
              </article>
            </div>

            <FundAgentNewsDigest report={agentReport} toolTrace={agentToolTrace} />

            <div className="agent-analysis-grid">
              <article className="detail-card">
                <span>分析周期</span>
                <strong>{ensureText(agentReport.horizon, "--")}</strong>
              </article>
              <article className="detail-card">
                <span>仓位幅度</span>
                <strong>{ensureText(agentReport.positionSizing, "暂无建议")}</strong>
              </article>
              <article className="detail-card">
                <span>持仓背景</span>
                <strong>{ensureText(agentReport.holdingContext, "暂无持仓背景")}</strong>
              </article>
              <article className="detail-card">
                <span>更适合谁</span>
                <strong>{ensureText(agentReport.suitableFor, "暂无结论")}</strong>
              </article>
              <article className="detail-card">
                <span>不太适合谁</span>
                <strong>{ensureText(agentReport.unsuitableFor, "暂无结论")}</strong>
              </article>
            </div>

            <div className="agent-analysis-flow">
              <article className="agent-analysis-section">
                <h4>最近一周发生了什么</h4>
                <p>{ensureText(agentReport.recentWeekSummary, "暂无最近一周变化说明")}</p>
              </article>
              <article className="agent-analysis-section">
                <h4>变化的可能原因</h4>
                {renderList(agentReport.recentWeekDrivers, "暂无变化原因说明")}
              </article>
              <article className="agent-analysis-section">
                <h4>现在该怎么做</h4>
                <p>{ensureText(agentReport.positionInstruction, "暂无明确动作")}</p>
                <p>建议幅度：{ensureText(agentReport.positionSizing, "暂无建议")}</p>
              </article>
              <article className="agent-analysis-section">
                <h4>未来路径预测</h4>
                <p>主图右侧已经把这几条分支沿着收盘价延伸出来了，鼠标移上去能直接看日期、目标价和概率。</p>
                {renderForecastScenarios(agentForecast?.scenarios)}
              </article>
              <article className="agent-analysis-section">
                <h4>执行规则</h4>
                {renderList(agentReport.executionRules, "暂无执行规则")}
              </article>
              <article className="agent-analysis-section">
                <h4>重新评估条件</h4>
                {renderList(agentReport.reEvaluationTriggers, "暂无重新评估条件")}
              </article>
              <article className="agent-analysis-section">
                <h4>关键价位计划</h4>
                {renderPlanLevels(agentReport.planLevels)}
              </article>
              <article className="agent-analysis-section">
                <h4>核心依据</h4>
                {renderList(agentReport.reasoning, "暂无核心依据")}
              </article>
              <article className="agent-analysis-section">
                <h4>主要风险</h4>
                {renderList(agentReport.risks, "暂无主要风险提示")}
              </article>
              <article className="agent-analysis-section">
                <h4>接下来盯这些</h4>
                {renderList(agentReport.watchItems, "暂无后续观察点")}
              </article>
            </div>

            {agentToolTrace.length > 0 ? (
              <div className="agent-tool-trace">
                <strong>{showingSavedAgentRecord ? "这份已保存记录当时用到的工具" : "本次用到的工具"}</strong>
                <div className="agent-tool-trace-list">
                  {agentToolTrace.map((item) => (
                    <article key={`${item.toolName}-${item.summary}`} className="agent-tool-trace-item">
                      <h4>{item.toolName}</h4>
                      <p>{item.summary}</p>
                    </article>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="disclaimer-banner">
              <strong>风险提示</strong>
              <span>{ensureText(agentReport.disclaimer, "以上内容仅供研究参考，不构成投资建议。")}</span>
            </div>
          </section>
        ) : null}
      </section>

      <StockKLineChartPanel detail={detail} forecast={agentForecast} />

      <section className="panel">
        <div className="section-head">
          <div>
            <h3>阶段表现</h3>
            <p>股票这页默认还是把常用阶段涨跌幅摊开，方便先看中短期强弱，再回到 K 线上确认结构。</p>
          </div>
        </div>
        <div className="performance-grid">
          {performanceCards.map((item) => {
            const value = performance[item.key];
            return (
              <article key={item.key} className="performance-card">
                <span>{item.label}</span>
                <strong className={signedClass(value)}>{formatPercent(value)}</strong>
              </article>
            );
          })}
          <article className="performance-card">
            <span>最近 30 日收盘区间</span>
            <strong>{formatPrice(performance.lowestRecentClose)} - {formatPrice(performance.highestRecentClose)}</strong>
          </article>
        </div>
      </section>

      <section className="panel">
        <div className="section-head">
          <div>
            <h3>最近 30 条日 K 线原始记录</h3>
            <p>原始 K 线表格还是保留着，方便你回头核对开高低收、振幅和换手率，不只听 AI 讲故事。</p>
          </div>
        </div>
        <div className="table-shell">
          <table className="data-table stock-kline-table">
            <thead>
              <tr>
                <th>日期</th>
                <th className="align-right">开盘</th>
                <th className="align-right">收盘</th>
                <th className="align-right">最高</th>
                <th className="align-right">最低</th>
                <th className="align-right">涨跌额</th>
                <th className="align-right">涨跌幅</th>
                <th className="align-right">振幅</th>
                <th className="align-right">换手率</th>
              </tr>
            </thead>
            <tbody>
              {kline.slice(-30).reverse().map((item) => (
                <tr key={item.date}>
                  <td>{item.date}</td>
                  <td className="align-right">{formatPrice(item.open)}</td>
                  <td className={`align-right ${signedClass(item.changeRate)}`}>{formatPrice(item.close)}</td>
                  <td className="align-right">{formatPrice(item.high)}</td>
                  <td className="align-right">{formatPrice(item.low)}</td>
                  <td className={`align-right ${signedClass(item.changeAmount)}`}>{formatSignedPrice(item.changeAmount)}</td>
                  <td className={`align-right ${signedClass(item.changeRate)}`}>{formatPercent(item.changeRate)}</td>
                  <td className="align-right">{formatPercent(item.amplitude)}</td>
                  <td className="align-right">{formatPercent(item.turnoverRate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
