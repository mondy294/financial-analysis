import { useMemo, useState } from "react";
import type { ScreenerFundCategory, ScreenerQueryPayload } from "../types";

type ScreenerFilterPanelProps = {
  query: ScreenerQueryPayload;
  fundTypes: ScreenerFundCategory[];
  themes: string[];
  onChange: (next: ScreenerQueryPayload) => void;
  onSubmit: () => void;
  onReset: () => void;
  refreshing: boolean;
  onRefresh: () => Promise<void>;
  updatedAt: string | null;
  isStale: boolean;
  coverageNote: string;
};

function toText(value: number | null | undefined) {
  return value === null || value === undefined ? "" : String(value);
}

function parseNullable(value: string) {
  if (!value.trim()) {
    return null;
  }

  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function ScreenerFilterPanel({
  query,
  fundTypes,
  themes,
  onChange,
  onSubmit,
  onReset,
  refreshing,
  onRefresh,
  updatedAt,
  isStale,
  coverageNote,
}: ScreenerFilterPanelProps) {
  const [showAllThemes, setShowAllThemes] = useState(false);

  const visibleThemes = useMemo(() => {
    const merged = Array.from(new Set([...(query.themes ?? []), ...themes]));
    return showAllThemes ? merged : merged.slice(0, 18);
  }, [query.themes, showAllThemes, themes]);

  return (
    <section className="panel screener-filter-panel">
      <div className="section-head compact-head">
        <div>
          <h3>筛选器</h3>
          <p>这里专门负责调条件。应用之后，中间基金列表会按当前筛选和数据源重新取数。</p>
        </div>
        <button type="button" className="secondary-button" disabled={refreshing} onClick={() => void onRefresh()}>
          {refreshing ? "刷新中..." : "刷新基金池"}
        </button>
      </div>

      <div className={`cache-hint${isStale ? " stale" : ""}`}>
        <strong>{updatedAt ? `缓存更新于 ${new Date(updatedAt).toLocaleString("zh-CN")}` : "基金池尚未生成"}</strong>
        <span>{coverageNote}</span>
      </div>

      <div className="filter-section">
        <span className="filter-title">基金类型</span>
        <div className="chip-check-row">
          {fundTypes.map((item) => {
            const active = query.fundTypes?.includes(item) ?? false;
            return (
              <button
                key={item}
                type="button"
                className={`toggle-chip${active ? " active" : ""}`}
                onClick={() => {
                  const current = new Set(query.fundTypes ?? []);
                  if (current.has(item)) {
                    current.delete(item);
                  } else {
                    current.add(item);
                  }
                  onChange({ ...query, fundTypes: [...current] });
                }}
              >
                {item}
              </button>
            );
          })}
        </div>
      </div>

      <div className="filter-section">
        <span className="filter-title">主题标签</span>
        <div className="chip-check-row">
          {visibleThemes.map((item) => {
            const active = query.themes?.includes(item) ?? false;
            return (
              <button
                key={item}
                type="button"
                className={`toggle-chip${active ? " active" : ""}`}
                onClick={() => {
                  const current = new Set(query.themes ?? []);
                  if (current.has(item)) {
                    current.delete(item);
                  } else {
                    current.add(item);
                  }
                  onChange({ ...query, themes: [...current] });
                }}
              >
                {item}
              </button>
            );
          })}
        </div>
        {themes.length > 18 ? (
          <button type="button" className="ghost-chip filter-more-button" onClick={() => setShowAllThemes((current) => !current)}>
            {showAllThemes ? "收起主题标签" : `展开更多主题（剩余 ${Math.max(themes.length - visibleThemes.length, 0)} 个）`}
          </button>
        ) : null}
      </div>

      <div className="filter-grid compact-filter-grid">
        <label>
          <span>近 1 月收益下限 (%)</span>
          <input value={toText(query.minReturn1m)} onChange={(event) => onChange({ ...query, minReturn1m: parseNullable(event.target.value) })} />
        </label>
        <label>
          <span>近 3 月收益下限 (%)</span>
          <input value={toText(query.minReturn3m)} onChange={(event) => onChange({ ...query, minReturn3m: parseNullable(event.target.value) })} />
        </label>
        <label>
          <span>近 6 月收益下限 (%)</span>
          <input value={toText(query.minReturn6m)} onChange={(event) => onChange({ ...query, minReturn6m: parseNullable(event.target.value) })} />
        </label>
        <label>
          <span>近 1 年收益下限 (%)</span>
          <input value={toText(query.minReturn1y)} onChange={(event) => onChange({ ...query, minReturn1y: parseNullable(event.target.value) })} />
        </label>
        <label>
          <span>最大回撤上限 (%)</span>
          <input value={toText(query.maxDrawdown1y)} onChange={(event) => onChange({ ...query, maxDrawdown1y: parseNullable(event.target.value) })} />
        </label>
        <label>
          <span>波动率上限 (%)</span>
          <input value={toText(query.maxVolatility1y)} onChange={(event) => onChange({ ...query, maxVolatility1y: parseNullable(event.target.value) })} />
        </label>
        <label>
          <span>费率上限 (%)</span>
          <input value={toText(query.maxFeeRate)} onChange={(event) => onChange({ ...query, maxFeeRate: parseNullable(event.target.value) })} />
        </label>
        <label>
          <span>最小规模 (亿)</span>
          <input value={toText(query.minSize)} onChange={(event) => onChange({ ...query, minSize: parseNullable(event.target.value) })} />
        </label>
        <label>
          <span>最大规模 (亿)</span>
          <input value={toText(query.maxSize)} onChange={(event) => onChange({ ...query, maxSize: parseNullable(event.target.value) })} />
        </label>
        <label>
          <span>最小成立年限</span>
          <input value={toText(query.minEstablishedYears)} onChange={(event) => onChange({ ...query, minEstablishedYears: parseNullable(event.target.value) })} />
        </label>
      </div>

      <label className="inline-switch">
        <input
          type="checkbox"
          checked={query.autoInvestOnly ?? false}
          onChange={(event) => onChange({ ...query, autoInvestOnly: event.target.checked })}
        />
        <span>仅看可定投</span>
      </label>

      <div className="form-actions screener-filter-actions">
        <button type="button" className="primary-button" onClick={onSubmit}>
          应用到列表
        </button>
        <button type="button" className="secondary-button" onClick={onReset}>
          重置条件
        </button>
      </div>
    </section>
  );
}

