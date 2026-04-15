import type { FundUniverseItem } from "../types";
import { formatNav, formatPercent, signedClass } from "../utils/fund";

type FundScoreDrawerProps = {
  item: FundUniverseItem | null;
  onClose?: () => void;
};

const scoreRows: Array<{ key: keyof FundUniverseItem["score"]; label: string; max: number; description: string }> = [
  { key: "return", label: "收益能力", max: 30, description: "综合近 1 月 / 3 月 / 1 年收益。" },
  { key: "stability", label: "稳定性", max: 20, description: "波动更低、阶段收益更平顺会更高。" },
  { key: "drawdown", label: "回撤控制", max: 20, description: "1 年最大回撤越浅，得分越高。" },
  { key: "fee", label: "费用友好度", max: 10, description: "费率更低更划算。" },
  { key: "management", label: "管理持续性", max: 10, description: "V1 先用成立年限做代理。" },
  { key: "health", label: "规模/成立健康度", max: 10, description: "规模和成立年限都更健康时加分。" },
];

export function FundScoreDrawer({ item, onClose }: FundScoreDrawerProps) {
  if (!item) {
    return (
      <section className="panel score-drawer empty-drawer">
        <div className="section-head compact-head">
          <div>
            <h3>透明评分卡</h3>
            <p>点一只基金，就能看到它为什么排在这里，而不是一个黑盒分数。</p>
          </div>
        </div>
        <div className="empty-state">先从结果列表里选一只基金。</div>
      </section>
    );
  }

  return (
    <section className="panel score-drawer">
      <div className="section-head compact-head">
        <div>
          <span className="eyebrow">Score Card</span>
          <h3>{item.name}</h3>
          <p>{item.code} · {item.category} · {item.rawFundType ?? "类型待补全"}</p>
        </div>
        <div className="score-drawer-header-actions">
          <div className="score-total-chip">
            <span>总分</span>
            <strong>{item.score.total}</strong>
          </div>
          {onClose ? (
            <button type="button" className="secondary-button score-drawer-close" onClick={onClose}>
              关闭
            </button>
          ) : null}
        </div>
      </div>

      <div className="tag-row compact-tags">
        {item.sectorTags.map((tag) => (
          <span key={tag} className="tag-pill">{tag}</span>
        ))}
        {item.themeTags.map((tag) => (
          <span key={tag} className="tag-pill subtle">{tag}</span>
        ))}
      </div>

      <div className="score-list">
        {scoreRows.map((row) => {
          const value = item.score[row.key];
          const width = `${(value / row.max) * 100}%`;
          return (
            <article key={row.key} className="score-row">
              <div className="score-row-head">
                <strong>{row.label}</strong>
                <span>{value}/{row.max}</span>
              </div>
              <div className="score-bar-track">
                <div className="score-bar-fill" style={{ width }} />
              </div>
              <p>{row.description}</p>
            </article>
          );
        })}
      </div>

      <div className="drawer-insight-grid">
        <article className="indicator-card">
          <span>近 1 年收益</span>
          <strong className={signedClass(item.metrics.return1y)}>{formatPercent(item.metrics.return1y)}</strong>
        </article>
        <article className="indicator-card">
          <span>最大回撤</span>
          <strong className={signedClass(item.metrics.maxDrawdown1y)}>{formatPercent(item.metrics.maxDrawdown1y)}</strong>
        </article>
        <article className="indicator-card">
          <span>年化波动率</span>
          <strong>{formatPercent(item.metrics.volatility1y)}</strong>
        </article>
        <article className="indicator-card">
          <span>当前费率</span>
          <strong>{item.metrics.feeRate !== null ? `${item.metrics.feeRate.toFixed(2)}%` : "--"}</strong>
        </article>
        <article className="indicator-card">
          <span>基金规模</span>
          <strong>{item.metrics.size !== null ? `${item.metrics.size.toFixed(2)} 亿` : "--"}</strong>
        </article>
        <article className="indicator-card">
          <span>最新净值</span>
          <strong>{formatNav(item.metrics.latestNav)}</strong>
        </article>
      </div>

      <div className="score-summary-box">
        <strong>规则解释</strong>
        <p>{item.scoreSummary}</p>
      </div>

      {item.dataWarnings.length > 0 ? (
        <div className="warning-box">
          <strong>数据提醒</strong>
          <ul>
            {item.dataWarnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
