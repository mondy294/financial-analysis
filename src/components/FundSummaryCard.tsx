import { useEffect, useState } from "react";
import { analyzeFundWithAgent } from "../api/client";
import type { FundAgentAnalysisResponse, FundDetailResponse, FundHoldingStock, HoldingItem } from "../types";
import { formatAmount, formatDateTime, formatNav, formatPercent, signedClass } from "../utils/fund";
import { ChartPanel } from "./ChartPanel";

type FundSummaryCardProps = {
  detail: FundDetailResponse;
  inWatchlist: boolean;
  holding: HoldingItem | null;
  onAddWatchlist: (code: string) => Promise<void>;
  onRemoveWatchlist: (code: string) => Promise<void>;
  onUseForHolding: (code: string) => void;
};

const performanceCards = [
  { label: "近 1 周", key: "oneWeek" },
  { label: "近 1 月", key: "oneMonth" },
  { label: "近 3 月", key: "threeMonths" },
  { label: "近 6 月", key: "sixMonths" },
  { label: "近 1 年", key: "oneYear" },
  { label: "年初至今", key: "yearToDate" },
  { label: "成立以来", key: "sinceInception" },
] as const;

const stockNumberFormatter = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function formatStockNumber(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  return stockNumberFormatter.format(Number(value));
}

function formatSignedStockNumber(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  const numeric = Number(value);
  return `${numeric > 0 ? "+" : ""}${stockNumberFormatter.format(numeric)}`;
}

function formatHoldingShares(value: FundHoldingStock["holdingSharesWan"]) {
  return value === null || value === undefined ? "--" : `${stockNumberFormatter.format(value)} 万股`;
}

function formatHoldingMarketValue(value: FundHoldingStock["holdingMarketValueWan"]) {
  return value === null || value === undefined ? "--" : `${stockNumberFormatter.format(value)} 万元`;
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

function renderPlanLevels(levels: FundAgentAnalysisResponse["report"]["planLevels"]) {
  if (!Array.isArray(levels) || levels.length === 0) {
    return <p className="empty-state compact-empty">暂无关键价位计划</p>;
  }

  return (
    <div className="agent-tool-trace-list">
      {levels.map((level, index) => (
        <article key={`${level.kind}-${level.reference}-${index}`} className="agent-tool-trace-item">
          <h4>{level.kind}</h4>
          <p>参考位：{formatNav(level.nav)}{level.relativeToLatest !== null && level.relativeToLatest !== undefined ? `（相对当前 ${formatPercent(level.relativeToLatest)}）` : ""}</p>
          <p>依据：{ensureText(level.reference, "--")}</p>
          <p>触发条件：{ensureText(level.condition, "--")}</p>
          <p>执行动作：{ensureText(level.action, "--")}</p>
          <p>原因：{ensureText(level.reason, "--")}</p>
        </article>
      ))}
    </div>
  );
}

export function FundSummaryCard({
  detail,
  inWatchlist,
  holding,
  onAddWatchlist,
  onRemoveWatchlist,
  onUseForHolding,
}: FundSummaryCardProps) {
  const { fund, performance, navHistory, stockHoldings, stockHoldingsReportDate } = detail;
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [agentResult, setAgentResult] = useState<FundAgentAnalysisResponse | null>(null);

  useEffect(() => {
    setAgentLoading(false);
    setAgentError(null);
    setAgentResult(null);
  }, [fund.code]);

  async function handleRunAgentAnalysis() {
    setAgentLoading(true);
    setAgentError(null);

    try {
      const payload = await analyzeFundWithAgent(fund.code, {
        horizon: "未来 1-3 个月",
        userQuestion: "请先解释最近一周净值变化，再说明可能原因，并分析未来 1-3 个月走势；如果我有持仓，请结合当前持仓金额、成本净值和组合占比，给出明确的仓位动作、加减仓幅度，以及跌到哪些净值附近可以考虑加仓、反弹到哪些净值附近更适合减仓或重新评估。",
      });
      setAgentResult(payload);
    } catch (error) {
      setAgentError(error instanceof Error ? error.message : "基金 AI 分析失败，请稍后再试。");
    } finally {
      setAgentLoading(false);
    }
  }

  const agentReport = agentResult?.report ?? null;
  const agentToolTrace = Array.isArray(agentResult?.toolTrace) ? agentResult.toolTrace : [];

  return (

    <div className="content-grid">
      <section className="panel spotlight-panel">
        <div className="section-head">
          <div>
            <div className="eyebrow">当前查看</div>
            <h2 className="spotlight-title">{fund.name}</h2>
            <p className="spotlight-subtitle">
              基金代码 {fund.code} · 最新净值日期 {fund.latestNavDate}
            </p>
          </div>
          <div className="badge-wrap">
            <span className="badge badge-muted">{fund.estimateTime ? `${fund.estimateTime} 估值` : "仅净值数据"}</span>
            {inWatchlist ? <span className="badge badge-emerald">已在自选</span> : null}
            {holding ? <span className="badge badge-gold">{holding.status}</span> : null}
          </div>
        </div>

        <div className="metric-grid">
          <article className="metric-card">
            <span>最新单位净值</span>
            <strong>{formatNav(fund.latestNav)}</strong>
          </article>
          <article className="metric-card">
            <span>最新日涨跌</span>
            <strong className={signedClass(fund.latestDailyGrowthRate)}>{formatPercent(fund.latestDailyGrowthRate)}</strong>
          </article>
          <article className="metric-card">
            <span>实时估算涨跌</span>
            <strong className={signedClass(fund.estimatedChangeRate)}>{formatPercent(fund.estimatedChangeRate)}</strong>
          </article>
          <article className="metric-card">
            <span>累计净值</span>
            <strong>{formatNav(fund.latestCumulativeNav)}</strong>
          </article>
        </div>

        <div className="detail-grid">
          <div className="detail-card"><span>估算净值</span><strong>{formatNav(fund.estimatedNav)}</strong></div>
          <div className="detail-card"><span>申购状态</span><strong>{fund.purchaseStatus || "--"}</strong></div>
          <div className="detail-card"><span>赎回状态</span><strong>{fund.redemptionStatus || "--"}</strong></div>
          <div className="detail-card"><span>当前费率</span><strong>{fund.currentRate ? `${fund.currentRate}%` : "--"}</strong></div>
        </div>

        <div className="summary-actions">
          <button type="button" className="primary-button" onClick={() => onUseForHolding(fund.code)}>
            {holding ? "更新持有信息" : "录入到我的持有"}
          </button>
          {inWatchlist ? (
            <button type="button" className="secondary-button" onClick={() => onRemoveWatchlist(fund.code)}>
              从自选移除
            </button>
          ) : (
            <button type="button" className="secondary-button" onClick={() => onAddWatchlist(fund.code)}>
              添加到我的自选
            </button>
          )}
          <button type="button" className="secondary-button" onClick={() => void handleRunAgentAnalysis()} disabled={agentLoading}>
            {agentLoading ? "AI 分析中..." : "AI 分析未来走势"}
          </button>
        </div>

        {holding ? (
          <div className="holding-note-card">
            <div>
              <span className="subtle-label">我的持有</span>
              <strong>{holding.status}</strong>
            </div>
            <div>
              <span className="subtle-label">手动收益率</span>
              <strong className={signedClass(holding.holdingReturnRate)}>{formatPercent(holding.holdingReturnRate)}</strong>
            </div>
            <div>
              <span className="subtle-label">持仓金额</span>
              <strong>{formatAmount(holding.positionAmount)}</strong>
            </div>
            <div>
              <span className="subtle-label">成本净值</span>
              <strong>{formatNav(holding.costNav)}</strong>
            </div>
            <div>
              <span className="subtle-label">最近更新</span>
              <strong>{formatDateTime(holding.updatedAt)}</strong>
            </div>
          </div>
        ) : null}

        {agentError ? (
          <div className="warning-box agent-analysis-block">
            <strong>AI 分析失败</strong>
            <p>{agentError}</p>
          </div>
        ) : null}

        {agentResult && agentReport ? (
          <section className="agent-analysis-card">
            <div className="section-head compact-head">
              <div>
                <span className="eyebrow">Agent Analysis</span>
                <h3>未来走势与操作建议</h3>
                <p>这部分由项目内 Agent 结合 MCP 数据实时生成，属于研究辅助，不是自动交易信号。</p>
              </div>
              <div className="badge-wrap">
                <span className="badge badge-emerald">{ensureText(agentReport.outlook, "无法判断")}</span>
                <span className="badge badge-muted">置信度 {agentReport.confidence ?? "--"}</span>
                <span className="badge badge-muted">{formatDateTime(agentResult.generatedAt)}</span>
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
                <p>{ensureText(agentReport.positionInstruction, "暂无明确仓位动作")}</p>
                <p>建议幅度：{ensureText(agentReport.positionSizing, "暂无建议")}</p>
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
                <strong>本次用到的工具</strong>
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

      <ChartPanel points={detail.trend} costNav={holding?.costNav ?? null} />

      <section className="panel">
        <div className="section-head">
          <div>
            <h3>近期业绩表现</h3>
            <p>把常看的阶段收益摊开看，一眼就能分辨是短跑选手还是长线慢热型。</p>
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
            <span>最近 30 日波动区间</span>
            <strong>{formatNav(performance.lowestRecentNav)} - {formatNav(performance.highestRecentNav)}</strong>
          </article>
        </div>
      </section>

      <section className="panel">
        <div className="section-head">
          <div>
            <h3>持仓股票观察表</h3>
            <p>持仓结构按基金最近一次披露的季报展示，列表里的价格和涨跌幅使用股票实时行情，方便你直接看基金到底在涨什么、跌什么。</p>
          </div>
          <div className="badge-wrap">
            <span className="badge badge-muted">{stockHoldingsReportDate ? `持仓截止 ${stockHoldingsReportDate}` : "暂无持仓披露"}</span>
          </div>
        </div>

        {stockHoldings.length === 0 ? (
          <div className="empty-state compact-empty">这只基金暂时没有可展示的股票持仓，可能是基金类型不适用，或者最新季报尚未披露。</div>
        ) : (
          <>
            <div className="section-note">说明：持仓占比、持股数、持仓市值来自基金定期报告；最新价、涨跌额、涨跌幅来自股票实时行情。</div>
            <div className="table-shell">
              <table className="data-table compact-table holding-stock-table">
                <thead>
                  <tr>
                    <th>股票</th>
                    <th className="align-right">最新价</th>
                    <th className="align-right">涨跌额</th>
                    <th className="align-right">涨跌幅</th>
                    <th className="align-right">占净值比例</th>
                    <th className="align-right">持股数</th>
                    <th className="align-right">持仓市值</th>
                  </tr>
                </thead>
                <tbody>
                  {stockHoldings.map((item) => (
                    <tr key={`${item.code}-${item.exchange ?? "NA"}`}>
                      <td>
                        <div className="holding-stock-cell">
                          <strong>{item.name}</strong>
                          <span>{item.code}{item.exchange ? `.${item.exchange}` : ""}</span>
                        </div>
                      </td>
                      <td className="align-right">{formatStockNumber(item.latestPrice)}</td>
                      <td className={`align-right ${signedClass(item.changeAmount)}`}>{formatSignedStockNumber(item.changeAmount)}</td>
                      <td className={`align-right ${signedClass(item.changeRate)}`}>{formatPercent(item.changeRate)}</td>
                      <td className="align-right">{formatPercent(item.navRatio)}</td>
                      <td className="align-right">{formatHoldingShares(item.holdingSharesWan)}</td>
                      <td className="align-right">{formatHoldingMarketValue(item.holdingMarketValueWan)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <section className="panel">
        <div className="section-head">
          <div>
            <h3>最近 30 条净值记录</h3>
            <p>表格还是得留着，毕竟有些时候你想看的不是故事，是原始材料。</p>
          </div>
        </div>
        <div className="table-shell">
          <table className="data-table">
            <thead>
              <tr>
                <th>日期</th>
                <th>单位净值</th>
                <th>累计净值</th>
                <th>日涨跌</th>
                <th>申购</th>
                <th>赎回</th>
              </tr>
            </thead>
            <tbody>
              {navHistory.map((item) => (
                <tr key={item.date}>
                  <td>{item.date}</td>
                  <td>{formatNav(item.unitNav)}</td>
                  <td>{formatNav(item.cumulativeNav)}</td>
                  <td className={signedClass(item.dailyGrowthRate)}>{formatPercent(item.dailyGrowthRate)}</td>
                  <td>{item.purchaseStatus || "--"}</td>
                  <td>{item.redemptionStatus || "--"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
