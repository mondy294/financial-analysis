import { randomUUID } from "node:crypto";
import type {
  FundMarketNewsFeedStat,
  FundMarketNewsItem,
  FundMarketNewsQueryResponse,
  FundMarketNewsRegion,
  FundMarketNewsTopic,
} from "./types.js";

type FundMarketNewsQueryOptions = {
  startTime: string;
  endTime: string;
  regions?: FundMarketNewsRegion[];
  topics?: FundMarketNewsTopic[];
  keywords?: string[];
  limit?: number;
};

type EastmoneyFastNewsItem = {
  summary?: string;
  code?: string;
  titleColor?: number;
  realSort?: string;
  showTime?: string;
  title?: string;
  share?: number;
  pinglun_Num?: number;
  stockList?: Array<{
    code?: string;
    name?: string;
    market?: string;
  }>;
  image?: Array<{
    img?: string;
  }>;
};

type EastmoneyFastNewsPayload = {
  code?: string;
  message?: string;
  data?: {
    sortEnd?: string;
    index?: number;
    total?: number;
    size?: number;
    fastNewsList?: EastmoneyFastNewsItem[];
  };
};

type FeedDescriptor = {
  key: string;
  label: string;
  columnId: string;
  topic: FundMarketNewsTopic;
  region: FundMarketNewsRegion;
  priority: number;
};

type NormalizedRange = {
  startTime: string;
  endTime: string;
  startTimestamp: number;
  endTimestamp: number;
  days: number;
};

const EASTMONEY_NEWS_BASE_URL = "https://np-weblist.eastmoney.com/";
const EASTMONEY_KUAIXUN_REFERER = "https://kuaixun.eastmoney.com/";
const USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36";
const API_HEADERS = {
  "user-agent": USER_AGENT,
  accept: "application/json, text/plain, */*",
  referer: EASTMONEY_KUAIXUN_REFERER,
};
const MAX_LIMIT = 500;
const MAX_PAGES_PER_FEED = 12;
const MAX_RANGE_DAYS = 31;
const DEFAULT_LIMIT = 200;
const DEFAULT_REGIONS: FundMarketNewsRegion[] = ["国内", "海外"];
const DEFAULT_TOPICS: FundMarketNewsTopic[] = ["焦点", "基金", "全球股市", "商品", "外汇", "债券", "地区", "央行", "经济数据"];
const SOURCE_NAME = "东方财富全球财经快讯";
const DEFAULT_COVERAGE_NOTE =
  "当前新闻 MCP 基于东方财富 np-weblist 快讯公开接口，聚合焦点、基金、全球股市、商品、外汇、债券、地区、央行和经济数据栏目，更适合近 31 天内的滚动事件检索。";

const feedRegistry: Record<string, FeedDescriptor> = {
  focus: {
    key: "focus",
    label: "焦点",
    columnId: "101",
    topic: "焦点",
    region: "综合",
    priority: 98,
  },
  fund: {
    key: "fund",
    label: "基金",
    columnId: "109",
    topic: "基金",
    region: "综合",
    priority: 96,
  },
  equities: {
    key: "equities",
    label: "全球股市",
    columnId: "105",
    topic: "全球股市",
    region: "综合",
    priority: 90,
  },
  commodities: {
    key: "commodities",
    label: "商品",
    columnId: "106",
    topic: "商品",
    region: "综合",
    priority: 88,
  },
  fx: {
    key: "fx",
    label: "外汇",
    columnId: "107",
    topic: "外汇",
    region: "综合",
    priority: 89,
  },
  bonds: {
    key: "bonds",
    label: "债券",
    columnId: "108",
    topic: "债券",
    region: "综合",
    priority: 91,
  },
  domesticRegion: {
    key: "domesticRegion",
    label: "中国地区",
    columnId: "110",
    topic: "地区",
    region: "国内",
    priority: 84,
  },
  overseasRegion: {
    key: "overseasRegion",
    label: "海外地区",
    columnId: "111,112,113,114,115,116,117",
    topic: "地区",
    region: "海外",
    priority: 83,
  },
  domesticCentralBank: {
    key: "domesticCentralBank",
    label: "中国央行",
    columnId: "118",
    topic: "央行",
    region: "国内",
    priority: 97,
  },
  overseasCentralBank: {
    key: "overseasCentralBank",
    label: "海外央行",
    columnId: "119,120,121,122,123,124",
    topic: "央行",
    region: "海外",
    priority: 95,
  },
  domesticEconomic: {
    key: "domesticEconomic",
    label: "中国经济数据",
    columnId: "125",
    topic: "经济数据",
    region: "国内",
    priority: 94,
  },
  overseasEconomic: {
    key: "overseasEconomic",
    label: "海外经济数据",
    columnId: "126,127,128,129,130,131",
    topic: "经济数据",
    region: "海外",
    priority: 93,
  },
};

function normalizeDateTimeInput(value: string, bound: "start" | "end") {
  const trimmed = String(value || "").trim();
  if (!trimmed) {
    throw new Error(bound === "start" ? "开始时间不能为空。" : "结束时间不能为空。");
  }

  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return `${trimmed} ${bound === "start" ? "00:00:00" : "23:59:59"}`;
  }

  if (/^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}$/.test(trimmed)) {
    return trimmed;
  }

  throw new Error(`${bound === "start" ? "开始时间" : "结束时间"}格式不正确，请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:mm:ss。`);
}

function toShanghaiTimestamp(dateTime: string) {
  const timestamp = new Date(dateTime.replace(" ", "T") + "+08:00").getTime();
  if (!Number.isFinite(timestamp)) {
    throw new Error(`无法解析时间：${dateTime}`);
  }
  return timestamp;
}

function normalizeRange(startTime: string, endTime: string): NormalizedRange {
  const normalizedStartTime = normalizeDateTimeInput(startTime, "start");
  const normalizedEndTime = normalizeDateTimeInput(endTime, "end");
  const startTimestamp = toShanghaiTimestamp(normalizedStartTime);
  const endTimestamp = toShanghaiTimestamp(normalizedEndTime);

  if (startTimestamp > endTimestamp) {
    throw new Error("开始时间不能晚于结束时间。");
  }

  const days = Math.ceil((endTimestamp - startTimestamp) / (24 * 60 * 60 * 1000)) + 1;

  return {
    startTime: normalizedStartTime,
    endTime: normalizedEndTime,
    startTimestamp,
    endTimestamp,
    days,
  };
}

function normalizeKeywords(keywords?: string[]) {
  return Array.from(new Set((keywords ?? []).map((item) => String(item || "").trim()).filter(Boolean))).slice(0, 12);
}

function normalizeRegions(regions?: FundMarketNewsRegion[]) {
  const safeRegions = Array.from(new Set((regions ?? DEFAULT_REGIONS).filter((item): item is FundMarketNewsRegion => item === "国内" || item === "海外")));
  return safeRegions.length > 0 ? safeRegions : DEFAULT_REGIONS;
}

function normalizeTopics(topics?: FundMarketNewsTopic[]) {
  const topicSet = new Set(DEFAULT_TOPICS);
  const safeTopics = Array.from(new Set((topics ?? DEFAULT_TOPICS).filter((item): item is FundMarketNewsTopic => topicSet.has(item))));
  return safeTopics.length > 0 ? safeTopics : DEFAULT_TOPICS;
}

function buildFeedPlan(regions: FundMarketNewsRegion[], topics: FundMarketNewsTopic[]) {
  const regionSet = new Set(regions);
  const topicSet = new Set(topics);
  const feeds: FeedDescriptor[] = [];

  if (topicSet.has("焦点") && regionSet.size === 2) {
    feeds.push(feedRegistry.focus);
  }

  if (topicSet.has("基金")) {
    feeds.push(feedRegistry.fund);
  }

  if (topicSet.has("全球股市")) {
    feeds.push(feedRegistry.equities);
  }

  if (topicSet.has("商品")) {
    feeds.push(feedRegistry.commodities);
  }

  if (topicSet.has("外汇")) {
    feeds.push(feedRegistry.fx);
  }

  if (topicSet.has("债券")) {
    feeds.push(feedRegistry.bonds);
  }

  if (topicSet.has("地区")) {
    if (regionSet.has("国内")) {
      feeds.push(feedRegistry.domesticRegion);
    }
    if (regionSet.has("海外")) {
      feeds.push(feedRegistry.overseasRegion);
    }
  }

  if (topicSet.has("央行")) {
    if (regionSet.has("国内")) {
      feeds.push(feedRegistry.domesticCentralBank);
    }
    if (regionSet.has("海外")) {
      feeds.push(feedRegistry.overseasCentralBank);
    }
  }

  if (topicSet.has("经济数据")) {
    if (regionSet.has("国内")) {
      feeds.push(feedRegistry.domesticEconomic);
    }
    if (regionSet.has("海外")) {
      feeds.push(feedRegistry.overseasEconomic);
    }
  }

  return Array.from(new Map(feeds.map((item) => [item.key, item])).values());
}

function stripHtml(source: string) {
  return source.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
}

function matchesKeywords(item: { title: string; summary: string }, keywords: string[]) {
  if (keywords.length === 0) {
    return true;
  }

  const haystack = `${item.title} ${item.summary}`.toLowerCase();
  return keywords.some((keyword) => haystack.includes(keyword.toLowerCase()));
}

function uniqueStrings(items: string[]) {
  return Array.from(new Set(items.filter(Boolean)));
}

function inferImpactTags(feed: FeedDescriptor, item: { title: string; summary: string }) {
  const text = `${item.title} ${item.summary}`;
  const tags = new Set<string>();

  switch (feed.topic) {
    case "焦点":
      tags.add("市场焦点");
      break;
    case "基金":
      tags.add("基金行业");
      break;
    case "全球股市":
      tags.add("权益市场");
      break;
    case "商品":
      tags.add("大宗商品");
      break;
    case "外汇":
      tags.add("汇率");
      break;
    case "债券":
      tags.add("债券利率");
      break;
    case "地区":
      tags.add(feed.region === "国内" ? "国内市场" : "海外市场");
      break;
    case "央行":
      tags.add("货币政策");
      break;
    case "经济数据":
      tags.add("宏观数据");
      break;
  }

  if (/(美联储|欧洲央行|英国央行|日本央行|中国央行|央行|降息|加息|利率决议|准备金|逆回购|MLF|LPR)/.test(text)) {
    tags.add("货币政策");
  }
  if (/(CPI|PPI|PMI|GDP|非农|失业率|就业|社融|M2|零售销售|出口|通胀)/i.test(text)) {
    tags.add("宏观数据");
  }
  if (/(美元|人民币|汇率|离岸人民币|欧元|日元|英镑)/.test(text)) {
    tags.add("汇率");
  }
  if (/(国债|美债|债券|收益率|信用利差|票息)/.test(text)) {
    tags.add("债券利率");
  }
  if (/(原油|黄金|白银|铜|天然气|煤炭|锂|有色)/.test(text)) {
    tags.add("大宗商品");
  }
  if (/(A股|港股|美股|欧股|日股|纳指|纳斯达克|标普|道指|恒生|沪深300|创业板)/.test(text)) {
    tags.add("权益市场");
  }
  if (/(基金|ETF|QDII|公募|赎回|申购|分红)/.test(text)) {
    tags.add("基金行业");
  }

  return Array.from(tags);
}

function computeImportanceScore(feed: FeedDescriptor, impactTags: string[]) {
  const bonus = impactTags.reduce((total, tag) => {
    switch (tag) {
      case "货币政策":
      case "宏观数据":
        return total + 5;
      case "债券利率":
      case "汇率":
      case "权益市场":
      case "基金行业":
        return total + 3;
      case "大宗商品":
        return total + 2;
      default:
        return total + 1;
    }
  }, 0);
  return Math.min(feed.priority + bonus, 100);
}

function toDetailUrl(code?: string) {
  const cleanCode = String(code || "").trim();
  return cleanCode ? `https://finance.eastmoney.com/a/${cleanCode}.html` : null;
}

function normalizeNewsItem(feed: FeedDescriptor, rawItem: EastmoneyFastNewsItem): FundMarketNewsItem | null {
  const publishedAt = String(rawItem.showTime || "").trim();
  if (!publishedAt) {
    return null;
  }

  const title = stripHtml(String(rawItem.title || rawItem.summary || "").trim());
  const summary = stripHtml(String(rawItem.summary || rawItem.title || "").trim());
  if (!title && !summary) {
    return null;
  }

  const impactTags = inferImpactTags(feed, {
    title,
    summary,
  });

  return {
    id: String(rawItem.code || `${publishedAt}-${title}`).trim(),
    title: title || summary,
    summary,
    publishedAt,
    source: SOURCE_NAME,
    detailUrl: toDetailUrl(rawItem.code),
    topic: feed.topic,
    region: feed.region,
    feedKey: feed.key,
    feedLabel: feed.label,
    importanceScore: computeImportanceScore(feed, impactTags),
    impactTags,
    relatedStocks: Array.isArray(rawItem.stockList)
      ? rawItem.stockList
          .map((item) => ({
            code: String(item.code || "").trim(),
            name: String(item.name || "").trim(),
          }))
          .filter((item) => item.code || item.name)
      : [],
  };
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    headers: API_HEADERS,
  });

  if (!response.ok) {
    throw new Error(`新闻接口请求失败：${response.status}`);
  }

  return response.json() as Promise<T>;
}

async function fetchFeedPage(feed: FeedDescriptor, sortEnd: string, pageSize: number) {
  const url = new URL("comm/web/getFastNewsList", EASTMONEY_NEWS_BASE_URL);
  url.searchParams.set("client", "web");
  url.searchParams.set("biz", "web_724");
  url.searchParams.set("fastColumn", feed.columnId);
  url.searchParams.set("sortEnd", sortEnd);
  url.searchParams.set("pageSize", String(pageSize));
  url.searchParams.set("req_trace", randomUUID().replace(/-/g, ""));
  url.searchParams.set("_", String(Date.now()));

  const payload = await fetchJson<EastmoneyFastNewsPayload>(url.toString());
  if (String(payload.code || "") !== "1") {
    throw new Error(payload.message || `新闻接口返回异常：${feed.label}`);
  }

  return payload;
}

function buildFeedStats(feed: FeedDescriptor, pagesFetched: number, matchedCount: number, earliestMatchedAt: string | null, latestMatchedAt: string | null, truncated: boolean): FundMarketNewsFeedStat {
  return {
    feedKey: feed.key,
    feedLabel: feed.label,
    topic: feed.topic,
    region: feed.region,
    pagesFetched,
    matchedCount,
    earliestMatchedAt,
    latestMatchedAt,
    truncated,
  };
}

async function collectFeedItems(feed: FeedDescriptor, range: NormalizedRange, keywords: string[], perFeedLimit: number) {
  const items: FundMarketNewsItem[] = [];
  let sortEnd = "";
  let previousSortEnd = "__init__";
  let pagesFetched = 0;
  let truncated = false;
  let earliestMatchedAt: string | null = null;
  let latestMatchedAt: string | null = null;

  while (pagesFetched < MAX_PAGES_PER_FEED && items.length < perFeedLimit) {
    pagesFetched += 1;
    const payload = await fetchFeedPage(feed, sortEnd, Math.min(100, perFeedLimit));
    const list = Array.isArray(payload.data?.fastNewsList) ? payload.data.fastNewsList : [];
    if (list.length === 0) {
      break;
    }

    let crossedStartTime = false;

    for (const rawItem of list) {
      const item = normalizeNewsItem(feed, rawItem);
      if (!item) {
        continue;
      }

      const itemTimestamp = toShanghaiTimestamp(item.publishedAt);
      if (itemTimestamp > range.endTimestamp) {
        continue;
      }

      if (itemTimestamp < range.startTimestamp) {
        crossedStartTime = true;
        break;
      }

      if (!matchesKeywords(item, keywords)) {
        continue;
      }

      items.push(item);
      if (earliestMatchedAt === null) {
        earliestMatchedAt = item.publishedAt;
      } else if (earliestMatchedAt > item.publishedAt) {
        earliestMatchedAt = item.publishedAt;
      }

      if (latestMatchedAt === null) {
        latestMatchedAt = item.publishedAt;
      } else if (latestMatchedAt < item.publishedAt) {
        latestMatchedAt = item.publishedAt;
      }

      if (items.length >= perFeedLimit) {
        break;
      }
    }

    if (crossedStartTime || items.length >= perFeedLimit) {
      truncated = items.length >= perFeedLimit;
      break;
    }

    const nextSortEnd = String(payload.data?.sortEnd || list.at(-1)?.realSort || "").trim();
    if (!nextSortEnd || nextSortEnd === previousSortEnd) {
      break;
    }

    previousSortEnd = nextSortEnd;
    sortEnd = nextSortEnd;
  }

  if (pagesFetched >= MAX_PAGES_PER_FEED) {
    truncated = true;
  }

  return {
    items,
    stat: buildFeedStats(feed, pagesFetched, items.length, earliestMatchedAt, latestMatchedAt, truncated),
  };
}

function buildStats(items: FundMarketNewsItem[]) {
  const byTopic = new Map<string, number>();
  const byRegion = new Map<string, number>();

  for (const item of items) {
    byTopic.set(item.topic, (byTopic.get(item.topic) ?? 0) + 1);
    byRegion.set(item.region, (byRegion.get(item.region) ?? 0) + 1);
  }

  return {
    byTopic: Array.from(byTopic.entries())
      .map(([topic, count]) => ({ topic, count }))
      .sort((left, right) => right.count - left.count),
    byRegion: Array.from(byRegion.entries())
      .map(([region, count]) => ({ region, count }))
      .sort((left, right) => right.count - left.count),
  };
}

export async function queryFundMarketNews(options: FundMarketNewsQueryOptions): Promise<FundMarketNewsQueryResponse> {
  const range = normalizeRange(options.startTime, options.endTime);
  const limit = Math.min(Math.max(Number(options.limit || DEFAULT_LIMIT), 10), MAX_LIMIT);
  const keywords = normalizeKeywords(options.keywords);
  const regions = normalizeRegions(options.regions);
  const topics = normalizeTopics(options.topics);

  if (range.days > MAX_RANGE_DAYS) {
    throw new Error(`当前公开新闻源更适合近 ${MAX_RANGE_DAYS} 天检索，请缩短时间范围后再查。`);
  }

  const feedPlan = buildFeedPlan(regions, topics);
  if (feedPlan.length === 0) {
    throw new Error("当前筛选条件没有可用的新闻栏目。请调整地区或主题。");
  }

  const perFeedLimit = Math.min(120, Math.max(40, Math.ceil(limit / feedPlan.length) * (keywords.length > 0 ? 4 : 2)));
  const feedResults = await Promise.all(feedPlan.map((feed) => collectFeedItems(feed, range, keywords, perFeedLimit)));

  const merged = new Map<string, FundMarketNewsItem>();
  const feedStats: FundMarketNewsFeedStat[] = [];
  let truncated = false;

  for (const result of feedResults) {
    feedStats.push(result.stat);
    truncated = truncated || result.stat.truncated;

    for (const item of result.items) {
      const dedupeKey = `${item.publishedAt}__${item.title}`;
      const existing = merged.get(dedupeKey);
      if (!existing) {
        merged.set(dedupeKey, item);
        continue;
      }

      if (item.importanceScore > existing.importanceScore) {
        merged.set(dedupeKey, {
          ...item,
          impactTags: uniqueStrings([...item.impactTags, ...existing.impactTags]),
          relatedStocks: [...existing.relatedStocks, ...item.relatedStocks].slice(0, 10),
        });
      } else {
        existing.impactTags = uniqueStrings([...existing.impactTags, ...item.impactTags]);
        existing.relatedStocks = [...existing.relatedStocks, ...item.relatedStocks].slice(0, 10);
      }
    }
  }

  const items = Array.from(merged.values())
    .sort((left, right) => toShanghaiTimestamp(right.publishedAt) - toShanghaiTimestamp(left.publishedAt))
    .slice(0, limit);

  return {
    startTime: range.startTime,
    endTime: range.endTime,
    limit,
    keywords,
    regions,
    topics,
    total: items.length,
    truncated,
    coverageNote: DEFAULT_COVERAGE_NOTE,
    feedStats,
    stats: buildStats(items),
    items,
  };
}
