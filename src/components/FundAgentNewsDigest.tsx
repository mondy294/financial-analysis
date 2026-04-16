import type { AgentToolTrace, FundAgentReport } from "../types";

type FundAgentNewsDigestProps = {
  report: FundAgentReport;
  toolTrace: AgentToolTrace[];
};

const NEWS_KEYWORD_PATTERN = /新闻|市场|政策|央行|股市|债券|外汇|商品|海外|国内|经济数据|利率|汇率|人民币|美元|美债|黄金|原油|通胀|CPI|PPI|就业|风险偏好|流动性|加息|降息|宽松|紧缩|风格切换|申赎/;

function ensureStringList(value: unknown) {
  if (!Array.isArray(value)) {
    return [] as string[];
  }

  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function renderList(items: string[], emptyText: string) {
  if (items.length === 0) {
    return <p className="empty-state compact-empty">{emptyText}</p>;
  }

  return (
    <ul className="agent-analysis-list">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function splitSummary(summary: string) {
  return summary
    .split(/[；\n]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 4);
}

function pickNewsRelatedItems(items: string[], limit: number) {
  const related = items.filter((item) => NEWS_KEYWORD_PATTERN.test(item));
  const source = related.length > 0 ? related : items;
  return source.slice(0, limit);
}

function findNewsTrace(toolTrace: AgentToolTrace[]) {
  return [...toolTrace].reverse().find((item) => item.toolName === "get_fund_market_news") ?? null;
}

export function FundAgentNewsDigest({ report, toolTrace }: FundAgentNewsDigestProps) {
  const newsTrace = findNewsTrace(toolTrace);
  const summaryItems = splitSummary(newsTrace?.summary ?? "");
  const drivers = pickNewsRelatedItems(ensureStringList(report.recentWeekDrivers), 3);
  const watchItems = pickNewsRelatedItems(ensureStringList(report.watchItems), 3);

  if (summaryItems.length === 0 && drivers.length === 0 && watchItems.length === 0) {
    return null;
  }

  return (
    <section className="agent-news-digest">
      <div className="section-head compact-head">
        <div>
          <span className="eyebrow">News Evidence</span>
          <h3>近期影响因素</h3>
          <p>把新闻快讯、近期驱动和后续观察点放到一起，至少别只被一天的波动牵着走。</p>
        </div>
        <div className="badge-wrap">
          {newsTrace ? <span className="badge badge-muted">新闻证据已纳入本次分析</span> : null}
        </div>
      </div>

      <div className="agent-news-digest-grid">
        <article className="agent-news-panel">
          <h4>新闻摘要</h4>
          {renderList(summaryItems, "这次没有提取到可展示的新闻摘要。")}
        </article>
        <article className="agent-news-panel">
          <h4>近期影响因素</h4>
          {renderList(drivers, "这次没有整理出近期影响因素。")}
        </article>
        <article className="agent-news-panel">
          <h4>接下来要盯的外部线索</h4>
          {renderList(watchItems, "这次没有额外的外部观察点。")}
        </article>
      </div>
    </section>
  );
}
