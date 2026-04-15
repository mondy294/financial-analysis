import { useMemo, useState } from "react";
import type { ScreenerSectorStat } from "../types";

type SectorNavigatorProps = {
  items: ScreenerSectorStat[];
  selectedSectors: string[];
  onToggle: (sectorId: string) => void;
};

const groupOrder = ["行业", "概念", "标签"];
const collapsedSize = 14;

export function SectorNavigator({ items, selectedSectors, onToggle }: SectorNavigatorProps) {
  const [keyword, setKeyword] = useState("");
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({
    行业: true,
    概念: false,
    标签: false,
  });

  const normalizedKeyword = keyword.trim().toLowerCase();

  const groupedItems = useMemo(() => {
    const filtered = normalizedKeyword
      ? items.filter((item) => `${item.name} ${item.group}`.toLowerCase().includes(normalizedKeyword))
      : items;

    return groupOrder
      .map((group) => ({
        group,
        items: filtered
          .filter((item) => item.group === group && item.count > 0)
          .sort((a, b) => {
            const aActive = selectedSectors.includes(a.id) || selectedSectors.includes(a.name) ? 1 : 0;
            const bActive = selectedSectors.includes(b.id) || selectedSectors.includes(b.name) ? 1 : 0;
            return bActive - aActive || b.count - a.count || a.name.localeCompare(b.name, "zh-CN");
          }),
      }))
      .filter((entry) => entry.items.length > 0);
  }, [items, normalizedKeyword, selectedSectors]);

  return (
    <section className="panel sector-panel">
      <div className="section-head compact-head sector-panel-head">
        <div>
          <h3>主题板块</h3>
          <p>这里只展示确实有基金数据的行业、概念和标签；常点的板块会自动排在前面，避免大面积空标签干扰视线。</p>
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

      {groupedItems.length === 0 ? (
        <div className="empty-inline compact-empty">当前没有匹配到有数据的行业或概念，可以换个关键词试试。</div>
      ) : (
        <div className="sector-groups">
          {groupedItems.map((group) => {
            const expanded = normalizedKeyword ? true : (expandedGroups[group.group] ?? false);
            const visibleItems = expanded ? group.items : group.items.slice(0, collapsedSize);

            return (
              <div key={group.group} className="sector-group-block">
                <div className="sector-group-title">
                  <div>
                    <strong>{group.group}</strong>
                    <span>{group.items.length} 个</span>
                  </div>
                  {group.items.length > collapsedSize ? (
                    <button
                      type="button"
                      className="ghost-chip sector-group-toggle"
                      onClick={() => setExpandedGroups((current) => ({ ...current, [group.group]: !expanded }))}
                    >
                      {expanded ? "收起" : `展开全部 ${group.items.length} 个`}
                    </button>
                  ) : null}
                </div>

                <div className="sector-chip-row">
                  {visibleItems.map((item) => {
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
            );
          })}
        </div>
      )}
    </section>
  );
}

