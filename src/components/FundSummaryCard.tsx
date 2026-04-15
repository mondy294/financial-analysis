import type { FundDetailResponse, HoldingItem } from "../types";
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

export function FundSummaryCard({
  detail,
  inWatchlist,
  holding,
  onAddWatchlist,
  onRemoveWatchlist,
  onUseForHolding,
}: FundSummaryCardProps) {
  const { fund, performance, navHistory } = detail;

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
              <span className="subtle-label">最近更新</span>
              <strong>{formatDateTime(holding.updatedAt)}</strong>
            </div>
          </div>
        ) : null}
      </section>

      <ChartPanel points={detail.trend} />

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
