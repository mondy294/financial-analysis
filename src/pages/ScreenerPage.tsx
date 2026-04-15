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
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    void bootstrap();
  }, []);

  useEffect(() => {
    if (!scoreDrawerOpen) {
      return;
    }

    function handleKeydown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setScoreDrawerOpen(false);
      }
    }

    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, [scoreDrawerOpen]);

  async function bootstrap() {
    const [optionPayload, sectorPayload, presetPayload] = await Promise.all([getScreenerOptions(), getScreenerSectors(), getScreenerPresets()]);
    setOptions(optionPayload);
    setSectors(sectorPayload);
    setPresets(presetPayload);

    if (optionPayload.updatedAt) {
      await runQuery(defaultQuery);
    }
  }

  async function runQuery(nextQuery: ScreenerQueryPayload) {
    setLoading(true);
    try {
      const payload = await queryScreener(nextQuery);
      setQuery(nextQuery);
      setResult(payload);
      setSelectedItem(payload.items[0] ?? null);
    } finally {
      setLoading(false);
    }
  }

  const currentRanking = useMemo(() => query.ranking ?? "value", [query.ranking]);
  const selectedSectors = query.sectors ?? [];

  return (
    <div className="screener-page-layout">
      <div className="page-layout screener-layout">
        <div className="screener-left-rail">
          <ScreenerPresetBar
            presets={presets}
            query={query}
            onApply={(preset) => {
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

          <ScreenerFilterPanel
            query={query}
            fundTypes={options?.fundTypes ?? []}
            themes={options?.themes ?? []}
            onChange={setQuery}
            onSubmit={() => void runQuery({ ...query, page: 1, pageSize: 50 })}
            onReset={() => {
              setQuery(defaultQuery);
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
        </div>

        <div className="screener-main-rail">
          <SectorNavigator
            items={sectors}
            selectedSectors={selectedSectors}
            onToggle={(sector) => {
              const current = new Set(query.sectors ?? []);
              if (current.has(sector)) {
                current.delete(sector);
              } else {
                current.add(sector);
              }
              void runQuery({ ...query, sectors: [...current], page: 1, pageSize: 50 });
            }}
          />

          <RankingTabs
            items={options?.rankings ?? []}
            activeKey={currentRanking as ScreenerRankingKey}
            onChange={(ranking) => {
              void runQuery({ ...query, ranking, page: 1, pageSize: 50 });
            }}
          />

          <div className="disclaimer-banner">
            <strong>研究辅助说明</strong>
            <span>本页面结果仅为条件筛选与研究辅助，不构成投资建议。当前评分和板块标签都尽量做成可解释口径，不走黑盒。</span>
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
      </div>

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
