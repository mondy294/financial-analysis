import { getFundUniverseCache, getScreenerPresets, saveFundUniverseCache, saveScreenerPresets } from "./data-store.js";
import { getFundPerformance } from "./fund-service.js";
import type {
  FundDetailResponse,
  FundTrendPoint,
  FundUniverseCacheFile,
  FundUniverseItem,
  FundUniverseMetrics,
  FundUniverseScore,
  PersistedScreenerPreset,
  ScreenerFundCategory,
  ScreenerOptionsResponse,
  ScreenerQueryPayload,
  ScreenerQueryResult,
  ScreenerRankingKey,
  ScreenerSectorStat,
  ScreenerSortOrder,
} from "./types.js";

type RawCatalogEntry = [string, string, string, string, string];
type CatalogItem = {
  code: string;
  name: string;
  pinyin: string;
  rawFundType: string | null;
};

type RankRow = {
  code: string;
  name: string;
  pinyin: string;
  latestNavDate: string | null;
  latestNav: number | null;
  latestDailyGrowthRate: number | null;
  return1w: number | null;
  return1m: number | null;
  return3m: number | null;
  return6m: number | null;
  return1y: number | null;
  returnYtd: number | null;
  returnSinceInception: number | null;
  establishedDate: string | null;
  size: number | null;
  originalFeeRate: number | null;
  currentFeeRate: number | null;
  canBuy: boolean;
  canAutoInvest: boolean;
};

type RankSeedConfig = {
  fundTypeKey: string;
  sortKey: string;
  pageSize: number;
};

const USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36";

const API_HEADERS = {
  "user-agent": USER_AGENT,
  accept: "application/json, text/plain, */*",
};

const FUND_CATALOG_URL = "https://fund.eastmoney.com/js/fundcode_search.js";
const CACHE_TTL_MS = 24 * 60 * 60 * 1000;
const DEFAULT_COVERAGE_NOTE =
  "V1 基金池通过东方财富基金排行 rankhandler.aspx 与 fundcode_search.js 交叉构建，优先覆盖主动、指数、纯债、固收+、QDII、FOF 等常见候选。";

const BASE_FUND_TYPES: ScreenerFundCategory[] = ["主动", "指数", "纯债", "固收+", "QDII", "FOF"];
const BASE_SECTORS = ["红利", "医疗", "科技", "新能源", "消费", "宽基", "纯债", "固收+", "海外", "黄金"];

const rankingDefinitions: Array<{ key: ScreenerRankingKey; label: string; description: string }> = [
  { key: "return1m", label: "近 1 月收益榜", description: "按近 1 月收益率降序排列，适合看短期强势候选。" },
  { key: "return3m", label: "近 3 月收益榜", description: "按近 3 月收益率降序排列，偏向看一段可延续趋势。" },
  { key: "return1y", label: "近 1 年收益榜", description: "按近 1 年收益率降序排列，更适合看中期胜率。" },
  { key: "lowDrawdown", label: "低回撤榜", description: "优先选择 1 年最大回撤更浅的基金，适合找更能扛波动的候选。" },
  { key: "lowVolatility", label: "低波动榜", description: "优先选择 1 年波动率更低的基金，适合做防守和底仓筛选。" },
  { key: "value", label: "高性价比榜", description: "综合收益、费率、回撤与总分，找相对更均衡、更划算的候选。" },
  { key: "core", label: "稳健底仓榜", description: "规则：低波动 + 低回撤 + 费率友好 + 中等以上收益，更适合作为长期底仓候选。" },
  { key: "aggressive", label: "高弹性进攻榜", description: "规则：收益强、主题鲜明、弹性更高，但通常伴随更高波动。" },
];

const rankSeedConfigs: RankSeedConfig[] = [
  { fundTypeKey: "hh", sortKey: "1yzf", pageSize: 24 },
  { fundTypeKey: "hh", sortKey: "3yzf", pageSize: 24 },
  { fundTypeKey: "hh", sortKey: "1nzf", pageSize: 24 },
  { fundTypeKey: "gp", sortKey: "1yzf", pageSize: 18 },
  { fundTypeKey: "gp", sortKey: "3yzf", pageSize: 18 },
  { fundTypeKey: "gp", sortKey: "1nzf", pageSize: 18 },
  { fundTypeKey: "zs", sortKey: "1yzf", pageSize: 18 },
  { fundTypeKey: "zs", sortKey: "3yzf", pageSize: 18 },
  { fundTypeKey: "zs", sortKey: "1nzf", pageSize: 18 },
  { fundTypeKey: "zq", sortKey: "1yzf", pageSize: 20 },
  { fundTypeKey: "zq", sortKey: "3yzf", pageSize: 20 },
  { fundTypeKey: "zq", sortKey: "1nzf", pageSize: 20 },
  { fundTypeKey: "qdii", sortKey: "1yzf", pageSize: 16 },
  { fundTypeKey: "qdii", sortKey: "3yzf", pageSize: 16 },
  { fundTypeKey: "qdii", sortKey: "1nzf", pageSize: 16 },
  { fundTypeKey: "fof", sortKey: "1yzf", pageSize: 10 },
  { fundTypeKey: "fof", sortKey: "3yzf", pageSize: 10 },
];

const themeRules: Array<{ tag: string; keywords: string[] }> = [
  { tag: "红利", keywords: ["红利", "股息", "高股息", "分红"] },
  { tag: "创新药", keywords: ["创新药", "CXO", "医药", "医疗", "生物"] },
  { tag: "AI", keywords: ["人工智能", "AI", "算力", "机器人"] },
  { tag: "半导体", keywords: ["半导体", "芯片"] },
  { tag: "新能源车", keywords: ["新能源车", "汽车", "电池", "锂"] },
  { tag: "光伏", keywords: ["光伏", "太阳能"] },
  { tag: "消费", keywords: ["消费", "白酒", "食品", "饮料", "家电"] },
  { tag: "沪深300", keywords: ["沪深300", "300ETF", "300联接"] },
  { tag: "中证500", keywords: ["中证500", "500ETF", "500联接"] },
  { tag: "中证1000", keywords: ["中证1000", "1000ETF", "1000联接"] },
  { tag: "恒生", keywords: ["恒生", "港股"] },
  { tag: "纳斯达克", keywords: ["纳指", "纳斯达克"] },
  { tag: "标普500", keywords: ["标普", "SP500", "标普500"] },
  { tag: "黄金", keywords: ["黄金", "贵金属"] },
];

async function fetchText(url: string, init?: RequestInit): Promise<string> {
  const response = await fetch(url, {
    ...init,
    headers: {
      ...API_HEADERS,
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }

  return response.text();
}

function parseNumber(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function parsePercent(value: string | null | undefined) {
  if (!value) {
    return null;
  }

  return parseNumber(String(value).replace(/%/g, ""));
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function mapRange(value: number | null, fromMin: number, fromMax: number, toMin: number, toMax: number) {
  if (value === null) {
    return 0;
  }

  const normalized = clamp((value - fromMin) / (fromMax - fromMin), 0, 1);
  return toMin + (toMax - toMin) * normalized;
}

function toTimestamp(dateText: string) {
  return new Date(`${dateText}T00:00:00`).getTime();
}

function filterTrendByDays(points: FundTrendPoint[], days: number) {
  if (points.length === 0) {
    return [];
  }

  const latestDate = points.at(-1)?.date;
  if (!latestDate) {
    return points;
  }

  const base = new Date(`${latestDate}T00:00:00`);
  base.setDate(base.getDate() - days);
  const threshold = base.getTime();
  const filtered = points.filter((point) => toTimestamp(point.date) >= threshold);
  return filtered.length >= 2 ? filtered : points;
}

function calculateAnnualizedVolatility(points: FundTrendPoint[]) {
  const relevant = points.filter((point) => point.nav !== null) as Array<FundTrendPoint & { nav: number }>;
  if (relevant.length < 2) {
    return null;
  }

  const returns: number[] = [];
  for (let index = 1; index < relevant.length; index += 1) {
    const previous = relevant[index - 1]?.nav;
    const current = relevant[index]?.nav;

    if (!previous || !current || previous === 0) {
      continue;
    }

    returns.push((current - previous) / previous);
  }

  if (returns.length < 2) {
    return null;
  }

  const mean = returns.reduce((total, item) => total + item, 0) / returns.length;
  const variance = returns.reduce((total, item) => total + (item - mean) ** 2, 0) / (returns.length - 1);
  return Number((Math.sqrt(variance) * Math.sqrt(252) * 100).toFixed(2));
}

function calculateMaxDrawdown(points: FundTrendPoint[]) {
  const navValues = points.map((point) => point.nav).filter((value): value is number => value !== null);
  if (navValues.length < 2) {
    return null;
  }

  let peak = navValues[0];
  let maxDrawdown = 0;

  for (const nav of navValues) {
    peak = Math.max(peak, nav);
    if (peak === 0) {
      continue;
    }

    const drawdown = ((nav - peak) / peak) * 100;
    maxDrawdown = Math.min(maxDrawdown, drawdown);
  }

  return Number(maxDrawdown.toFixed(2));
}

function normalizeCategory(rawFundType: string | null, fundName: string): ScreenerFundCategory {
  const raw = rawFundType ?? "";
  const name = fundName || "";

  if (/QDII/i.test(raw) || /全球|海外|纳指|纳斯达克|标普|恒生/.test(name)) {
    return "QDII";
  }

  if (/FOF/i.test(raw) || /FOF/i.test(name)) {
    return "FOF";
  }

  if (/指数/.test(raw) || /ETF|联接|指数/.test(name)) {
    return "指数";
  }

  if (/债券型-混合一级|偏债混合|固收\+/.test(raw) || /固收\+|偏债/.test(name)) {
    return "固收+";
  }

  if (/债券型/.test(raw) || /短债|中短债|纯债|债券/.test(name)) {
    return "纯债";
  }

  return "主动";
}

function deriveTags(name: string, category: ScreenerFundCategory) {
  const sectorTags = new Set<string>();
  const themeTags = new Set<string>();

  if (/红利|股息|高股息|分红/.test(name)) {
    sectorTags.add("红利");
  }
  if (/医疗|医药|生物|创新药|CXO/.test(name)) {
    sectorTags.add("医疗");
  }
  if (/科技|半导体|芯片|AI|人工智能|互联网|软件|通信|数字经济/.test(name)) {
    sectorTags.add("科技");
  }
  if (/新能源|光伏|储能|锂|电池|风电|新能车|新能源汽车/.test(name)) {
    sectorTags.add("新能源");
  }
  if (/消费|白酒|食品|饮料|家电|品牌/.test(name)) {
    sectorTags.add("消费");
  }
  if (/沪深300|中证500|中证1000|上证50|创业板|科创50|全指|宽基|300ETF|500ETF|1000ETF/.test(name) || category === "指数") {
    sectorTags.add("宽基");
  }
  if (category === "纯债") {
    sectorTags.add("纯债");
    sectorTags.add("债基");
  }
  if (category === "固收+") {
    sectorTags.add("固收+");
    sectorTags.add("债基");
  }
  if (category === "QDII" || /全球|海外|纳指|纳斯达克|标普|恒生|美股|港股/.test(name)) {
    sectorTags.add("海外");
  }
  if (/黄金|贵金属/.test(name)) {
    sectorTags.add("黄金");
  }

  for (const rule of themeRules) {
    if (rule.keywords.some((keyword) => name.includes(keyword))) {
      themeTags.add(rule.tag);
    }
  }

  if (sectorTags.size === 0) {
    sectorTags.add("其他");
  }

  return {
    sectorTags: [...sectorTags],
    themeTags: [...themeTags],
  };
}

function buildScore(metrics: FundUniverseMetrics): FundUniverseScore {
  const scoreReturn = Math.round(
    clamp(
      mapRange(metrics.return1y, -10, 40, 0, 18) +
        mapRange(metrics.return3m, -6, 20, 0, 8) +
        mapRange(metrics.return1m, -4, 10, 0, 4),
      0,
      30,
    ),
  );

  const scoreStability = Math.round(
    clamp(
      mapRange(metrics.volatility1y !== null ? 35 - metrics.volatility1y : null, 0, 30, 0, 14) +
        mapRange(metrics.return6m, -5, 20, 0, 6),
      0,
      20,
    ),
  );

  const scoreDrawdown = Math.round(
    clamp(mapRange(metrics.maxDrawdown1y !== null ? Math.abs(metrics.maxDrawdown1y) : null, 40, 4, 0, 20), 0, 20),
  );

  const scoreFee = Math.round(clamp(mapRange(metrics.feeRate, 2, 0.1, 0, 10), 0, 10));
  const scoreManagement = Math.round(clamp(mapRange(metrics.establishedYears, 0.5, 8, 0, 10), 0, 10));
  const scoreHealth = Math.round(
    clamp(
      mapRange(metrics.size, 0.5, 50, 0, 6) + mapRange(metrics.establishedYears, 1, 6, 0, 4),
      0,
      10,
    ),
  );

  const total = clamp(scoreReturn + scoreStability + scoreDrawdown + scoreFee + scoreManagement + scoreHealth, 0, 100);

  return {
    total,
    return: scoreReturn,
    stability: scoreStability,
    drawdown: scoreDrawdown,
    fee: scoreFee,
    management: scoreManagement,
    health: scoreHealth,
  };
}

function buildScoreSummary(category: ScreenerFundCategory, metrics: FundUniverseMetrics, score: FundUniverseScore) {
  if ((metrics.return1y ?? -999) >= 20 && (metrics.volatility1y ?? 0) >= 22) {
    return "收益冲得更猛，但波动也更大，适合高风险偏好的进攻型观察。";
  }

  if ((metrics.maxDrawdown1y ?? -999) >= -10 && (metrics.volatility1y ?? 999) <= 12) {
    return "回撤和波动都相对克制，更适合作为长期底仓或防守候选。";
  }

  if (category === "纯债" || category === "固收+") {
    return "收益不是重点，核心看回撤、波动和费率，偏防守型角色更明显。";
  }

  if (score.fee >= 8 && score.drawdown >= 12) {
    return "费率和回撤控制都不差，属于更均衡、更省心的一档。";
  }

  return "整体指标较均衡，适合先放入观察池，再结合详情页趋势做二次判断。";
}

function buildRankingSignals(score: FundUniverseScore, metrics: FundUniverseMetrics, sectorTags: string[]) {
  const value = Number((score.total + score.fee * 0.8 + score.drawdown * 0.4).toFixed(2));
  const core = Number((score.stability * 1.1 + score.drawdown * 1.05 + score.fee * 0.6 + score.health * 0.5 + score.return * 0.45).toFixed(2));
  const sectorBoost = sectorTags.some((tag) => ["科技", "新能源", "医疗", "海外"].includes(tag)) ? 3 : 0;
  const aggressive = Number((score.return * 1.2 + (metrics.return3m ?? 0) * 0.3 + (metrics.return1m ?? 0) * 0.25 + sectorBoost).toFixed(2));
  return { value, core, aggressive };
}

function parseRankRow(raw: string): RankRow {
  const fields = raw.split(",");
  return {
    code: fields[0] ?? "",
    name: fields[1] ?? "",
    pinyin: fields[2] ?? "",
    latestNavDate: fields[3] || null,
    latestNav: parseNumber(fields[4]),
    latestDailyGrowthRate: parseNumber(fields[6]),
    return1w: parseNumber(fields[7]),
    return1m: parseNumber(fields[8]),
    return3m: parseNumber(fields[9]),
    return6m: parseNumber(fields[10]),
    return1y: parseNumber(fields[11]),
    returnYtd: parseNumber(fields[14]),
    returnSinceInception: parseNumber(fields[15]),
    establishedDate: fields[16] || null,
    size: parseNumber(fields[18]),
    originalFeeRate: parsePercent(fields[19]),
    currentFeeRate: parsePercent(fields[20]),
    canBuy: fields[17] === "1",
    canAutoInvest: fields[23] === "1",
  };
}

async function fetchFundCatalogMap() {
  const text = await fetchText(FUND_CATALOG_URL, {
    headers: {
      referer: "https://fund.eastmoney.com/",
    },
  });

  const match = text.match(/var\s+r\s*=\s*(\[[\s\S]*\]);?/);
  if (!match?.[1]) {
    throw new Error("基金目录索引返回格式无法识别。") ;
  }

  const entries = JSON.parse(match[1]) as RawCatalogEntry[];
  const catalog = new Map<string, CatalogItem>();

  for (const entry of entries) {
    catalog.set(entry[0], {
      code: entry[0],
      name: entry[2],
      pinyin: entry[4],
      rawFundType: entry[3] || null,
    });
  }

  return catalog;
}

async function fetchRankRows(config: RankSeedConfig) {
  const now = new Date();
  const end = now.toISOString().slice(0, 10);
  const start = new Date(now.getTime() - 365 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  const url = `https://fund.eastmoney.com/data/rankhandler.aspx?op=ph&dt=kf&ft=${config.fundTypeKey}&rs=&gs=0&sc=${config.sortKey}&st=desc&sd=${start}&ed=${end}&pi=1&pn=${config.pageSize}&dx=1`;
  const text = await fetchText(url, {
    headers: {
      referer: "https://fund.eastmoney.com/data/fundranking.html",
    },
  });

  const match = text.match(/datas:\[(.*)\],allRecords:/s);
  if (!match?.[1]) {
    throw new Error(`排行榜接口 ${config.fundTypeKey}/${config.sortKey} 返回格式无法识别。`);
  }

  const items = JSON.parse(`[${match[1]}]`) as string[];
  return items.map(parseRankRow).filter((item) => /^\d{6}$/.test(item.code));
}

async function mapWithConcurrency<T, R>(items: T[], limit: number, task: (item: T, index: number) => Promise<R>) {
  const results: R[] = new Array(items.length);
  let cursor = 0;

  async function worker() {
    while (cursor < items.length) {
      const index = cursor;
      cursor += 1;
      results[index] = await task(items[index], index);
    }
  }

  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, () => worker()));
  return results;
}

function buildMetricsFromDetail(detail: FundDetailResponse, rankRow: RankRow): FundUniverseMetrics {
  const oneYearTrend = filterTrendByDays(detail.trend, 365);

  return {
    return1w: detail.performance.oneWeek ?? rankRow.return1w,
    return1m: detail.performance.oneMonth ?? rankRow.return1m,
    return3m: detail.performance.threeMonths ?? rankRow.return3m,
    return6m: detail.performance.sixMonths ?? rankRow.return6m,
    return1y: detail.performance.oneYear ?? rankRow.return1y,
    returnYtd: detail.performance.yearToDate ?? rankRow.returnYtd,
    returnSinceInception: detail.performance.sinceInception ?? rankRow.returnSinceInception,
    maxDrawdown1y: calculateMaxDrawdown(oneYearTrend),
    volatility1y: calculateAnnualizedVolatility(oneYearTrend),
    feeRate: rankRow.currentFeeRate ?? parsePercent(detail.fund.currentRate),
    originalFeeRate: rankRow.originalFeeRate ?? parsePercent(detail.fund.sourceRate),
    size: rankRow.size,
    establishedYears: rankRow.establishedDate ? Number((((Date.now() - new Date(`${rankRow.establishedDate}T00:00:00`).getTime()) / 86400000) / 365).toFixed(2)) : null,
    latestNav: detail.fund.latestNav ?? rankRow.latestNav,
    latestDailyGrowthRate: detail.fund.latestDailyGrowthRate ?? rankRow.latestDailyGrowthRate,
    estimatedChangeRate: detail.fund.estimatedChangeRate,
    canBuy: rankRow.canBuy,
    canAutoInvest: rankRow.canAutoInvest,
  };
}

async function buildUniverseItem(rankRow: RankRow, catalogMap: Map<string, CatalogItem>): Promise<FundUniverseItem> {
  const catalog = catalogMap.get(rankRow.code);
  const displayName = catalog?.name ?? rankRow.name;
  const rawFundType = catalog?.rawFundType ?? null;
  const category = normalizeCategory(rawFundType, displayName);
  const { sectorTags, themeTags } = deriveTags(displayName, category);
  const warnings: string[] = [];

  try {
    const detail = await getFundPerformance(rankRow.code);
    const metrics = buildMetricsFromDetail(detail, rankRow);
    const score = buildScore(metrics);

    return {
      code: rankRow.code,
      name: displayName,
      pinyin: catalog?.pinyin ?? rankRow.pinyin,
      rawFundType,
      category,
      sectorTags,
      themeTags,
      establishedDate: rankRow.establishedDate,
      latestNavDate: detail.fund.latestNavDate ?? rankRow.latestNavDate,
      metrics,
      score,
      rankingSignals: buildRankingSignals(score, metrics, sectorTags),
      scoreSummary: buildScoreSummary(category, metrics, score),
      dataWarnings: warnings,
    };
  } catch (error) {
    warnings.push(error instanceof Error ? error.message : "明细抓取失败，使用排行快照兜底。");
    const metrics: FundUniverseMetrics = {
      return1w: rankRow.return1w,
      return1m: rankRow.return1m,
      return3m: rankRow.return3m,
      return6m: rankRow.return6m,
      return1y: rankRow.return1y,
      returnYtd: rankRow.returnYtd,
      returnSinceInception: rankRow.returnSinceInception,
      maxDrawdown1y: null,
      volatility1y: null,
      feeRate: rankRow.currentFeeRate,
      originalFeeRate: rankRow.originalFeeRate,
      size: rankRow.size,
      establishedYears: rankRow.establishedDate ? Number((((Date.now() - new Date(`${rankRow.establishedDate}T00:00:00`).getTime()) / 86400000) / 365).toFixed(2)) : null,
      latestNav: rankRow.latestNav,
      latestDailyGrowthRate: rankRow.latestDailyGrowthRate,
      estimatedChangeRate: null,
      canBuy: rankRow.canBuy,
      canAutoInvest: rankRow.canAutoInvest,
    };
    const score = buildScore(metrics);

    return {
      code: rankRow.code,
      name: displayName,
      pinyin: catalog?.pinyin ?? rankRow.pinyin,
      rawFundType,
      category,
      sectorTags,
      themeTags,
      establishedDate: rankRow.establishedDate,
      latestNavDate: rankRow.latestNavDate,
      metrics,
      score,
      rankingSignals: buildRankingSignals(score, metrics, sectorTags),
      scoreSummary: `${buildScoreSummary(category, metrics, score)} 当前部分风控指标缺失，结果请结合详情页进一步复核。`,
      dataWarnings: warnings,
    };
  }
}

function isCacheStale(updatedAt: string | null) {
  if (!updatedAt) {
    return true;
  }

  const timestamp = new Date(updatedAt).getTime();
  if (!Number.isFinite(timestamp)) {
    return true;
  }

  return Date.now() - timestamp > CACHE_TTL_MS;
}

function getRankingComparator(ranking: ScreenerRankingKey) {
  switch (ranking) {
    case "return1m":
      return (left: FundUniverseItem, right: FundUniverseItem) => (right.metrics.return1m ?? -Infinity) - (left.metrics.return1m ?? -Infinity);
    case "return3m":
      return (left: FundUniverseItem, right: FundUniverseItem) => (right.metrics.return3m ?? -Infinity) - (left.metrics.return3m ?? -Infinity);
    case "return1y":
      return (left: FundUniverseItem, right: FundUniverseItem) => (right.metrics.return1y ?? -Infinity) - (left.metrics.return1y ?? -Infinity);
    case "lowDrawdown":
      return (left: FundUniverseItem, right: FundUniverseItem) => (right.metrics.maxDrawdown1y ?? -Infinity) - (left.metrics.maxDrawdown1y ?? -Infinity);
    case "lowVolatility":
      return (left: FundUniverseItem, right: FundUniverseItem) => (left.metrics.volatility1y ?? Infinity) - (right.metrics.volatility1y ?? Infinity);
    case "value":
      return (left: FundUniverseItem, right: FundUniverseItem) => right.rankingSignals.value - left.rankingSignals.value;
    case "core":
      return (left: FundUniverseItem, right: FundUniverseItem) => right.rankingSignals.core - left.rankingSignals.core;
    case "aggressive":
      return (left: FundUniverseItem, right: FundUniverseItem) => right.rankingSignals.aggressive - left.rankingSignals.aggressive;
    default:
      return (left: FundUniverseItem, right: FundUniverseItem) => right.score.total - left.score.total;
  }
}

function getNestedValue(item: FundUniverseItem, path: string) {
  return path.split(".").reduce<unknown>((current, key) => {
    if (!current || typeof current !== "object") {
      return null;
    }

    return (current as Record<string, unknown>)[key];
  }, item);
}

function compareBySortPath(left: FundUniverseItem, right: FundUniverseItem, sortBy: string, sortOrder: ScreenerSortOrder) {
  const leftValue = getNestedValue(left, sortBy);
  const rightValue = getNestedValue(right, sortBy);
  const leftNumber = typeof leftValue === "number" ? leftValue : Number(leftValue);
  const rightNumber = typeof rightValue === "number" ? rightValue : Number(rightValue);

  const safeLeft = Number.isFinite(leftNumber) ? leftNumber : sortOrder === "asc" ? Infinity : -Infinity;
  const safeRight = Number.isFinite(rightNumber) ? rightNumber : sortOrder === "asc" ? Infinity : -Infinity;

  return sortOrder === "asc" ? safeLeft - safeRight : safeRight - safeLeft;
}

function matchQuery(item: FundUniverseItem, query: ScreenerQueryPayload) {
  if (query.fundTypes?.length && !query.fundTypes.includes(item.category)) {
    return false;
  }
  if (query.sectors?.length && !query.sectors.every((sector) => item.sectorTags.includes(sector))) {
    return false;
  }
  if (query.themes?.length && !query.themes.every((theme) => item.themeTags.includes(theme))) {
    return false;
  }
  if (query.minReturn1m !== null && query.minReturn1m !== undefined && (item.metrics.return1m ?? -Infinity) < query.minReturn1m) {
    return false;
  }
  if (query.minReturn3m !== null && query.minReturn3m !== undefined && (item.metrics.return3m ?? -Infinity) < query.minReturn3m) {
    return false;
  }
  if (query.minReturn6m !== null && query.minReturn6m !== undefined && (item.metrics.return6m ?? -Infinity) < query.minReturn6m) {
    return false;
  }
  if (query.minReturn1y !== null && query.minReturn1y !== undefined && (item.metrics.return1y ?? -Infinity) < query.minReturn1y) {
    return false;
  }
  if (query.maxDrawdown1y !== null && query.maxDrawdown1y !== undefined) {
    const drawdown = item.metrics.maxDrawdown1y;
    if (drawdown === null || Math.abs(drawdown) > query.maxDrawdown1y) {
      return false;
    }
  }
  if (query.maxVolatility1y !== null && query.maxVolatility1y !== undefined) {
    const volatility = item.metrics.volatility1y;
    if (volatility === null || volatility > query.maxVolatility1y) {
      return false;
    }
  }
  if (query.maxFeeRate !== null && query.maxFeeRate !== undefined) {
    const feeRate = item.metrics.feeRate;
    if (feeRate === null || feeRate > query.maxFeeRate) {
      return false;
    }
  }
  if (query.minSize !== null && query.minSize !== undefined && (item.metrics.size ?? -Infinity) < query.minSize) {
    return false;
  }
  if (query.maxSize !== null && query.maxSize !== undefined && (item.metrics.size ?? Infinity) > query.maxSize) {
    return false;
  }
  if (query.minEstablishedYears !== null && query.minEstablishedYears !== undefined && (item.metrics.establishedYears ?? -Infinity) < query.minEstablishedYears) {
    return false;
  }
  if (query.autoInvestOnly && !item.metrics.canAutoInvest) {
    return false;
  }

  return true;
}

export async function refreshFundUniverseCache() {
  const catalogMap = await fetchFundCatalogMap();
  const rankRows = await mapWithConcurrency(rankSeedConfigs, 3, (config) => fetchRankRows(config));
  const rankMap = new Map<string, RankRow>();

  for (const group of rankRows) {
    for (const row of group) {
      if (!rankMap.has(row.code)) {
        rankMap.set(row.code, row);
      }
    }
  }

  const items = await mapWithConcurrency([...rankMap.values()], 5, (row) => buildUniverseItem(row, catalogMap));
  const payload: FundUniverseCacheFile = {
    updatedAt: new Date().toISOString(),
    coverageNote: `${DEFAULT_COVERAGE_NOTE} 当前缓存通过 ${rankSeedConfigs.length} 组榜单交叉抽样生成，共 ${items.length} 只候选。`,
    items: items.sort((left, right) => right.score.total - left.score.total),
  };

  await saveFundUniverseCache(payload);
  return payload;
}

export async function getScreenerOptions(): Promise<ScreenerOptionsResponse> {
  const cache = await getFundUniverseCache();
  const sectors = cache.items.length
    ? [...new Set(cache.items.flatMap((item) => item.sectorTags))].sort((left, right) => left.localeCompare(right, "zh-CN"))
    : BASE_SECTORS;
  const themes = cache.items.length
    ? [...new Set(cache.items.flatMap((item) => item.themeTags))].sort((left, right) => left.localeCompare(right, "zh-CN"))
    : [];

  return {
    updatedAt: cache.updatedAt,
    isStale: isCacheStale(cache.updatedAt),
    coverageNote: cache.coverageNote,
    fundTypes: BASE_FUND_TYPES,
    sectors,
    themes,
    rankings: rankingDefinitions,
  };
}

export async function queryFundUniverse(query: ScreenerQueryPayload): Promise<ScreenerQueryResult> {
  const cache = await getFundUniverseCache();
  const filtered = cache.items.filter((item) => matchQuery(item, query));

  const items = [...filtered];
  if (query.ranking) {
    items.sort(getRankingComparator(query.ranking));
  } else if (query.sortBy) {
    items.sort((left, right) => compareBySortPath(left, right, query.sortBy ?? "score.total", query.sortOrder ?? "desc"));
  } else {
    items.sort((left, right) => right.score.total - left.score.total);
  }

  const page = Math.max(1, Number(query.page ?? 1));
  const pageSize = clamp(Number(query.pageSize ?? 50), 1, 100);
  const start = (page - 1) * pageSize;

  return {
    updatedAt: cache.updatedAt,
    isStale: isCacheStale(cache.updatedAt),
    coverageNote: cache.coverageNote,
    appliedRanking: query.ranking ?? null,
    items: items.slice(start, start + pageSize),
    total: items.length,
    page,
    pageSize,
  };
}

export async function getSectorStats(): Promise<ScreenerSectorStat[]> {
  const cache = await getFundUniverseCache();
  const counter = new Map<string, number>();

  for (const item of cache.items) {
    for (const sector of item.sectorTags) {
      counter.set(sector, (counter.get(sector) ?? 0) + 1);
    }
  }

  return [...counter.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((left, right) => right.count - left.count || left.name.localeCompare(right.name, "zh-CN"));
}

export async function getSectorFunds(sector: string, ranking?: ScreenerRankingKey | null) {
  return queryFundUniverse({
    sectors: [sector],
    ranking: ranking ?? "value",
    page: 1,
    pageSize: 100,
  });
}

export async function getScreenerPresetsList() {
  const payload = await getScreenerPresets();
  return payload.items;
}

export async function saveScreenerPreset(name: string, query: ScreenerQueryPayload) {
  const trimmedName = String(name || "").trim();
  if (!trimmedName) {
    throw new Error("筛选方案名称不能为空。") ;
  }

  const payload = await getScreenerPresets();
  const now = new Date().toISOString();
  const existingIndex = payload.items.findIndex((item) => item.name === trimmedName);
  const record: PersistedScreenerPreset = existingIndex >= 0
    ? {
        ...payload.items[existingIndex],
        name: trimmedName,
        query,
        updatedAt: now,
      }
    : {
        id: `preset-${Date.now()}`,
        name: trimmedName,
        query,
        createdAt: now,
        updatedAt: now,
      };

  const nextItems = payload.items.filter((item) => item.id !== record.id);
  nextItems.unshift(record);
  await saveScreenerPresets(nextItems);
  return record;
}

export async function deleteScreenerPreset(id: string) {
  const payload = await getScreenerPresets();
  const nextItems = payload.items.filter((item) => item.id !== id);
  await saveScreenerPresets(nextItems);
}

export async function getUniverseItemByCode(code: string) {
  const cache = await getFundUniverseCache();
  return cache.items.find((item) => item.code === code) ?? null;
}

export function getRankingDefinitions() {
  return rankingDefinitions;
}
