import type { ScreenerSectorStat } from "../types";

type SectorNavigatorProps = {
  items: ScreenerSectorStat[];
  selectedSectors: string[];
  onToggle: (sector: string) => void;
};

export function SectorNavigator({ items, selectedSectors, onToggle }: SectorNavigatorProps) {
  return (
    <section className="panel sector-panel">
      <div className="section-head compact-head">
        <div>
          <h3>热门板块</h3>
          <p>先按赛道看，再叠加收益、回撤、波动和费率条件。</p>
        </div>
      </div>

      <div className="sector-chip-row">
        {items.map((item) => {
          const active = selectedSectors.includes(item.name);
          return (
            <button
              key={item.name}
              type="button"
              className={`sector-chip${active ? " active" : ""}`}
              onClick={() => onToggle(item.name)}
            >
              <span>{item.name}</span>
              <em>{item.count}</em>
            </button>
          );
        })}
      </div>
    </section>
  );
}
