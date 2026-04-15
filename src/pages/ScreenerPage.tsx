import { useEffect, useMemo, useState } from "react";
import {
  deleteScreenerPreset,
  getScreenerOptions,
  getScreenerPresets,
  getScreenerSectors,
  queryScreener,
  refreshScreenerCache,
  saveScreenerPreset,
} from "../api/client";
import { FundScoreDrawer } from "../components/FundScoreDrawer";
import { RankingTabs } from "../components/RankingTabs";
import { ScreenerFilterPanel } from "../components/ScreenerFilterPanel";
import { ScreenerPresetBar } from "../components/ScreenerPresetBar";
import { ScreenerResultTable } from "../components/ScreenerResultTable";
import { SectorNavigator } from "../components/SectorNavigator";
import type {
  FundUniverseItem,
  ScreenerOptionResponse,
  ScreenerPreset,
  ScreenerQueryPayload,
  ScreenerQueryResponse,
  ScreenerRankingKey,
  ScreenerSectorStat,
} from "../types";

const defaultQuery: ScreenerQueryPayload = {
  fundTypes: [],
  sectors: [],
  themes: [],
  minReturn1m: null,
  minReturn3m: null,
  minReturn6m: null,
  minReturn1y: null,
  maxDrawdown1y: null,
  maxVolatility1y: null,
  maxFeeRate: null,
  minSize: null,
  maxSize: null,
  minEstablishedYears: null,
  autoInvestOnly: false,
  ranking: "value",
  sortBy: null,
  sortOrder: "desc",
  page: 1,
  pageSize: 50,
};

type ScreenerPageProps = {
  compareCodes: string[];
  watchlistCodes: string[];
  onAddWatchlist: (code: string) => Promise<void>;
  onAddCompare: (code: string) => Promise<void>;
  onOpenDetail: (code: string) => void;
  onUseForHolding: (code: string) => void;
};

function hasNumber(value: number | null | undefined) {
  return value !== null && value !== undefined;
}

function countActiveFilters(query: ScreenerQueryPayload) {
  let count = 0;

  if (query.fundTypes?.length) count += 1;
  if (query.sectors?.length) count += 1;
  if (query.themes?.length) count += 1;
  if (hasNumber(query.minReturn1m)) count += 1;
  if (hasNumber(query.minReturn3m)) count += 1;
  if (hasNumber(query.minReturn6m)) count += 1;
  if (hasNumber(query.minReturn1y)) count += 1;
  if (hasNumber(query.maxDrawdown1y)) count += 1;
  if (hasNumber(query.maxVolatility1y)) count += 1;
  if (hasNumber(query.maxFeeRate)) count += 1;
  if (hasNumber(query.minSize)) count += 1;
  if (hasNumber(query.maxSize)) count += 1;
  if (hasNumber(query.minEstablishedYears)) count += 1;
  if (query.autoInvestOnly) count += 1;

  return count;
}

function buildActiveTags(query: ScreenerQueryPayload, sectors: ScreenerSectorStat[]) {
  const tags: string[] = [];
  const sectorNameMap = new Map(sectors.map((item) => [item.id, item.name]));

  if (query.fundTypes?.length) {
    tags.push(`类型：${query.fundTypes.join(" / ")}`);
  }

  if (query.sectors?.length) {
    const sectorNames = query.sectors.map((item) => sectorNameMap.get(item) ?? item);
    const preview = sectorNames.slice(0, 2).join(" · ");
    tags.push(sectorNames.length > 2 ? `行业/概念：${preview} +${sectorNames.length - 2}` : `行业/概念：${preview}`);
  }

  if (query.themes?.length) {
    const preview = query.themes.slice(0, 2).join(" · ");
    tags.push(query.themes.length > 2 ? `主题：${preview} +${query.themes.length - 2}` : `主题：${preview}`);
  }

  if (query.autoInvestOnly) {
    tags.push("仅看可定投");
  }

  if (hasNumber(query.minReturn1y)) {
    tags.push(`近 1 年 ≥ ${query.minReturn1y}%`);
  }

  if (hasNumber(query.maxDrawdown1y)) {
    tags.push(`最大回撤 ≤ ${query.maxDrawdown1y}%`);
  }

  if (hasNumber(query.maxVolatility1y)) {
    tags.push(`波动率 ≤ ${query.maxVolatility1y}%`);
  }

  if (hasNumber(query.maxFeeRate)) {
    tags.push(`费率 ≤ ${query.maxFeeRate}%`);
  }

  return tags;
}

export function ScreenerPage({
  compareCodes,
  watchlistCodes,
  onAddWatchlist,
  onAddCompare,
  onOpenDetail,
  onUseForHolding,
}: ScreenerPageProps) {
  const [options, setOptions] = useState<ScreenerOptionResponse | null>(null);
  const [sectors, setSectors] = useState<ScreenerSectorStat[]>([]);
  const [presets, setPresets] = useState<ScreenerPreset[]>([]);
  const [query, setQuery] = useState<ScreenerQueryPayload>(defaultQuery);
  const [result, setResult] = useState<ScreenerQueryResponse | null>(null);
  const [selectedItem, setSelectedItem] = useState<FundUniverseItem | null>(null);
  const [scoreDrawerOpen, setScoreDrawerOpen] = useState(false);
  const [filterDrawerOpen, setFilterDrawerOpen] = useState(false);
  const [rankingDrawerOpen, setRankingDrawerOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    void bootstrap();
  }, []);

  useEffect(() => {
    if (!scoreDrawerOpen && !filterDrawerOpen && !rankingDrawerOpen) {
      return;
    }

    function handleKeydown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setScoreDrawerOpen(false);
        setFilterDrawerOpen(false);
        setRankingDrawerOpen(false);
      }
    }

    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, [filterDrawerOpen, rankingDrawerOpen, scoreDrawerOpen]);

  async function bootstrap() {
    const [optionPayload, sectorPayload, presetPayload] = await Promise.all([getScreenerOptions(), getScreenerSectors(), getScreenerPresets()]);
    setOptions(optionPayload);
    setSectors(sectorPayload);
    setPresets(presetPayload);
    await runQuery(defaultQuery);
  }

  async function runQuery(nextQuery: ScreenerQueryPayload) {
    setLoading(true);
    try {
      const payload = await queryScreener(nextQuery);
      setQuery(nextQuery);
      setResult(payload);
      setSelectedItem((current) => payload.items.find((item) => item.code === current?.code) ?? payload.items[0] ?? null);
    } finally {
      setLoading(false);
    }
  }

  function closeUtilityDrawers() {
    setFilterDrawerOpen(false);
    setRankingDrawerOpen(false);
  }

  const rankingItems = options?.rankings ?? [];
  const currentRanking = useMemo(() => query.ranking ?? "value", [query.ranking]);
  const currentRankingMeta = useMemo(() => rankingItems.find((item) => item.key === currentRanking) ?? null, [currentRanking, rankingItems]);
  const selectedSectors = query.sectors ?? [];
  const sectorsWithData = useMemo(() => sectors.filter((item) => item.count > 0), [sectors]);
  const activeFilterCount = useMemo(() => countActiveFilters(query), [query]);
  const activeTags = useMemo(() => buildActiveTags(query, sectorsWithData), [query, sectorsWithData]);
  const hasNonDefaultState = activeFilterCount > 0 || currentRanking !== defaultQuery.ranking;

  return (
    <div className="screener-page-layout">
      <section className="panel screener-hero-panel">
        <div className="screener-hero-head">
          <div>
            <span className="eyebrow">Fund Screener</span>
            <h3>基金列表优先</h3>
            <p>把筛选条件和排行榜收在右手边按需唤出，中间只保留行业概念速选和基金列表，找候选会更顺手。</p>
          </div>
          <div className="badge-wrap">
            <span className="badge badge-emerald">当前排序：{currentRankingMeta?.label ?? "综合价值"}</span>
            <span className="badge badge-muted">{loading ? "列表更新中..." : `展示 ${result?.items.length ?? 0} / ${result?.total ?? 0}`}</span>
          </div>
        </div>

        <div className="screener-summary-strip">
          <article className="screener-summary-card">
            <span>候选基金</span>
            <strong>{loading ? "..." : result?.total ?? 0}</strong>
            <p>当前条件命中的基金数量。</p>
          </article>
          <article className="screener-summary-card">
            <span>已选行业/概念</span>
            <strong>{selectedSectors.length}</strong>
            <p>点上方主题板块即可立即切换数据源。</p>
          </article>
          <article className="screener-summary-card">
            <span>可用行业/概念</span>
            <strong>{sectorsWithData.length}</strong>
            <p>只展示当前有基金数据的板块标签。</p>
          </article>
          <article className="screener-summary-card">
            <span>已存方案</span>
            <strong>{presets.length}</strong>
            <p>常用条件可以从右侧筛选抽屉直接复用。</p>
          </article>
        </div>

        <div className="screener-active-strip">
          <div className="screener-active-copy">
            <strong>{activeFilterCount > 0 ? `已启用 ${activeFilterCount} 个筛选条件` : "当前是默认基金池"}</strong>
            <span>
              {activeFilterCount > 0
                ? "右侧打开筛选器可继续细化；每次应用后，中间基金列表会按当前条件重新取数。"
                : "可以先点行业/概念或排行榜，再按收益、回撤、费率等维度进一步收窄范围。"}
            </span>
          </div>

          <div className="tag-row screener-active-tags">
            {activeTags.length > 0 ? activeTags.map((item) => <span key={item} className="tag-pill">{item}</span>) : <span className="tag-pill subtle">默认基金池</span>}
          </div>

          {hasNonDefaultState ? (
            <button
              type="button"
              className="ghost-chip"
              onClick={() => {
                setQuery(defaultQuery);
                void runQuery(defaultQuery);
              }}
            >
              清空当前条件
            </button>
          ) : null}
        </div>
      </section>

      <SectorNavigator
        items={sectorsWithData}
        selectedSectors={selectedSectors}
        onToggle={(sectorId) => {
          const current = new Set(query.sectors ?? []);
          if (current.has(sectorId)) {
            current.delete(sectorId);
          } else {
            current.add(sectorId);
          }
          void runQuery({ ...query, sectors: [...current], page: 1, pageSize: 50 });
        }}
      />

      <div className="screener-stage">
        <div className="screener-results-wrap">
          <div className="disclaimer-banner screener-disclaimer">
            <strong>研究辅助说明</strong>
            <span>本页只做条件筛选和研究辅助，不构成投资建议。评分、板块标签和排序规则尽量保持可解释，不走黑盒。</span>
          </div>

          <ScreenerResultTable
            items={result?.items ?? []}
            total={result?.total ?? 0}
            loading={loading}
            selectedCode={selectedItem?.code ?? null}
            compareCodes={compareCodes}
            watchlistCodes={watchlistCodes}
            onSelect={setSelectedItem}
            onViewScore={(item) => {
              setSelectedItem(item);
              setScoreDrawerOpen(true);
            }}
            onOpenDetail={onOpenDetail}
            onAddWatchlist={onAddWatchlist}
            onAddCompare={onAddCompare}
            onUseForHolding={onUseForHolding}
          />
        </div>

        <aside className="screener-side-dock">
          <button
            type="button"
            className="screener-dock-button"
            onClick={() => {
              setFilterDrawerOpen(true);
              setRankingDrawerOpen(false);
            }}
          >
            <strong>筛选</strong>
            <span>{activeFilterCount > 0 ? `${activeFilterCount} 个条件` : "打开抽屉"}</span>
          </button>

          <button
            type="button"
            className="screener-dock-button"
            onClick={() => {
              setRankingDrawerOpen(true);
              setFilterDrawerOpen(false);
            }}
          >
            <strong>排行</strong>
            <span>{currentRankingMeta?.label ?? "综合价值"}</span>
          </button>
        </aside>
      </div>

      {filterDrawerOpen ? (
        <div className="utility-drawer-overlay" onClick={closeUtilityDrawers}>
          <aside className="utility-drawer utility-drawer--wide" onClick={(event) => event.stopPropagation()}>
            <div className="utility-drawer-head">
              <div>
                <h3>筛选器与方案</h3>
                <p>在这里调整条件或保存常用筛选，应用后中间基金列表会立即刷新。</p>
              </div>
              <button type="button" className="secondary-button" onClick={closeUtilityDrawers}>
                关闭
              </button>
            </div>

            <div className="utility-drawer-content">
              <ScreenerFilterPanel
                query={query}
                fundTypes={options?.fundTypes ?? []}
                themes={options?.themes ?? []}
                onChange={setQuery}
                onSubmit={() => {
                  closeUtilityDrawers();
                  void runQuery({ ...query, page: 1, pageSize: 50 });
                }}
                onReset={() => {
                  setQuery(defaultQuery);
                  closeUtilityDrawers();
                  void runQuery(defaultQuery);
                }}
                refreshing={refreshing}
                onRefresh={async () => {
                  setRefreshing(true);
                  try {
                    await refreshScreenerCache();
                    const [optionPayload, sectorPayload] = await Promise.all([getScreenerOptions(), getScreenerSectors()]);
                    setOptions(optionPayload);
                    setSectors(sectorPayload);
                    await runQuery({ ...query, page: 1, pageSize: 50 });
                  } finally {
                    setRefreshing(false);
                  }
                }}
                updatedAt={options?.updatedAt ?? null}
                isStale={options?.isStale ?? true}
                coverageNote={options?.coverageNote ?? "基金池尚未生成。"}
              />

              <ScreenerPresetBar
                presets={presets}
                query={query}
                onApply={(preset) => {
                  closeUtilityDrawers();
                  void runQuery({ ...defaultQuery, ...preset.query, page: 1, pageSize: 50 });
                }}
                onSave={async (name) => {
                  await saveScreenerPreset(name, query);
                  setPresets(await getScreenerPresets());
                }}
                onDelete={async (presetId) => {
                  await deleteScreenerPreset(presetId);
                  setPresets(await getScreenerPresets());
                }}
              />
            </div>
          </aside>
        </div>
      ) : null}

      {rankingDrawerOpen ? (
        <div className="utility-drawer-overlay" onClick={closeUtilityDrawers}>
          <aside className="utility-drawer utility-drawer--narrow" onClick={(event) => event.stopPropagation()}>
            <div className="utility-drawer-head">
              <div>
                <h3>排行榜</h3>
                <p>把排序收起来，需要时再展开，避免主视图被排行榜打断。</p>
              </div>
              <button type="button" className="secondary-button" onClick={closeUtilityDrawers}>
                关闭
              </button>
            </div>

            <div className="utility-drawer-content">
              <RankingTabs
                items={rankingItems}
                activeKey={currentRanking as ScreenerRankingKey}
                onChange={(ranking) => {
                  closeUtilityDrawers();
                  void runQuery({ ...query, ranking, page: 1, pageSize: 50 });
                }}
              />

              <section className="panel utility-note-panel">
                <div className="section-head compact-head">
                  <div>
                    <h3>当前排序口径</h3>
                    <p>{currentRankingMeta?.description ?? "按当前排序规则展示候选基金。"}</p>
                  </div>
                </div>
                <div className="cache-hint">
                  <strong>{currentRankingMeta?.label ?? "综合价值"}</strong>
                  <span>切换后只更新中间基金列表，不打断已选中的板块和其他筛选条件。</span>
                </div>
              </section>
            </div>
          </aside>
        </div>
      ) : null}

      {scoreDrawerOpen && selectedItem ? (
        <div className="score-drawer-overlay" onClick={() => setScoreDrawerOpen(false)}>
          <div className="score-drawer-modal" onClick={(event) => event.stopPropagation()}>
            <FundScoreDrawer item={selectedItem} onClose={() => setScoreDrawerOpen(false)} />
          </div>
        </div>
      ) : null}
    </div>
  );
}

