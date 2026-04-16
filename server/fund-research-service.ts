import { roundNullable, sumNumbers } from "./analysis-utils.js";
import { getFundHoldingStocks } from "./stock-service.js";
import { getFundUniverseCache } from "./data-store.js";
import { getFundPerformance } from "./fund-service.js";
import { getUniverseItemByCode, refreshFundUniverseCache } from "./screener-service.js";
import type { FundHoldingBreadthResponse, FundPeerBenchmarkPeer, FundPeerBenchmarkResponse, FundUniverseItem } from "./types.js";

function normalizeFundCode(code: string) {
  const cleanCode = String(code || "").trim();
  if (!/^\d{6}$/.test(cleanCode)) {
    throw new Error("基金编号必须是 6 位数字。");
  }
  return cleanCode;
}

function averageNumbers(values: Array<number | null | undefined>) {
  const numbers = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (numbers.length === 0) {
    return null;
  }
  return roundNullable(numbers.reduce((total, value) => total + value, 0) / numbers.length, 2);
}

function buildComparableUniverse(subject: FundUniverseItem, items: FundUniverseItem[]) {
  return items.filter((item) => item.category === subject.category && item.code !== subject.code);
}

function calculateOverlapScore(source: string[], target: string[], multiplier: number) {
  const sourceSet = new Set(source);
  const shared = target.filter((item) => sourceSet.has(item));
  return shared.length * multiplier;
}

function calculateDistanceScore(sourceValue: number | null, targetValue: number | null, tolerance: number, maxScore: number) {
  if (typeof sourceValue !== "number" || typeof targetValue !== "number") {
    return 0;
  }

  const distance = Math.abs(sourceValue - targetValue);
  if (distance >= tolerance) {
    return 0;
  }

  return roundNullable(((tolerance - distance) / tolerance) * maxScore, 2) ?? 0;
}

function buildPeerCandidate(subject: FundUniverseItem, candidate: FundUniverseItem): FundPeerBenchmarkPeer {
  const rawTypeBonus = subject.rawFundType && candidate.rawFundType && subject.rawFundType === candidate.rawFundType ? 8 : 0;
  const categoryBonus = subject.category === candidate.category ? 10 : 0;
  const sectorOverlapScore = calculateOverlapScore(subject.sectorTags, candidate.sectorTags, 10);
  const themeOverlapScore = calculateOverlapScore(subject.themeTags, candidate.themeTags, 6);
  const sizeClosenessScore = calculateDistanceScore(subject.metrics.size, candidate.metrics.size, 120, 12);
  const volatilityClosenessScore = calculateDistanceScore(subject.metrics.volatility1y, candidate.metrics.volatility1y, 18, 12);
  const drawdownClosenessScore = calculateDistanceScore(subject.metrics.maxDrawdown1y, candidate.metrics.maxDrawdown1y, 20, 10);
  const returnClosenessScore = calculateDistanceScore(subject.metrics.return1y, candidate.metrics.return1y, 35, 8);

  const similarityScore = roundNullable(
    categoryBonus + rawTypeBonus + sectorOverlapScore + themeOverlapScore + sizeClosenessScore + volatilityClosenessScore + drawdownClosenessScore + returnClosenessScore,
    2,
  ) ?? 0;

  return {
    code: candidate.code,
    name: candidate.name,
    category: candidate.category,
    rawFundType: candidate.rawFundType,
    sectorTags: candidate.sectorTags,
    themeTags: candidate.themeTags,
    scoreTotal: candidate.score.total,
    similarityScore,
    metrics: candidate.metrics,
  };
}

function percentileHigherIsBetter(items: FundUniverseItem[], targetCode: string, selector: (item: FundUniverseItem) => number | null) {
  const values = items
    .map((item) => ({ code: item.code, value: selector(item) }))
    .filter((item): item is { code: string; value: number } => typeof item.value === "number" && Number.isFinite(item.value));

  if (values.length === 0) {
    return null;
  }

  const target = values.find((item) => item.code === targetCode);
  if (!target) {
    return null;
  }

  const worseOrEqualCount = values.filter((item) => item.value <= target.value).length;
  return roundNullable((worseOrEqualCount / values.length) * 100, 1);
}

function percentileLowerIsBetter(items: FundUniverseItem[], targetCode: string, selector: (item: FundUniverseItem) => number | null) {
  const values = items
    .map((item) => ({ code: item.code, value: selector(item) }))
    .filter((item): item is { code: string; value: number } => typeof item.value === "number" && Number.isFinite(item.value));

  if (values.length === 0) {
    return null;
  }

  const target = values.find((item) => item.code === targetCode);
  if (!target) {
    return null;
  }

  const worseOrEqualCount = values.filter((item) => item.value >= target.value).length;
  return roundNullable((worseOrEqualCount / values.length) * 100, 1);
}

async function ensureUniverseReady() {
  const cache = await getFundUniverseCache();
  if (cache.items.length > 0) {
    return cache;
  }
  return refreshFundUniverseCache();
}

export class FundResearchService {
  async getPeerBenchmark(code: string, limit = 5): Promise<FundPeerBenchmarkResponse> {
    const cleanCode = normalizeFundCode(code);
    const cache = await ensureUniverseReady();
    const subject = (await getUniverseItemByCode(cleanCode)) ?? null;
    const safeLimit = Math.min(Math.max(Number(limit || 5), 1), 10);

    if (!subject) {
      return {
        fundCode: cleanCode,
        updatedAt: cache.updatedAt,
        peerBaseCount: 0,
        subject: null,
        percentile: null,
        peers: [],
      };
    }

    const peerBase = [subject, ...buildComparableUniverse(subject, cache.items)];
    const peers = peerBase
      .filter((item) => item.code !== subject.code)
      .map((item) => buildPeerCandidate(subject, item))
      .sort((left, right) => right.similarityScore - left.similarityScore || right.scoreTotal - left.scoreTotal)
      .slice(0, safeLimit);

    return {
      fundCode: cleanCode,
      updatedAt: cache.updatedAt,
      peerBaseCount: peerBase.length,
      subject,
      percentile: {
        return1m: percentileHigherIsBetter(peerBase, subject.code, (item) => item.metrics.return1m),
        return3m: percentileHigherIsBetter(peerBase, subject.code, (item) => item.metrics.return3m),
        return1y: percentileHigherIsBetter(peerBase, subject.code, (item) => item.metrics.return1y),
        maxDrawdown1y: percentileLowerIsBetter(peerBase, subject.code, (item) => item.metrics.maxDrawdown1y),
        volatility1y: percentileLowerIsBetter(peerBase, subject.code, (item) => item.metrics.volatility1y),
        feeRate: percentileLowerIsBetter(peerBase, subject.code, (item) => item.metrics.feeRate),
        scoreTotal: percentileHigherIsBetter(peerBase, subject.code, (item) => item.score.total),
      },
      peers,
    };
  }

  async getHoldingBreadth(code: string, topline = 10): Promise<FundHoldingBreadthResponse> {
    const cleanCode = normalizeFundCode(code);
    const safeTopline = Math.min(Math.max(Number(topline || 10), 1), 20);
    const payload = await getFundHoldingStocks(cleanCode, safeTopline);
    const items = payload.items;

    const positiveCount = items.filter((item) => typeof item.changeRate === "number" && item.changeRate > 0).length;
    const negativeCount = items.filter((item) => typeof item.changeRate === "number" && item.changeRate < 0).length;
    const flatCount = items.filter((item) => typeof item.changeRate === "number" && item.changeRate === 0).length;

    return {
      fundCode: cleanCode,
      reportDate: payload.reportDate,
      totalHoldings: items.length,
      positiveCount,
      negativeCount,
      flatCount,
      averageChangeRate: averageNumbers(items.map((item) => item.changeRate)),
      concentrationTop3: sumNumbers(items.slice(0, 3).map((item) => item.navRatio)),
      concentrationTop5: sumNumbers(items.slice(0, 5).map((item) => item.navRatio)),
      strongestStocks: [...items]
        .filter((item) => typeof item.changeRate === "number")
        .sort((left, right) => (right.changeRate ?? -Infinity) - (left.changeRate ?? -Infinity))
        .slice(0, 3),
      weakestStocks: [...items]
        .filter((item) => typeof item.changeRate === "number")
        .sort((left, right) => (left.changeRate ?? Infinity) - (right.changeRate ?? Infinity))
        .slice(0, 3),
    };
  }

  async getSnapshotForAgent(code: string) {
    const cleanCode = normalizeFundCode(code);
    const [detail, peerBenchmark, holdingBreadth] = await Promise.all([
      getFundPerformance(cleanCode),
      this.getPeerBenchmark(cleanCode, 5),
      this.getHoldingBreadth(cleanCode, 10).catch(() => null),
    ]);

    return {
      detail,
      peerBenchmark,
      holdingBreadth,
    };
  }
}
