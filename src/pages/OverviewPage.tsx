import type { FundDetailResponse, HoldingItem } from "../types";
import { FundSummaryCard } from "../components/FundSummaryCard";

type OverviewPageProps = {
  spotlight: FundDetailResponse | null;
  inWatchlist: boolean;
  holding: HoldingItem | null;
  onAddWatchlist: (code: string) => Promise<void>;
  onRemoveWatchlist: (code: string) => Promise<void>;
  onUseForHolding: (code: string) => void;
};

const overviewCards = [
  {
    title: "先查基金，再决定动作",
    description: "顶部输入 6 位基金编号，管理台会把净值、估值、区间业绩和走势一次摊开。",
  },
  {
    title: "自选负责观察",
    description: "把常看的基金先放进“我的自选”，后面只需要回来看实时变化和阶段表现。",
  },
  {
    title: "持有负责记录你自己的仓位",
    description: "成本净值、持仓金额、收益率都能手动维护，省得信息散落在别处。",
  },
] as const;

export function OverviewPage({
  spotlight,
  inWatchlist,
  holding,
  onAddWatchlist,
  onRemoveWatchlist,
  onUseForHolding,
}: OverviewPageProps) {
  if (!spotlight) {
    return (
      <section className="panel overview-empty-panel">
        <div className="section-head">
          <div>
            <h2>先搜一只基金</h2>
            <p>这里是总览页。查到基金之后，你会在这里看到更完整的区间走势图、阶段收益和最近净值记录。</p>
          </div>
        </div>

        <div className="overview-guide-grid">
          {overviewCards.map((item) => (
            <article key={item.title} className="overview-guide-card">
              <h3>{item.title}</h3>
              <p>{item.description}</p>
            </article>
          ))}
        </div>
      </section>
    );
  }

  return (
    <FundSummaryCard
      detail={spotlight}
      inWatchlist={inWatchlist}
      holding={holding}
      onAddWatchlist={onAddWatchlist}
      onRemoveWatchlist={onRemoveWatchlist}
      onUseForHolding={onUseForHolding}
    />
  );
}
