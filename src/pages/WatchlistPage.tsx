import type { FundDetailResponse, WatchlistItem } from "../types";
import { formatDateTime, formatNav, formatPercent, signedClass } from "../utils/fund";

type WatchlistPageProps = {
  items: WatchlistItem[];
  loading: boolean;
  onRemove: (code: string) => Promise<void>;
  onOpenDetail: (detail: FundDetailResponse | null) => void;
  onUseForHolding: (code: string) => void;
};

export function WatchlistPage({ items, loading, onRemove, onOpenDetail, onUseForHolding }: WatchlistPageProps) {
  return (
    <section className="panel">
      <div className="section-head">
        <div>
          <h3>我的自选</h3>
          <p>这里是观察池。看顺眼的先放进来，想进一步记录仓位就直接转去我的持有。</p>
        </div>
        <div className="badge badge-muted">共 {items.length} 条</div>
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
