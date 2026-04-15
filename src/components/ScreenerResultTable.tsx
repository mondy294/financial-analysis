import type { FundUniverseItem } from "../types";
import { formatNav, formatPercent, signedClass } from "../utils/fund";

type ScreenerResultTableProps = {
  items: FundUniverseItem[];
  total: number;
  loading: boolean;
  selectedCode: string | null;
  compareCodes: string[];
  watchlistCodes: string[];
  onSelect: (item: FundUniverseItem) => void;
  onViewScore: (item: FundUniverseItem) => void;
  onOpenDetail: (code: string) => void;
  onAddWatchlist: (code: string) => Promise<void>;
  onAddCompare: (code: string) => Promise<void>;
  onUseForHolding: (code: string) => void;
};

export function ScreenerResultTable({
  items,
  total,
  loading,
  selectedCode,
  compareCodes,
  watchlistCodes,
  onSelect,
  onViewScore,
  onOpenDetail,
  onAddWatchlist,
  onAddCompare,
  onUseForHolding,
}: ScreenerResultTableProps) {
  return (
    <section className="panel screener-result-panel">
      <div className="section-head compact-head">
        <div>
          <h3>基金列表</h3>
          <p>这里固定作为主视图。先点一行选中基金，再看评分、详情、自选、对比或录入持有。</p>
        </div>

        <div className="badge badge-muted">命中 {total} 条</div>
      </div>

      {loading ? (
        <div className="empty-state">正在根据条件重排基金池...</div>
      ) : items.length === 0 ? (
        <div className="empty-state">当前条件下没有命中基金。可以先放宽收益、回撤或板块条件。</div>
      ) : (
        <div className="table-shell">
          <table className="data-table screener-table">
            <thead>
              <tr>
                <th>基金</th>
                <th>分类 / 板块</th>
                <th>总分</th>
                <th>近 1 月</th>
                <th>近 3 月</th>
                <th>近 1 年</th>
                <th>回撤</th>
                <th>波动率</th>
                <th>费率</th>
                <th>规模</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const inCompare = compareCodes.includes(item.code);
                const inWatchlist = watchlistCodes.includes(item.code);
                return (
                  <tr key={item.code} className={selectedCode === item.code ? "selected-row" : undefined} onClick={() => onSelect(item)}>
                    <td>
                      <div className="fund-cell">
                        <strong>{item.name}</strong>
                        <span>{item.code}</span>
                      </div>
                    </td>
                    <td>
                      <div className="tag-row table-tags">
                        <span className="tag-pill subtle">{item.category}</span>
                        {item.sectorTags.slice(0, 2).map((tag) => (
                          <span key={tag} className="tag-pill">{tag}</span>
                        ))}
                      </div>
                    </td>
                    <td>
                      <strong className="score-inline">{item.score.total}</strong>
                    </td>
                    <td className={signedClass(item.metrics.return1m)}>{formatPercent(item.metrics.return1m)}</td>
                    <td className={signedClass(item.metrics.return3m)}>{formatPercent(item.metrics.return3m)}</td>
                    <td className={signedClass(item.metrics.return1y)}>{formatPercent(item.metrics.return1y)}</td>
                    <td className={signedClass(item.metrics.maxDrawdown1y)}>{formatPercent(item.metrics.maxDrawdown1y)}</td>
                    <td>{formatPercent(item.metrics.volatility1y)}</td>
                    <td>{item.metrics.feeRate !== null ? `${item.metrics.feeRate.toFixed(2)}%` : "--"}</td>
                    <td>{item.metrics.size !== null ? `${item.metrics.size.toFixed(2)} 亿` : "--"}</td>
                    <td>
                      <div className="row-actions stacked-actions">
                        <button type="button" className="inline-button" onClick={(event) => { event.stopPropagation(); onViewScore(item); }}>
                          查看评分
                        </button>
                        <button type="button" className="inline-button" onClick={(event) => { event.stopPropagation(); onOpenDetail(item.code); }}>
                          看详情
                        </button>
                        <button type="button" className="inline-button" disabled={inWatchlist} onClick={(event) => { event.stopPropagation(); void onAddWatchlist(item.code); }}>
                          {inWatchlist ? "已在自选" : "加自选"}
                        </button>
                        <button type="button" className="inline-button" disabled={inCompare} onClick={(event) => { event.stopPropagation(); void onAddCompare(item.code); }}>
                          {inCompare ? "已在对比" : "加对比"}
                        </button>
                        <button type="button" className="inline-button" onClick={(event) => { event.stopPropagation(); onUseForHolding(item.code); }}>
                          录入持有
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
