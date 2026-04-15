import { useMemo, useState } from "react";
import type { ScreenerSectorStat } from "../types";

type SectorNavigatorProps = {
  items: ScreenerSectorStat[];
  selectedSectors: string[];
  onToggle: (sectorId: string) => void;
};

const groupOrder = ["行业", "概念", "标签"];

export function SectorNavigator({ items, selectedSectors, onToggle }: SectorNavigatorProps) {
  const [keyword, setKeyword] = useState("");

  const groupedItems = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();
    const filtered = normalizedKeyword
      ? items.filter((item) => `${item.name} ${item.group}`.toLowerCase().includes(normalizedKeyword))
      : items;

    return groupOrder
      .map((group) => ({
        group,
        items: filtered.filter((item) => item.group === group),
      }))
      .filter((entry) => entry.items.length > 0);
  }, [items, keyword]);

  return (
    <section className="panel sector-panel">
      <div className="section-head compact-head sector-panel-head">
        <div>
          <h3>主题板块</h3>
          <p>已接入天天基金主题接口，板块明显比手工关键词版更全。可先搜板块，再叠加收益、回撤和费率条件。</p>
        </div>
        <label className="sector-search-input">
          <span>搜索板块</span>
          <input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="例如：创新药、机器人、红利、港股"
          />
        </label>
      </div>

      <div className="sector-groups">
        {groupedItems.map((group) => (
          <div key={group.group} className="sector-group-block">
            <div className="sector-group-title">
              <strong>{group.group}</strong>
              <span>{group.items.length} 个</span>
            </div>
            <div className="sector-chip-row">
              {group.items.map((item) => {
                const active = selectedSectors.includes(item.id) || selectedSectors.includes(item.name);
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`sector-chip${active ? " active" : ""}`}
                    onClick={() => onToggle(item.id)}
                    title={`${item.name} · 当前候选池命中 ${item.count} 只${item.totalFundCount ? `，主题接口返回 ${item.totalFundCount} 只相关基金` : ""}`}
                  >
                    <span>{item.name}</span>
                    <em>{item.count}</em>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
