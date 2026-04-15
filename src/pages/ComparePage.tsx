import type { CompareItem, FundDetailResponse } from "../types";
import { formatDateTime, formatNav, formatPercent, signedClass } from "../utils/fund";

type ComparePageProps = {
  items: CompareItem[];
  loading: boolean;
  onRemove: (code: string) => Promise<void>;
  onOpenDetail: (detail: FundDetailResponse | null) => void;
  onUseForHolding: (code: string) => void;
};

export function ComparePage({ items, loading, onRemove, onOpenDetail, onUseForHolding }: ComparePageProps) {
  return (
    <section className="panel compare-panel">
      <div className="section-head">
        <div>
          <h3>基金对比</h3>
          <p>这里改成并排卡片，不再用一整张横向大表去挤 4 只基金。核心指标直接平铺，看差异会更快。</p>
        </div>
        <div className="badge badge-muted">共 {items.length} 条</div>
      </div>

      {loading ? (
        <div className="empty-state">正在加载对比池...</div>
      ) : items.length === 0 ? (
        <div className="empty-state">对比池还是空的。先去条件选基页把候选基金加进来，横向对比会更顺手。</div>
      ) : (
        <div className="compare-card-grid">
          {items.map((item) => (
            <article key={item.code} className="compare-card">
              <div className="compare-card-head">
                <div className="compare-card-title">
                  <strong>{item.detail?.fund.name || item.screener?.name || item.code}</strong>
                  <span>{item.code}</span>
                </div>
                <span className="badge badge-muted">{formatDateTime(item.addedAt)}</span>
              </div>

              <div className="tag-row">
                {item.screener?.category ? <span className="tag-pill subtle">{item.screener.category}</span> : null}
                {item.screener?.sectorTags.slice(0, 2).map((tag) => (
                  <span key={tag} className="tag-pill">{tag}</span>
                ))}
              </div>

              <div className="compare-metric-grid">
                <div className="detail-card">
                  <span>最新净值</span>
                  <strong>{formatNav(item.detail?.fund.latestNav ?? item.screener?.metrics.latestNav ?? null)}</strong>
                </div>
                <div className="detail-card">
                  <span>近 1 月</span>
                  <strong className={signedClass(item.screener?.metrics.return1m ?? null)}>{formatPercent(item.screener?.metrics.return1m ?? null)}</strong>
                </div>
                <div className="detail-card">
                  <span>近 3 月</span>
                  <strong className={signedClass(item.screener?.metrics.return3m ?? null)}>{formatPercent(item.screener?.metrics.return3m ?? null)}</strong>
                </div>
                <div className="detail-card">
                  <span>近 1 年</span>
                  <strong className={signedClass(item.screener?.metrics.return1y ?? null)}>{formatPercent(item.screener?.metrics.return1y ?? null)}</strong>
                </div>
                <div className="detail-card">
                  <span>最大回撤</span>
                  <strong className={signedClass(item.screener?.metrics.maxDrawdown1y ?? null)}>{formatPercent(item.screener?.metrics.maxDrawdown1y ?? null)}</strong>
                </div>
                <div className="detail-card">
                  <span>波动率</span>
                  <strong>{formatPercent(item.screener?.metrics.volatility1y ?? null)}</strong>
                </div>
                <div className="detail-card">
                  <span>费率</span>
                  <strong>{item.screener?.metrics.feeRate !== null && item.screener?.metrics.feeRate !== undefined ? `${item.screener.metrics.feeRate.toFixed(2)}%` : "--"}</strong>
                </div>
                <div className="detail-card">
                  <span>总分</span>
                  <strong>{item.screener?.score.total ?? "--"}</strong>
                </div>
              </div>

              {item.error ? <div className="empty-inline compact-empty">{item.error}</div> : null}

              <div className="row-actions">
                <button type="button" className="inline-button" onClick={() => onOpenDetail(item.detail)}>
                  查看总览
                </button>
                <button type="button" className="inline-button" onClick={() => onUseForHolding(item.code)}>
                  录入持有
                </button>
                <button type="button" className="inline-button danger-text" onClick={() => void onRemove(item.code)}>
                  移除
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
