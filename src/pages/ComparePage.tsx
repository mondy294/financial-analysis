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
    <section className="panel">
      <div className="section-head">
        <div>
          <h3>基金对比</h3>
          <p>最多保留 4 只基金做横向对比。这里先看核心指标，想看细节再跳回总览页。</p>
        </div>
        <div className="badge badge-muted">共 {items.length} 条</div>
      </div>

      {loading ? (
        <div className="empty-state">正在加载对比池...</div>
      ) : items.length === 0 ? (
        <div className="empty-state">对比池还是空的。先去条件选基页把候选基金加进来，横向对比会更顺手。</div>
      ) : (
        <div className="table-shell">
          <table className="data-table compact-table">
            <thead>
              <tr>
                <th>基金</th>
                <th>最新净值</th>
                <th>近 1 月</th>
                <th>近 3 月</th>
                <th>近 1 年</th>
                <th>最大回撤</th>
                <th>波动率</th>
                <th>总分</th>
                <th>加入时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.code}>
                  <td>
                    <button type="button" className="link-button" onClick={() => onOpenDetail(item.detail)}>
                      <strong>{item.detail?.fund.name || item.screener?.name || item.code}</strong>
                      <span>{item.code}</span>
                    </button>
                  </td>
                  <td>{formatNav(item.detail?.fund.latestNav ?? item.screener?.metrics.latestNav ?? null)}</td>
                  <td className={signedClass(item.screener?.metrics.return1m ?? null)}>{formatPercent(item.screener?.metrics.return1m ?? null)}</td>
                  <td className={signedClass(item.screener?.metrics.return3m ?? null)}>{formatPercent(item.screener?.metrics.return3m ?? null)}</td>
                  <td className={signedClass(item.screener?.metrics.return1y ?? null)}>{formatPercent(item.screener?.metrics.return1y ?? null)}</td>
                  <td className={signedClass(item.screener?.metrics.maxDrawdown1y ?? null)}>{formatPercent(item.screener?.metrics.maxDrawdown1y ?? null)}</td>
                  <td>{formatPercent(item.screener?.metrics.volatility1y ?? null)}</td>
                  <td>{item.screener?.score.total ?? "--"}</td>
                  <td>{formatDateTime(item.addedAt)}</td>
                  <td>
                    <div className="row-actions">
                      <button type="button" className="inline-button" onClick={() => onUseForHolding(item.code)}>
                        录入持有
                      </button>
                      <button type="button" className="inline-button danger-text" onClick={() => void onRemove(item.code)}>
                        移除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
