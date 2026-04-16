import type { FundAgentBatchAnalysisResult, FundDetailResponse, WatchlistItem } from "../types";
import { formatDateTime, formatNav, formatPercent, signedClass } from "../utils/fund";

type WatchlistPageProps = {
  items: WatchlistItem[];
  loading: boolean;
  batchAnalyzing: boolean;
  batchResult: FundAgentBatchAnalysisResult | null;
  onAnalyzeAll: () => Promise<void>;
  onRemove: (code: string) => Promise<void>;
  onOpenDetail: (detail: FundDetailResponse | null) => void;
  onUseForHolding: (code: string) => void;
};

function formatDuration(durationMs: number | null | undefined) {
  if (typeof durationMs !== "number" || !Number.isFinite(durationMs) || durationMs < 0) {
    return "--";
  }

  if (durationMs < 1_000) {
    return `${Math.round(durationMs)} ms`;
  }

  if (durationMs < 60_000) {
    return `${(durationMs / 1_000).toFixed(durationMs >= 10_000 ? 0 : 1)} 秒`;
  }

  const minutes = Math.floor(durationMs / 60_000);
  const seconds = Math.round((durationMs % 60_000) / 1_000);
  return `${minutes} 分 ${seconds} 秒`;
}

function buildBatchResultText(batchResult: FundAgentBatchAnalysisResult | null) {
  if (!batchResult) {
    return "点击之后会按当前自选列表逐只跑 Agent 分析，并覆盖保存每只基金的最新结论与未来预测。";
  }

  if (batchResult.total === 0) {
    return "最近一次运行时自选列表为空，所以没有实际触发分析。";
  }

  if (batchResult.failed === 0) {
    return `最近一次共跑了 ${batchResult.total} 只，全部成功。`;
  }

  return `最近一次共跑了 ${batchResult.total} 只，成功 ${batchResult.succeeded} 只，失败 ${batchResult.failed} 只。`;
}

function buildFailureSummary(batchResult: FundAgentBatchAnalysisResult | null) {
  if (!batchResult || batchResult.failed === 0) {
    return null;
  }

  const failedItems = batchResult.items.filter((item) => item.status === "failed");
  if (failedItems.length === 0) {
    return null;
  }

  return failedItems
    .slice(0, 4)
    .map((item) => `${item.fundCode}${item.error ? `：${item.error}` : ""}`)
    .join("；");
}

export function WatchlistPage({
  items,
  loading,
  batchAnalyzing,
  batchResult,
  onAnalyzeAll,
  onRemove,
  onOpenDetail,
  onUseForHolding,
}: WatchlistPageProps) {
  const failureSummary = buildFailureSummary(batchResult);

  return (
    <section className="panel">
      <div className="section-head">
        <div>
          <h3>我的自选</h3>
          <p>这里是观察池。看顺眼的先放进来，想进一步记录仓位就直接转去我的持有。</p>
        </div>
        <div className="badge badge-muted">共 {items.length} 条</div>
      </div>

      <div className="watchlist-batch-panel">
        <div className="watchlist-batch-copy">
          <span className="eyebrow">Batch Agent Run</span>
          <strong>{batchAnalyzing ? "正在逐只跑自选 Agent 分析..." : "一键批量跑自选 Agent 分析"}</strong>
          <p>{buildBatchResultText(batchResult)}</p>
          {batchResult ? (
            <div className="watchlist-batch-meta">
              <span>开始：{formatDateTime(batchResult.startedAt)}</span>
              <span>结束：{formatDateTime(batchResult.finishedAt)}</span>
              <span>耗时：{formatDuration(batchResult.durationMs)}</span>
            </div>
          ) : null}
          {failureSummary ? <p className="watchlist-batch-warning">失败明细：{failureSummary}</p> : null}
        </div>

        <div className="watchlist-batch-actions">
          <button
            type="button"
            className="primary-button"
            onClick={() => void onAnalyzeAll()}
            disabled={loading || batchAnalyzing || items.length === 0}
          >
            {batchAnalyzing ? "批量分析中..." : items.length === 0 ? "先加自选基金" : "批量跑 Agent 分析"}
          </button>
          <p>这会复用现有单基金分析链路，按当前自选列表逐只覆盖写入最新缓存。</p>
        </div>
      </div>

      {loading ? (
        <div className="empty-state">正在加载自选列表...</div>
      ) : items.length === 0 ? (
        <div className="empty-state">还没有自选基金。先在顶部查一只基金，再点“添加到我的自选”。</div>
      ) : (
        <div className="watchlist-grid">
          {items.map((item) => (
            <article key={item.code} className="watch-card">
              <div className="watch-card-head">
                <div>
                  <strong>{item.detail?.fund.name || item.code}</strong>
                  <span>{item.code}</span>
                </div>
                <span className="badge badge-muted">{formatDateTime(item.addedAt)}</span>
              </div>

              {item.detail ? (
                <>
                  <div className="watch-card-metrics">
                    <div>
                      <span>最新净值</span>
                      <strong>{formatNav(item.detail.fund.latestNav)}</strong>
                    </div>
                    <div>
                      <span>实时估算涨跌</span>
                      <strong className={signedClass(item.detail.fund.estimatedChangeRate)}>{formatPercent(item.detail.fund.estimatedChangeRate)}</strong>
                    </div>
                    <div>
                      <span>近 1 月</span>
                      <strong className={signedClass(item.detail.performance.oneMonth)}>{formatPercent(item.detail.performance.oneMonth)}</strong>
                    </div>
                    <div>
                      <span>近 1 年</span>
                      <strong className={signedClass(item.detail.performance.oneYear)}>{formatPercent(item.detail.performance.oneYear)}</strong>
                    </div>
                  </div>

                  <div className="row-actions spaced-top">
                    <button type="button" className="inline-button" onClick={() => onOpenDetail(item.detail)}>
                      查看总览
                    </button>
                    <button type="button" className="inline-button" onClick={() => onUseForHolding(item.code)}>
                      录入持有
                    </button>
                    <button type="button" className="inline-button danger-text" onClick={() => onRemove(item.code)}>
                      移除
                    </button>
                  </div>
                </>
              ) : (
                <div className="empty-inline">
                  <p>{item.error || "这只基金暂时拉不到详情。"}</p>
                  <div className="row-actions">
                    <button type="button" className="inline-button danger-text" onClick={() => onRemove(item.code)}>
                      移除
                    </button>
                  </div>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
