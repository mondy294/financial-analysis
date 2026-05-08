import type { StockAnalysisResponse } from "../types";
import { StockSummaryCard } from "../components/StockSummaryCard";

type StocksPageProps = {
  spotlight: StockAnalysisResponse | null;
};

const guideCards = [
  {
    title: "这里专门分析股票",
    description: "和基金页拆开处理，股票页会单独看 K 线、开高低收、均线和布林带。",
  },
  {
    title: "先看结构，再看推理",
    description: "先把日 K 和关键价位摊开，再让独立股票 Agent 给出未来 1-3 个月的路径推演。",
  },
  {
    title: "分析结果会单独缓存",
    description: "同一只股票下次再搜，会自动读取最近一次已保存的股票 Agent 分析记录。",
  },
] as const;

export function StocksPage({ spotlight }: StocksPageProps) {
  if (!spotlight) {
    return (
      <section className="panel overview-empty-panel">
        <div className="section-head">
          <div>
            <h2>先搜一只股票</h2>
            <p>这里是股票分析页。查到股票之后，你会在这里看到 K 线、阶段表现、关键价位和独立股票 Agent 的推理结果。</p>
          </div>
        </div>

        <div className="overview-guide-grid">
          {guideCards.map((item) => (
            <article key={item.title} className="overview-guide-card">
              <h3>{item.title}</h3>
              <p>{item.description}</p>
            </article>
          ))}
        </div>
      </section>
    );
  }

  return <StockSummaryCard detail={spotlight} />;
}
