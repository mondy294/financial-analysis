import type { ScreenerRankingKey } from "../types";

type RankingTabsProps = {
  items: Array<{ key: ScreenerRankingKey; label: string; description: string }>;
  activeKey: ScreenerRankingKey | null;
  onChange: (key: ScreenerRankingKey) => void;
};

export function RankingTabs({ items, activeKey, onChange }: RankingTabsProps) {
  return (
    <section className="panel ranking-panel">
      <div className="section-head compact-head">
        <div>
          <h3>排行榜</h3>
          <p>收益榜、低回撤榜、低波动榜和规则榜都在这里切换。</p>
        </div>
      </div>

      <div className="ranking-tab-grid">
        {items.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`ranking-tab${activeKey === item.key ? " active" : ""}`}
            onClick={() => onChange(item.key)}
          >
            <strong>{item.label}</strong>
            <span>{item.description}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
